# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``credentials-unsafe`` messages: the one ``WARNING:`` for a URL stripped
of its credentials, and the errors for a registry value that holds some.

See also: :mod:`pitloom.messages._url_credentials` (the entries).
"""

from __future__ import annotations

import logging

from pitloom.core.url_masking import masked_given_path
from pitloom.messages._emit import CodedValueError, emit
from pitloom.messages._url_credentials import (
    GIT_LINE,
    KEY_LINE,
    STRIPPED_LINE,
    URL_CREDENTIALS,
    URL_CREDENTIALS_REGISTRY,
)

__all__ = [
    "URL_CREDENTIALS",
    "URL_CREDENTIALS_REGISTRY",
    "registry_key_credentials_error",
    "warn_git_credentials_unsent",
    "warn_url_credentials_stripped",
]


def warn_url_credentials_stripped(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log*, once per *url* and process, that *url*
    (given masked: nothing here masks it again) is stated without its
    credentials."""
    emit(
        log,
        URL_CREDENTIALS,
        logging.WARNING,
        line=STRIPPED_LINE,
        once=f"credentials-unsafe:{url}",
        url=url,
    )


def warn_git_credentials_unsent(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log* that the credentials of the Git *url*
    (given masked) hold a line break and are not sent."""
    emit(log, URL_CREDENTIALS, logging.WARNING, line=GIT_LINE, url=url)


def registry_key_credentials_error(url: str) -> CodedValueError:
    """The error for a registry key *url* that holds credentials, shown
    masked."""
    return CodedValueError(
        URL_CREDENTIALS_REGISTRY, line=KEY_LINE, url=masked_given_path(url)
    )
