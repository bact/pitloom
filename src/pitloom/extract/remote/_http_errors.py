# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The errors of the hardened HTTP client, each a catalogued line, and how a
caller that goes on without the file says one as a ``WARNING:``.

See also: :mod:`pitloom.extract.remote._http_fetch` (the client that raises
them) and :mod:`pitloom.extract.remote.errors` (the class).
"""

from __future__ import annotations

import logging
import math
import urllib.error
from typing import Any

from pitloom.core.internal_error import InternalError
from pitloom.core.url_masking import sanitize_url
from pitloom.extract.remote._http_watch import Watch
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import loggable
from pitloom.messages import (
    Line,
    Message,
    emit,
)
from pitloom.messages.files import (
    OVER_CAP,
)
from pitloom.messages.network import (
    DOWNLOAD_FAILED,
    DOWNLOAD_FAILED_LINE,
    DOWNLOAD_TIMEOUT,
    DOWNLOAD_TIMEOUT_LINE,
)

__all__ = [
    "CutShortError",
    "NotFoundError",
    "failed_error",
    "not_found_error",
    "remote_error",
    "shown_url",
    "timeout_error",
    "warn_instead",
]


class NotFoundError(RemoteSourceError):
    """The server answered 404 or 410 for :attr:`url`: a failed download
    (``<route>.download-failed``), which a JSON API caller names as a
    missing project or release instead, and a Hugging Face caller reads as a
    file the repository does not hold."""

    #: The URL that was not found.
    url: str


class CutShortError(ConnectionError):
    """A body that ended before the length its server declared."""


def shown_url(url: str) -> str:
    """*url* as a message writes it: without credentials, escaped."""
    return loggable(sanitize_url(url))


def remote_error(
    code: str, message: Message, line: Line, **values: object
) -> RemoteSourceError:
    """A :class:`RemoteSourceError` *code* whose text is *message*'s ``ERROR``
    *line* written from *values*, its ``pitloom_code`` *message*'s code. The
    error keeps *message* and *values* (:attr:`RemoteSourceError.said`), so a
    caller that goes on without the file says it as a ``WARNING:``
    (:func:`warn_instead`).

    Raises:
        ValueError: *line* is not one of *message*'s ``ERROR`` lines naming
            *values*, or a value does not have its field's shape.
    """
    text = message.line_for("ERROR", values, line).render(values)
    error = RemoteSourceError(code, text, pitloom_code=message.code)
    error.said = (message, dict(values))
    return error


def warn_instead(
    logger: logging.Logger, error: RemoteSourceError, outcome: str
) -> None:
    """Say *error* as its family's ``WARNING:`` line, ending in *outcome*
    (what was not read), for a caller that goes on without the file.

    Raises:
        InternalError: *error* was not made by :func:`remote_error`, or its
            family has no ``WARNING`` line naming its values and an outcome.
    """
    if error.said is None:
        raise InternalError(f"not a catalogued fetch error: {error.code}")
    message, said = error.said
    if not isinstance(message, Message):
        raise InternalError(f"not a catalogued fetch error: {error.code}")
    # Each value is a field's, written by it: emit takes them as keywords.
    values: dict[str, Any] = dict(said)
    if message is OVER_CAP and "file" in values:
        # The cap's warning names its input by key (KEY_LINE).
        values.update(key="FILE", name=values.pop("file"))
    try:
        emit(logger, message, logging.WARNING, **values, outcome=outcome)
    except ValueError as exc:
        raise InternalError(f"{error.code}: {exc}") from exc


def timeout_error(url: str, watch: Watch, route: str) -> RemoteSourceError:
    """The ``<route>.download-timeout`` error of *url*: the deadline of
    *watch* passed, or one socket operation timed out."""
    seconds = watch.seconds if watch.fired.is_set() else watch.socket_seconds
    return remote_error(
        f"{route}.download-timeout",
        DOWNLOAD_TIMEOUT,
        DOWNLOAD_TIMEOUT_LINE,
        url=shown_url(url),
        seconds=max(math.ceil(seconds), 1),
    )


def failed_error(
    url: str, failure: BaseException, watch: Watch, route: str
) -> RemoteSourceError:
    """The error for *failure* while fetching *url*: a timeout when the
    deadline passed or a socket timed out, else a failed download."""
    reason = getattr(failure, "reason", failure)
    if watch.fired.is_set() or isinstance(reason, TimeoutError):
        return timeout_error(url, watch, route)
    return remote_error(
        f"{route}.download-failed",
        DOWNLOAD_FAILED,
        DOWNLOAD_FAILED_LINE,
        url=shown_url(url),
        failure=reason if isinstance(reason, BaseException) else failure,
    )


def not_found_error(
    url: str, status: urllib.error.HTTPError, route: str
) -> NotFoundError:
    """The :class:`NotFoundError` of *url*, which answered *status*."""
    values: dict[str, object] = {"url": shown_url(url), "failure": status}
    error = NotFoundError(
        f"{route}.download-failed",
        DOWNLOAD_FAILED.line_for("ERROR", values).render(values),
        pitloom_code=DOWNLOAD_FAILED.code,
    )
    error.url = url
    error.said = (DOWNLOAD_FAILED, values)
    return error
