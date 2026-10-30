# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The parameter count warnings, and what a derived count records.

See also: :mod:`tests.core.test_model_parameters` (the arithmetic).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest

from pitloom.core.model_parameters import (
    MAX_PARAMETER_COUNT,
    PARAMETER_COUNT_PROVENANCE_KEY,
    ParameterCountRejected,
)
from pitloom.extract.ai_model.parameter_count import (
    derived_parameter_count,
    warn_parameter_count,
)
from pitloom.logging_config import CODE_ATTR
from tests.warning_helpers import logged_warnings

_CAPPED, _INVALID = "over-cap", "parameter-count-invalid"

_LOG = logging.getLogger("pitloom.parameter_count_test")
_CAP = "larger than the 1000000000000000-element parameter-count cap"
_BAD = ParameterCountRejected(
    "tensor dimension -1 is not a non-negative integer", over_cap=False, value="-1"
)
_STATED = ParameterCountRejected(
    "stated parameter count is not a non-negative integer", over_cap=False
)
_OVER = ParameterCountRejected("count is over", over_cap=True)
_DIMENSION_LINE = (
    "tensor dimension -1 is not a non-negative integer; parameter count not recorded"
)


@pytest.mark.parametrize(
    ("exc", "fmt", "expected", "code"),
    [
        (_OVER, None, f"FILE=m.gguf: {_CAP}; parameter count not recorded", _CAPPED),
        (
            _OVER,
            "gguf",
            f"FORMAT=gguf FILE=m.gguf: {_CAP}; parameter count not recorded",
            _CAPPED,
        ),
        (_BAD, None, _DIMENSION_LINE, _INVALID),
        # a dimension's line is the reader's: the scan names the model
        (_BAD, "onnx", _DIMENSION_LINE, _INVALID),
        (
            _STATED,
            "huggingface",
            "FORMAT=huggingface FILE=m.gguf: stated parameter count is not a"
            " non-negative integer; parameter count not recorded",
            _INVALID,
        ),
    ],
    ids=["cap", "cap-format", "reason", "reason-format", "stated"],
)
def test_warning_wordings(
    exc: ParameterCountRejected,
    fmt: str | None,
    expected: str,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    warn_parameter_count(_LOG, exc, "m.gguf", fmt)
    assert logged_warnings(caplog) == [expected]
    (record,) = caplog.records
    assert getattr(record, CODE_ATTR) == code


def test_a_stated_count_needs_the_model_it_names() -> None:
    with pytest.raises(ValueError, match="is not a format"):
        warn_parameter_count(_LOG, _STATED, "m.gguf")


def test_the_file_and_the_value_are_escaped(caplog: pytest.LogCaptureFixture) -> None:
    hostile = ParameterCountRejected("x", over_cap=False, value="'a\nWARNING: x'")
    warn_parameter_count(_LOG, _OVER, "a\nWARNING: x", "gguf")
    warn_parameter_count(_LOG, _STATED, "a\nWARNING: x", "gguf")
    warn_parameter_count(_LOG, hostile, "m.gguf")
    warnings = logged_warnings(caplog)
    assert len(warnings) == 3
    assert all("\n" not in text for text in warnings)


def test_a_sum_records_its_provenance(caplog: pytest.LogCaptureFixture) -> None:
    provenance: dict[str, str] = {"name": "n"}
    count = derived_parameter_count(
        [[2, 3], [4]], "tensor_infos", "Source: m.gguf", provenance, "m.gguf"
    )
    assert count == 10
    assert provenance == {
        "name": "n",
        PARAMETER_COUNT_PROVENANCE_KEY: (
            "Source: m.gguf | Field: tensor_infos | Method: tensor_element_sum"
        ),
    }
    assert logged_warnings(caplog) == []


@pytest.mark.parametrize(
    "shapes", [[], [[0]], [[0, 3]]], ids=["no-tensor", "empty", "zero-dim"]
)
def test_no_element_is_quiet_and_unrecorded(
    shapes: list[list[int]], caplog: pytest.LogCaptureFixture
) -> None:
    provenance: dict[str, str] = {}
    assert derived_parameter_count(shapes, "f", "Source: m", provenance, "m") is None
    assert not provenance
    assert logged_warnings(caplog) == []


def _fail_midway() -> Iterator[list[Any]]:
    yield [2]
    yield [-1]


@pytest.mark.parametrize(
    ("shapes", "message"),
    [
        (
            [[2], ["a"]],
            "tensor dimension 'a' is not a non-negative integer;"
            " parameter count not recorded",
        ),
        (
            _fail_midway(),
            "tensor dimension -1 is not a non-negative integer;"
            " parameter count not recorded",
        ),
        (
            [[MAX_PARAMETER_COUNT], [1]],
            f"FILE=m: {_CAP}; parameter count not recorded",
        ),
    ],
    ids=["bad-dim", "generator", "over-cap"],
)
def test_a_rejection_is_one_warning_and_no_count(
    shapes: Any, message: str, caplog: pytest.LogCaptureFixture
) -> None:
    provenance: dict[str, str] = {}
    assert derived_parameter_count(shapes, "f", "Source: m", provenance, "m") is None
    assert not provenance
    assert logged_warnings(caplog) == [message]
    (record,) = caplog.records
    assert getattr(record, CODE_ATTR) == (_CAPPED if "cap;" in message else _INVALID)


def test_another_error_from_the_shapes_is_not_swallowed() -> None:
    def broken() -> Iterator[list[int]]:
        yield [1]
        raise ValueError("reader failure")

    with pytest.raises(ValueError, match="reader failure"):
        derived_parameter_count(broken(), "f", "Source: m", {}, "m")
