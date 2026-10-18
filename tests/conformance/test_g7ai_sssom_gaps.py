# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""G7 elements the checker does not check (``catalogue-only``) although
Pitloom already writes a profile property that the SSSOM mapping assigns to
them.

The set is pinned both ways: a new Pitloom property, or a checker that starts
checking a rule, changes it and forces a deliberate edit here (and in
``g7-ai-sbom-coverage.md``). Property level only, on an element of the subject's
kind: a property written is not a value that satisfies the element.

See also: tests/conformance/test_g7ai_outcomes.py,
tests/fixtures/conformance/README.md (the mapping snapshot).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import csv
import hashlib
import json

from ntia_conformance_checker import get_spec

from tests.conformance.g7ai_shared import MAPPING, SCENARIOS

# sha256 of the snapshot; refresh with the file when the mapping changes.
MAPPING_SHA256 = "d4dab53ba3e62568b64333d588d394ae2bafc374dc00921d3d3b7f6207a9547e"
_PROFILES = ("ai_", "dataset_", "software_")

#: Unchecked element -> mapped profile properties Pitloom writes today.
EMITTED_BUT_UNCHECKED = {
    "model-architecture": ["typeOfModel"],
    "model-context-length": ["hyperparameter"],
    "model-input-modality": ["informationAboutApplication", "typeOfModel"],
    "model-output-modality": ["informationAboutApplication", "typeOfModel"],
    "model-parameter-count": ["hyperparameter"],
    "system-data-flow": ["informationAboutApplication"],
    "system-input-modality": ["informationAboutApplication", "typeOfModel"],
    "system-output-modality": ["informationAboutApplication", "typeOfModel"],
}


#: Subject prefix -> the element types the element is, in the SBOM.
_ELEMENT_TYPES = {
    "dataset": {"dataset_DatasetPackage"},
    "model": {"ai_AIPackage"},
    "system": {"ai_AIPackage", "software_Package"},
}


def _emitted_properties() -> set[tuple[str, str]]:
    """(element type, property) pairs Pitloom writes, profile properties only."""
    pairs = set()
    for build in SCENARIOS.values():
        for element in json.loads(build())["@graph"]:
            pairs |= {
                (element["type"], key.split("_", 1)[1])
                for key in element
                if key.startswith(_PROFILES)
            }
    return pairs


def _mapped() -> dict[str, set[str]]:
    with MAPPING.open(encoding="utf-8") as f:
        lines = (line for line in f if not line.startswith("#"))
        rows = list(csv.DictReader(lines, delimiter="\t"))
    mapped: dict[str, set[str]] = {}
    for row in rows:
        subject = row["subject_id"].split(":", 1)[1]
        name = row["object_id"].split(":", 1)[1].split("/")[-1]
        mapped.setdefault(subject, set()).add(name)
    return mapped


def test_mapping_snapshot_is_unchanged() -> None:
    assert hashlib.sha256(MAPPING.read_bytes()).hexdigest() == MAPPING_SHA256


def test_emitted_but_unchecked_is_pinned() -> None:
    spec = get_spec("g7ai")
    unchecked = {r.slug[5:-8] for r in spec.rules if r.status == "catalogue-only"}
    emitted = _emitted_properties()

    def written(subject: str) -> set[str]:
        """The mapped properties written on an element of the subject's kind."""
        types = _ELEMENT_TYPES.get(subject.split("-", 1)[0], set())
        return {name for kind, name in emitted if kind in types}

    actual = {
        subject: sorted(names & written(subject))
        for subject, names in _mapped().items()
        if subject in unchecked and names & written(subject)
    }
    assert actual == EMITTED_BUT_UNCHECKED
