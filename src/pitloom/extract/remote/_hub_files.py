# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Download the small metadata files of a Hugging Face repository
(``config.json``, the model or dataset card, a licence file) through the
hardened HTTP client, into a temporary directory removed on exit.

See also: :mod:`pitloom.extract.remote.huggingface_fetch` and
:mod:`pitloom.extract.remote.huggingface_dataset` (the readers),
:mod:`pitloom.extract.remote._http_fetch` (the client) and
:mod:`pitloom.extract.remote.pypi` (the PyPI route, which fetches the same
way).

A file is asked of ``<hub>/<repo>/resolve/<revision>/<file>``
(``/datasets/<repo>/...`` for a dataset), as ``huggingface_hub`` asks it; the
Hub is ``huggingface_hub``'s own ``ENDPOINT`` (``HF_ENDPOINT``, else
``https://huggingface.co``), which must be https (:func:`hub_base`). The Hub
answers a file kept in Git with a redirect on its own host (``/api/
resolve-cache/...``) and a file kept in Xet or LFS storage with a signed URL
on a CDN host; only the Hub's host and the hosts under :data:`CDN_DOMAINS`
are fetched from. The download stops past its cap (counted on the bytes
received: the smaller of the ``max-download-bytes`` cap and the cap of its
kind, :data:`HUB_JSON_CAP` for a JSON file, the card's or the licence
file's own), past :data:`METADATA_DEADLINE_SECONDS`, or at a redirect
elsewhere. The Hugging Face token ``huggingface_hub`` would send
(``HF_TOKEN``, else the stored login, unless
``HF_HUB_DISABLE_IMPLICIT_TOKEN``) goes to the Hub's own origin only, never
to a CDN or any other host. With ``HF_ENDPOINT`` refused,
:attr:`HubFiles.asks_hub` is false and the readers ask the Hub nothing, not
even through ``huggingface_hub``. With ``huggingface_hub``'s
``HF_HUB_OFFLINE`` set, nothing is fetched. Weights are never downloaded.

A file the repository does not hold (404) is absent, silently; any other
failure leaves that file out with one catalogued ``WARNING:``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final
from urllib.parse import quote, urlsplit

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.internal_error import InternalError
from pitloom.core.model_extract_limit import MAX_DOWNLOAD_BYTES_KEY
from pitloom.core.quote_source import quote_source
from pitloom.core.temp_dirs import temp_dir
from pitloom.core.url_masking import HUB_DIR_PREFIX
from pitloom.extract.remote._http_credential import (
    DEFAULT_PORTS,
    Credential,
    origin_of,
)
from pitloom.extract.remote._http_errors import (
    NotFoundError,
    remote_error,
    shown_url,
    warn_instead,
)
from pitloom.extract.remote._http_fetch import (
    JSON_DEADLINE_SECONDS,
    Policy,
    fetch_capped,
    url_refusal,
)
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.messages import emit
from pitloom.messages.files import Cap
from pitloom.messages.network import (
    ENDPOINT_MOVED,
    ENDPOINT_REFUSED,
    OFFLINE_LINE,
    OFFLINE_UNUSABLE,
)

log = logging.getLogger(__name__)

__all__ = [
    "CDN_DOMAINS",
    "DEFAULT_HUB_BASE",
    "HUB_JSON_CAP",
    "HUB_JSON_MAX_BYTES",
    "METADATA_DEADLINE_SECONDS",
    "ROUTE",
    "FileKind",
    "HubFiles",
    "endpoint_refusal",
    "file_cap",
    "file_policy",
    "file_url",
    "hub_base",
    "hub_credential",
    "hub_endpoint",
    "hub_files",
    "hub_offline",
    "hub_token",
    "local_reason",
]

#: The Hub ``huggingface_hub`` asks when ``HF_ENDPOINT`` is not set.
DEFAULT_HUB_BASE: Final = "https://huggingface.co"

#: The DNS domains any host under which a file is fetched from, on the
#: default https port, besides the Hub's own host (which answers a file kept
#: in Git itself: ``resolve`` redirects to ``/api/resolve-cache/``): the CDN
#: the Hub sends a file kept in Xet storage to (a signed URL), whose host is
#: regional (``us.aws.cdn.hf.co`` measured on 2026-11-10 with
#: huggingface_hub 2.4.0's resolve URL). A file tracked by Git LFS goes
#: there too: every LFS file probed that day was Xet-backed, and none was
#: sent to a ``cdn-lfs`` or ``cas-bridge`` host.
CDN_DOMAINS: frozenset[str] = frozenset({"cdn.hf.co"})

#: What starts each error's code and the ``User-Agent``.
ROUTE: Final = "huggingface"

#: The most bytes of one Hub JSON file read (``config.json``,
#: ``tokenizer_config.json``, ``generation_config.json``): each is parsed
#: whole, which takes about ten times its size in memory. These are a few
#: KiB; a ``tokenizer_config.json`` listing thousands of added tokens, about
#: a MiB. 16 MiB leaves room for an order of magnitude more.
HUB_JSON_MAX_BYTES: Final = 16 * 1024 * 1024
#: :data:`HUB_JSON_MAX_BYTES` as an ``over-cap`` line names it.
HUB_JSON_CAP: Final = Cap(HUB_JSON_MAX_BYTES, "byte", "Hub-JSON")

#: Seconds for one metadata file, redirects included: a JSON API request's.
METADATA_DEADLINE_SECONDS: float = JSON_DEADLINE_SECONDS

#: What starts a message about the temporary directory.
_LOG_PREFIX: Final = "Hugging Face source: "


def file_url(
    repo_id: str,
    filename: str,
    *,
    revision: str | None,
    repo_type: str = "model",
    base: str = DEFAULT_HUB_BASE,
) -> str:
    """The URL of *filename* of the repository *repo_id* at *revision*
    (``main`` when ``None``) on the Hub *base*:
    ``<base>/[datasets/]<repo>/resolve/<rev>/<file>``, each part quoted as
    ``huggingface_hub.hf_hub_url`` quotes it."""
    prefix = "datasets/" if repo_type == "dataset" else ""
    return (
        f"{base.rstrip('/')}/{prefix}{quote(repo_id, safe='/')}/resolve/"
        f"{quote(revision or 'main', safe='')}/{quote(filename)}"
    )


@dataclass(frozen=True)
class FileKind:
    """What a Hub metadata file is read as: its own cap (*cap*, below
    the ``max-download-bytes`` one, :func:`file_cap`) and what is not read
    when it cannot be fetched (*outcome*, ending its ``WARNING:``)."""

    cap: Cap
    outcome: str


def file_cap(kind_cap: Cap, policy: RemoteFetchPolicy) -> Cap:
    """The cap a file of the kind capped by *kind_cap* is downloaded under:
    *kind_cap* when it is the smaller, else *policy*'s
    ``max-download-bytes`` cap (named so, the setting that bounds it)."""
    if kind_cap.limit < policy.max_bytes:
        return kind_cap
    return Cap(policy.max_bytes, "byte", MAX_DOWNLOAD_BYTES_KEY)


def hub_endpoint() -> str:
    """The Hub ``huggingface_hub`` itself asks: its ``constants.ENDPOINT``
    (``HF_ENDPOINT`` as read when it was imported, the staging Hub under
    ``HUGGINGFACE_CO_STAGING``, else ``https://huggingface.co``), so a file
    and the API calls go to one Hub."""
    # pylint: disable-next=import-outside-toplevel
    from huggingface_hub import constants

    return str(constants.ENDPOINT)


def _host_entry(base: str) -> str | None:
    """*base*'s host as an allowlist names it (``host``, or ``host:port``
    for a port that is not its scheme's default), or ``None`` when it has
    none or its port is no number."""
    origin = origin_of(base)
    if origin is None:
        return None
    scheme, host, port = origin
    return host if port == DEFAULT_PORTS.get(scheme) else f"{host}:{port}"


def endpoint_refusal(base: str) -> str | None:
    """Why no file is fetched from the Hub *base*, or ``None`` when files
    may be: it is not an https URL with a host, or it holds user
    information, a query or a fragment."""
    host = _host_entry(base)
    if host is None:
        return "it is not a URL with a host"
    why = url_refusal(base, frozenset({host}))
    if why is None and ("?" in base or "#" in base):
        why = "it holds a query or a fragment"
    return why


def _is_default_hub(base: str) -> bool:
    """Whether *base* names :data:`DEFAULT_HUB_BASE` itself: https, the
    host ``huggingface.co`` in any case, on the default port, with no user
    information, path, query or fragment."""
    try:
        parts = urlsplit(base)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme.lower() == "https"
        and "@" not in parts.netloc
        and (parts.hostname or "") == "huggingface.co"
        and port in (None, DEFAULT_PORTS["https"])
        and parts.path in ("", "/")
        and not (parts.query or parts.fragment or "?" in base or "#" in base)
    )


