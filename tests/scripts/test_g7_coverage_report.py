# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/g7_coverage_report.py``, the G7 coverage report."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

P = "BOM-G7AI2026-"
KINDS = {
    P + "MDL-001": "requirement",
    P + "MDL-002": "requirement",
    P + "MDL-006.1": "recommendation",
    P + "DP-001": "requirement",
    P + "INF-001": "requirement",
}
ACTUAL = {
    P + "MDL-001": "present",
    P + "MDL-002": "missing",
    P + "MDL-006.1": "present",
    P + "DP-001": "not-applicable",
    P + "INF-001": "out-of-scope",
}


@pytest.fixture(name="module")
def module_fixture(load_script: Callable[[str], ModuleType]) -> ModuleType:
    return load_script("g7_coverage_report")


def test_summary_counts_and_coverage(module: ModuleType) -> None:
    summary = module.summarise(ACTUAL, KINDS, 7)
    assert summary["outcomes"] == {
        "missing": 1,
        "not-applicable": 1,
        "out-of-scope": 1,
        "present": 2,
    }
    # Undecided and unchecked rules are not in the denominator.
    assert summary["coverage_percent"] == 66.7
    assert summary["requirement_coverage_percent"] == 50.0
    assert summary["clusters"]["MDL"]["present"] == 2
    assert summary["clusters"]["DP"]["coverage_percent"] is None
    assert summary["properties_written"] == 7


def _make(
    module: ModuleType, outcome: str, *, checker: str = "1", props: int = 3
) -> dict[str, Any]:
    actual = {P + "MDL-001": outcome, P + "MDL-002": "missing"}
    kinds = dict.fromkeys(actual, "requirement")
    return {
        "header": {"checker": checker, "mapping_sha256": "m", "rules": 2},
        "scenarios": {
            "s": {
                "outcomes": actual,
                "summary": module.summarise(actual, kinds, props),
            }
        },
    }


def test_compare_reports_flips_and_series_breaks(module: ModuleType) -> None:
    before = _make(module, "missing")
    after = _make(module, "present", checker="2", props=5)
    lines = module.compare(before, after)
    assert "SERIES BREAK: checker changed; compare with care" in lines
    assert any("s: coverage +50.0 points" in line for line in lines)
    assert f"  {P}MDL-001: missing -> present" in lines
    assert "  properties written: +2" in lines
    assert module.compare(before, before)[-1] == "s: coverage +0.0 points"


def test_compare_names_a_new_scenario(module: ModuleType) -> None:
    before = _make(module, "missing")
    after = _make(module, "missing")
    after["scenarios"]["t"] = after["scenarios"]["s"]
    assert "t: new scenario" in module.compare(before, after)


def test_report_of_one_scenario_is_deterministic(
    module: ModuleType, tmp_path: Path
) -> None:
    out = [tmp_path / "a.json", tmp_path / "b.json"]
    for path in out:
        assert module.main(["--scenario", "gguf", "-o", str(path)]) == 0
    assert out[0].read_bytes() == out[1].read_bytes()
    report = json.loads(out[0].read_text(encoding="utf-8"))
    assert list(report["scenarios"]) == ["gguf"]
    assert report["header"]["rules"] == 81


def test_compare_command_prints_the_changes(
    module: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = []
    for name, outcome in (("a", "missing"), ("b", "present")):
        paths.append(tmp_path / f"{name}.json")
        paths[-1].write_text(json.dumps(_make(module, outcome)), encoding="utf-8")
    assert module.main(["--compare", str(paths[0]), str(paths[1])]) == 0
    assert f"{P}MDL-001: missing -> present" in capsys.readouterr().out


def test_write_expected_reproduces_the_committed_table(
    module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    committed = module.shared.EXPECTED.read_bytes()
    monkeypatch.setattr(module.shared, "EXPECTED", tmp_path / "expected.tsv")
    assert module.main(["--write-expected"]) == 0
    assert (tmp_path / "expected.tsv").read_bytes() == committed


def test_write_expected_needs_every_scenario(module: ModuleType) -> None:
    with pytest.raises(SystemExit):
        module.main(["--write-expected", "--scenario", "gguf"])
