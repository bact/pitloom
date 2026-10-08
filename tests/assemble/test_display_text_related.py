# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Invisible and bidi controls in the elements a model brings in (a Hugging
Face base model, datasets, references) are escaped like the model's own
package, with the same one ``WARNING:`` per model.

See also: :mod:`tests.assemble.test_display_text_escape` (the model's own
package), :mod:`tests.core.test_untrusted_text` (the escape itself).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import enrich_model, generate_model_sbom
from pitloom.assemble.spdx3 import _display_text
from pitloom.assemble.spdx3._display_text import escape_element_display_text
from pitloom.assemble.spdx3.ai import add_ai_models
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.untrusted_text import (
    escape_display_controls_in_iri,
    escape_display_controls_in_json,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests.extract.remote.hf_patches._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)
from tests.warning_helpers import logged_warnings

from .conftest import _DOC_NAME, _DOC_UUID, _make_ci

_RLO = "\u202e"
_ENCODED = "%E2%80%AE"
_SAFETENSORS = (
    Path(__file__).parents[1]
    / "fixtures"
    / "aimodels"
    / "safetensors"
    / "phi-tiny-random.safetensors"
)


def _escape_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [m for m in logged_warnings(caplog) if "bidi control" in m]


def _by_type(graph: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [e for e in graph if e["type"] == kind]


def _hub_sbom(card: dict[str, Any], tags: list[str]) -> str:
    hub_info = {"author": "o", "sha": "1", "tags": tags}
    with _patch_hf_calls(card_data=_make_card_data(**card), hub_info=hub_info):
        return generate_model_sbom("o/model")


# card fields, Hub tags, the properties the warning names ("": no warning)
_HUB_CASES: dict[str, tuple[dict[str, Any], list[str], str]] = {
    "base-model": (
        {"base_model": f"o/b{_RLO}x"},
        [],
        "base model externalRef, base model name",
    ),
    "dataset": (
        {"datasets": [f"o/d{_RLO}s"]},
        [],
        "dataset name, dataset software_downloadLocation",
    ),
    # the second reference only: every entry is escaped, not the first
    "arxiv": ({}, ["arxiv:1", f"arxiv:2401.1{_RLO}"], "externalRef"),
    "none": ({"base_model": "o/b", "datasets": ["o/d"]}, ["arxiv:1"], ""),
}


@pytest.mark.parametrize("case", _HUB_CASES)
def test_a_hub_control_is_escaped_with_one_warning(
    case: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    card, tags, labels = _HUB_CASES[case]
    sbom = _hub_sbom(card, tags)
    graph = json.loads(sbom)["@graph"]
    messages = _escape_warnings(caplog)
    if not labels:
        assert not messages  # no control: quiet
    else:
        assert messages == [
            "FORMAT=huggingface FILE=https://huggingface.co/o/model: invisible or "
            f"bidi control characters written as \\uXXXX in {labels}"
        ]
    # Only the artifact-metadata annotation keeps the card as read.
    for element in graph:
        if "artifact-metadata" not in element.get("statement", ""):
            assert _RLO not in json.dumps(element, ensure_ascii=False)
    # Every reference still resolves: ids are minted from the text as read.
    ids = {e["spdxId"] for e in graph if "spdxId" in e}
    for rel in _by_type(graph, "Relationship"):
        assert {rel["from"], *rel["to"]} <= ids
    caplog.clear()
    assert _hub_sbom(card, tags) == sbom  # deterministic


def test_each_hub_family_is_escaped_where_it_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    card = {"base_model": f"o/b{_RLO}x", "datasets": [f"o/d{_RLO}s"]}
    graph = json.loads(_hub_sbom(card, [f"arxiv:2401.1{_RLO}"]))["@graph"]
    base, model = sorted(_by_type(graph, "ai_AIPackage"), key=lambda e: e["name"])
    assert base["name"] == "b\\u202ex"
    assert base["externalRef"][0]["locator"] == [
        f"https://huggingface.co/o/b{_ENCODED}x"
    ]
    assert _ENCODED in base["spdxId"]  # the IRI form, as before the escape
    (lineage,) = [
        r for r in _by_type(graph, "Relationship") if r["to"] == [base["spdxId"]]
    ]
    assert lineage["from"] == model["spdxId"]
    (dataset,) = _by_type(graph, "dataset_DatasetPackage")
    assert dataset["name"] == "o/d\\u202es"
    assert dataset["software_downloadLocation"] == (
        f"https://huggingface.co/datasets/o/d{_ENCODED}s"
    )
    arxiv = next(r for r in model["externalRef"] if r["comment"].startswith("arXiv"))
    assert arxiv["comment"] == "arXiv:2401.1\\u202e"
    assert arxiv["locator"] == [f"https://arxiv.org/abs/2401.1{_ENCODED}"]


def test_a_base_model_named_by_an_escaped_package_reuses_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Project surface: the first model's package, already escaped, is still
    found as the second one's base; each model warns once, for its own."""
    exporter = Spdx3JsonExporter()
    dataset = DatasetMetadata(name=f"d{_RLO}", creator=f"e{_RLO}")
    models = [
        AiModelMetadata(name=f"a{_RLO}b"),
        AiModelMetadata(
            name="c",
            base_model=f"a{_RLO}b",
            base_model_relation=f"f{_RLO}",
            datasets=[DatasetReference(role=f"g{_RLO}", metadata=dataset)],
        ),
    ]
    add_ai_models(models, "urn:main", {}, _make_ci(), _DOC_NAME, _DOC_UUID, exporter)
    objects = exporter.object_set.objects
    packages = [o for o in objects if isinstance(o, spdx3.ai_AIPackage)]
    assert sorted(str(p.name) for p in packages) == ["a\\u202eb", "c"]
    messages = _escape_warnings(caplog)
    assert [m.rsplit(" in ", 1)[1] for m in messages] == [
        "name",
        "base model relationship comment, dataset creator name, dataset name, "
        "dataset relationship comment",
    ]
    for obj in objects:
        assert _RLO not in json.dumps(
            [getattr(obj, p, None) for p in ("name", "comment")], ensure_ascii=False
        )


def test_an_enrichment_dataset_is_escaped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(_SAFETENSORS.read_bytes())
    (tmp_path / "README.md").write_text(
        f"---\ndatasets:\n  - tiny{_RLO}net\n---\n", encoding="utf-8"
    )
    graph = json.loads(enrich_model(model_path))["@graph"]
    (dataset,) = _by_type(graph, "dataset_DatasetPackage")
    assert dataset["name"] == "tiny\\u202enet"
    (message,) = _escape_warnings(caplog)
    assert message.endswith(" in dataset name")


_CLASSES = (
    spdx3.ai_AIPackage,
    spdx3.dataset_DatasetPackage,
    spdx3.simplelicensing_SimpleLicensingText,
    spdx3.simplelicensing_LicenseExpression,
)


def _holder(prop: str) -> Any:
    """A hand-built element of the first class that has *prop*."""
    for cls in _CLASSES:
        element = cls(spdxId="urn:x")
        if hasattr(element, prop):
            return element
    raise AssertionError(prop)


def _raw_and_shown(escape: Any) -> tuple[str, str]:
    if escape is escape_display_controls_in_iri:
        return f"https://h/{_RLO}", f"https://h/{_ENCODED}"
    if escape is escape_display_controls_in_json:
        return json.dumps({"k": f"v{_RLO}"}), '{"k":"v\\\\u202e"}'
    return f"a{_RLO}", "a\\u202e"


@pytest.mark.parametrize(
    ("prop", "escape", "is_list"),
    _display_text._FIELDS,
    ids=[prop for prop, _, _ in _display_text._FIELDS],
)
def test_each_display_property_is_escaped(
    prop: str, escape: Any, is_list: bool
) -> None:
    element = _holder(prop)
    raw, shown = _raw_and_shown(escape)
    setattr(element, prop, [raw] if is_list else raw)
    assert escape_element_display_text(element) == [prop]
    assert getattr(element, prop) == ([shown] if is_list else shown)
    assert escape_element_display_text(element) == []  # once


_ENTRY_CLASSES = {
    "ai_hyperparameter": spdx3.DictionaryEntry,
    "externalRef": spdx3.ExternalRef,
    "externalIdentifier": spdx3.ExternalIdentifier,
}


_ENTRY_CASES = [
    (prop, *field)
    for prop, fields in _display_text._ENTRY_FIELDS.items()
    for field in fields
]


@pytest.mark.parametrize(
    ("prop", "entry_prop", "escape", "is_list"),
    _ENTRY_CASES,
    ids=[f"{case[0]}.{case[1]}" for case in _ENTRY_CASES],
)
def test_each_entry_property_is_escaped(
    prop: str, entry_prop: str, escape: Any, is_list: bool
) -> None:
    element = spdx3.ai_AIPackage(spdxId="urn:x")
    entry = _ENTRY_CLASSES[prop]()
    raw, shown = _raw_and_shown(escape)
    setattr(entry, entry_prop, [raw] if is_list else raw)
    getattr(element, prop).append(entry)
    assert escape_element_display_text(element) == [prop]
    assert getattr(entry, entry_prop) == ([shown] if is_list else shown)
