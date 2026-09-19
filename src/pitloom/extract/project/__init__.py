# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Project metadata extraction subsystem.

Per-backend extractors in this subpackage are internal implementation
modules; callers should use the facade functions exported below.
"""

from __future__ import annotations

from pitloom.extract.project.reader import (
    read_project,
    resolve_project_with_lockfile,
    warn_use_lockfile_no_effect,
)

__all__ = [
    "read_project",
    "resolve_project_with_lockfile",
    "warn_use_lockfile_no_effect",
]