def hub_base() -> str | None:
    """The Hub files are asked of (:func:`hub_endpoint`), or ``None`` when
    :func:`endpoint_refusal` refuses it, said as one ``WARNING:``
    (``url-unsafe/hf-endpoint``): the token is never sent over plain http.
    A Hub other than :data:`DEFAULT_HUB_BASE` (another host or port, a
    path) is said as one ``INFO:``; the default spelt otherwise
    (``https://HuggingFace.co/``) is the default, said nothing of."""
    base = hub_endpoint()
    if _is_default_hub(base):
        return DEFAULT_HUB_BASE
    why = endpoint_refusal(base)
    if why is not None:
        emit(log, ENDPOINT_REFUSED, logging.WARNING, url=shown_url(base), why=why)
        return None
    emit(log, ENDPOINT_MOVED, logging.INFO, url=shown_url(base))
    return base


def file_policy(
    base: str, credential: Credential | None, policy: RemoteFetchPolicy
) -> Policy:
    """Where a file of the Hub *base* may be fetched from: the Hub's host
    and the hosts under :data:`CDN_DOMAINS`, each URL passed to *policy*'s
    ``check_url``; *credential* sent to its own origin only.

    Raises:
        InternalError: *base* has no host.
    """
    host = _host_entry(base)
    if host is None:
        raise InternalError(f"not a Hub to fetch from: {shown_url(base)}")
    return Policy(frozenset({host}), policy.check_url, ROUTE, credential, CDN_DOMAINS)


