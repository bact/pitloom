# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""G7 SBOM for AI coverage of Pitloom's SBOMs, as the checker reads it.

The expected outcome of every rule, per scenario, is in
``tests/fixtures/conformance/g7ai-expected.tsv``. A ``present`` that becomes
anything else is a regression; a ``missing`` that becomes ``present`` is an
improvement. Either way the table changes in the same commit.

See also: tests/conformance/g7ai_shared.py, tests/_spdx3_validate.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest
from ntia_conformance_checker import SbomChecker, get_spec

from tests._spdx3_validate import assert_spdx3_valid
from tests.conformance.g7ai_shared import (
    OUTCOMES,
    SCENARIOS,
    outcomes,
    provisions,
    read_expected,
)

_SCENARIOS = list(SCENARIOS)


def test_table_lists_every_rule_with_its_provision() -> None:
    expected = read_expected()
    assert set(expected) == set(provisions())
    for cells in expected.values():
        assert set(cells.values()) <= set(OUTCOMES)


def test_only_unchecked_rules_are_out_of_scope() -> None:
    spec = get_spec("g7ai")
    unchecked = {spec.rule_id(r) for r in spec.rules if r.status == "catalogue-only"}
    for scenario in _SCENARIOS:
        out = {r for r, c in read_expected().items() if c[scenario] == "out-of-scope"}
        assert out == unchecked, scenario


@pytest.mark.parametrize("scenario", _SCENARIOS)
def test_scenario_sbom_is_valid_spdx3(sboms: dict[str, Path], scenario: str) -> None:
    assert_spdx3_valid(sboms[scenario])


@pytest.mark.parametrize("scenario", _SCENARIOS)
def test_outcomes_match_the_table(sboms: dict[str, Path], scenario: str) -> None:
    actual = outcomes(sboms[scenario])
    expected = {r: c[scenario] for r, c in read_expected().items()}
    regressed = {
        r: (expected[r], actual[r])
        for r in expected
        if expected[r] == "present" and actual[r] != "present"
    }
    improved = {
        r: (expected[r], actual[r])
        for r in expected
        if actual[r] == "present" and expected[r] != "present"
    }
    assert not regressed, f"G7 regressions: {regressed}"
    assert not improved, f"G7 improvements, update the table: {improved}"
    assert actual == expected


@pytest.mark.parametrize("scenario", _SCENARIOS)
def test_generation_is_deterministic(scenario: str) -> None:
    assert SCENARIOS[scenario]() == SCENARIOS[scenario]()


def test_checker_surfaces_agree(sboms: dict[str, Path]) -> None:
    """Library outcomes equal the SARIF ``ruleOutcomes`` that Lumina reads."""
    path = sboms["hub"]
    checker = SbomChecker(str(path), compliance="g7ai", sbom_spec="spdx3")
    sarif = checker.output_sarif()
    assert sarif["runs"][0]["properties"]["ruleOutcomes"] == outcomes(path)
