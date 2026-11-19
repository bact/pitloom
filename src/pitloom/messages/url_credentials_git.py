# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The helpers that say the ``credentials-unsafe`` variants of a Git URL's
user information, each once per URL and process.

See also: :mod:`pitloom.messages._url_credentials_git` (the entries).
"""

from __future__ import annotations

import logging

from pitloom.messages._emit import emit
from pitloom.messages._url_credentials_git import (
    CREDENTIALS_UNSAFE_GIT_LINE_BREAK,
    CREDENTIALS_UNSAFE_HTTP_CLEAR,
)

__all__ = ["warn_git_credentials_in_clear", "warn_git_credentials_line_break"]


def warn_git_credentials_line_break(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log* that the credentials of the Git *url*
    (given masked) hold a line break and are not sent."""
    emit(
        log,
        CREDENTIALS_UNSAFE_GIT_LINE_BREAK,
        logging.WARNING,
        once=f"{CREDENTIALS_UNSAFE_GIT_LINE_BREAK.code}:{url}",
        url=url,
    )


def warn_git_credentials_in_clear(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log* that the credentials of the Git *url*
    (given masked) go to the server over plain http."""
    emit(
        log,
        CREDENTIALS_UNSAFE_HTTP_CLEAR,
        logging.WARNING,
        once=f"{CREDENTIALS_UNSAFE_HTTP_CLEAR.code}:{url}",
        url=url,
    )
