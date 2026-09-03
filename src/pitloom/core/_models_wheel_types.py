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

from pathlib import Path
from typing import NamedTuple, Protocol, TypedDict


class IncludedFile(NamedTuple):
    """One file that belongs in the wheel, as resolved by a backend.

    Mirrors the two attributes every backend-specific discoverer and
    Hatchling's own ``hatchling.builders.plugin.interface.IncludedFile``
    both expose, so the shared per-file processing loop in
    :mod:`pitloom.core._models_wheel` can consume either uniformly.
    """

    path: str
    distribution_path: str


# pylint: disable-next=too-few-public-methods
class BackendDiscoverer(Protocol):
    """Call signature every backend discovery module's ``discover()`` must
    share, so the dispatch registry in :mod:`pitloom.core._models_wheel`
    can call any of them uniformly -- adding a new backend is then one
    module implementing this signature plus one registry entry, never a
    special case at the call site. *pyproject_data*, when given, is the
    already-parsed ``pyproject.toml`` (see
    :func:`pitloom.extract._setuptools.read_pyproject_toml`); a backend
    that doesn't need it (e.g. Hatchling, which re-reads config itself via
    ``WheelBuilder``) still accepts and ignores the keyword."""

    def __call__(
        self, project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile] | None: ...


def has_resolvable_pyproject_config(
    pyproject_data: dict[str, object], backend: str
) -> bool:
    """Whether the parsed ``pyproject.toml`` declares enough for *backend*
    to resolve packages from: a PEP 621 ``[project]`` table (every
    registered backend's own zero-config auto-discovery applies here,
    even without an explicit ``[tool.<backend>]`` table) or an explicit
    ``[tool.<backend>]`` table. A ``pyproject.toml`` with only
    ``[build-system]`` (e.g. packages declared imperatively in
    ``setup.py`` instead) declares neither.

    Shared by :mod:`pitloom.core._models_wheel_setuptools` (deciding
    whether to attempt static discovery at all) and
    :mod:`pitloom.core._models_wheel` (deciding what a failed
    discoverer's fallback ``WARNING:`` should say), so the two stay in
    sync rather than re-deriving the same check independently."""
    tool = pyproject_data.get("tool", {})
    return "project" in pyproject_data or (
        backend in tool if isinstance(tool, dict) else False
    )


def to_posix_distribution_path(path: str) -> str:
    """Normalize *path* to forward-slash separators for use as an
    ``IncludedFile.distribution_path`` -- a wheel's internal paths are
    always ``/``-separated regardless of the platform Pitloom runs on.

    Shared so this one-line normalization doesn't keep getting
    hand-copied per backend discovery module (setuptools, Hatchling,
    Poetry, Flit each needed it independently) -- see CLAUDE.md's note
    that a pattern repeated across 3+ call sites drifts."""
    return path.replace("\\", "/")


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
