# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Remote data source extraction subsystem.

Platform-specific fetchers in this subpackage are internal implementation
modules; callers should use the facade functions exported below.
"""

from __future__ import annotations

from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout, fetch_git_project
from pitloom.extract.remote.git_url import (
    is_git_url,
    is_unsupported_remote_url,
    parse_git_page,
)
from pitloom.extract.remote.huggingface import (
    is_huggingface_source,
    log_hf_url_rewrite,
    parse_hf_model_id,
    read_huggingface,
)

__all__ = [
    "GitCheckout",
    "RemoteSourceError",
    "fetch_git_project",
    "is_git_url",
    "is_huggingface_source",
    "is_unsupported_remote_url",
    "parse_git_page",
    "log_hf_url_rewrite",
    "parse_hf_model_id",
    "read_huggingface",
]
