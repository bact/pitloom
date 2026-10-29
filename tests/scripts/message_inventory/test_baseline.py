# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory``: the baseline writer and reader, and the
ratchet that compares counts to it, in both directions.

See also: test_inventory.py (the counts), tests/test_message_ratchet.py (the
real tree against the real baseline).
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

BASE = {"pitloom.a": 3, "pitloom.b": 1}


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (BASE, []),  # unchanged: nothing to say
        (
            {"pitloom.a": 4, "pitloom.b": 1},
            ["pitloom.a: 4 uncoded", "total: 5 uncoded"],
        ),  # rise
        (
            {"pitloom.a": 3, "pitloom.b": 1, "pitloom.c": 1},
            ["pitloom.c: 1", "total: 5 uncoded"],
        ),  # new
        ({"pitloom.a": 2, "pitloom.b": 1}, ["pitloom.a: 2 uncoded"]),  # fall
        ({"pitloom.a": 3}, ["pitloom.b: 0 uncoded"]),  # last one coded
        (
            {"pitloom.a": 2, "pitloom.b": 1, "pitloom.c": 1},
            ["pitloom.c: 1", "pitloom.a: 2 uncoded"],
        ),  # a site moved to a new module: the total holds
    ],
    ids=["same", "rise", "new-module", "fall", "module-gone", "moved"],
)
def test_compare_flags_a_rise_and_a_fall(
    mi: ModuleType, current: dict[str, int], expected: list[str]
) -> None:
    problems = mi.compare(BASE, current)
    assert len(problems) == len(expected)
    for problem, start in zip(problems, expected, strict=True):
        assert problem.startswith(start)


def test_compare_says_how_to_fix_each_direction(mi: ModuleType) -> None:
    rise, total = mi.compare({"pitloom.a": 1}, {"pitloom.a": 2})
    (fall,) = mi.compare({"pitloom.a": 2}, {"pitloom.a": 1})
    assert "needs a code" in rise and mi.REGENERATE not in rise
    assert total.startswith("total: 2 uncoded") and "baseline 1" in total
    assert mi.REGENERATE in fall and "lower" in fall


def test_baseline_round_trip(mi: ModuleType) -> None:
    text = mi.format_baseline({"pitloom.z": 2, "pitloom.a": 10})
    assert mi.parse_baseline(text) == {"pitloom.a": 10, "pitloom.z": 2}
    body = [ln for ln in text.splitlines() if not ln.startswith("#")]
    assert body == ["pitloom.a 10", "pitloom.z 2"]  # sorted by module
    assert mi.REGENERATE in text and "\r" not in text


@pytest.mark.parametrize(
    "line", ["pitloom.a", "pitloom.a x", "pitloom.a 1 2", "pitloom.a -1"]
)
def test_parse_rejects_a_malformed_line(mi: ModuleType, line: str) -> None:
    with pytest.raises(ValueError, match="baseline line 2"):
        mi.parse_baseline(f"# header\n{line}\n")


def test_parse_rejects_a_repeated_module(mi: ModuleType) -> None:
    with pytest.raises(ValueError, match="baseline line 2"):
        mi.parse_baseline("pitloom.a 1\npitloom.a 2\n")


def test_write_then_check_then_a_coded_site_goes_stale(
    mi_main: ModuleType, tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = tree / "uncoded.txt"
    args = ["--root", str(tree), "--baseline", str(baseline)]
    assert mi_main.main([*args, "--write-baseline"]) == 0
    written = baseline.read_bytes()
    assert b"pitloom.uncoded 4\n" in written
    assert mi_main.main([*args, "--write-baseline"]) == 0
    assert baseline.read_bytes() == written  # rewriting changes nothing
    assert mi_main.main([*args, "--check"]) == 0

    # A new uncoded site: the count rises.
    source = tree / "src" / "pitloom" / "uncoded.py"
    original = source.read_text(encoding="utf-8")
    new = '    _log.warning("FILE=%s: new", path)\n'
    source.write_bytes((original + new).encode("utf-8"))
    capsys.readouterr()
    assert mi_main.main([*args, "--check"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR: pitloom.uncoded: 5 uncoded") and "baseline 4" in err

    # A site gone (or given a code): the count falls below a now stale baseline.
    odd = '    _log.warning("FILE=%s: odd", path)\n'
    assert odd in original
    source.write_bytes(original.replace(odd, "    pass\n").encode("utf-8"))
    assert mi_main.main([*args, "--check"]) == 1
    assert "baseline 4: lower the baseline" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("baseline", "written"),
    [
        ("pitloom.uncoded 9\npitloom.helpers 9\npitloom.callers 9\n", True),
        ("pitloom.uncoded 3\npitloom.helpers 9\npitloom.callers 9\n", False),
        ("pitloom.old 6\npitloom.helpers 1\npitloom.callers 1\n", False),
    ],
    ids=["falls-only", "a-module-rises", "moved-total-holds"],
)
def test_rewriting_the_baseline_only_lowers_it(
    mi_main: ModuleType,
    tree: Path,
    capsys: pytest.CaptureFixture[str],
    baseline: str,
    written: bool,
) -> None:
    """``--write-baseline`` writes falls; a module above its count is
    refused, even when the total holds (a site moved there is moved in the
    file by hand)."""
    path = tree / "uncoded.txt"
    path.write_bytes(f"pitloom.internal 1\npitloom.relay 1\n{baseline}".encode())
    before = path.read_bytes()
    args = ["--root", str(tree), "--baseline", str(path), "--write-baseline"]
    assert mi_main.main(args) == (0 if written else 1)
    err = capsys.readouterr().err
    if written:
        assert path.read_bytes() != before and err.startswith("INFO: wrote")
    else:
        assert path.read_bytes() == before
        assert err.startswith("ERROR: pitloom.uncoded: 4 uncoded")
