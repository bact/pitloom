# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.core.provenance: ProvenanceConfig and
require_max_source_metadata_bytes().
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import numpy as np
import pytest

from pitloom.core.provenance import (
    MIN_SOURCE_METADATA_BYTES,
    ProvenanceConfig,
    require_max_source_metadata_bytes,
)


def test_min_floor_is_eight_bytes() -> None:
    # {"a":""} under RFC 8785 (JCS) compact separators -- no whitespace.
    assert MIN_SOURCE_METADATA_BYTES == 8


@pytest.mark.parametrize("value", [0, 8, 9, 1000, 10**9, np.int64(8)])
def test_require_passes_zero_and_a_usable_budget_unchanged(value: int) -> None:
    result = require_max_source_metadata_bytes(value)
    assert result == value
    assert result.__class__ is int  # an index-able integer comes back as int


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (1, "0 (unlimited) or at least 8 bytes, got 1"),
        (7, "at least 8 bytes, got 7"),
        (-1, "at least 8 bytes, got -1"),
        (-1000, "at least 8 bytes"),
        (True, "must be an integer"),
        ("5", "must be an integer"),
        (4096.0, "must be an integer"),
        (None, "must be an integer"),
    ],
)
def test_require_rejects_an_invalid_budget(value: object, text: str) -> None:
    with pytest.raises(ValueError, match="max_source_metadata_bytes must be") as exc:
        require_max_source_metadata_bytes(value)
    assert text in str(exc.value)


def test_require_label_names_the_setting_or_none() -> None:
    with pytest.raises(ValueError, match=r"^\[t\] 'k' must be"):
        require_max_source_metadata_bytes(1, "[t] 'k'")
    with pytest.raises(ValueError, match=r"^must be 0"):
        require_max_source_metadata_bytes(1, "")


def test_provenance_config_default_max_source_metadata_bytes_is_zero() -> None:
    assert ProvenanceConfig().max_source_metadata_bytes == 0


def test_provenance_config_max_source_metadata_bytes_round_trips() -> None:
    assert (
        ProvenanceConfig(max_source_metadata_bytes=5000).max_source_metadata_bytes
        == 5000
    )


def test_provenance_config_stores_a_plain_int() -> None:
    stored = ProvenanceConfig(
        max_source_metadata_bytes=np.int64(4096)  # type: ignore[arg-type]
    )
    assert stored.max_source_metadata_bytes == 4096
    assert stored.max_source_metadata_bytes.__class__ is int
