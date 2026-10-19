# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Edited SBOMs must lose the G7 outcome that the edit removes.

Guards both ways: the checker must notice a missing element, and the
generated SBOM must really carry what makes a rule ``present``.

See also: tests/conformance/test_g7ai_outcomes.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.conformance.g7ai_shared import (
    BACKENDS,
    SCENARIOS,
    check,
    outcomes,
    project_sbom,
)

P = "BOM-G7AI2026-"
Graph = list[dict[str, Any]]


def _package(graph: Graph) -> dict[str, Any]:
    return next(e for e in graph if e["type"] == "ai_AIPackage")


def _drop(*keys: str) -> Callable[[Graph], None]:
    def edit(graph: Graph) -> None:
        for key in keys:
            _package(graph).pop(key)

    return edit


def _set(key: str, value: object) -> Callable[[Graph], None]:
    def edit(graph: Graph) -> None:
        _package(graph)[key] = value

    return edit


def _without(**match: str) -> Callable[[Graph], None]:
    def edit(graph: Graph) -> None:
        graph[:] = [e for e in graph if any(e.get(k) != v for k, v in match.items())]

    return edit


def _drop_dataset_licence(graph: Graph) -> None:
    dataset = next(e for e in graph if e["type"] == "dataset_DatasetPackage")
    graph[:] = [
        e
        for e in graph
        if not (
            e.get("relationshipType") == "hasDeclaredLicense"
            and e["from"] == dataset["spdxId"]
        )
    ]


def _unroot(graph: Graph) -> None:
    for element in graph:
        if element["type"] in ("SpdxDocument", "software_Sbom"):
            element["rootElement"] = []


_CASES = [
    ("onnx", _drop("verifiedUsing"), {"MDL-007": "missing", "MDL-008": "missing"}),
    ("hub", _drop("originatedBy"), {"MDL-005": "missing"}),
    ("hub", _set("originatedBy", []), {"MDL-005": "missing"}),
    ("hub", _set("name", ""), {"MDL-001": "missing"}),
    ("hub", _set("name", "  "), {"MDL-001": "missing"}),
    # An unlinked dataset is not the model's: its rules fail, not skip.
    ("hub", _without(relationshipType="trainedOn"), {"DP-001": "missing"}),
    (
        "hub",
        _without(relationshipType="hasDeclaredLicense"),
        {"MDL-012": "missing"},
    ),
    # The model's licence is not the dataset's.
    ("library", _drop_dataset_licence, {"DP-010": "missing", "MDL-012": "present"}),
]
_IDS = ["no-hash", "no-producer", "empty-producer", "empty-name", "blank-name",
        "dataset-unlinked", "no-licence", "no-dataset-licence"]  # fmt: skip


@pytest.mark.parametrize(("scenario", "edit", "expected"), _CASES, ids=_IDS)
def test_edit_changes_the_outcome(
    tmp_path: Path,
    scenario: str,
    edit: Callable[[Graph], None],
    expected: dict[str, str],
) -> None:
    document = json.loads(SCENARIOS[scenario]())
    before = json.dumps(document, sort_keys=True)
    edit(document["@graph"])
    assert json.dumps(document, sort_keys=True) != before  # the edit did something
    path = tmp_path / "edited.spdx3.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    actual = outcomes(path)
    assert {P + r: actual[P + r] for r in expected} == {
        P + r: o for r, o in expected.items()
    }


def test_unrooted_sbom_has_no_system(tmp_path: Path) -> None:
    document = json.loads(SCENARIOS["hub"]())
    _unroot(document["@graph"])
    path = tmp_path / "unrooted.spdx3.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AssertionError, match="nothing to evaluate"):
        check(path)
    actual = outcomes(path, evaluated=False)
    assert (actual[P + "MDL-001"], actual[P + "SLP-001"]) == ("missing", "missing")


def test_unreadable_sbom_fails_instead_of_reporting_all_missing(tmp_path: Path) -> None:
    path = tmp_path / "truncated.spdx3.json"
    path.write_text(SCENARIOS["hub"]()[:200], encoding="utf-8")
    with pytest.raises(AssertionError, match="could not read"):
        check(path)


def test_a_model_setuptools_does_not_ship_is_not_claimed() -> None:
    """Without ``package-data`` setuptools leaves the model out of the
    distribution, so the SBOM does not describe it."""
    pyproject = BACKENDS["setuptools"].replace(
        '[tool.setuptools.package-data]\ndemo = ["*.safetensors"]\n', ""
    )
    assert pyproject != BACKENDS["setuptools"]
    graph = json.loads(project_sbom(pyproject))["@graph"]
    assert not [e for e in graph if e["type"] == "ai_AIPackage"]
