# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A fragment licence equal to one already merged unifies with it: equal is
the ``(kind, value)`` key a build dedupes by, so ``mit`` and ``MIT`` are one
expression, and an expression and a text of one string stay two. The base
document wins, then the earlier fragment, then the lower id in a fragment.

See also: tests/assemble/test_fragments_surfaces.py (the same on every
surface) and tests/assemble/test_license_elements_classifier.py (how a build
makes these elements).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_licenses import LICENSE_TYPES
from pitloom.assemble.spdx3._license_elements import (
    TEXT_REF_PREFIX,
    license_key,
    text_ref,
)
from pitloom.assemble.spdx3.deps_license import _apply_license
from pitloom.assemble.spdx3.document import build
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.extract.license_refs import classifier_expression
from tests._license_graph import (
    _new_document,
    fragment_graph,
    graph_of,
    license_elements,
    license_node,
    license_targets,
    license_values,
    licensed_package,
    text_wrapper_node,
    write_fragment,
)

_NS = "https://spdx.org/spdxdocs/frag"
_NS2 = "https://spdx.org/spdxdocs/frag2"


def _merge(
    tmp: Path, base_license: str | None, *documents: dict[str, Any]
) -> list[dict[str, Any]]:
    """The graph of project ``demo`` licensed *base_license* merged with
    *documents*, in order."""
    exporter = build(
        DocumentModel(
            project=ProjectMetadata(
                name="demo", version="1.0", license_name=base_license
            ),
            creation_metadata=CreationMetadata(
                creation_datetime="2026-01-01T00:00:00Z"
            ),
        )
    )
    configs = []
    for i, document in enumerate(documents):
        write_fragment(tmp / f"f{i}.spdx3.json", document)
        configs.append(FragmentConfig(path=f"f{i}.spdx3.json"))
    merge_fragments(tmp, configs, exporter)
    return graph_of(exporter)


def _fragment(*licences: tuple[str, str, str], ns: str = _NS) -> dict[str, Any]:
    """A fragment with one package per ``(id, kind, value)`` licence."""
    elements: list[dict[str, Any]] = []
    for name, kind, value in licences:
        target = f"{ns}#{name}"
        elements.append(license_node(target, kind, value))
        if kind == "text":
            target = f"{ns}#{name}-ref"
            elements.append(text_wrapper_node(target, f"{ns}#{name}", value))
        elements.extend(licensed_package(f"P{name}", target, ns))
    return fragment_graph(elements, ns)


