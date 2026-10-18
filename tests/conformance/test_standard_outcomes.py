# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""CISA 2026, FSCT 2024 and BSI coverage of Pitloom's SBOMs, as the checker
reads it.

The expected outcome of every rule, per scenario, is in
``tests/fixtures/conformance/<standard>-expected.tsv``; it changes in the same
commit as any change of an outcome, as for G7.

See also: tests/conformance/test_g7ai_outcomes.py, tests/conformance/g7ai_shared.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest
from ntia_conformance_checker import get_spec

from tests.conformance.g7ai_shared import (
    OUTCOMES,
    SCENARIOS,
    outcomes,
    provisions,
    read_expected,
)

STANDARDS = ("cisa2026", "fsct3", "bsi")
_SCENARIOS = list(SCENARIOS)


@pytest.mark.parametrize("standard", STANDARDS)
def test_table_lists_every_rule_with_its_provision(standard: str) -> None:
    expected = read_expected(standard)
    assert set(expected) == set(provisions(standard))
    for cells in expected.values():
        assert set(cells.values()) <= set(OUTCOMES)


@pytest.mark.parametrize("standard", STANDARDS)
def test_only_unchecked_rules_are_out_of_scope(standard: str) -> None:
    spec = get_spec(standard)
    unchecked = {spec.rule_id(r) for r in spec.rules if r.status == "catalogue-only"}
    for scenario in _SCENARIOS:
        out = {
            r
            for r, c in read_expected(standard).items()
            if c[scenario] == "out-of-scope"
        }
        assert out == unchecked, scenario


@pytest.mark.parametrize("scenario", _SCENARIOS)
@pytest.mark.parametrize("standard", STANDARDS)
def test_outcomes_match_the_table(
    sboms: dict[str, Path], scenario: str, standard: str
) -> None:
    actual = outcomes(sboms[scenario], standard=standard)
    expected = {r: c[scenario] for r, c in read_expected(standard).items()}
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
    assert not regressed, f"{standard} regressions: {regressed}"
    assert not improved, f"{standard} improvements, update the table: {improved}"
    assert actual == expected
