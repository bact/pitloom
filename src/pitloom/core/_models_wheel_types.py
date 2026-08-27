# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared types for per-backend wheel file discovery.

See also: :mod:`pitloom.core._models_wheel` (dispatch facade),
:mod:`pitloom.core._models_wheel_hatchling`,
:mod:`pitloom.core._models_wheel_setuptools`.
"""

from __future__ import annotations

from typing import NamedTuple, TypedDict


class IncludedFile(NamedTuple):
    """One file that belongs in the wheel, as resolved by a backend.

    Mirrors the two attributes every backend-specific discoverer and
    Hatchling's own ``hatchling.builders.plugin.interface.IncludedFile``
    both expose, so the shared per-file processing loop in
    :mod:`pitloom.core._models_wheel` can consume either uniformly.
    """

    path: str
    distribution_path: str


class FileHeaderExtras(TypedDict):
    """Keyword arguments for :class:`~pitloom.core.project.ProjectFile`'s
    header/content-type fields."""

    copyright_text: str | None
    copyright_source: str | None
    file_contributors: list[str]
    file_type: str | None
    spdx_license_identifier: str | None
    content_type: str | None
    content_type_method: str | None
