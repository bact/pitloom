# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM generators for different project types and build systems."""

from __future__ import annotations

from pathlib import Path

from loom.core.creation import CreationInfo
from loom.extractors.pyproject import read_pyproject
from loom.generators.fragments import merge_fragments
from loom.generators.python_project import build


def generate_sbom(
    project_dir: Path,
    output_path: Path | None = None,
    creation_info: CreationInfo | None = None,
    pretty: bool | None = None,
) -> str:
    """Generate an SPDX 3 SBOM for a Python project.

    Orchestrates the full pipeline:

    1. Extract project metadata from ``pyproject.toml``.
    2. Assemble SPDX 3 elements (see :func:`loom.generators.python_project.build`).
    3. Merge any pre-generated SBOM fragments listed under
       ``[tool.loom] fragments`` in ``pyproject.toml``.
    4. Serialize to JSON-LD and optionally write to ``output_path``.

    Args:
        project_dir: Path to the project directory containing ``pyproject.toml``.
        output_path: If given, the JSON-LD output is also written to this path.
        pretty: If ``True``, indent the JSON output with 2 spaces.
            If ``False``, produce compact output (no extra whitespace).
            If ``None`` (default), read the setting from ``[tool.loom] pretty``
            in ``pyproject.toml`` (which itself defaults to ``False``).
        creation_info: Creator and timestamp metadata for the SBOM document.
            When ``None`` a default :class:`~loom.core.creation.CreationInfo`
            is used (creator ``"Loom"``, current UTC time).

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.

    Raises:
        FileNotFoundError: If ``pyproject.toml`` is not found in ``project_dir``.
        ValueError: If required project metadata (e.g., ``name``) is missing.
    """
    metadata, loom_config = read_pyproject(project_dir / "pyproject.toml")
    effective_pretty: bool = loom_config.pretty if pretty is None else pretty

    exporter = build(metadata, creation_info)
    merge_fragments(project_dir, loom_config.fragments, exporter)

    sbom_json = exporter.to_json(pretty=effective_pretty)

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


__all__ = ["generate_sbom"]
