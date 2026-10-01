# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The entry cap: what it keeps, and that it gives the memory back.

See also: :mod:`tests.extract.scanner.test_scanner_model_limits` (the cap's
warning through the scanner).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import sys
from typing import Any

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.extract.ai_model.limits import MAX_MODEL_ENTRIES, cap_entries

_MANY = 100_000


def _fresh_size(count: int) -> int:
    return sys.getsizeof({i: i for i in range(count)})


def test_a_capped_map_gives_back_its_table_and_keeps_the_first_entries() -> None:
    meta = AiModelMetadata()
    for name in ("hyperparameters", "properties", "raw_metadata"):
        meta_map: dict[str, Any] = {f"k{i}": str(i) for i in range(_MANY)}
        setattr(meta, name, meta_map)
        meta.provenance.update({f"{name}.{key}": "src" for key in meta_map})
    meta.provenance["version"] = "kept"
    before = sys.getsizeof(meta.properties)
    assert before > 10 * _fresh_size(MAX_MODEL_ENTRIES)  # not vacuous

    cut = cap_entries(meta)

    assert cut == ["hyperparameters", "properties", "raw_metadata"]
    for mapping in (
        meta.hyperparameters,
        meta.properties,
        meta.raw_metadata,
        meta.provenance,
    ):
        assert sys.getsizeof(mapping) <= 2 * _fresh_size(len(mapping))
    assert list(meta.properties) == [f"k{i}" for i in range(MAX_MODEL_ENTRIES)]
    assert len(meta.provenance) == 3 * MAX_MODEL_ENTRIES + 1
    assert meta.provenance["version"] == "kept"
    assert "properties.k1000" not in meta.provenance


def test_nothing_is_cut_within_the_cap() -> None:
    meta = AiModelMetadata()
    meta.properties = {f"k{i}": "v" for i in range(MAX_MODEL_ENTRIES)}
    meta.provenance = {"properties.k0": "src"}
    properties, provenance = meta.properties, meta.provenance
    assert cap_entries(meta) == []
    assert meta.properties is properties
    assert meta.provenance is provenance


def test_provenance_follows_its_own_field_and_dotted_entry_names() -> None:
    """One map is capped and another is not; keys contain dots, as
    ``modelspec.title`` does: a field's provenance is cut by its own map."""
    meta = AiModelMetadata()
    meta.properties = {f"modelspec.k{i}": "v" for i in range(MAX_MODEL_ENTRIES + 1)}
    meta.hyperparameters = {"a.b": 1}
    meta.provenance = {f"properties.{key}": "p" for key in meta.properties}
    meta.provenance["hyperparameters.a.b"] = "h"  # a map within the cap
    meta.provenance["name"] = "n"  # no entry: a plain field
    assert cap_entries(meta) == ["properties"]
    assert f"properties.modelspec.k{MAX_MODEL_ENTRIES}" not in meta.provenance
    assert "properties.modelspec.k0" in meta.provenance
    assert (meta.provenance["hyperparameters.a.b"], meta.provenance["name"]) == (
        "h",
        "n",
    )
    assert len(meta.provenance) == MAX_MODEL_ENTRIES + 2
