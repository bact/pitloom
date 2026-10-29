# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory``: which sites it finds, which it calls coded,
which count, and that its output is the same on every run.

See also: test_baseline.py (the counts and the ratchet),
tests/test_message_ratchet.py (the real tree).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _site(records: list[dict[str, Any]], module: str, line: int) -> dict[str, Any]:
    (found,) = [r for r in records if r["module"] == module and r["line"] == line]
    return found


# (module, line, coded, forwards the exception's code)
SITES = [
    ("pitloom.coded", 9, True, False),  # emit(...)
    ("pitloom.coded", 10, True, False),  # extra={CODE_ATTR: ...}
    ("pitloom.coded", 11, True, False),  # raise CodedValueError(...)
    ("pitloom.helpers", 13, True, False),  # a helper body that codes
    ("pitloom.callers", 5, True, False),  # a call of that helper
    ("pitloom.helpers", 17, False, False),  # a helper body that does not
    ("pitloom.callers", 6, False, False),  # a call of that helper
    ("pitloom.callers", 11, True, False),  # a call found by its name only
    ("pitloom.callers", 15, True, False),  # raise of a coded builder's result
    ("pitloom.callers", 7, False, False),  # raise ValueError("text")
    ("pitloom.uncoded", 10, False, False),  # logging.warning
    ("pitloom.uncoded", 13, False, False),  # print_error(code=None)
    ("pitloom.uncoded", 14, False, True),  # print_error(code=code_of(exc))
    ("pitloom.relay", 9, False, True),  # extra=relay_extra(...)
    ("pitloom.caps", 16, True, False),  # warn_over_cap(...)
    ("pitloom.caps", 17, True, False),  # a wrapper of it
    ("pitloom.caps", 19, True, False),  # raise ...(pitloom_code=M.code)
]
IDS = [f"{m.rsplit('.', 1)[-1]}:{n}" for m, n, _, _ in SITES]


@pytest.mark.parametrize(("module", "line", "coded", "forwards"), SITES, ids=IDS)
def test_coded_detection(
    mi: ModuleType, tree: Path, module: str, line: int, coded: bool, forwards: bool
) -> None:
    site = _site(mi.inventory(tree), module, line)
    assert (site["coded"], site["forwards_code"]) == (coded, forwards)


def test_a_site_is_one_record_with_its_template(mi: ModuleType, tree: Path) -> None:
    site = _site(mi.inventory(tree), "pitloom.uncoded", 10)
    assert (site["emitter"], site["level"]) == ("logging.warning", "WARNING")
    assert site["template"] == "FILE=%s: odd"
    assert site["file"] == "src/pitloom/uncoded.py"
    assert _site(mi.inventory(tree), "pitloom.callers", 7)["emitter"] == "raise"


def test_scope_and_counts(mi: ModuleType, tree: Path) -> None:
    records = mi.inventory(tree)
    # Out of scope: DEBUG, a call whose text lives in a helper body, and the
    # catalogue's own emit() body.
    assert not mi.in_scope(_site(records, "pitloom.uncoded", 12))
    assert not mi.in_scope(_site(records, "pitloom.callers", 6))
    assert not mi.in_scope(_site(records, "pitloom.messages._emit", 2))
    assert mi.in_scope(_site(records, "pitloom.coded", 9))
    # A catalogue helper's call counts, coded; a wrapper's own call of it is
    # counted at the wrapper's callers.
    assert all(mi.in_scope(_site(records, "pitloom.caps", n)) for n in (16, 17, 19))
    assert not [r for r in records if r["module"] == "pitloom.caps" and r["line"] == 12]
    assert mi.uncoded_counts(records) == {
        "pitloom.callers": 1,
        "pitloom.helpers": 1,
        "pitloom.internal": 1,
        "pitloom.relay": 1,
        "pitloom.uncoded": 4,
    }
    counts = mi.summary(records)
    assert (counts["IN_SCOPE"], counts["IN_SCOPE_CODED"]) == (17, 9)
    assert counts["IN_SCOPE_UNCODED"] == 8 == sum(mi.uncoded_counts(records).values())


@pytest.mark.parametrize(
    ("line", "template"),
    [
        (16, "{cap.subject}={path}: {cap.reason}; skipped"),
        (18, "FORMAT=gguf FILE={path}: larger than the 9-character name cap; cut"),
    ],
    ids=["cap", "model-cap"],
)
def test_an_over_cap_call_names_its_input_as_the_line_does(
    mi: ModuleType, tree: Path, line: int, template: str
) -> None:
    """A cap passed in is named by its fields; a model's cap
    (``model_cap(cap, fmt)``) names the format first and is resolved to its
    constant."""
    assert _site(mi.inventory(tree), "pitloom.caps", line)["template"] == template


@pytest.mark.parametrize(("line", "scoped"), [(6, False), (10, False), (14, True)])
def test_a_programming_error_is_out_of_scope_by_its_class(
    mi: ModuleType, tree: Path, line: int, scoped: bool
) -> None:
    """``InternalError`` by its name or the name it is imported under; the
    same text raised as a plain ``ValueError`` counts."""
    site = _site(mi.inventory(tree), "pitloom.internal", line)
    assert site["emitter"] == "raise"
    assert mi.in_scope(site) is scoped


def test_output_is_the_same_on_every_run(
    mi_main: ModuleType, tree: Path, tmp_path: Path
) -> None:
    out = [tmp_path / "a.jsonl", tmp_path / "b.jsonl"]
    for target in out:
        assert mi_main.main(["--root", str(tree), "--jsonl", str(target)]) == 0
    first, second = (p.read_bytes() for p in out)
    assert first == second
    assert first.endswith(b"\n") and b"\r" not in first
    rows = [json.loads(line) for line in first.decode("utf-8").splitlines()]
    assert len(rows) > 10  # not a vacuous comparison
    order = [(r["file"], r["line"]) for r in rows]
    assert order == sorted(order)
    assert "created" not in first.decode("utf-8")  # no timestamp
