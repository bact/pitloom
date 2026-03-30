# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dataset metadata extraction public API.

Provides format-dispatched access to dataset metadata extractors.
Currently supports the Croissant JSON-LD format.

Usage::

    from pitloom.extract.dataset import read_croissant
    meta = read_croissant("https://huggingface.co/datasets/example/croissant.json")
    meta = read_croissant(Path("local/dataset.json"))
"""

from __future__ import annotations

from pathlib import Path

from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.extract._croissant import read_croissant as _read_croissant

__all__ = [
    "DatasetMetadata",
    "read_croissant",
]


def read_croissant(source: str | Path) -> DatasetMetadata:
    """Extract dataset metadata from a Croissant JSON-LD document.

    Accepts a local file path or an HTTP/HTTPS URL.  No third-party packages
    are required.

    Args:
        source: Path to a local ``.json`` file or an HTTP/HTTPS URL pointing
            to a Croissant-formatted JSON-LD document.

    Returns:
        :class:`~pitloom.core.dataset_metadata.DatasetMetadata` with available
        fields populated.

    Raises:
        ValueError: If *source* cannot be read, is not valid JSON, or has no
            ``name`` field.
    """
    return _read_croissant(source)
