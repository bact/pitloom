# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dataset metadata extraction subsystem.

Format-specific dataset readers in this subpackage are internal implementation
modules; callers should use the facade functions exported below.
"""

from __future__ import annotations

from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.extract.dataset.card import read_dataset_card
from pitloom.extract.dataset.licence import DatasetLicence, dataset_licence
from pitloom.extract.dataset.reader import read_croissant, read_dataset

__all__ = [
    "DatasetLicence",
    "DatasetMetadata",
    "dataset_licence",
    "read_croissant",
    "read_dataset",
    "read_dataset_card",
]
