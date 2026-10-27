# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model's originators become ``originatedBy`` generic Agents, and its
supplier (only a hub repository owner) the ``suppliedBy`` Agent, the same on
the project route (:func:`~pitloom.assemble.spdx3.document.build`) and the
single-model route (:func:`~pitloom.assemble.spdx3.document.build_model`).

See also: :mod:`tests.assemble.test_ai_parameter_count` (the count, and the
drift guard between the two routes), :mod:`tests.core.test_model_originators`
(the names a reader keeps).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from pitloom.assemble.spdx3.document import build, build_model
from pitloom.core.ai_metadata import (
    MAX_MODEL_NAME_CHARS,
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    cap_model_name,
)
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.enrich.base import EnrichedField, EnrichmentResult
from tests.warning_helpers import logged_warnings

_FIXED = "2026-01-01T00:00:00Z"
_Graph = list[dict[str, Any]]


def _model(originators: list[str], name: str = "m", **kwargs: Any) -> AiModelMetadata:
    return AiModelMetadata(
        name=name,
        originators=originators,
        format_info=AiModelFormatInfo(
            file_name="m.gguf", model_format=AiModelFormat.GGUF
        ),
        **kwargs,
    )


def _creation(*creators: Creator) -> CreationMetadata:
    return CreationMetadata(creators=list(creators), creation_datetime=_FIXED)


def _project(
    *models: AiModelMetadata,
    creation: CreationMetadata | None = None,
    authors: list[dict[str, str]] | None = None,
) -> _Graph:
    doc = DocumentModel(
        project=ProjectMetadata(name="p", version="1", authors=authors or []),
        creation_metadata=creation or _creation(),
        ai_models=list(models),
    )
    graph: _Graph = json.loads(build(doc, offline=True).to_json())["@graph"]
    return graph


def _single(model: AiModelMetadata, creation: CreationMetadata | None = None) -> _Graph:
    graph: _Graph = json.loads(build_model(model, creation or _creation()).to_json())[
        "@graph"
    ]
    return graph


_SURFACES: dict[str, Callable[..., _Graph]] = {"project": _project, "model": _single}


def _of_type(graph: _Graph, kind: str) -> _Graph:
    return [e for e in graph if e["type"] == kind]


def _originator_names(graph: _Graph, package: dict[str, Any]) -> list[str]:
    names = {e["spdxId"]: e["name"] for e in graph if "name" in e}
    return [names[spdx_id] for spdx_id in package.get("originatedBy", [])]


# originators as read -> Agent names, in order
_CASES: dict[str, tuple[list[str], list[str]]] = {
    "none": ([], []),
    "two": (["Bob", "Alice"], ["Bob", "Alice"]),
    "blank": (["", "  ", " Alice "], ["Alice"]),
    "same-stripped": (["A", " A "], ["A"]),  # one id, listed once
}


@pytest.mark.parametrize("surface", _SURFACES)
@pytest.mark.parametrize("case", _CASES)
def test_each_name_is_one_agent_in_order(surface: str, case: str) -> None:
    originators, expected = _CASES[case]
    graph = _SURFACES[surface](_model(originators))
    (package,) = [e for e in _of_type(graph, "ai_AIPackage") if e["name"] == "m"]
    # The graph is sorted by id, which carries the name; the package keeps the
    # source order.
    assert sorted(e["name"] for e in _of_type(graph, "Agent")) == sorted(expected)
    assert _originator_names(graph, package) == expected
    assert ("originatedBy" in package) == bool(expected)
    assert all("suppliedBy" not in e for e in _of_type(graph, "ai_AIPackage"))


def test_two_models_share_one_agent_and_neither_is_supplied() -> None:
    graph = _project(
        _model(["Org", "Ann"], name="a"),
        _model(["Org"], name="b", base_model="up/base"),
    )
    (agent,) = [e for e in _of_type(graph, "Agent") if e["name"] == "Org"]
    packages = {e["name"]: e for e in _of_type(graph, "ai_AIPackage")}
    assert set(packages) == {"a", "b", "base"}
    assert packages["a"]["originatedBy"][0] == agent["spdxId"]
    assert packages["b"]["originatedBy"] == [agent["spdxId"]]
    assert all("suppliedBy" not in e for e in packages.values())


