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

import pytest

from pitloom.core.ai_metadata import (
    MAX_MODEL_NAME_CHARS,
    AiModelFormatInfo,
    AiModelMetadata,
)
from pitloom.extract.ai_model.formats import Limits
from pitloom.extract.ai_model.limits import (
    MAX_MODEL_ENTRIES,
    cap_entries,
    recordable_labels,
    warn_name_cut,
)
from tests.warning_helpers import logged_warnings

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
    # Every other key typed, the last one over the cut too.
    meta.raw_metadata_types = {f"k{i}": "integer" for i in range(0, _MANY, 2)}
    meta.raw_metadata_dropped = 3  # a reader's own cut, before this one
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
    assert meta.raw_metadata_dropped == 3 + _MANY - MAX_MODEL_ENTRIES
    assert meta.raw_metadata_types == {  # a dropped key loses its type
        f"k{i}": "integer" for i in range(0, MAX_MODEL_ENTRIES, 2)
    }


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
    assert meta.raw_metadata_dropped == 0  # only raw_metadata counts
    assert f"properties.modelspec.k{MAX_MODEL_ENTRIES}" not in meta.provenance
    assert "properties.modelspec.k0" in meta.provenance
    assert (meta.provenance["hyperparameters.a.b"], meta.provenance["name"]) == (
        "h",
        "n",
    )
    assert len(meta.provenance) == MAX_MODEL_ENTRIES + 2


_LABEL_BYTES = Limits().max_label_bytes


@pytest.mark.parametrize(
    ("labels", "kept"),
    [
        ([], True),
        (["O", "x" * _LABEL_BYTES], True),
        (["\u00e9" * (_LABEL_BYTES // 2)], True),  # 2 bytes each: at the cap
        (["O", "\u00e9" * (_LABEL_BYTES // 2) + "x"], False),
        (["x" * (_LABEL_BYTES + 1), "y" * (2 * _LABEL_BYTES)], False),
        # A lone surrogate is counted (3 bytes), not an encoding error.
        (["\ud800" * (_LABEL_BYTES // 3)], True),
        (["\ud800" * (_LABEL_BYTES // 3) + "xx"], False),
    ],
    ids=[
        "none",
        "at-cap",
        "at-cap-utf8",
        "one-byte-over",
        "two-over",
        "surrogates-under",
        "surrogates-over",
    ],
)
def test_a_label_over_the_cap_drops_every_label_with_one_warning(
    labels: list[str], kept: bool, caplog: pytest.LogCaptureFixture
) -> None:
    assert _LABEL_BYTES == 4096
    assert recordable_labels(labels, Limits()) == (tuple(labels) if kept else ())
    warnings = logged_warnings(caplog)
    assert warnings == (
        [] if kept else [f"a label over {_LABEL_BYTES} bytes; no label recorded"]
    )


@pytest.mark.parametrize("extra", [0, 1], ids=["at-cap", "over"])
def test_a_cut_name_is_said_once_with_its_length(
    extra: int, caplog: pytest.LogCaptureFixture
) -> None:
    meta = AiModelMetadata(
        format_info=AiModelFormatInfo(file_name="x" * (MAX_MODEL_NAME_CHARS + extra))
    )
    warn_name_cut(meta, "gguf", "m.gguf")
    expected = "FORMAT=gguf FILE=m.gguf: model name of 1025 characters cut to 1024"
    assert logged_warnings(caplog) == ([expected] if extra else [])
