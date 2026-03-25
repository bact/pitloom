# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Merging of pre-generated SPDX 3 fragment files into an SBOM document."""

from __future__ import annotations

import logging
from pathlib import Path

from spdx_python_model import v3_0_1 as spdx3

from loom.exporters.spdx3_json import Spdx3JsonExporter

log = logging.getLogger(__name__)


def merge_fragments(
    project_dir: Path,
    fragment_files: list[str],
    exporter: Spdx3JsonExporter,
) -> None:
    """Load SPDX 3 JSON-LD fragment files and merge them into the exporter.

    Each fragment is a standalone SPDX document (e.g., produced by
    ``loom.bom.track``). Its elements are merged into the main document's
    object set so they appear in the final SBOM output.

    Missing or unreadable fragment files are logged as warnings; they do not
    raise exceptions so that the rest of the SBOM is still produced.

    Args:
        project_dir: Project root used to resolve relative fragment paths.
        fragment_files: List of paths to fragment files, relative to
            ``project_dir``.
        exporter: The exporter whose object set receives the merged elements.
    """
    for fragment_file in fragment_files:
        fragment_path = project_dir / fragment_file
        if not fragment_path.exists():
            log.warning("Configured SBOM fragment %s not found.", fragment_path)
            continue
        try:
            with open(fragment_path, "rb") as f:
                fragment_set = spdx3.SHACLObjectSet()
                spdx3.JSONLDDeserializer().read(f, fragment_set)
                for obj in fragment_set.foreach():
                    exporter.object_set.add(obj)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning("Failed to ingest SBOM fragment %s: %s", fragment_path, exc)