@pytest.mark.parametrize("surface", _SURFACES)
def test_a_control_in_a_name_is_escaped_with_one_warning(
    surface: str, caplog: pytest.LogCaptureFixture
) -> None:
    graph = _SURFACES[surface](_model(["o\u202ex"]))
    (agent,) = _of_type(graph, "Agent")
    assert agent["name"] == "o\\u202ex"
    assert [m for m in logged_warnings(caplog) if "bidi" in m] == [
        "FORMAT=gguf FILE=m.gguf: invisible or bidi control characters written "
        "as \\uXXXX in model originator name"
    ]


@pytest.mark.parametrize("surface", _SURFACES)
def test_a_long_name_is_cut_with_the_name_cap_warning(
    surface: str, caplog: pytest.LogCaptureFixture
) -> None:
    long_name = "n" * 1100
    graph = _SURFACES[surface](_model([long_name]))
    (agent,) = _of_type(graph, "Agent")
    assert agent["name"] == cap_model_name(long_name)
    assert len(agent["name"]) == MAX_MODEL_NAME_CHARS
    assert logged_warnings(caplog) == [
        "FORMAT=gguf FILE=m.gguf: larger than the 1024-character name cap; "
        "model originator name cut"
    ]


@pytest.mark.parametrize("surface", _SURFACES)
@pytest.mark.parametrize(
    "originators",
    [["a" * 1100, "b" * 1100, "c" * 1100], ["short", "d" * 1100, "e" * 1100, "f"]],
    ids=["all-cut", "mixed"],
)
def test_many_long_names_are_cut_with_one_warning_and_stay_distinct(
    surface: str, originators: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    graph = _SURFACES[surface](_model(originators))
    names = sorted(e["name"] for e in _of_type(graph, "Agent"))
    assert names == sorted(cap_model_name(n) for n in originators)
    assert len(set(names)) == len(originators)  # the digest keeps them apart
    assert logged_warnings(caplog) == [
        "FORMAT=gguf FILE=m.gguf: larger than the 1024-character name cap; "
        "model originator name cut"
    ]


@pytest.mark.parametrize("surface", _SURFACES)
def test_an_entry_that_is_not_text_is_skipped(surface: str) -> None:
    graph = _SURFACES[surface](_model([None, 5, "Alice"]))  # type: ignore[list-item]
    (agent,) = _of_type(graph, "Agent")
    assert agent["name"] == "Alice"


@pytest.mark.parametrize("surface", _SURFACES)
def test_a_generic_agent_creator_keeps_the_first_agent_id(surface: str) -> None:
    creation = _creation(Creator(name="Bot", type="agent"))
    graph = _SURFACES[surface](_model(["Bot"]), creation=creation)
    # Not deduplicated with the creator of the same name (pinned).
    creator, model_agent = sorted(_of_type(graph, "Agent"), key=lambda e: e["spdxId"])
    assert creator["name"] == model_agent["name"] == "Bot"
    assert creator["spdxId"].endswith("#Agent-1")
    assert model_agent["spdxId"].endswith("#Agent-Bot-1")  # the id carries the name
    (package,) = [e for e in _of_type(graph, "ai_AIPackage") if e["name"] == "m"]
    assert package["originatedBy"] == [model_agent["spdxId"]]


def test_a_main_author_and_a_model_originator_of_one_name_are_two_agents() -> None:
    graph = _project(_model(["Alice"]), authors=[{"name": "Alice"}])
    (person,) = _of_type(graph, "Person")
    (agent,) = _of_type(graph, "Agent")
    assert person["name"] == agent["name"] == "Alice"
    (main,) = [e for e in _of_type(graph, "software_Package") if e["name"] == "p"]
    (model,) = [e for e in _of_type(graph, "ai_AIPackage") if e["name"] == "m"]
    assert main["originatedBy"] == [person["spdxId"]]
    assert model["originatedBy"] == [agent["spdxId"]]


def _dataset(creator: str, name: str = "d") -> DatasetReference:
    return DatasetReference(
        role="trainedOn", metadata=DatasetMetadata(name=name, creator=creator)
    )


@pytest.mark.parametrize("surface", sorted(_SURFACES))
@pytest.mark.parametrize(
    ("originators", "creators", "agents"),
    [
        pytest.param(["Alice"], ["Alice"], ["Alice"], id="originator-is-creator"),
        pytest.param([], ["Alice", "Alice"], ["Alice"], id="two-datasets-one-creator"),
        pytest.param(["Alice"], ["Bob"], ["Alice", "Bob"], id="different-names"),
        pytest.param(["Alice"], ["alice"], ["Alice", "alice"], id="case-differs"),
        pytest.param(["Alice"], [" Alice "], ["Alice"], id="stripped-name"),
    ],
)
def test_one_name_is_one_agent_whoever_it_is_for(
    surface: str, originators: list[str], creators: list[str], agents: list[str]
) -> None:
    """A model's originator and a dataset's creator of one name are one
    generic Agent, linked by ``originatedBy`` and by ``publishedBy``."""
    model = _model(
        originators,
        datasets=[_dataset(c, f"d{i}") for i, c in enumerate(creators)],
    )
    graph = _SURFACES[surface](model)
    assert sorted(e["name"] for e in _of_type(graph, "Agent")) == sorted(agents)
    by_name = {e["name"]: e["spdxId"] for e in _of_type(graph, "Agent")}
    published = [
        e["to"][0]
        for e in _of_type(graph, "Relationship")
        if e["relationshipType"] == "publishedBy"
    ]
    assert sorted(published) == sorted(by_name[c.strip()] for c in creators)
    if originators:
        (package,) = _of_type(graph, "ai_AIPackage")
        assert package["originatedBy"] == [by_name[originators[0]]]


def test_an_agents_id_does_not_depend_on_the_models_around_it() -> None:
    """Another model's dataset creator, built before this model's originators,
    must not take over an id: each Agent's id carries its name, so one IRI
    names one person in every version of the SBOM."""

    def ids(creator: str | None) -> dict[str, str]:
        first = _model(
            [],
            name="a",
            datasets=[_dataset(creator)] if creator else [],
        )
        graph = _project(first, _model(["Alice", "Bob"], name="b"))
        return {e["name"]: e["spdxId"] for e in _of_type(graph, "Agent")}

    without, with_creator = ids(None), ids("Alice")
    assert without.keys() == with_creator.keys() == {"Alice", "Bob"}  # one Alice
    assert without == with_creator
    assert len(set(without.values())) == 2


@pytest.mark.parametrize("surface", sorted(_SURFACES))
@pytest.mark.parametrize(
    ("creator", "agents"),
    [("   ", []), ("\t", []), (" Alice ", ["Alice"])],
    ids=["spaces", "tab", "padded"],
)
@pytest.mark.parametrize("with_originator", [False, True], ids=["alone", "named"])
def test_a_dataset_creator_is_stripped_and_a_blank_one_names_no_one(
    surface: str, creator: str, agents: list[str], with_originator: bool
) -> None:
    """The same rule as for an originator: blank names are skipped, the rest
    stripped, so " Alice " and "Alice" are one Agent."""
    named = with_originator and bool(agents)  # an originator "Alice" hides a miss
    model = _model(["Alice"] if named else [], datasets=[_dataset(creator)])
    graph = _SURFACES[surface](model)
    assert [e["name"] for e in _of_type(graph, "Agent")] == agents
    ids = {e["spdxId"] for e in _of_type(graph, "Agent")}
    assert all("%20" not in i for i in ids)  # " Alice " would be Agent-%20Alice%20-1
    published = [
        e
        for e in _of_type(graph, "Relationship")
        if e["relationshipType"] == "publishedBy"
    ]
    assert len(published) == len(agents)


def test_adding_an_originator_adds_one_agent_and_shifts_no_other_id() -> None:
    """Every element a model, its dataset, base model and licence, the
    creators and the main authors mint keeps its id."""

    def ids(originators: list[str]) -> tuple[AiModelMetadata, set[str]]:
        model = _model(
            originators,
            base_model="up/base",
            license="MIT",
            datasets=[
                DatasetReference(
                    role="trainedOn", metadata=DatasetMetadata(name="d", creator="Ann")
                )
            ],
        )
        creation = _creation(Creator(name="Bot", type="agent"))
        graph = _project(model, creation=creation, authors=[{"name": "Ann"}])
        return model, {e["spdxId"] for e in graph if "spdxId" in e}

    before_model, before = ids([])
    after_model, after = ids(["X"])
    assert before_model.originators != after_model.originators  # input changed
    assert before < after
    (added,) = after - before
    assert added.endswith("#Agent-X-1")  # named, so no other Agent's id moved


def _supplier_name(graph: _Graph, package: dict[str, Any]) -> str | None:
    names = {e["spdxId"]: e["name"] for e in graph if "name" in e}
    return names[package["suppliedBy"]] if "suppliedBy" in package else None


# (originators, supplier) -> (Agent names in order, originatedBy names,
# suppliedBy name)
_SUPPLIER_CASES: dict[str, tuple[tuple[list[str], Any], tuple[Any, ...]]] = {
    "only": (([], "Hub"), (["Hub"], [], "Hub")),
    "same": ((["Hub"], "Hub"), (["Hub"], ["Hub"], "Hub")),
    "same-stripped": ((["Hub"], " Hub "), (["Hub"], ["Hub"], "Hub")),
    "other": ((["Maker"], "Hub"), (["Maker", "Hub"], ["Maker"], "Hub")),
    "second": ((["A", "Hub"], "Hub"), (["A", "Hub"], ["A", "Hub"], "Hub")),
    "blank": ((["A"], " \t"), (["A"], ["A"], None)),
    "not-text": ((["A"], 5), (["A"], ["A"], None)),
    "absent": ((["A"], None), (["A"], ["A"], None)),
}


@pytest.mark.parametrize("surface", _SURFACES)
@pytest.mark.parametrize("case", _SUPPLIER_CASES)
def test_the_supplier_is_one_agent_shared_with_an_originator(
    surface: str, case: str, caplog: pytest.LogCaptureFixture
) -> None:
    (originators, supplier), expected = _SUPPLIER_CASES[case]
    graph = _SURFACES[surface](_model(originators, supplier=supplier))
    (package,) = [e for e in _of_type(graph, "ai_AIPackage") if e["name"] == "m"]
    agents = sorted(e["name"] for e in _of_type(graph, "Agent"))
    assert (agents, _originator_names(graph, package)) == (
        sorted(expected[0]),
        expected[1],
    )
    assert _supplier_name(graph, package) == expected[2]
    assert ("originatedBy" in package) == bool(expected[1])
    assert not logged_warnings(caplog)


_CUT = "FORMAT=gguf FILE=m.gguf: larger than the 1024-character name cap; "


@pytest.mark.parametrize("surface", _SURFACES)
@pytest.mark.parametrize(
    ("originators", "supplier", "cut"),
    [
        ([], "s" * 1100, "model supplier name"),
        (["s" * 1100], "s" * 1100, "model originator name"),  # one Agent
        (["o" * 1100], "s" * 1100, "model originator name, model supplier name"),
        (["o" * 1100], "Hub", "model originator name"),
        (["Hub"], "s" * 1100, "model supplier name"),
    ],
    ids=["supplier", "same", "both", "originator", "other"],
)
def test_cut_originator_and_supplier_names_give_one_warning(
    surface: str,
    originators: list[str],
    supplier: str,
    cut: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = _SURFACES[surface](_model(originators, supplier=supplier))
    (package,) = [e for e in _of_type(graph, "ai_AIPackage") if e["name"] == "m"]
    assert _supplier_name(graph, package) == cap_model_name(supplier)
    assert len(_of_type(graph, "Agent")) == len({*originators, supplier})
    assert logged_warnings(caplog) == [f"{_CUT}{cut} cut"]


@pytest.mark.parametrize("surface", _SURFACES)
@pytest.mark.parametrize(
    ("originators", "supplier", "shown", "label"),
    [
        ([], "s\u202ex", "s\\u202ex", "model supplier name"),
        (["s\u202ex"], "s\u202ex", "s\\u202ex", "model originator name"),
        (
            ["o\u202ex"],
            "s\x00x",
            "s\\u0000x",
            "model originator name, model supplier name",
        ),
    ],
    ids=["supplier", "same", "both"],
)
def test_controls_in_a_supplier_name_are_escaped_with_one_warning(
    surface: str,
    originators: list[str],
    supplier: str,
    shown: str,
    label: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = _SURFACES[surface](_model(originators, supplier=supplier))
    (package,) = [e for e in _of_type(graph, "ai_AIPackage") if e["name"] == "m"]
    assert _supplier_name(graph, package) == shown
    assert [m for m in logged_warnings(caplog) if "bidi" in m] == [
        "FORMAT=gguf FILE=m.gguf: invisible or bidi control characters written "
        f"as \\uXXXX in {label}"
    ]


@pytest.mark.parametrize(
    ("supplier", "added"), [("Ann", 0), ("Hub", 1)], ids=["originator", "other"]
)
def test_a_supplier_adds_at_most_one_agent_and_shifts_no_other_id(
    supplier: str, added: int
) -> None:
    def graph(supplier: str | None) -> _Graph:
        model = _model(["Ann"], supplier=supplier, base_model="up/base")
        creation = _creation(Creator(name="Bot", type="agent"))
        return _project(model, creation=creation, authors=[{"name": "Ann"}])

    before = {e["spdxId"] for e in graph(None) if "spdxId" in e}
    after_graph = graph(supplier)
    after = {e["spdxId"] for e in after_graph if "spdxId" in e}
    (package,) = [e for e in after_graph if e.get("name") == "m"]
    assert "suppliedBy" in package  # not vacuous: the input changed
    assert before <= after
    assert len(after - before) == added
    assert all(i.endswith(f"#Agent-{supplier}-1") for i in after - before)
    # Deterministic: the same input gives the same bytes.
    assert json.dumps(after_graph) == json.dumps(graph(supplier))


@pytest.mark.parametrize("order", ["ab", "ba"])
def test_a_shared_agent_has_the_documents_creation_info_whoever_builds_it_first(
    order: str,
) -> None:
    """An enrichment run adds model ``a``'s dataset with its own creation info;
    its creator "Alice" is also model ``b``'s originator. The Agent is one
    element with the document's creation info in either order, not the
    enrichment run's when ``a`` happens to come first."""
    models = {
        "a": _model(
            [],
            name="a",
            datasets=[
                DatasetReference(
                    role="trainedOn",
                    metadata=DatasetMetadata(name="ds", creator="Alice"),
                )
            ],
        ),
        "b": _model(["Alice"], name="b"),
    }
    enrichment = {
        "a": [
            EnrichmentResult(
                source_name="readme",
                fields=[
                    EnrichedField(
                        field="datasets:ds",
                        before=None,
                        after="ds",
                        role="detected",
                        source="Source: README.md",
                    )
                ],
            )
        ],
        "b": [],
    }
    doc = DocumentModel(
        project=ProjectMetadata(name="p", version="1"),
        creation_metadata=_creation(),
        ai_models=[models[k] for k in order],
    )
    graph: _Graph = json.loads(
        build(
            doc,
            offline=True,
            enrichment_results_by_model=[enrichment[k] for k in order],
        ).to_json()
    )["@graph"]
    (agent,) = [e for e in graph if e["type"] == "Agent" and e["name"] == "Alice"]
    (document,) = [e for e in graph if e["type"] == "SpdxDocument"]
    (dataset,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert dataset["creationInfo"] != document["creationInfo"]  # input changed
    assert agent["creationInfo"] == document["creationInfo"]