def _unifications(graph: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Survivor id -> dropped ids, from the ``license`` unification
    Annotations."""
    out: dict[str, list[str]] = {}
    for e in graph:
        if e["type"] == "Annotation":
            statement = json.loads(e["statement"])
            if statement.get("criterion") == "license":
                out[e["subject"]] = statement["unified"]
    return out


@pytest.mark.parametrize("value", ["MIT", "mit"])
def test_fragment_licence_unifies_with_the_base(tmp_path: Path, value: str) -> None:
    """The base's element is kept as it was: the fragment's ``name`` and
    ``comment`` are not folded into an element others share."""
    document = _fragment(("L", "expression", value))
    document["@graph"][2].update(name="Overrides: x", comment="from README")
    graph = _merge(tmp_path, "MIT", document)
    values = license_values(graph)
    assert list(values.values()) == ["MIT"]
    (kept,) = values
    assert not kept.startswith(_NS)  # the base's element, not the fragment's
    (element,) = [e for e in graph if e.get("spdxId") == kept]
    assert element["name"] == "MIT"
    assert "comment" not in element
    assert license_targets(graph) == ["MIT", "MIT"]
    assert _unifications(graph) == {kept: [f"{_NS}#L"]}


def test_a_built_text_unifies_with_the_fragments_wrapper_and_text(
    tmp_path: Path,
) -> None:
    """Base and fragment each hold a text and the wrapper a build gives it
    (the same ``LicenseRef-``): one text, one wrapper, both unified."""
    graph = _merge(tmp_path, "Acme terms", _fragment(("L", "text", "Acme terms")))
    assert list(license_values(graph).values()) == ["Acme terms"]
    wrappers = [
        e
        for e in graph
        if e["type"] == "simplelicensing_LicenseExpression"
        and e["simplelicensing_licenseExpression"].startswith(TEXT_REF_PREFIX)
    ]
    assert len(wrappers) == 1
    (entry,) = wrappers[0]["simplelicensing_customIdToUri"]
    assert entry["value"] in license_values(graph)
    assert license_targets(graph) == ["Acme terms", "Acme terms"]
    assert sorted(f for dropped in _unifications(graph).values() for f in dropped) == [
        f"{_NS}#L",
        f"{_NS}#L-ref",
    ]


def test_a_users_text_ref_expression_is_not_the_fragments_wrapper(
    tmp_path: Path,
) -> None:
    """The base declares ``LicenseRef-loom-text-<hash>`` as an expression of
    its own (no text behind it); the fragment's wrapper of that string stays
    a second element, so its package keeps the text."""
    ref = text_ref("Foo Terms")
    graph = _merge(tmp_path, ref, _fragment(("L", "text", "Foo Terms")))
    assert sorted(license_targets(graph)) == sorted([ref, "Foo Terms"])
    assert not _unifications(graph)


def test_expression_and_text_of_one_string_stay_apart(tmp_path: Path) -> None:
    graph = _merge(tmp_path, "MIT", _fragment(("L", "text", "MIT")))
    assert list(license_values(graph).values()) == ["MIT", "MIT"]
    assert not _unifications(graph)


@pytest.mark.parametrize("split", [False, True], ids=["one-fragment", "two"])
def test_equal_fragment_licences_unify(tmp_path: Path, split: bool) -> None:
    """Within a fragment the lower id is kept; across two, the earlier."""
    first, second = ("L1", "expression", "MIT"), ("L2", "expression", "mit")
    documents = (
        [_fragment(first), _fragment(second, ns=_NS2)]
        if split
        else [_fragment(first, second)]
    )
    graph = _merge(tmp_path, None, *documents)
    assert license_values(graph) == {f"{_NS}#L1": "MIT"}
    assert license_targets(graph) == ["MIT", "MIT"]
    dropped = f"{_NS2 if split else _NS}#L2"
    assert _unifications(graph) == {f"{_NS}#L1": [dropped]}


def test_provenance_annotation_follows_the_kept_licence(tmp_path: Path) -> None:
    document = _fragment(("L", "expression", "mit"))
    document["@graph"].append(
        {
            "type": "Annotation",
            "spdxId": f"{_NS}#Note",
            "creationInfo": "_:ci",
            "annotationType": "other",
            "subject": f"{_NS}#L",
            "statement": "seen in README",
        }
    )
    graph = _merge(tmp_path, "MIT", document)
    (kept,) = license_values(graph)
    (note,) = [e for e in graph if e.get("spdxId") == f"{_NS}#Note"]
    assert note["subject"] == kept


def test_a_named_individual_target_is_left_alone(tmp_path: Path) -> None:
    document = fragment_graph(
        [
            *licensed_package("P", "expandedlicensing_NoAssertionLicense"),
            license_node(f"{_NS}#L", "expression", "MIT"),
            *licensed_package("Q", f"{_NS}#L"),
        ]
    )
    graph = _merge(tmp_path, "MIT", document)
    assert sorted(license_targets(graph)) == ["MIT", "MIT", "NOASSERTION"]


def test_classifier_and_points_at_the_kept_texts(tmp_path: Path) -> None:
    """The fragment's ``Foo License`` text unifies with the base's; its
    ``AND`` expression is kept, its map now naming the base's text."""
    expression = classifier_expression(["Foo License", "Bar License"])
    terms = expression.split(" AND ")
    node = license_node(f"{_NS}#AND", "expression", expression)
    node["simplelicensing_customIdToUri"] = [
        {"type": "DictionaryEntry", "key": terms[0], "value": f"{_NS}#Foo"},
        {"type": "DictionaryEntry", "key": terms[1], "value": f"{_NS}#Bar"},
    ]
    document = fragment_graph(
        [
            node,
            license_node(f"{_NS}#Foo", "text", "Foo License"),
            license_node(f"{_NS}#Bar", "text", "Bar License"),
            *licensed_package("P", f"{_NS}#AND"),
        ]
    )
    graph = _merge(tmp_path, "Foo License", document)
    values = license_values(graph)
    (base_foo,) = [i for i, v in values.items() if v == "Foo License"]
    assert not base_foo.startswith(_NS)
    (merged,) = [e for e in graph if e.get("spdxId") == f"{_NS}#AND"]
    targets = {e["key"]: e["value"] for e in merged["simplelicensing_customIdToUri"]}
    assert targets == {terms[0]: base_foo, terms[1]: f"{_NS}#Bar"}
    assert set(targets.values()) <= set(values)  # no orphan, no dangling


_BUILT = [
    "MIT",
    "mit and apache-2.0",
    "Apache-2.0+",
    "LGPL-2.0+",
    "  Some licence text  \n",
    "first line\nsecond line",
    classifier_expression(["Foo License", "Bar License"]),
]


def test_license_key_matches_what_a_build_indexes() -> None:
    """Drift guard: a merge keys a licence as a build indexed it."""
    exporter, ci, doc_uuid = _new_document("drift")
    for i, value in enumerate(_BUILT):
        package = spdx3.software_Package(
            spdxId=f"https://x/1#Package-{i}", name=f"p{i}", creationInfo=ci
        )
        exporter.add_package(package)
        _apply_license(value, "Source: x", package, ci, "drift", doc_uuid, exporter)
    # pylint: disable-next=protected-access
    index = exporter._license_index
    assert len(index) >= len(_BUILT)
    for key, spdx_id in index.items():
        element = exporter.object_set.find_by_id(spdx_id)
        assert isinstance(element, LICENSE_TYPES)
        assert license_key(element) == key


@pytest.mark.parametrize(
    ("element", "key"),
    [
        (
            spdx3.simplelicensing_LicenseExpression(
                simplelicensing_licenseExpression="mit and apache-2.0"
            ),
            ("expression", "Apache-2.0 AND MIT"),
        ),
        (
            spdx3.simplelicensing_LicenseExpression(
                simplelicensing_licenseExpression=" Foo Bar "
            ),
            ("expression", "Foo Bar"),
        ),
        (
            spdx3.simplelicensing_SimpleLicensingText(
                simplelicensing_licenseText="  MIT\n"
            ),
            ("text-body", "MIT"),
        ),
        (
            spdx3.simplelicensing_SimpleLicensingText(
                simplelicensing_licenseText="Acme\n \nNo use."
            ),
            ("text-body", "Acme\n\nNo use."),
        ),
    ],
    ids=["canonical", "not-an-expression", "text", "blank-space-line"],
)
def test_license_key(element: Any, key: tuple[str, str]) -> None:
    assert license_key(element) == key


def test_blank_licences_never_unify(tmp_path: Path) -> None:
    graph = _merge(
        tmp_path, None, _fragment(("L1", "expression", ""), ("L2", "expression", ""))
    )
    assert len(license_elements(graph)) == 2
    assert not _unifications(graph)


def test_blank_texts_never_unify(tmp_path: Path) -> None:
    graph = _merge(tmp_path, None, _fragment(("L1", "text", " "), ("L2", "text", "")))
    texts = [e for e in graph if e["type"] == "simplelicensing_SimpleLicensingText"]
    assert len(texts) == 2


def test_wrappers_sharing_a_foreign_ref_stay_apart(tmp_path: Path) -> None:
    """Two fragments may pick the same ``LicenseRef-`` for different texts."""

    def fragment(ns: str, text: str) -> dict[str, Any]:
        wrapper = text_wrapper_node(f"{ns}#W", f"{ns}#T", text)
        wrapper["simplelicensing_licenseExpression"] = "LicenseRef-custom"
        (wrapper["simplelicensing_customIdToUri"][0])["key"] = "LicenseRef-custom"
        return fragment_graph(
            [license_node(f"{ns}#T", "text", text), wrapper]
            + licensed_package("P", f"{ns}#W", ns),
            ns,
        )

    graph = _merge(
        tmp_path,
        None,
        fragment("https://x/f1", "Acme Research Licence"),
        fragment("https://x/f2", "Globex Commercial Licence"),
    )
    kinds = [e["type"] for e in graph if e["type"].startswith("simplelicensing_")]
    assert (
        sorted(kinds)
        == ["simplelicensing_LicenseExpression"] * 2
        + ["simplelicensing_SimpleLicensingText"] * 2
    )
    assert not _unifications(graph)
