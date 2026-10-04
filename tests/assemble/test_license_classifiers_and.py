# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Several ``License ::`` classifiers are one ``LicenseExpression``, the AND
of ``LicenseRef-pitloom-classifier-`` terms, whose ``customIdToUri`` maps
each term to the text element of its licence name; identical for the main
package and for a dependency's installed copy or PyPI record.

See also: :mod:`tests.assemble.test_license_elements_classifier` (the
cross-surface parity table) and :mod:`pitloom.extract.license_refs`.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import _fragments_refs
from pitloom.assemble.spdx3._fragments_refs import _find_dangling_references
from pitloom.assemble.spdx3.document import build
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.license_refs import classifier_expression, classifier_terms
from tests._license_graph import (
    dependency_graph,
    graph_of,
    license_targets,
    two_packages,
)
from tests._network import assert_spdx3_validate_ok

_MIT = "License :: OSI Approved :: MIT License"
_APACHE = "License :: OSI Approved :: Apache Software License"
_AND = (
    "LicenseRef-pitloom-classifier-Apache-Software-License"
    " AND LicenseRef-pitloom-classifier-MIT-License"
)


_SOURCES: dict[str, Callable[[list[str]], Any]] = {
    "dependency-installed": lambda found: dependency_graph(
        {}, classifiers=found, offline=True
    ),
    "dependency-pypi": lambda found: dependency_graph(None, {"classifiers": found}),
}
_PARENT = "License :: OSI Approved"


