# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.spdx3._main_authors: the main package's
``originatedBy``, through :func:`pitloom.assemble.generate_project_sbom`;
the authors never make its copyright text.

See also: :mod:`tests.test_author_surfaces` (the same facts on every route).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import deps_installed
from pitloom.assemble.spdx3.document import build
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from tests.assemble.conftest import _FakeMetadata

_ANN = '{name = "Ann", email = "ann@example.com"}'
_BOB = '{name = "Bob"}'


def _sbom(
    tmp_path: Path,
    authors: list[str],
    *,
    dependencies: tuple[str, ...] = (),
    creators: tuple[Creator, ...] = (),
) -> list[dict[str, Any]]:
    """The ``@graph`` of the SBOM of project ``demo`` in *tmp_path*
    declaring *authors* (TOML inline tables), created 2024."""
    (tmp_path / "demo").mkdir(parents=True, exist_ok=True)
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    deps = ", ".join(f'"{d}"' for d in dependencies)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n'
        f"authors = [{', '.join(authors)}]\ndependencies = [{deps}]\n",
        encoding="utf-8",
    )
    sbom = generate_project_sbom(
        tmp_path,
        creation_metadata=CreationMetadata(
            creators=list(creators), creation_datetime="2024-05-01T00:00:00Z"
        ),
        provenance=ProvenanceConfig(format="annotation", detail="full"),
        offline=True,
    )
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _package(graph: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(
        e for e in graph if e["type"] == "software_Package" and e["name"] == name
    )


def _originators(graph: list[dict[str, Any]], name: str = "demo") -> list[str]:
    by_id = {e.get("spdxId"): e for e in graph}
    return [by_id[i]["name"] for i in _package(graph, name).get("originatedBy", [])]


def _has_copyright_provenance(graph: list[dict[str, Any]]) -> bool:
    main = _package(graph, "demo")["spdxId"]
    return any(
        "copyright_text" in json.loads(element["statement"]).get("fields", {})
        for element in graph
        if element["type"] == "Annotation" and element["subject"] == main
    )


_ANN_B = '{name = "Ann", email = "ann@example.org"}'


@pytest.mark.parametrize(
    ("authors", "names"),
    [
        (
            [_ANN, _BOB, '{name = "Cee", email = "cee@example.com"}'],
            ["Ann", "Bob", "Cee"],
        ),
        ([_ANN, _ANN], ["Ann"]),
        ([], []),
        (['{name = "  "}', _ANN], ["Ann"]),
        (['{name = "  "}'], []),
        (['{name = " ", email = "x@example.com"}'], ["x@example.com"]),
        ([_ANN, _ANN_B, _BOB], ["Ann", "Ann", "Bob"]),
        ([_ANN, '{name = " Ann ", email = "ann@example.com"}'], ["Ann"]),
        ([_ANN, '{name = "Ann"}'], ["Ann", "Ann"]),
    ],
    ids=[
        "several",
        "repeat",
        "none",
        "blank-name",
        "only-blank",
        "blank-email",
        "same-name",
        "same-identity",
        "one-without-email",
    ],
)
def test_main_package_authors(
    tmp_path: Path, authors: list[str], names: list[str]
) -> None:
    """One ``originatedBy`` Agent per author identity, in order; with no
    licence file, the copyright text is ``NOASSERTION`` whatever the
    authors, with no provenance."""
    graph = _sbom(tmp_path, authors)
    assert _originators(graph) == names
    assert _package(graph, "demo")["software_copyrightText"] == "NOASSERTION"
    assert not _has_copyright_provenance(graph)


@pytest.mark.parametrize(
    ("creator", "author", "shared", "author_type"),
    [
        (Creator(name="Bob"), _BOB, True, "Person"),
        (Creator(name="Ann", email="ann@example.com"), _BOB, True, "Person"),
        (Creator(name="Ann", email="other@example.com"), _BOB, False, "Person"),
        (Creator(name="Bob", type="organization"), _BOB, False, "Person"),
        (
            Creator(name=" Bob ", email=" bob@example.com "),
            '{name = "Bob", email = "bob@example.com"}',
            True,
            "Person",
        ),
        (
            Creator(name="Acme Inc.", type="organization"),
            '{name = "Acme Inc."}',
            False,
            "Person",
        ),
        (
            Creator(name="Acme and others", type="organization"),
            '{name = "Acme and others"}',
            False,
            "Organization",
        ),
    ],
    ids=[
        "person-name-only",
        "name-email",
        "other-email",
        "organization-vs-person",
        "whitespace",
        "organization-name-author-is-person",
        "contributor-group",
    ],
)
def test_author_who_is_sbom_creator_is_one_agent(
    tmp_path: Path, creator: Creator, author: str, shared: bool, author_type: str
) -> None:
    """An author is the creator's Agent only when type, name and address
    match; an author is a Person, or an Organization for a contributor
    group (one per package, so never a creator's)."""
    graph = _sbom(tmp_path, [_ANN, author], creators=(creator,))
    by_id = {e.get("spdxId"): e for e in graph}
    created_by = next(e for e in graph if e["type"] == "CreationInfo")["createdBy"]
    originated_by = _package(graph, "demo")["originatedBy"]
    assert (created_by[0] in originated_by) is shared
    assert len(originated_by) == 2
    assert by_id[originated_by[1]]["type"] == author_type
    agents = [e for e in graph if e["type"] in ("Person", "Organization")]
    assert len(agents) == (2 if shared else 3)
    # the creator's Agent is named and addressed as the author it matches
    identities = [
        (a["name"], *(x["identifier"] for x in a.get("externalIdentifier", [])))
        for a in agents
    ]
    assert identities == [tuple(v.strip() for v in i) for i in identities]


def test_dependency_originator_is_not_creator_of_other_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Person originator shared by two dependencies and an author is one
    Agent; an Organization creator of the same name is another."""
    monkeypatch.setattr(
        deps_installed,
        "get_pkg_metadata",
        lambda name: _FakeMetadata({"Author": "Acme"}),
    )
    graph = _sbom(
        tmp_path,
        ['{name = "Acme"}'],
        dependencies=("alpha", "beta"),
        creators=(Creator(name="Acme", type="organization"),),
    )
    by_id = {e.get("spdxId"): e for e in graph}
    [person] = _package(graph, "alpha")["originatedBy"]
    assert _package(graph, "beta")["originatedBy"] == [person]
    assert _package(graph, "demo")["originatedBy"] == [person]
    [creator] = next(e for e in graph if e["type"] == "CreationInfo")["createdBy"]
    agents = sorted(
        (e["type"], e["name"]) for e in graph if e["type"] in ("Person", "Organization")
    )
    assert agents == [("Organization", "Acme"), ("Person", "Acme")]
    assert (by_id[person]["type"], by_id[creator]["type"]) == (
        "Person",
        "Organization",
    )


#: The originator of dependency ``alpha``, also an SBOM creator.
_DEP_AUTHOR, _DEP_EMAIL = "Dee", "dee@example.com"


def test_authors_minted_last_and_shared_with_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dependency originator's Agent id is the same with or without the
    project's authors; an author who is that originator is that Agent (also
    when an SBOM creator has the same name and address: the creator's Agent
    is not merged into it after the fact); a new author's Agent comes after
    every other one."""
    originators = {"alpha": f"{_DEP_AUTHOR} <{_DEP_EMAIL}>", "beta": "Tee <t@x.org>"}
    monkeypatch.setattr(
        deps_installed,
        "get_pkg_metadata",
        lambda name: _FakeMetadata({"Author-email": originators[name]}),
    )
    deps = ("alpha", "beta")
    creators = (Creator(name=_DEP_AUTHOR, email=_DEP_EMAIL),)
    without = _sbom(tmp_path / "a", [], dependencies=deps, creators=creators)
    shared = f'{{name = "{_DEP_AUTHOR}", email = "{_DEP_EMAIL}"}}'
    with_authors = _sbom(
        tmp_path / "b",
        ['{name = "Zed"}', shared],
        dependencies=deps,
        creators=creators,
    )

    def people(graph: list[dict[str, Any]]) -> set[tuple[str, str]]:
        return {(e["name"], e["spdxId"]) for e in graph if e["type"] == "Person"}

    def number(spdx_id: str) -> int:
        return int(spdx_id.rsplit("-", 1)[1])

    before, after = people(without), people(with_authors)
    assert before < after
    [(name, zed)] = after - before
    assert name == "Zed"
    assert number(zed) == max(number(i) for _, i in after)
    originated_by = _package(with_authors, "demo")["originatedBy"]
    assert originated_by[0] == zed
    assert originated_by[1] in _package(with_authors, "alpha")["originatedBy"]
    creation_info = next(e for e in with_authors if e["type"] == "CreationInfo")
    assert originated_by[1] not in creation_info["createdBy"]


def test_blank_author_entry_is_skipped() -> None:
    """A library caller's ``{}`` author names no one: no Agent."""
    doc = DocumentModel(
        project=ProjectMetadata(name="demo", authors=[{}, {"name": "Ann"}]),
        creation_metadata=CreationMetadata(creation_datetime="2024-05-01T00:00:00Z"),
    )
    graph = json.loads(build(doc, offline=True).to_json(pretty=False))["@graph"]
    assert _originators(graph) == ["Ann"]


@pytest.mark.parametrize(
    ("author", "agent_type"),
    [
        ("Jan Brothers", "Person"),
        ("Rothersby", "Person"),
        ("Others", "Organization"),
        ("others", "Organization"),
        ("Jane and others", "Organization"),
        ("Smith et al.", "Organization"),
    ],
    ids=["brothers", "rothersby", "Others", "others", "and-others", "et-al"],
)
def test_contributor_group_is_whole_word(author: str, agent_type: str) -> None:
    """Only a whole-word ``others``/``et al`` names a group of contributors
    (an Organization); a name merely containing ``others`` is a Person."""
    doc = DocumentModel(
        project=ProjectMetadata(name="demo", authors=[{"name": author}]),
        creation_metadata=CreationMetadata(creation_datetime="2024-05-01T00:00:00Z"),
    )
    graph = json.loads(build(doc, offline=True).to_json(pretty=False))["@graph"]
    by_id = {e.get("spdxId"): e for e in graph}
    [agent_id] = _package(graph, "demo")["originatedBy"]
    assert (by_id[agent_id]["name"], by_id[agent_id]["type"]) == (author, agent_type)
