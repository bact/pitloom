# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a PyPI URL names: a project, and maybe one of its releases.

See also: :mod:`pitloom.extract.remote.pypi` (the resolver that reads it) and
:mod:`pitloom.extract.remote.git_url` (the Git URL, which a PyPI URL is never
taken for).

Two forms are read, on ``pypi.org`` (or ``www.pypi.org``, any case, a
trailing dot dropped): ``https://pypi.org/project/<name>/`` and
``https://pypi.org/project/<name>/<version>/``, the trailing slash optional
and each segment percent-decoded. A query or fragment is cut. The name must
be a valid PEP 508 name, compared by its PEP 503 form; the version must parse
as PEP 440. Anything else on the host, ``http:``, user information or a port
that is not 443 is refused. A URL on another host of the PyPI family (any
``*.pypi.org`` such as ``test.pypi.org``, or ``pypi.python.org``) is a PyPI
URL too, so that it is refused with a PyPI message and never fetched as a
Git repository.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import quote, unquote, urlsplit

from packaging.utils import canonicalize_name

from pitloom.core.pep440 import parse_version
from pitloom.core.url_masking import sanitize_url
from pitloom.logging_config import loggable
from pitloom.messages import (
    PYPI_INDEX_LINE,
    PYPI_NAME_INVALID_LINE,
    PYPI_OLD_HOST_LINE,
    PYPI_URL_CREDENTIALS_LINE,
    PYPI_URL_FORM_LINE,
    PYPI_URL_INVALID,
    PYPI_URL_SCHEME_LINE,
    PYPI_VERSION_INVALID_LINE,
    CodedValueError,
    Line,
)

log = logging.getLogger(__name__)

__all__ = [
    "API_BASE",
    "FILE_HOSTS",
    "PYPI_JSON_API",
    "PYPI_PROJECT_HOSTS",
    "PypiTarget",
    "is_pypi_url",
    "parse_pypi_url",
    "project_page_url",
    "pypi_json_url",
]

#: The hosts of a PyPI project page Pitloom reads.
PYPI_PROJECT_HOSTS: Final = frozenset({"pypi.org", "www.pypi.org"})
#: PyPI's old host: a PyPI URL, refused with the form to give instead.
_OLD_HOST: Final = "pypi.python.org"
#: The domain of every other host of the PyPI family (``test.pypi.org``):
#: a PyPI URL, refused as another index.
_FAMILY_DOMAIN: Final = ".pypi.org"

#: The JSON API as provenance names it: the ``Source`` of what it declares
#: (a download's digest and release, a dependency's licence and originator).
PYPI_JSON_API: Final = "PyPI JSON API"

#: The base of the PyPI JSON API (a test points it at a local server).
API_BASE: str = "https://pypi.org/pypi/"

#: The hosts a release file is downloaded from (a test adds a local one).
FILE_HOSTS: frozenset[str] = frozenset({"files.pythonhosted.org"})

#: The project page a :class:`PypiTarget` is written as.
_PROJECT_PAGE: Final = "https://pypi.org/project/"

#: A valid project name (PEP 508).
#: ASCII only: with IGNORECASE alone, ``\u212a`` (Kelvin) would match ``k``
#: and ``\u017f`` (long s) ``s``.
_NAME_RE: Final = re.compile(
    r"[A-Z0-9](?:[A-Z0-9._-]*[A-Z0-9])?", re.IGNORECASE | re.ASCII
)


@dataclass(frozen=True)
class PypiTarget:
    """A PyPI project URL, read.

    ``name`` and ``version`` are as the URL gives them (percent-decoded);
    ``canonical`` is the name's PEP 503 form; ``project_url`` is the page
    written canonically (``https://pypi.org/project/<canonical>/`` and the
    version segment when given); ``cut`` says a query or fragment was cut.
    """

    name: str
    canonical: str
    version: str | None
    project_url: str
    cut: bool = False


def _host(hostname: str | None) -> str:
    """*hostname* (``urlsplit`` gives it lower-cased) without its trailing
    dots (a fully qualified name); empty for none."""
    return (hostname or "").rstrip(".")


def _in_family(host: str) -> bool:
    """Whether *host* (:func:`_host`'s form) is a host of the PyPI family:
    :data:`PYPI_PROJECT_HOSTS`, any ``*.pypi.org`` or ``pypi.python.org``."""
    return (
        host in PYPI_PROJECT_HOSTS or host.endswith(_FAMILY_DOMAIN) or host == _OLD_HOST
    )


