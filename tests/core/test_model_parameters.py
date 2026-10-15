# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parameter count arithmetic: bounded, and never a partial result.

See also: :mod:`tests.extract.ai_model.test_parameter_count` (the warnings).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from pitloom.core.model_parameters import (
    MAX_PARAMETER_COUNT,
    PARAMETER_COUNT_NOTE,
    ParameterCountRejected,
    stated_parameter_count,
    tensor_element_sum,
    tensor_elements,
    with_parameter_count_note,
)

_MAX = MAX_PARAMETER_COUNT


def test_constants() -> None:
    assert _MAX == 10**15
    assert PARAMETER_COUNT_NOTE.isascii()
    # A ';' would read as a provenance-entry separator once comments merge
    assert ";" not in PARAMETER_COUNT_NOTE
    assert "\n" not in PARAMETER_COUNT_NOTE


_NOTE = PARAMETER_COUNT_NOTE


@pytest.mark.parametrize(
    ("comment", "has_count", "expected"),
    [
        (None, False, None),
        (None, True, _NOTE),
        ("", True, _NOTE),
        ("a", True, f"{_NOTE}\na"),
        (_NOTE, True, _NOTE),
        (_NOTE, False, None),
        (f"{_NOTE}\na", True, f"{_NOTE}\na"),
        (f"a\n{_NOTE}", True, f"{_NOTE}\na"),
        (f"a; {_NOTE}", True, f"{_NOTE}\na"),
        (f"a; {_NOTE}; b", False, "a; b"),
        (f"{_NOTE}; a\n{_NOTE}\nb", True, f"{_NOTE}\na\nb"),
        (f"{_NOTE}\n\n{_NOTE}", False, None),
        ("a\n\nb", False, "a\n\nb"),  # the rest as it was
        (f"x {_NOTE}", False, f"x {_NOTE}"),  # not a whole segment
    ],
    ids=[
        "none",
        "none-count",
        "empty-count",
        "first-line",
        "note-only",
        "note-only-no-count",
        "kept",
        "moved",
        "segment",
        "segment-middle",
        "many",
        "blank-between",
        "blank-line-kept",
        "inside-text",
    ],
)
def test_with_parameter_count_note(
    comment: str | None, has_count: bool, expected: str | None
) -> None:
    assert with_parameter_count_note(comment, has_count) == expected
    if expected is not None:  # idempotent
        assert with_parameter_count_note(expected, has_count) == expected


@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        ([], 1),
        ([2, 3], 6),
        ([5], 5),
        ([0], 0),
        ([0, 2**62], 0),
        ([2**62, 0], 0),
        ([1, _MAX], _MAX),
        ([10**5, 10**5, 10**5], _MAX),
        ([_MAX, 1, 1, 1], _MAX),
    ],
    ids=[
        "scalar",
        "matrix",
        "vector",
        "zero",
        "zero-then-huge",
        "huge-then-zero",
        "at-cap",
        "three-way-at-cap",
        "trailing-ones",
    ],
)
def test_tensor_elements(shape: Sequence[int], expected: int) -> None:
    assert tensor_elements(shape) == expected


@pytest.mark.parametrize(
    "shape",
    [[_MAX + 1], [_MAX, 2], [10**5, 10**5, 10**5, 2], [2**62] * 1000, [10**30]],
    ids=["max-plus-one", "max-times-two", "product-over", "many-huge", "huge-int"],
)
def test_tensor_elements_over_cap(shape: Sequence[int]) -> None:
    with pytest.raises(ParameterCountRejected) as caught:
        tensor_elements(shape)
    assert caught.value.over_cap
    assert len(caught.value.reason) < 100  # no raw huge value in the reason


@pytest.mark.parametrize(
    "shape",
    [[True], [-1], [1.0], ["3"], [None], [2, 3, -1], [0, -1], [-1, 0], [[2]]],
    ids=[
        "bool",
        "negative",
        "float",
        "str",
        "none",
        "late-negative",
        "zero-then-negative",
        "negative-then-zero",
        "nested",
    ],
)
def test_tensor_elements_rejects_a_bad_dimension(shape: Sequence[Any]) -> None:
    with pytest.raises(ParameterCountRejected) as caught:
        tensor_elements(shape)
    assert not caught.value.over_cap
    assert "non-negative integer" in caught.value.reason


# pylint: disable-next=too-few-public-methods
class _Huge:
    """A dimension whose ``repr`` is a megabyte."""

    def __repr__(self) -> str:
        return "x" * 10**6


# pylint: disable-next=too-few-public-methods
class _Broken:
    """A dimension whose ``repr`` raises."""

    def __repr__(self) -> str:
        raise RuntimeError("no repr")


@pytest.mark.parametrize(
    "dim", [_Huge(), _Broken(), "y" * 10**6], ids=["huge-repr", "no-repr", "long-str"]
)
def test_a_hostile_dimension_cannot_flood_the_reason(dim: object) -> None:
    with pytest.raises(ParameterCountRejected) as caught:
        tensor_elements([dim])
    assert len(caught.value.reason) < 200


@pytest.mark.parametrize(
    ("shapes", "expected"),
    [
        ([], None),
        ([[0]], None),
        ([[0], [2, 0]], None),
        ([[2, 3], [4]], 10),
        ([[]], 1),
        ([[_MAX]], _MAX),
        ([[1]] * 1001, 1001),
    ],
    ids=["none", "one-empty", "all-empty", "sum", "scalar", "at-cap", "many"],
)
def test_tensor_element_sum(shapes: list[list[int]], expected: int | None) -> None:
    assert tensor_element_sum(shapes) == expected


def _shapes_failing_midway() -> Iterator[list[object]]:
    yield [2]
    yield [-1]


@pytest.mark.parametrize(
    ("shapes", "over_cap"),
    [
        ([[_MAX], [1]], True),
        ([[_MAX + 1]], True),
        ([[2], [-1]], False),
        (_shapes_failing_midway(), False),
        ([[_MAX // 2 + 1]] * 2, True),
    ],
    ids=["sum-over", "one-over", "bad-dim", "generator", "halves-over"],
)
def test_a_rejection_anywhere_gives_no_sum(shapes: Any, over_cap: bool) -> None:
    with pytest.raises(ParameterCountRejected) as caught:
        tensor_element_sum(shapes)
    assert caught.value.over_cap is over_cap


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), (0, None), (5, 5), (_MAX, _MAX), (1, 1)],
    ids=["none", "zero", "five", "at-cap", "one"],
)
def test_stated_parameter_count(value: object, expected: int | None) -> None:
    assert stated_parameter_count(value) == expected


@pytest.mark.parametrize(
    "value",
    [True, False, -1, "7", 7.0, [7], {}],
    ids=["true", "false", "negative", "str", "float", "list", "dict"],
)
def test_stated_count_rejects_a_non_count(value: object) -> None:
    with pytest.raises(ParameterCountRejected) as caught:
        stated_parameter_count(value)
    assert not caught.value.over_cap


def test_a_stated_count_over_the_cap_is_over_cap() -> None:
    with pytest.raises(ParameterCountRejected) as caught:
        stated_parameter_count(_MAX + 1)
    assert caught.value.over_cap