def hub_token() -> str | None:
    """The token ``huggingface_hub`` sends to the Hub when none is given:
    ``HF_TOKEN``, else the stored login; ``None`` with
    ``HF_HUB_DISABLE_IMPLICIT_TOKEN`` or when there is none."""
    # pylint: disable-next=import-outside-toplevel
    from huggingface_hub import constants, get_token

    if constants.HF_HUB_DISABLE_IMPLICIT_TOKEN:
        return None
    return get_token()


def hub_credential(base: str) -> Credential | None:
    """:func:`hub_token` as an ``Authorization`` header for the origin of
    the Hub *base* only (its scheme, host and port), or ``None`` when there
    is no token or *base* has no host."""
    token = hub_token()
    origin = origin_of(base)
    if not token or origin is None:
        return None
    return Credential(f"Bearer {token}", origin)


def hub_offline() -> bool:
    """Whether ``huggingface_hub``'s own offline mode (``HF_HUB_OFFLINE``)
    is on."""
    # pylint: disable-next=import-outside-toplevel
    from huggingface_hub import constants

    return bool(constants.HF_HUB_OFFLINE)


def local_reason(exc: BaseException) -> object:
    """What a message says about *exc*, a failure to read a downloaded file:
    an :class:`OSError` naming a file says its reason only (its text quotes
    the temporary path)."""
    if isinstance(exc, OSError) and exc.filename:
        return exc.strerror or type(exc).__name__
    return exc


def _local_name(filename: str) -> str:
    """The name *filename* (a path in the repository) is saved as: its last
    part, which must be a plain name on every platform.

    Raises:
        InternalError: That part is empty, ``.`` or ``..``, or holds a
            backslash or a drive (the readers name fixed files only).
    """
    name = PurePosixPath(filename).name
    if name in ("", ".", "..") or PureWindowsPath(name).name != name:
        raise InternalError(f"not a file name to save: {quote_source(filename)}")
    return name


