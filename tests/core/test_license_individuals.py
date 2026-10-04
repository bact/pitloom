# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one table of licence individuals (:mod:`pitloom.core.license_individuals`)
agrees with the bindings and with what the serialiser writes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.license_individuals import (
    INDIVIDUAL_BY_COMPACT_NAME,
    INDIVIDUAL_BY_KIND,
    INDIVIDUAL_BY_REFERENCE,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter


def test_every_binding_individual_is_in_the_table() -> None:
    named = spdx3.expandedlicensing_IndividualLicensingInfo.NAMED_INDIVIDUALS
    assert {i.iri for i in INDIVIDUAL_BY_KIND.values()} == set(named.values())


@pytest.mark.parametrize("kind", sorted(INDIVIDUAL_BY_KIND))
def test_the_compact_name_is_what_the_serialiser_writes(kind: str) -> None:
    """A wrong compact name would make every lookup by serialised value miss."""
    individual = INDIVIDUAL_BY_KIND[kind]
    ci = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=["https://x/1#A"],
    )
    exporter = Spdx3JsonExporter()
    exporter.add_package(
        spdx3.software_Package(spdxId="https://x/1#P", name="p", creationInfo=ci)
    )
    exporter.add_relationship(
        spdx3.Relationship(
            spdxId="https://x/1#R",
            from_="https://x/1#P",
            to=[individual.iri],
            relationshipType=spdx3.RelationshipType.hasDeclaredLicense,
            creationInfo=ci,
        )
    )
    graph = json.loads(exporter.to_json())["@graph"]
    (rel,) = [e for e in graph if e["type"] == "Relationship"]
    assert rel["to"] == [individual.compact_name]
    assert INDIVIDUAL_BY_COMPACT_NAME[individual.compact_name] is individual
    assert INDIVIDUAL_BY_REFERENCE[individual.iri] is individual
    assert individual.spdx_name == kind.upper()


@pytest.mark.parametrize(
    "target",
    ["https://x/1#Foo_NoneLicense", "Foo/NoneLicense", "expandedlicensing_none"],
)
def test_a_lookalike_is_no_individual(target: str) -> None:
    assert target not in INDIVIDUAL_BY_REFERENCE
