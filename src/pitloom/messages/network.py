# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Network"
(``network`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._pypi_info import (
    QUERY_LINE,
    QUERY_NO_EFFECT,
    REDIRECT_LINE,
    URL_MOVED,
)
from pitloom.messages._remote_fetch import (
    DOWNLOAD_FAILED,
    DOWNLOAD_FAILED_LINE,
    DOWNLOAD_FAILED_WARNING_LINE,
    DOWNLOAD_TIMEOUT,
    DOWNLOAD_TIMEOUT_LINE,
    DOWNLOAD_TIMEOUT_WARNING_LINE,
    ENDPOINT_LINE,
    ENDPOINT_MOVED,
    ENDPOINT_REFUSED,
    ENDPOINT_REFUSED_LINE,
    FILE_HOST_REFUSED_LINE,
    GIT_HOST_SPELLING_LINE,
    GIT_NETWORK_FAILED_LINE,
    GIT_TIMEOUT_LINE,
    OFFLINE_LINE,
    OFFLINE_UNUSABLE,
    OFFLINE_WARNING_LINE,
    REDIRECT_REFUSED_LINE,
    REDIRECT_REFUSED_WARNING_LINE,
    TOO_MANY_REDIRECTS_LINE,
    TOO_MANY_REDIRECTS_WARNING_LINE,
    URL_HOST_SPELLING,
    URL_REFUSED,
)

__all__ = [
    "DOWNLOAD_FAILED",
    "DOWNLOAD_FAILED_LINE",
    "DOWNLOAD_FAILED_WARNING_LINE",
    "DOWNLOAD_TIMEOUT",
    "DOWNLOAD_TIMEOUT_LINE",
    "DOWNLOAD_TIMEOUT_WARNING_LINE",
    "ENDPOINT_LINE",
    "ENDPOINT_MOVED",
    "ENDPOINT_REFUSED",
    "ENDPOINT_REFUSED_LINE",
    "FILE_HOST_REFUSED_LINE",
    "GIT_HOST_SPELLING_LINE",
    "GIT_NETWORK_FAILED_LINE",
    "GIT_TIMEOUT_LINE",
    "OFFLINE_LINE",
    "OFFLINE_UNUSABLE",
    "OFFLINE_WARNING_LINE",
    "QUERY_LINE",
    "QUERY_NO_EFFECT",
    "REDIRECT_LINE",
    "REDIRECT_REFUSED_LINE",
    "REDIRECT_REFUSED_WARNING_LINE",
    "TOO_MANY_REDIRECTS_LINE",
    "TOO_MANY_REDIRECTS_WARNING_LINE",
    "URL_HOST_SPELLING",
    "URL_MOVED",
    "URL_REFUSED",
]
