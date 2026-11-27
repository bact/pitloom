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
from pitloom.messages import code_of
from pitloom.messages.config import ConfigPlace, Parameter
from tests.argument_errors import integer_refusal


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
        (1, "must be 0 (no cap) or an integer of at least 8, got an integer 1"),
        (7, "of at least 8, got an integer 7"),
        (-1, "of at least 8, got an integer -1"),
        (-1000, "of at least 8, got an integer -1000"),
        (True, "must be an integer, got a boolean true"),
        ("5", "must be an integer, got a string '5'"),
        (4096.0, "must be an integer, got a float 4096.0"),
        (None, "must be an integer, got None"),
    ],
    ids=repr,
)
def test_require_rejects_an_invalid_budget(value: object, text: str) -> None:
    """The default stage is a library parameter: ``option-invalid``, a
    ``TypeError`` for a value that is no integer."""
    error = integer_refusal(value)
    with pytest.raises(error, match="^max_source_metadata_bytes: must be") as exc:
        require_max_source_metadata_bytes(value)
    assert text in str(exc.value)
    assert code_of(exc.value) == "option-invalid"


def test_require_where_names_the_setting_and_picks_the_code() -> None:
    """A file setting is ``config-invalid``, a library parameter
    ``option-invalid``; each is named as given."""
    with pytest.raises(ValueError, match=r"^\[tool\.pitloom\] k: must be 0") as file:
        require_max_source_metadata_bytes(1, ConfigPlace("tool.pitloom").at("k"))
    assert code_of(file.value) == "config-invalid"
    with pytest.raises(ValueError, match=r"^pc: must be 0") as lib:
        require_max_source_metadata_bytes(1, Parameter("pc"))
    assert code_of(lib.value) == "option-invalid"


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
