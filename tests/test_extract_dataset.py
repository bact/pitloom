# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.dataset -- the public dataset-extraction API.

test_extract_croissant.py tests the Croissant format in depth via the
internal pitloom.extract._croissant module directly; this file only
confirms the public re-export in pitloom.extract.dataset itself works,
since nothing else imports read_croissant through that public path.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

from pitloom.extract.dataset import DatasetMetadata, read_croissant

FIXTURES = Path(__file__).parent / "fixtures" / "croissant"


def test_read_croissant_public_reexport() -> None:
    meta = read_croissant(FIXTURES / "minimal.json")
    assert isinstance(meta, DatasetMetadata)
    assert meta.name
