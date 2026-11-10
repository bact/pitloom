# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fetch the wheel or the sdist of a PyPI release, by its project URL, into a
temporary directory, verified against the SHA-256 PyPI declares.

See also: :mod:`pitloom.extract.remote.pypi_url` (the URL),
:mod:`pitloom.extract.remote._pypi_release` (which release),
:mod:`pitloom.extract.remote.pypi_select` (which release and file),
:mod:`pitloom.extract.remote._http_fetch` (the one HTTP client) and
:mod:`pitloom.extract.remote.git` (the Git URL route this mirrors).

The JSON API is asked for the release (the latest when the URL names none,
:func:`~pitloom.extract.remote.pypi_select.select_release`), the file is
picked (the wheel that best matches the running environment, or the sdist),
downloaded from :data:`~pitloom.extract.remote.pypi_url.FILE_HOSTS` only and
hashed as it arrives; a digest that does not match the declared one is an
error. Nothing is built or run. Each decision is one ``INFO:``; each
refusal is a :class:`~pitloom.extract.remote.errors.RemoteSourceError` (or,
for the URL, a :class:`~pitloom.messages.CodedValueError`) carrying its
catalogued code, and a ``WARNING:`` too. Messages name the file by its PyPI
file name, never the temporary path.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.internal_error import InternalError
from pitloom.core.model_extract_limit import DEFAULT_MAX_DOWNLOAD_BYTES
from pitloom.core.temp_dirs import temp_dir
from pitloom.core.url_masking import DOWNLOAD_DIR_PREFIX, sanitize_url_credentials
from pitloom.extract.remote import pypi_url
from pitloom.extract.remote._http_fetch import (
    Policy,
    fetch_to_file,
    remote_error,
    shown_url,
    url_refusal,
)
from pitloom.extract.remote._pypi_release import (
    NAME_SHOWN,
    Release,
    hosts_of,
    resolve_release,
)
from pitloom.extract.remote.pypi_select import (
    PRERELEASE,
    SDIST,
    STABLE,
    WHEEL,
    YANKED,
    ReleaseFile,
    pick_sdist,
    pick_wheel,
    read_files,
)
from pitloom.extract.remote.pypi_url import (
    PYPI_JSON_API,
    PypiTarget,
    parse_pypi_url,
    project_page_url,
)
from pitloom.logging_config import loggable
from pitloom.messages import (
    DIGEST_MISMATCH,
    DIGEST_MISMATCH_LINE,
    FILE_AMBIGUOUS,
    FILE_HOST_REFUSED_LINE,
    FILE_SKIPPED_LINE,
    GENERATE_WHEEL_LIBRARY_LINE,
    GENERATE_WHEEL_LINE,
    LATEST_LINE,
    LATEST_PRERELEASE_LINE,
    LATEST_YANKED_LINE,
    NO_COMPATIBLE_WHEEL_LINE,
    NO_DIGEST_LINE,
    NO_SDIST_LINE,
    NO_WHEEL_LINE,
    OFFLINE_LINE,
    OFFLINE_UNUSABLE,
    PYPI_RESPONSE_INVALID,
    QUERY_NO_EFFECT,
    RELEASE_FILE_NOT_FOUND,
    RELEASE_FILE_NOT_FOUND_COMPATIBLE,
    RELEASE_FILE_NOT_FOUND_SDIST,
    RELEASE_UNPINNED,
    RELEASE_UNPINNED_PRERELEASE,
    RELEASE_UNPINNED_YANKED,
    RELEASE_YANKED,
    SDIST_PICK_LINE,
    URL_REFUSED,
    WHEEL_PICK_LINE,
    YANKED_LINE,
    emit,
)

log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_MAX_DOWNLOAD_BYTES",
    "SDIST",
    "WHEEL",
    "PypiDownload",
    "fetch_pypi_file",
    "sdist_hint",
]

#: What a digest was checked against, as its line names it.
DIGEST_SOURCE: Final = f"the {PYPI_JSON_API}"

#: The wheel's ``chosen_by``: picked for the running environment.
RUNNING_ENVIRONMENT: Final = "running-environment"

