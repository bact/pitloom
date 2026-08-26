# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.core.provenance: ProvenanceConfig and
normalize_max_source_metadata_bytes().
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging

import pytest

from pitloom.core.provenance import (
    _MIN_EFFECTIVE_MAX_SOURCE_METADATA_BYTES,
    ProvenanceConfig,
    normalize_max_source_metadata_bytes,
)


def test_min_effective_floor_is_eight_bytes() -> None:
    # {"a":""} under RFC 8785 (JCS) compact separators -- no whitespace.
    assert _MIN_EFFECTIVE_MAX_SOURCE_METADATA_BYTES == 8


def test_normalize_zero_passes_through_unchanged() -> None:
    assert normalize_max_source_metadata_bytes(0) == 0


@pytest.mark.parametrize("value", [8, 9, 1000, 10**9])
def test_normalize_valid_values_pass_through_unchanged(value: int) -> None:
    assert normalize_max_source_metadata_bytes(value) == value


@pytest.mark.parametrize("value", [1, 2, 7])
def test_normalize_too_small_positive_collapses_to_zero(
    value: int, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert normalize_max_source_metadata_bytes(value) == 0
    assert "max-source-metadata-bytes" in caplog.text
    assert str(value) in caplog.text


@pytest.mark.parametrize("value", [-1, -1000])
def test_normalize_negative_collapses_to_zero(
    value: int, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert normalize_max_source_metadata_bytes(value) == 0
    assert "max-source-metadata-bytes" in caplog.text


def test_provenance_config_default_max_source_metadata_bytes_is_zero() -> None:
    assert ProvenanceConfig().max_source_metadata_bytes == 0


def test_provenance_config_max_source_metadata_bytes_round_trips() -> None:
    assert (
        ProvenanceConfig(max_source_metadata_bytes=5000).max_source_metadata_bytes
        == 5000
    )
