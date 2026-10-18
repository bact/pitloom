# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""CISA 2026 Minimum Elements coverage of Pitloom's SBOMs, as the checker reads it.

The expected outcome of every rule, per scenario, is in
``tests/fixtures/conformance/cisa2026-expected.tsv``; it changes in the same
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

STANDARD = "cisa2026"
_SCENARIOS = list(SCENARIOS)


def test_table_lists_every_rule_with_its_provision() -> None:
    expected = read_expected(STANDARD)
    assert set(expected) == set(provisions(STANDARD))
    for cells in expected.values():
        assert set(cells.values()) <= set(OUTCOMES)


def test_only_unchecked_rules_are_out_of_scope() -> None:
    spec = get_spec(STANDARD)
    unchecked = {spec.rule_id(r) for r in spec.rules if r.status == "catalogue-only"}
    for scenario in _SCENARIOS:
        out = {
            r
            for r, c in read_expected(STANDARD).items()
            if c[scenario] == "out-of-scope"
        }
        assert out == unchecked, scenario


@pytest.mark.parametrize("scenario", _SCENARIOS)
def test_outcomes_match_the_table(sboms: dict[str, Path], scenario: str) -> None:
    actual = outcomes(sboms[scenario], standard=STANDARD)
    expected = {r: c[scenario] for r, c in read_expected(STANDARD).items()}
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
    assert not regressed, f"CISA 2026 regressions: {regressed}"
    assert not improved, f"CISA 2026 improvements, update the table: {improved}"
    assert actual == expected