#: How many wheel file names a refusal lists before "and N more".
_NAMES_SHOWN: Final = 10
#: What starts a message about the download's temporary directory.
_LOG_PREFIX: Final = "PyPI source: "
#: The yank reason written when PyPI gives none.
_NO_REASON: Final = "no reason given"


# Every fact the SBOM records about the download is one field of it.
@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes
class PypiDownload:
    """A release file downloaded and verified.

    ``path`` is the file in the temporary directory, named by its PyPI file
    name (``filename``); ``name`` is the project's PEP 503 name and
    ``version`` the release as PyPI lists it; ``project_url`` the release
    page (``https://pypi.org/project/<name>/<version>/``) and ``file_url``
    the URL downloaded. ``sha256`` (lower-case hex) was measured from the
    bytes and equals the digest PyPI declares; ``size`` is the bytes
    measured. ``status`` holds ``"prerelease"`` and ``"yanked"`` as they
    apply, ``yanked_reason`` PyPI's reason when it gives one. For a wheel,
    ``tags`` are its tags (sorted), ``compatible_skipped`` the other wheels
    the environment matched and ``chosen_by`` ``"running-environment"``.
    ``requested_version`` is the version the URL named, as spelled there
    (``1.0`` for a release PyPI lists as ``1.0.0``), or ``None`` when it
    named none and the latest release was read.
    """

    path: Path
    filename: str
    kind: str
    name: str
    version: str
    project_url: str
    file_url: str
    sha256: str
    size: int
    status: tuple[str, ...] = ()
    yanked_reason: str | None = None
    tags: tuple[str, ...] = ()
    compatible_skipped: int = 0
    chosen_by: str | None = None
    requested_version: str | None = None


@dataclass(frozen=True)
class _Pick:
    """The file picked and how many of its kind were candidates."""

    file: ReleaseFile
    candidates: int


def sdist_hint(url: str, *, library: bool = False) -> None:
    """Say, as ``loom generate`` does after reading a release's wheel from
    the PyPI URL *url*, that ``loom project`` reads its sdist; with
    *library* (:func:`pitloom.assemble.generate`), that
    :func:`pitloom.assemble.generate_pypi_sbom` with ``kind="sdist"`` does.

    Raises:
        CodedValueError: *url* is not a PyPI project or release URL (it is,
            once its wheel was read).
    """
    target = parse_pypi_url(url)
    emit(
        log,
        FILE_AMBIGUOUS,
        logging.INFO,
        line=GENERATE_WHEEL_LIBRARY_LINE if library else GENERATE_WHEEL_LINE,
        name=target.canonical,
        url=target.project_url,
    )


def _names(files: Sequence[ReleaseFile]) -> str:
    """The file names of *files*, comma-separated, ``and N more`` after
    :data:`_NAMES_SHOWN`."""
    shown = ", ".join(f.filename for f in files[:_NAMES_SHOWN])
    more = len(files) - _NAMES_SHOWN
    return shown + (f" and {more} more" if more > 0 else "")


def _pick(
    target: PypiTarget, release: Release, files: list[ReleaseFile], kind: str
) -> _Pick:
    """The file of *kind* to read.

    Raises:
        RemoteSourceError: ``pypi.no-wheel``, ``pypi.no-compatible-wheel``
            or ``pypi.no-sdist``.
    """
    names = {"name": target.canonical, "version": loggable(release.version)}
    url = target.project_url
    if kind == SDIST:
        sdist = pick_sdist(files)
        if sdist is None:
            raise remote_error(
                "pypi.no-sdist",
                RELEASE_FILE_NOT_FOUND_SDIST,
                NO_SDIST_LINE,
                url=url,
                **names,
            )
        return _Pick(sdist.file, sdist.count)
    wheels = [f for f in files if f.kind == WHEEL]
    if not wheels:
        raise remote_error(
            "pypi.no-wheel", RELEASE_FILE_NOT_FOUND, NO_WHEEL_LINE, url=url, **names
        )
    wheel = pick_wheel(wheels)
    if wheel is None:
        raise remote_error(
            "pypi.no-compatible-wheel",
            RELEASE_FILE_NOT_FOUND_COMPATIBLE,
            NO_COMPATIBLE_WHEEL_LINE,
            url=url,
            files=_names(wheels),
            **names,
        )
    return _Pick(wheel.file, wheel.compatible)


