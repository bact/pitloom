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

A file is asked of ``https://huggingface.co/<repo>/resolve/<revision>/<file>``
(``/datasets/<repo>/...`` for a dataset), as ``huggingface_hub`` asks it. The
Hub answers a file kept in Git with a redirect on its own host (``/api/
resolve-cache/...``) and a file kept in Xet or LFS storage with a signed URL
on a CDN host; only :data:`FILE_HOSTS` are fetched from. The download stops
past the ``max-download-bytes`` cap (counted on the bytes received), the
deadline, or a redirect elsewhere. The Hugging Face token ``huggingface_hub``
would send (``HF_TOKEN``, else the stored login, unless
``HF_HUB_DISABLE_IMPLICIT_TOKEN``) goes to the Hub's own origin only, never to
a CDN or any other host. With ``huggingface_hub``'s ``HF_HUB_OFFLINE`` set,
nothing is fetched. Weights are never downloaded.

A file the repository does not hold (404) is absent, silently; any other
failure leaves that file out with one catalogued ``WARNING:``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Final
from urllib.parse import quote

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.temp_dirs import temp_dir
from pitloom.core.url_masking import HUB_DIR_PREFIX
from pitloom.extract.remote._http_credential import Credential, origin_of
from pitloom.extract.remote._http_errors import (
    NotFoundError,
    remote_error,
    shown_url,
    warn_instead,
)
from pitloom.extract.remote._http_fetch import Policy, fetch_to_file
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.messages import NETWORK_UNUSABLE, OFFLINE_LINE

log = logging.getLogger(__name__)

__all__ = [
    "FILE_HOSTS",
    "HUB_BASE",
    "ROUTE",
    "HubFiles",
    "file_url",
    "hub_files",
    "hub_offline",
    "hub_token",
    "local_reason",
]

#: The Hub every file is asked of.
HUB_BASE: str = "https://huggingface.co"

#: The hosts a file is fetched from, a redirect included: the Hub, which
#: answers a file kept in Git itself (``resolve`` redirects to
#: ``/api/resolve-cache/`` on the same host), and the CDN host it sent a
#: file kept in Xet storage to when measured (a signed URL). Measured on
#: 2026-11-10 with huggingface_hub 2.4.0's resolve URL. The CDN host is
#: regional: a file the Hub sends to another one is refused (``url-unsafe``).
FILE_HOSTS: frozenset[str] = frozenset({"huggingface.co", "us.aws.cdn.hf.co"})

#: What starts each error's code and the ``User-Agent``.
ROUTE: Final = "huggingface"

#: What starts a message about the temporary directory.
_LOG_PREFIX: Final = "Hugging Face source: "


def file_url(
    repo_id: str, filename: str, *, revision: str | None, repo_type: str = "model"
) -> str:
    """The URL of *filename* of the repository *repo_id* at *revision*
    (``main`` when ``None``): ``<HUB_BASE>/[datasets/]<repo>/resolve/<rev>/<file>``,
    each part quoted as ``huggingface_hub.hf_hub_url`` quotes it."""
    prefix = "datasets/" if repo_type == "dataset" else ""
    return (
        f"{HUB_BASE}/{prefix}{quote(repo_id, safe='/')}/resolve/"
        f"{quote(revision or 'main', safe='')}/{quote(filename)}"
    )


def hub_token() -> str | None:
    """The token ``huggingface_hub`` sends to the Hub when none is given:
    ``HF_TOKEN``, else the stored login; ``None`` with
    ``HF_HUB_DISABLE_IMPLICIT_TOKEN`` or when there is none."""
    # pylint: disable-next=import-outside-toplevel
    from huggingface_hub import constants, get_token

    if constants.HF_HUB_DISABLE_IMPLICIT_TOKEN:
        return None
    return get_token()


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


class HubFiles:
    """The files of Hugging Face repositories one read downloads, each into
    its own folder of *work_dir*, under *policy*; *credential* is sent to the
    Hub's origin only."""

    def __init__(
        self,
        policy: RemoteFetchPolicy,
        work_dir: Path,
        credential: Credential | None,
    ) -> None:
        self.policy = policy
        self.work_dir = work_dir
        self._http = Policy(FILE_HOSTS, policy.check_url, ROUTE, credential)
        self._count = 0

    def fetch(
        self,
        repo_id: str,
        filename: str,
        *,
        revision: str | None,
        repo_type: str = "model",
    ) -> Path | None:
        """The local copy of *filename*, or ``None`` when the repository
        does not hold it (404 or 410).

        Raises:
            RemoteSourceError: ``huggingface.offline`` (``network-unusable``)
                under ``HF_HUB_OFFLINE``, or as
                :func:`~pitloom.extract.remote._http_fetch.fetch_to_file`.
            Exception: Whatever the policy's ``check_url`` raises, unchanged.
        """
        url = file_url(repo_id, filename, revision=revision, repo_type=repo_type)
        if hub_offline():
            raise remote_error(
                f"{ROUTE}.offline", NETWORK_UNUSABLE, OFFLINE_LINE, url=shown_url(url)
            )
        self._count += 1
        folder = self.work_dir / str(self._count)
        folder.mkdir()
        dest = folder / PurePosixPath(filename).name
        try:
            fetch_to_file(
                url,
                self._http,
                dest,
                max_bytes=self.policy.max_bytes,
                file=f"{repo_id}/{filename}",
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
        outcome: str,
        repo_type: str = "model",
    ) -> Path | None:
        """:meth:`fetch`, a failure said as one ``WARNING:`` ending in
        *outcome* (what is not read) and ``None``, as for a file the
        repository does not hold (which is silent).

        Raises:
            Exception: Whatever the policy's ``check_url`` raises, unchanged
                (a :class:`RemoteSourceError` of its own included): the
                caller's address policy stops the read.
        """
        try:
            return self.fetch(repo_id, filename, revision=revision, repo_type=repo_type)
        except RemoteSourceError as exc:
            if exc.said is None:
                raise
            warn_instead(log, exc, outcome)
            return None


@contextmanager
def hub_files(policy: RemoteFetchPolicy) -> Iterator[HubFiles]:
    """A :class:`HubFiles` downloading into a new temporary directory
    (``pitloom-hf-`` and eight random characters), removed on exit; one that
    cannot be removed is left behind with one ``WARNING:``."""
    token = hub_token()
    origin = origin_of(HUB_BASE)
    credential = (
        Credential(f"Bearer {token}", origin) if token and origin is not None else None
    )
    with temp_dir(HUB_DIR_PREFIX, log_prefix=_LOG_PREFIX) as work:
        yield HubFiles(policy, work, credential)
