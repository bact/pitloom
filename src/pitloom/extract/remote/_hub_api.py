# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Say a failed ``huggingface_hub`` API request (``model_info()``,
``dataset_info()``) as one catalogued ``WARNING:``, by what failed:
offline mode, a timeout, a failed request, or an answer that could not be
read; or, for the model a run reads, the error that the Hub knows no such
model (:func:`is_repository_not_found`, :func:`model_not_found`).

``huggingface_hub`` raises its own HTTP errors and passes on its HTTP
client's: ``httpx`` from 1.0, ``httpx2`` in 2.x. Both are recognised, each
only once it is imported (an error of a client that is not imported cannot
be raised).

See also: :mod:`pitloom.extract.remote.huggingface_fetch` and
:mod:`pitloom.extract.remote.huggingface_dataset` (the requests),
:mod:`pitloom.extract.remote._hub_files` (the Hub's files, said by
:func:`~pitloom.extract.remote._http_errors.warn_instead`).
"""

from __future__ import annotations

import logging
import sys
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.extract.remote._http_errors import remote_error, shown_url
from pitloom.extract.remote._hub_files import ROUTE, hub_endpoint
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.messages import emit, whole_seconds
from pitloom.messages.network import (
    DOWNLOAD_FAILED,
    DOWNLOAD_TIMEOUT,
    HUB_RESPONSE_INVALID,
    OFFLINE_UNUSABLE,
)
from pitloom.messages.targets import (
    HUB_ID_NOT_FOUND_LINE,
    HUB_URL_NOT_FOUND_LINE,
    INPUT_NOT_FOUND_HUB,
)

__all__ = [
    "REPOSITORY_NOT_FOUND",
    "is_repository_not_found",
    "model_not_found",
    "repo_page_url",
    "say_hub_failure",
]

#: The :attr:`~pitloom.extract.remote.errors.RemoteSourceError.code` of a
#: model the Hub knows no repository for (``input-not-found/hub``).
REPOSITORY_NOT_FOUND: Final = f"{ROUTE}.repository-not-found"

#: The HTTP clients ``huggingface_hub`` sends its API requests through.
_HTTP_CLIENTS: Final = ("httpx", "httpx2")


def repo_page_url(repo_id: str, repo_type: str = "model") -> str:
    """The page of the repository *repo_id* on the Hub the API asks
    (:func:`~pitloom.extract.remote._hub_files.hub_endpoint`), as a message
    writes it: ``<hub>/<repo>``, ``<hub>/datasets/<repo>`` for a dataset."""
    prefix = "datasets/" if repo_type == "dataset" else ""
    return shown_url(f"{hub_endpoint().rstrip('/')}/{prefix}{repo_id}")


def is_repository_not_found(exc: BaseException) -> bool:
    """Whether *exc*, raised by a ``huggingface_hub`` API request about one
    repository, says the Hub knows no repository by that id that the
    request could read: a ``RepositoryNotFoundError`` (a 404, or the 401 an
    anonymous request gets for a missing or a private repository alike),
    but not its subclass ``GatedRepoError`` (a gated repository is
    found)."""
    # pylint: disable-next=import-outside-toplevel
    from huggingface_hub.errors import GatedRepoError, RepositoryNotFoundError

    return isinstance(exc, RepositoryNotFoundError) and not isinstance(
        exc, GatedRepoError
    )


def model_not_found(model_id: str, *, as_id: bool) -> RemoteSourceError:
    """The error for the model *model_id* the Hub knows no repository for
    (:func:`is_repository_not_found`): :data:`REPOSITORY_NOT_FOUND`,
    ``input-not-found/hub``, naming its page on the Hub asked
    (:func:`repo_page_url`). *as_id*: the target was spelt as a model id,
    which is no local path either, and the line says so too."""
    url = repo_page_url(model_id)
    if as_id:
        return remote_error(
            REPOSITORY_NOT_FOUND,
            INPUT_NOT_FOUND_HUB,
            HUB_ID_NOT_FOUND_LINE,
            path=model_id,
            url=url,
        )
    return remote_error(
        REPOSITORY_NOT_FOUND, INPUT_NOT_FOUND_HUB, HUB_URL_NOT_FOUND_LINE, url=url
    )


def _client_errors(name: str) -> tuple[type[BaseException], ...]:
    """The exception class *name* of each HTTP client imported."""
    found: list[type[BaseException]] = []
    for client in _HTTP_CLIENTS:
        cls = getattr(sys.modules.get(client), name, None)
        if isinstance(cls, type) and issubclass(cls, BaseException):
            found.append(cls)
    return tuple(found)


def say_hub_failure(
    log: logging.Logger,
    exc: Exception,
    *,
    url: str,
    outcome: str,
    seconds: float,
) -> None:
    """Say *exc*, what a Hub API request about the repository at *url*
    (:func:`repo_page_url`) raised, as one ``WARNING:`` ending in
    *outcome* (what is not recorded): ``offline-unusable`` under
    ``HF_HUB_OFFLINE``; ``download-timeout`` (*seconds*, the timeout the
    request was given) for a request that did not finish;
    ``download-network-failed`` for an HTTP error status, a connection
    that failed or any other :class:`OSError`; else
    ``hub-response-invalid`` (an answer that is not JSON, or not of the
    API's shape). The text of *exc* holds the server's: it is masked, then
    written on one line.

    Raises:
        InternalError: *exc* is one, unchanged.
    """
    if isinstance(exc, InternalError):
        raise exc
    # pylint: disable-next=import-outside-toplevel
    from huggingface_hub.errors import HfHubHTTPError, OfflineModeIsEnabled

    level = logging.WARNING
    if isinstance(exc, OfflineModeIsEnabled):
        emit(log, OFFLINE_UNUSABLE, level, url=url, outcome=outcome)
    elif isinstance(exc, (TimeoutError, *_client_errors("TimeoutException"))):
        shown = whole_seconds(seconds)
        emit(log, DOWNLOAD_TIMEOUT, level, url=url, duration=shown, outcome=outcome)
    elif isinstance(
        exc,
        (
            HfHubHTTPError,
            OSError,
            *_client_errors("TransportError"),
            *_client_errors("TooManyRedirects"),
        ),
    ):
        emit(log, DOWNLOAD_FAILED, level, url=url, failure=exc, outcome=outcome)
    else:
        emit(log, HUB_RESPONSE_INVALID, level, url=url, failure=exc, outcome=outcome)