def _yank_reason(release: Release, file: ReleaseFile) -> str | None:
    """Why *file* was yanked, as PyPI says it, or ``None``."""
    if file.yanked_reason:
        return file.yanked_reason
    reason = release.info.get("yanked_reason")
    return reason if isinstance(reason, str) and reason.strip() else None


#: The message and line of each release kind picked when no version is
#: given, but a yanked one (whose line names the reason).
_UNPINNED: Final = {
    STABLE: (RELEASE_UNPINNED, LATEST_LINE),
    PRERELEASE: (RELEASE_UNPINNED_PRERELEASE, LATEST_PRERELEASE_LINE),
}


def _say_decisions(target: PypiTarget, release: Release, pick: _Pick) -> None:
    """One ``INFO:`` per decision: the release when the URL named none, a
    yanked file, and the file when several were candidates. A pre-release the
    URL names is what was asked for: it is said in the SBOM only."""
    name, version = target.canonical, loggable(release.version)
    why = loggable(_yank_reason(release, pick.file) or _NO_REASON)
    if release.choice == YANKED:
        emit(
            log,
            RELEASE_UNPINNED_YANKED,
            logging.INFO,
            line=LATEST_YANKED_LINE,
            name=name,
            version=version,
            why=why,
        )
    elif release.choice is not None:
        message, line = _UNPINNED[release.choice]
        emit(log, message, logging.INFO, line=line, name=name, version=version)
    if pick.file.yanked and release.choice != YANKED:
        emit(
            log,
            RELEASE_YANKED,
            logging.INFO,
            line=YANKED_LINE,
            name=name,
            version=version,
            file=pick.file.filename,
            why=why,
        )
    if pick.candidates > 1:
        emit(
            log,
            FILE_AMBIGUOUS,
            logging.INFO,
            line=WHEEL_PICK_LINE if pick.file.kind == WHEEL else SDIST_PICK_LINE,
            name=name,
            version=version,
            number=pick.candidates,
            file=pick.file.filename,
        )


def _checked_file(pick: _Pick) -> str:
    """The SHA-256 PyPI declares for the picked file, once its digest and
    host are checked.

    Raises:
        RemoteSourceError: ``pypi.response-invalid`` (no digest) or
            ``pypi.url-refused`` (a download URL on another host).
    """
    file = pick.file
    if file.sha256 is None:
        raise remote_error(
            "pypi.response-invalid",
            PYPI_RESPONSE_INVALID,
            NO_DIGEST_LINE,
            file=loggable(file.filename),
        )
    hosts = pypi_url.FILE_HOSTS
    if url_refusal(file.url, hosts) is not None:
        raise remote_error(
            "pypi.url-refused",
            URL_REFUSED,
            FILE_HOST_REFUSED_LINE,
            file=loggable(file.filename),
            target=shown_url(file.url),
            hosts=", ".join(sorted(hosts)),
        )
    return file.sha256


def _download(
    target: PypiTarget, kind: str, work_dir: Path, policy: RemoteFetchPolicy
) -> PypiDownload:
    """Resolve, pick, download into *work_dir* and verify."""
    check_url = policy.check_url
    release = resolve_release(target, Policy(hosts_of(pypi_url.API_BASE), check_url))
    files, refused = read_files(release.urls, target.canonical, release.parsed)
    for skipped, why in refused:
        emit(
            log,
            PYPI_RESPONSE_INVALID,
            logging.WARNING,
            line=FILE_SKIPPED_LINE,
            name=target.canonical,
            file=skipped[:NAME_SHOWN],
            why=why,
        )
    pick = _pick(target, release, files, kind)
    declared = _checked_file(pick)
    _say_decisions(target, release, pick)
    path = work_dir / pick.file.filename
    measured, size = _fetch_verified(
        pick.file, declared, path, check_url, policy.max_bytes
    )
    file = pick.file
    wheel = file.kind == WHEEL
    return PypiDownload(
        path=path,
        filename=file.filename,
        kind=file.kind,
        name=target.canonical,
        version=release.version,
        project_url=project_page_url(target.canonical, release.version),
        file_url=file.url,
        sha256=measured,
        size=size,
        status=(("prerelease",) if release.parsed.is_prerelease else ())
        + (("yanked",) if file.yanked else ()),
        yanked_reason=_yank_reason(release, file) if file.yanked else None,
        tags=tuple(sorted(str(tag) for tag in file.tags)),
        compatible_skipped=pick.candidates - 1 if wheel else 0,
        chosen_by=RUNNING_ENVIRONMENT if wheel else None,
        requested_version=target.version,
    )