@pytest.mark.parametrize("source", list(_SOURCES))
@pytest.mark.parametrize(
    ("found", "expected", "warnings"),
    [
        ([_MIT, _APACHE], _AND, 1),
        ([_APACHE, _MIT, _APACHE], _AND, 1),
        ([_PARENT, _MIT], "MIT License", 0),  # a trove parent is a category
        ([_PARENT], None, 0),  # alone too: as if no classifier
        ([_MIT, _MIT + " :: X"], "X", 0),  # a licence's own trove child
    ],
)
def test_a_dependencys_classifiers_are_the_same_and(
    source: str,
    found: list[str],
    expected: str | None,
    warnings: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        targets = license_targets(_SOURCES[source](found))
    assert targets == ([] if expected is None else [expected])
    assert len(caplog.records) == warnings


def test_one_warning_per_set_of_classifiers(caplog: pytest.LogCaptureFixture) -> None:
    """The same set warns once per process; another set warns again."""
    other = "License :: OSI Approved :: BSD License"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        for found in ([_MIT, _APACHE], [_APACHE, _MIT], [_MIT, other]):
            _SOURCES["dependency-installed"](found)
    assert len(caplog.records) == 2


def test_the_and_maps_each_term_to_its_names_text_element() -> None:
    graph = _SOURCES["dependency-installed"]([_MIT, _APACHE])
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    (expression,) = [
        e for e in graph if e["type"] == "simplelicensing_LicenseExpression"
    ]
    assert expression["simplelicensing_licenseExpression"] == _AND
    mapped = {
        entry["key"]: by_id[entry["value"]]["simplelicensing_licenseText"]
        for entry in expression["simplelicensing_customIdToUri"]
    }
    assert mapped == dict(classifier_terms(_AND) or [])
    assert set(mapped.values()) == {"MIT License", "Apache Software License"}


@pytest.mark.parametrize("order", [["MIT License", _AND], [_AND, "MIT License"]])
def test_a_name_text_is_shared_with_a_single_classifier_text(order: list[str]) -> None:
    """The member text element is the one a lone ``MIT License`` elsewhere in
    the document records, whichever comes first: one element per text."""
    graph = two_packages(order)
    texts = {
        e["simplelicensing_licenseText"]: e["spdxId"]
        for e in graph
        if e["type"] == "simplelicensing_SimpleLicensingText"
    }
    assert len(texts) == len(
        [e for e in graph if e["type"] == "simplelicensing_SimpleLicensingText"]
    )
    assert sorted(texts) == ["Apache Software License", "MIT License"]
    (expression,) = [
        e for e in graph if e["type"] == "simplelicensing_LicenseExpression"
    ]
    mapped = {e["value"] for e in expression["simplelicensing_customIdToUri"]}
    assert mapped == set(texts.values())


def test_a_project_with_several_classifiers(tmp_path: Path) -> None:
    """End to end: the AND, a text element per name, simpleLicensing."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n'
        f"classifiers = {json.dumps([_MIT, _APACHE])}\n",
        encoding="utf-8",
    )
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    graph: list[dict[str, Any]] = json.loads(
        generate_project_sbom(tmp_path, offline=True)
    )["@graph"]
    texts = [
        e["simplelicensing_licenseText"]
        for e in graph
        if e["type"] == "simplelicensing_SimpleLicensingText"
    ]
    assert sorted(texts) == ["Apache Software License", "MIT License"]
    assert license_targets(graph) == [_AND]
    document = next(e for e in graph if e["type"] == "SpdxDocument")
    assert "simpleLicensing" in document["profileConformance"]


@pytest.mark.parametrize(
    "names",
    [
        ["MIT License", "Apache Software License"],
        ["Other/Proprietary License", "a-b.c", "Licence é"],
    ],
)
def test_classifier_terms_round_trip(names: list[str]) -> None:
    expression = classifier_expression(names)
    terms = classifier_terms(expression)
    assert terms is not None
    assert [name for _, name in terms] == names
    assert all(re.fullmatch(r"LicenseRef-[A-Za-z0-9.\-]+", ref) for ref, _ in terms)


@pytest.mark.parametrize(
    "expression",
    [
        "LicenseRef-pitloom-classifier-MIT-License",  # one term: not an AND
        "LicenseRef-pitloom-classifier-MIT AND MIT",  # a listed id
        "LicenseRef-pitloom-classifier-a.2f AND LicenseRef-pitloom-classifier-b",
        "LicenseRef-pitloom-classifier-a.ZZ AND LicenseRef-pitloom-classifier-b",
        "LicenseRef-pitloom-classifier-.FF AND LicenseRef-pitloom-classifier-b",
        "LicenseRef-pitloom-classifier-a+ AND LicenseRef-pitloom-classifier-b",
        "LicenseRef-pitloom-classifier- AND LicenseRef-pitloom-classifier-b",
        "LicenseRef-x AND LicenseRef-y",  # a user's own references
    ],
)
def test_other_expressions_are_not_classifier_terms(expression: str) -> None:
    assert classifier_terms(expression) is None


def _and_document(**extra: Any) -> Spdx3JsonExporter:
    """A project whose licence is the AND, with *extra* metadata."""
    project = ProjectMetadata(name="p", version="1.0", license_name=_AND, **extra)
    return build(DocumentModel(project=project, creation_metadata=CreationMetadata()))


def test_a_custom_id_target_in_the_document_must_resolve() -> None:
    """A ``customIdToUri`` value in the document's own namespace that names
    no element is dangling; an external licence URI is not."""
    exporter = _and_document()
    expression = next(
        o
        for o in exporter.object_set.objects
        if isinstance(o, spdx3.simplelicensing_LicenseExpression)
    )
    assert not _find_dangling_references(exporter)
    namespace = str(expression.spdxId).split("#", 1)[0]
    missing = f"{namespace}#License-404"
    expression.simplelicensing_customIdToUri.append(
        spdx3.DictionaryEntry(key="LicenseRef-x", value=missing)
    )
    expression.simplelicensing_customIdToUri.append(
        spdx3.DictionaryEntry(key="LicenseRef-y", value="https://example.org/l")
    )
    assert _find_dangling_references(exporter) == [
        (str(expression.spdxId), "simplelicensing_customIdToUri", missing)
    ]


def test_the_document_is_looked_up_once_whatever_the_graph_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The namespace is read once, not per object: a per-object lookup scans
    the graph each time (quadratic; 20,000 files took 19 s)."""
    files = [
        ProjectFile(
            physical_path=f"p/f{index}.py",
            distribution_path=f"p/f{index}.py",
            digest_sha256=f"{index:064x}",
        )
        for index in range(50)
    ]
    exporter = _and_document(files=files)
    assert len(exporter.object_set.objects) > 50
    calls: list[object] = []
    # pylint: disable-next=protected-access
    real = _fragments_refs._find_main_document

    def counting(object_set: spdx3.SHACLObjectSet) -> object:
        calls.append(object_set)
        return real(object_set)

    monkeypatch.setattr(_fragments_refs, "_find_main_document", counting)
    assert not _find_dangling_references(exporter)
    # once for the declared external ids, once for the namespace
    assert len(calls) == 2


def test_and_against_a_detected_id_is_a_conflict() -> None:
    """The listed-name match is for one name; an AND is a conflict unless
    equal."""
    graph = graph_of(_and_document(license_concluded="MIT"))
    assert sorted(license_targets(graph)) == sorted(["MIT", _AND])
    assert [e for e in graph if "conflict" in e.get("statement", "")]


@pytest.mark.network
def test_a_document_with_the_and_validates(tmp_path: Path) -> None:
    sbom = tmp_path / "sbom.json"
    exporter = _and_document()
    sbom.write_text(exporter.to_json(), encoding="utf-8")
    assert_spdx3_validate_ok(sbom)
