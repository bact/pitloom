# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Originator names: what is a name, what is a list, and the bounds.

See also: :mod:`tests.core.test_model_parameters` (the sibling for the count).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import time
from typing import Any

import pytest

from pitloom.core import model_originators
from pitloom.core.ai_metadata import MAX_MODEL_ENTRIES
from pitloom.core.model_originators import (
    MAX_ORIGINATOR_PARTS,
    ORIGINATOR_PARTS_CAP,
    originator_names,
    originator_names_cut,
)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((None,), []),
        (("",), []),
        (("  ",), []),
        ((5,), []),
        ((True,), []),
        ((["Alice"],), []),
        ((" Alice ",), ["Alice"]),
        (("Doe, Jane",), ["Doe, Jane"]),
        ((",,,",), [",,,"]),
        (("Org", "Org"), ["Org"]),
        (("A", None, "B"), ["A", "B"]),
        (("B", "A", " B"), ["B", "A"]),
        ((), []),
    ],
    ids=[
        "none",
        "empty",
        "blank",
        "int",
        "bool",
        "list",
        "stripped",
        "one-name-with-comma",
        "commas-are-a-name",
        "repeat",
        "skips-non-str",
        "first-kept-source-order",
        "no-values",
    ],
)
def test_each_string_is_one_name(values: tuple[Any, ...], expected: list[str]) -> None:
    assert originator_names(*values) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a, b,,a , c", ["a", "b", "c"]),
        ("Doe, Jane", ["Doe", "Jane"]),  # the documented caveat
        (",,,", []),
        ("  ", []),
        ("Alice", ["Alice"]),
        (",x,", ["x"]),
    ],
    ids=["list", "caveat", "only-commas", "blank", "single", "edges"],
)
def test_comma_list(text: str, expected: list[str]) -> None:
    assert originator_names(text, comma_list=True) == expected


def test_comma_list_over_several_values_dedups_across_them() -> None:
    assert originator_names("a,b", None, "b, c", comma_list=True) == ["a", "b", "c"]


def test_collecting_stops_one_past_the_cap() -> None:
    text = ",".join(f"n{i}" for i in range(1500))
    names = originator_names(text, comma_list=True)
    assert len(names) == MAX_MODEL_ENTRIES + 1
    assert names[0] == "n0"
    values = [f"n{i}" for i in range(1500)]
    assert len(originator_names(*values)) == MAX_MODEL_ENTRIES + 1


def test_a_string_of_millions_of_commas_is_not_listed() -> None:
    assert originator_names("," * 10**6 + "x", comma_list=True) == ["x"]


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("," * 10**7, []),
        ("a," * 10**7, ["a"]),  # repeats never reach the distinct-name stop
        (" ," * 10**7, []),
        (" " * 10**7 + ",x", ["x"]),  # a long blank run is not re-scanned
    ],
    ids=["commas", "repeats", "blank-parts", "blank-run"],
)
def test_hostile_comma_lists_are_read_quickly(text: str, names: list[str]) -> None:
    start = time.monotonic()
    assert originator_names(text, comma_list=True) == names
    assert time.monotonic() - start < 5  # generous: about 0.1 s


@pytest.mark.parametrize(
    ("values", "names", "cut"),
    [
        (("a,a,a,a,b",), ["a"], True),  # the fourth part is not examined
        (("a,b,c,d,e",), ["a", "b", "c"], True),
        (("a, ,b,c",), ["a", "b"], True),  # a blank part counts as examined
        ((" , , , x",), [], True),  # whitespace parts only
        ((",,,,,,,x",), ["x"], False),  # an empty part does not
        (("a,b,c",), ["a", "b", "c"], False),  # the bound met exactly at the end
        (("a,b,c,,,",), ["a", "b", "c"], False),  # only empty parts remain
        (("a,a,a",), ["a"], False),
        (("a,b", "c,d"), ["a", "b", "c"], True),  # one bound over several values
        (("a,b", "c", "d"), ["a", "b", "c"], True),
        (("a,b", None, "c"), ["a", "b", "c"], False),  # skipped values: no part
    ],
    ids=[
        "repeats",
        "distinct",
        "blank-counts",
        "blank-only",
        "empty-does-not",
        "exact-end",
        "empty-after-exact-end",
        "repeats-exact-end",
        "several-values",
        "one-part-values",
        "non-str-uncounted",
    ],
)
def test_names_past_the_parts_bound_are_not_read(
    monkeypatch: pytest.MonkeyPatch,
    values: tuple[Any, ...],
    names: list[str],
    cut: bool,
) -> None:
    """The flag is true only when parts remained unread."""
    monkeypatch.setattr(model_originators, "MAX_ORIGINATOR_PARTS", 3)
    assert originator_names_cut(*values, comma_list=True) == (names, cut)
    assert originator_names(*values, comma_list=True) == names


def test_without_comma_list_each_value_is_a_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_originators, "MAX_ORIGINATOR_PARTS", 3)
    assert originator_names_cut("a", "b", "c") == (["a", "b", "c"], False)
    assert originator_names_cut("a", "b", "c", "d") == (["a", "b", "c"], True)


def test_the_cut_flag_is_false_for_the_entry_stop() -> None:
    """The entry cap's own warning covers that stop, not the parts bound."""
    text = ",".join(f"n{i}" for i in range(1500))
    names, cut = originator_names_cut(text, comma_list=True)
    assert len(names) == MAX_MODEL_ENTRIES + 1
    assert not cut


def test_empty_pieces_do_not_warn_at_scale() -> None:
    assert originator_names_cut("," * 10**6 + "b", comma_list=True) == (["b"], False)


def test_the_parts_bound_leaves_room_for_the_distinct_name_stop() -> None:
    assert MAX_ORIGINATOR_PARTS >= MAX_MODEL_ENTRIES + 1


def test_the_parts_cap_says_its_bound() -> None:
    assert ORIGINATOR_PARTS_CAP.limit == MAX_ORIGINATOR_PARTS
    assert ORIGINATOR_PARTS_CAP.reason == (
        f"larger than the {MAX_ORIGINATOR_PARTS}-part model-author cap"
    )
