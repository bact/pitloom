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
from tests.warning_helpers import logged_warnings

_LOG = logging.getLogger("pitloom.test_parameter_count")
_CAP = "larger than the 1000000000000000-element parameter-count cap"
_BAD = ParameterCountRejected(
    "tensor dimension -1 is not a non-negative integer", over_cap=False
)
_OVER = ParameterCountRejected("count is over", over_cap=True)


@pytest.mark.parametrize(
    ("exc", "fmt", "expected"),
    [
        (_OVER, None, f"FILE=m.gguf: {_CAP}; parameter count not recorded"),
        (
            _OVER,
            "gguf",
            f"FORMAT=gguf FILE=m.gguf: {_CAP}; parameter count not recorded",
        ),
        (
            _BAD,
            None,
            "tensor dimension -1 is not a non-negative integer;"
            " parameter count not recorded",
        ),
        (
            _BAD,
            "onnx",
            "FORMAT=onnx FILE=m.gguf: tensor dimension -1 is not a non-negative"
            " integer; parameter count not recorded",
        ),
    ],
    ids=["cap", "cap-format", "reason", "reason-format"],
)
def test_warning_wordings(
    exc: ParameterCountRejected,
    fmt: str | None,
    expected: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    warn_parameter_count(_LOG, exc, "m.gguf", fmt)
    assert logged_warnings(caplog) == [expected]


def test_the_file_is_escaped(caplog: pytest.LogCaptureFixture) -> None:
    warn_parameter_count(_LOG, _OVER, "a\nWARNING: x", "gguf")
    warn_parameter_count(_LOG, _BAD, "a\nWARNING: x", "gguf")
    warnings = logged_warnings(caplog)
    assert len(warnings) == 2
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


def test_another_error_from_the_shapes_is_not_swallowed() -> None:
    def broken() -> Iterator[list[int]]:
        yield [1]
        raise ValueError("reader failure")

    with pytest.raises(ValueError, match="reader failure"):
        derived_parameter_count(broken(), "f", "Source: m", {}, "m")
