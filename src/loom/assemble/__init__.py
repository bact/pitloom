# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE

"""SBOM assemblers for different output specifications."""

from __future__ import annotations

from pathlib import Path

from loom.assemble.spdx3.assembler import build
from loom.assemble.spdx3.fragments import merge_fragments
from loom.core.creation import CreationMetadata
from loom.core.document import DocumentModel
from loom.extract.pyproject import read_pyproject


def generate_sbom(
    project_dir: Path,
    output_path: Path | None = None,
    creation_info: CreationMetadata | None = None,
    pretty: bool | None = None,
) -> str:
    """Generate an SPDX 3 SBOM for a Python project.

    Args:
        project_dir: Path to the project directory containing ``pyproject.toml``.
        output_path: If given, the JSON-LD output is also written to this path.
        pretty: If ``True``, indent the JSON output with 2 spaces.
            If ``False``, produce compact output (no extra whitespace).
            If ``None`` (default), read the setting from ``[tool.loom] pretty``
            in ``pyproject.toml`` (which itself defaults to ``False``).
        creation_info: Creator and timestamp metadata for the SBOM document.
            When ``None`` a default :class:`~loom.core.creation.CreationMetadata`
            is used (creator ``"Loom"``, current UTC time).

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.

    Raises:
        FileNotFoundError: If ``pyproject.toml`` is not found in ``project_dir``.
        ValueError: If required project metadata (e.g., ``name``) is missing.
    """
    metadata, loom_config = read_pyproject(project_dir / "pyproject.toml")
    effective_pretty: bool = loom_config.pretty if pretty is None else pretty

    doc = DocumentModel(
        project=metadata,
        creation=creation_info or CreationMetadata(),
    )
    exporter = build(doc)
    merge_fragments(project_dir, loom_config.fragments, exporter)

    sbom_json = exporter.to_json(pretty=effective_pretty)

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


__all__ = ["generate_sbom"]
