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
    is_unfetchable_remote,
    is_unsupported_remote_url,
    parse_git_page,
)
from pitloom.extract.remote.huggingface import (
    is_hub_model_target,
    is_huggingface_source,
    log_hf_url_rewrite,
    parse_hf_model_id,
    read_huggingface,
    refuse_hub_model_target,
    require_hf_model_id,
)
from pitloom.extract.remote.pypi import PypiDownload, fetch_pypi_file, sdist_hint
from pitloom.extract.remote.pypi_url import (
    PypiTarget,
    is_pypi_url,
    parse_pypi_url,
    pypi_json_url,
)

__all__ = [
    "GitCheckout",
    "PypiDownload",
    "PypiTarget",
    "RemoteSourceError",
    "fetch_git_project",
    "fetch_pypi_file",
    "is_git_url",
    "is_hub_model_target",
    "is_huggingface_source",
    "is_pypi_url",
    "is_unfetchable_remote",
    "is_unsupported_remote_url",
    "log_hf_url_rewrite",
    "parse_git_page",
    "parse_hf_model_id",
    "parse_pypi_url",
    "pypi_json_url",
    "read_huggingface",
    "refuse_hub_model_target",
    "require_hf_model_id",
    "sdist_hint",
]