def is_pypi_url(text: str) -> bool:
    """Whether *text* is an ``http`` or ``https`` URL on a host of the PyPI
    family (:data:`PYPI_PROJECT_HOSTS`, any ``*.pypi.org`` such as
    ``test.pypi.org``, or ``pypi.python.org``; any case, a trailing dot
    dropped): ``http`` and the hosts :func:`parse_pypi_url` refuses too, so
    that each is refused with a PyPI message and never taken for a Git URL.
    Never raises."""
    stripped = text.strip()
    if not stripped.lower().startswith(("http://", "https://")):
        return False
    try:
        hostname = urlsplit(stripped).hostname
    except ValueError:
        return False
    return _in_family(_host(hostname))


def pypi_json_url(name: str, version: str | None) -> str:
    """The JSON API URL of project *name*, or of its release *version*:
    :data:`API_BASE`, then each segment quoted whole (a ``/`` in it too)."""
    path = quote(name, safe="")
    if version is not None:
        path += "/" + quote(version, safe="")
    return f"{API_BASE}{path}/json"


def project_page_url(canonical: str, version: str | None) -> str:
    """The project page URL of *canonical*, of its *version* when given."""
    page = f"{_PROJECT_PAGE}{quote(canonical, safe='')}/"
    return page + (f"{quote(version, safe='')}/" if version is not None else "")


def _refuse(text: str, line: Line, **values: str) -> CodedValueError:
    """The error for *text* refused with *line*, logged first (a rejected
    input is said as well as raised)."""
    error = CodedValueError(
        PYPI_URL_INVALID, line=line, url=loggable(sanitize_url(text)), **values
    )
    log.warning("%s", error)
    return error


def _segments(path: str) -> list[str] | None:
    """The segments of *path* after ``/project/``, one trailing slash
    dropped, or ``None`` for any other path or an empty segment."""
    if not path.startswith("/project/"):
        return None
    rest = path[len("/project/") :]
    rest = rest[:-1] if rest.endswith("/") else rest
    segments = rest.split("/")
    if not 1 <= len(segments) <= 2 or "" in segments:
        return None
    return [unquote(segment) for segment in segments]


def parse_pypi_url(text: str) -> PypiTarget:
    """The project, and the release when given, the PyPI URL *text* names.

    Raises:
        CodedValueError: ``pypi-url-invalid``: not https, user information,
            another host of the PyPI family (``test.pypi.org``,
            ``pypi.python.org``) or any other host, a port other than 443, a
            path that is not a project or release page, a name that is not
            a valid PEP 508 name or a version that is not PEP 440. The
            refusal is logged as a ``WARNING:`` too.
    """
    stripped = text.strip()
    try:
        parts = urlsplit(stripped)
        port = parts.port
    except ValueError:
        raise _refuse(stripped, PYPI_URL_FORM_LINE) from None
    scheme = parts.scheme.lower()
    if scheme == "http":
        raise _refuse(stripped, PYPI_URL_SCHEME_LINE)
    if "@" in parts.netloc:
        raise _refuse(stripped, PYPI_URL_CREDENTIALS_LINE)
    host = _host(parts.hostname)
    if host not in PYPI_PROJECT_HOSTS and _in_family(host):
        line = PYPI_OLD_HOST_LINE if host == _OLD_HOST else PYPI_INDEX_LINE
        raise _refuse(stripped, line)
    segments = _segments(parts.path)
    if (
        scheme != "https"
        or host not in PYPI_PROJECT_HOSTS
        or port not in (None, 443)
        or segments is None
    ):
        raise _refuse(stripped, PYPI_URL_FORM_LINE)
    name = segments[0]
    if _NAME_RE.fullmatch(name) is None:
        raise _refuse(stripped, PYPI_NAME_INVALID_LINE, name=loggable(name))
    version = segments[1] if len(segments) == 2 else None
    # packaging allows white space around a version; a URL does not.
    if version is not None and (
        version != version.strip() or parse_version(version) is None
    ):
        raise _refuse(stripped, PYPI_VERSION_INVALID_LINE, version=loggable(version))
    canonical = canonicalize_name(name)
    return PypiTarget(
        name=name,
        canonical=canonical,
        version=version,
        project_url=project_page_url(canonical, version),
        cut=bool(parts.query or parts.fragment),
    )