def _fetch_verified(
    file: ReleaseFile,
    declared: str,
    path: Path,
    check_url: Callable[[str], None] | None,
    max_bytes: int,
) -> tuple[str, int]:
    """Download *file* to *path* and return its measured SHA-256 and size,
    once the digest equals *declared*.

    Raises:
        RemoteSourceError: ``pypi.digest-mismatch``, or as
            :func:`~pitloom.extract.remote._http_fetch.fetch_to_file`
            (``pypi.too-large``, ``pypi.save-failed``,
            ``pypi.download-failed``, a 404 too).
    """

    policy = Policy(pypi_url.FILE_HOSTS, check_url)
    measured, size = fetch_to_file(
        file.url, policy, path, max_bytes=max_bytes, file=file.filename
    )
    if measured != declared:
        raise remote_error(
            "pypi.digest-mismatch",
            DIGEST_MISMATCH,
            DIGEST_MISMATCH_LINE,
            file=loggable(file.filename),
            measured=measured,
            declared=declared,
            source=DIGEST_SOURCE,
        )
    return measured, size


@contextmanager
def fetch_pypi_file(
    url: str, *, kind: str, policy: RemoteFetchPolicy = RemoteFetchPolicy()
) -> Iterator[PypiDownload]:
    """Download the *kind* (:data:`WHEEL` or :data:`SDIST`) file of the
    release the PyPI URL *url* names into a temporary directory
    (``pitloom-pypi-`` and eight random characters), removed on exit
    (no termination guard: Ctrl-C removes it, a process ended by SIGTERM or
    SIGKILL leaves it); one that cannot be removed (a file still held open on
    Windows) is left behind with one ``WARNING:``, never an error.

    *policy* (:func:`~pitloom.core.config_cascade.resolve_fetch_policy`)
    says what the fetch may do: its ``check_url`` is called with every URL
    before it is requested (the JSON API's, the file's and each redirect
    target) and raises for one that must not be fetched; with ``offline``
    nothing is fetched (*url* is read first: an invalid one is
    ``pypi-url-invalid`` all the same); ``max_bytes`` caps the file
    (default :data:`DEFAULT_MAX_DOWNLOAD_BYTES`).

    Raises:
        ValueError: *kind* is neither (an
            :class:`~pitloom.core.internal_error.InternalError`).
        CodedValueError: ``pypi-url-invalid``, from
            :func:`~pitloom.extract.remote.pypi_url.parse_pypi_url`.
        RemoteSourceError: ``pypi.offline`` (``offline-unusable``) and every
            ``pypi.*`` failure, each with its catalogued ``pitloom_code``.
        Exception: Whatever ``check_url`` raises, unchanged.
    """
    if kind not in (WHEEL, SDIST):
        raise InternalError(f"kind must be {WHEEL!r} or {SDIST!r}, got {kind!r}")
    target = parse_pypi_url(url)
    if policy.offline:
        error = remote_error(
            "pypi.offline",
            OFFLINE_UNUSABLE,
            OFFLINE_LINE,
            url=shown_url(url.strip()),
        )
        # The refusal is said as well as raised, as its own text.
        log.warning("%s", error)
        raise error
    if target.cut:
        emit(log, QUERY_NO_EFFECT, logging.INFO, url=shown_url(url.strip()))
    with temp_dir(DOWNLOAD_DIR_PREFIX, log_prefix=_LOG_PREFIX) as work_dir:
        try:
            download = _download(target, kind, work_dir, policy)
        except Exception as exc:
            # A refusal is said here, so a caller that only logs shows it.
            log.warning("%s", loggable(sanitize_url_credentials(str(exc))))
            raise
        yield download