class HubFiles:
    """The files of Hugging Face repositories one read downloads from the
    Hub *base*, each into its own folder of *work_dir*, under *policy*;
    *credential* is sent to the Hub's origin only. With *base* ``None`` (an
    ``HF_ENDPOINT`` refused, said once by :func:`hub_base`), no file is
    fetched, and a reader asks the Hub nothing else either
    (:attr:`asks_hub`)."""

    def __init__(
        self,
        policy: RemoteFetchPolicy,
        work_dir: Path,
        credential: Credential | None,
        base: str | None = DEFAULT_HUB_BASE,
    ) -> None:
        self.policy = policy
        self.work_dir = work_dir
        self.base = base
        self._http = None if base is None else file_policy(base, credential, policy)
        self._count = 0

    @property
    def asks_hub(self) -> bool:
        """Whether anything may be asked of the Hub in this read: a file,
        or ``huggingface_hub``'s ``model_info()``, ``dataset_info()`` or
        file listing, which go to the same ``HF_ENDPOINT`` with the token.
        ``False`` once :func:`hub_base` refused it."""
        return self.base is not None

    def fetch(
        self,
        repo_id: str,
        filename: str,
        *,
        revision: str | None,
        cap: Cap,
        repo_type: str = "model",
    ) -> Path | None:
        """The local copy of *filename*, downloaded under
        :func:`file_cap` of *cap* in :data:`METADATA_DEADLINE_SECONDS`, or
        ``None`` when the repository does not hold it (404 or 410).

        Raises:
            InternalError: There is no Hub to fetch from (*base* ``None``).
            RemoteSourceError: ``huggingface.offline`` (``offline-unusable``)
                under ``HF_HUB_OFFLINE``, or as
                :func:`~pitloom.extract.remote._http_fetch.fetch_capped`.
            Exception: Whatever the policy's ``check_url`` raises, unchanged.
        """
        if self.base is None or self._http is None:
            raise InternalError("no Hugging Face Hub to fetch a file from")
        url = file_url(
            repo_id, filename, revision=revision, repo_type=repo_type, base=self.base
        )
        if hub_offline():
            raise remote_error(
                f"{ROUTE}.offline", OFFLINE_UNUSABLE, OFFLINE_LINE, url=shown_url(url)
            )
        self._count += 1
        folder = self.work_dir / str(self._count)
        dest = folder / _local_name(filename)
        if dest.parent != folder:
            raise InternalError(f"not a file name to save: {quote_source(filename)}")
        folder.mkdir()
        try:
            fetch_capped(
                url,
                self._http,
                dest,
                cap=file_cap(cap, self.policy),
                file=f"{repo_id}/{filename}",
                deadline=METADATA_DEADLINE_SECONDS,
            )
        except NotFoundError:
            return None
        return dest

    def read(
        self,
        repo_id: str,
        filename: str,
        *,
        revision: str | None,
        kind: FileKind,
        repo_type: str = "model",
    ) -> Path | None:
        """:meth:`fetch` under *kind*'s cap, a failure said as one
        ``WARNING:`` ending in its outcome (what is not read) and ``None``,
        as for a file the repository does not hold (which is silent). With
        no Hub to fetch from, ``None`` and nothing more said
        (:func:`hub_base` said it).

        Raises:
            Exception: Whatever the policy's ``check_url`` raises, unchanged
                (a :class:`RemoteSourceError` of its own included): the
                caller's address policy stops the read.
        """
        if self.base is None:
            return None
        try:
            return self.fetch(
                repo_id, filename, revision=revision, cap=kind.cap, repo_type=repo_type
            )
        except RemoteSourceError as exc:
            if exc.said is None:
                raise
            warn_instead(log, exc, kind.outcome)
            return None


@contextmanager
def hub_files(policy: RemoteFetchPolicy) -> Iterator[HubFiles]:
    """A :class:`HubFiles` downloading from :func:`hub_base` into a new
    temporary directory (``pitloom-hf-`` and eight random characters),
    removed on exit; one that cannot be removed is left behind with one
    ``WARNING:``. The token is sent to the Hub's origin only."""
    base = hub_base()
    credential = None if base is None else hub_credential(base)
    with temp_dir(HUB_DIR_PREFIX, log_prefix=_LOG_PREFIX) as work:
        yield HubFiles(policy, work, credential, base)
