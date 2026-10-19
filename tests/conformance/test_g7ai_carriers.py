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


#: Probe ``kind`` -> the SPDX element types it reads.
_TYPES = {
    "system": {"ai_AIPackage", "software_Package"},
    "ai_model": {"ai_AIPackage"},
    "dataset": {"dataset_DatasetPackage"},
}


def _probes(name: str, field: str) -> dict[str, tuple[str, set[str]]]:
    """Rule id -> (probe kind, names in the probe's *field*) for probe *name*."""
    spec = get_spec("g7ai")
    return {
        spec.rule_id(r): (r.probe.params["kind"], set(r.probe.params[field]))
        for r in spec.rules
        if r.probe is not None and r.probe.name == name
    }


def _properties() -> dict[str, set[str]]:
    return {
        r: names for r, (_, names) in _probes("require_property", "properties").items()
    }


def _values(graph: list[dict[str, object]], key: str) -> list[object]:
    return [e[key] for e in graph if key in e]


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_present_rules_have_a_carrier(sboms: dict[str, Path], scenario: str) -> None:
    """A ``present`` rule needs its property on an element of the kind it
    reads, or its relationship type in the graph."""
    graph = json.loads(sboms[scenario].read_text(encoding="utf-8"))["@graph"]
    present = {r for r, o in outcomes(sboms[scenario]).items() if o == "present"}
    props = _probes("require_property", "properties")
    rels = _probes("require_relationship", "relationships")
    assert present & set(props)  # not vacuous
    types = {r["relationshipType"] for r in graph if "relationshipType" in r}
    bare = {
        rule: sorted(names)
        for rule, (kind, names) in props.items()
        if rule in present
        and not any(names & set(e) for e in graph if e["type"] in _TYPES[kind])
    }
    bare |= {
        rule: sorted(names)
        for rule, (_, names) in rels.items()
        if rule in present and not names & types
    }
    assert not bare, f"present with no carrier in the SBOM: {bare}"


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
