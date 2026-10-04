# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Merged SBOM generator: a directory of SPDX 3 fragments into one document.

See also:
- :mod:`pitloom.assemble.spdx3._fragments_envelope` for the merged
  document's envelope.
- :mod:`pitloom.assemble.spdx3.fragments` for the merge itself, shared with
  a project build's configured fragments.
"""

from __future__ import annotations

from pathlib import Path

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble.spdx3._fragments_envelope import (
    finish_merge_document,
    new_merge_document,
)
from pitloom.assemble.spdx3.fragments import fragment_files, merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.logging_config import configure_logging


def generate_merged_sbom(
    fragments_dir: Path | str,
    *,
    output_path: Path | str | None = None,
    pretty: bool = True,
) -> str:
    """Merge every ``*.json`` SPDX 3 fragment in *fragments_dir* into one
    SBOM, as ``loom merge`` does, and return it as JSON-LD.

    The output is one ``SpdxDocument`` rooted at what the fragments' own
    envelopes rooted; equal elements unify as in a project build with
    fragments. The same fragments give the same bytes, whatever the
    directory or the order the files were written in.

    Raises:
        FileNotFoundError: *fragments_dir* does not exist.
        ValueError: it has no ``*.json`` file.
        pitloom.assemble.FragmentMergeError: the merge left a dangling
            reference.
    """
    configure_logging()
    fragments_dir = Path(fragments_dir)
    if not fragments_dir.exists():
        raise FileNotFoundError(f"fragments directory not found: {fragments_dir}")
    files = fragment_files(fragments_dir)
    if not files:
        raise ValueError(f"no JSON fragment files found in {fragments_dir}")
    exporter = new_merge_document([fragments_dir / f for f in files])
    roots = merge_fragments(
        fragments_dir, [FragmentConfig(path=f) for f in files], exporter
    )
    finish_merge_document(exporter, roots)
    sbom_json = exporter.to_json(pretty=pretty)
    write_sbom_output(sbom_json, output_path)
    return sbom_json
