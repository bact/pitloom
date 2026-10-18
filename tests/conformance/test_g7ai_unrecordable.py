# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard for the G7 honesty notice: every element it names is a G7
element the checker does not check and that the mapping snapshot marks as a
GAP (no SPDX 3.0.1 property), and a value written in a broader property is
written in one the mapping assigns to that element and that
``EMITTED_BUT_UNCHECKED`` pins. A new SPDX property, or a checker that starts
checking the element, fails here and forces the element out of the notice.

See also: tests/conformance/test_g7ai_sssom_gaps.py,
tests/extract/ai_model/test_unrecordable.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import csv

import pytest
from ntia_conformance_checker import get_spec

from pitloom.extract.ai_model.unrecordable import UNRECORDABLE, Unrecordable
from tests.conformance.g7ai_shared import MAPPING
from tests.conformance.test_g7ai_sssom_gaps import EMITTED_BUT_UNCHECKED


def _rows() -> dict[str, list[dict[str, str]]]:
    with MAPPING.open(encoding="utf-8") as f:
        lines = (line for line in f if not line.startswith("#"))
        rows = list(csv.DictReader(lines, delimiter="\t"))
    by_subject: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_subject.setdefault(row["subject_id"].split(":", 1)[1], []).append(row)
    return by_subject


def test_the_notice_names_at_least_one_element() -> None:
    assert UNRECORDABLE


@pytest.mark.parametrize("entry", UNRECORDABLE, ids=lambda e: e.element)
def test_each_named_element_is_an_unchecked_gap(entry: Unrecordable) -> None:
    rows = _rows()[entry.element]
    assert all(row["comment"].startswith("GAP") for row in rows)
    unchecked = {
        r.slug[5:-8] for r in get_spec("g7ai").rules if r.status == "catalogue-only"
    }
    assert entry.element in unchecked
    if entry.written_in is not None:
        prop = entry.written_in.split("_", 1)[1]
        assert prop in {row["object_label"] for row in rows}
        assert prop in EMITTED_BUT_UNCHECKED[entry.element]
