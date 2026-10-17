# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``present`` rule must rest on a real SPDX property in the SBOM, and no
property a rule reads may hold a placeholder.

Catches a checker that reports ``present`` with no carrier, and a pitloom
that writes ``NOASSERTION`` or an empty value to satisfy a rule.

See also: tests/conformance/test_g7ai_outcomes.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ntia_conformance_checker import get_spec

from tests.conformance.g7ai_shared import SCENARIOS, outcomes

_PLACEHOLDERS = ("", "NOASSERTION", "UNKNOWN", "N/A")


def _properties() -> dict[str, set[str]]:
    """Rule id -> SPDX property keys its probe reads (``require_property``)."""
    spec = get_spec("g7ai")
    return {
        spec.rule_id(r): set(r.probe.params["properties"])
        for r in spec.rules
        if r.probe is not None and r.probe.name == "require_property"
    }


def _values(graph: list[dict[str, object]], key: str) -> list[object]:
    return [e[key] for e in graph if key in e]


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_present_rules_have_a_carrier(sboms: dict[str, Path], scenario: str) -> None:
    graph = json.loads(sboms[scenario].read_text(encoding="utf-8"))["@graph"]
    keys = {k for e in graph for k in e}
    present = {r for r, o in outcomes(sboms[scenario]).items() if o == "present"}
    assert present & set(_properties())  # the check below is not vacuous
    bare = {
        r: sorted(props)
        for r, props in _properties().items()
        if r in present and not props & keys
    }
    assert not bare, f"present with no carrier property in the SBOM: {bare}"


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_no_read_property_holds_a_placeholder(
    sboms: dict[str, Path], scenario: str
) -> None:
    graph = json.loads(sboms[scenario].read_text(encoding="utf-8"))["@graph"]
    read = {p for props in _properties().values() for p in props}
    held = {
        (key, value)
        for key in read
        for value in _values(graph, key)
        if value in _PLACEHOLDERS or value == [] or value == ["NOASSERTION"]
    }
    assert not held, f"placeholder values on read properties: {sorted(map(str, held))}"
