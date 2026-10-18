# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for what a loom dataset's own sources state
(:mod:`pitloom._loom_dataset_meta`): ``declared_license=``, a local
Croissant file (``croissant=``) and a directory dataset's card, written as
the dataset's ``hasDeclaredLicense`` and fields, with provenance.

See also: tests/extract/dataset/test_licence.py (the licence rules),
tests/extract/dataset/test_card.py (the card), tests/core/test_loom_dataset.py
(the package itself).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.license_individuals import INDIVIDUAL_BY_REFERENCE
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests._spdx3_validate import assert_spdx3_valid

Graph = list[dict[str, Any]]

_EXPRESSION = "simplelicensing_LicenseExpression"
_TEXT = "simplelicensing_SimpleLicensingText"
_LINK = "https://example.org/terms"


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project directory, entered; no calling script captured."""
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    (root / "t.txt").write_bytes(b"data\n")
    return root


def _croissant(path: Path, **fields: object) -> Path:
    path.write_text(json.dumps({"name": "from-croissant", **fields}), "utf-8")
    return path


def _dir_dataset(path: Path, frontmatter: str | None) -> Path:
    path.mkdir()
    (path / "a.txt").write_bytes(b"a\n")
    if frontmatter is not None:
        (path / "README.md").write_text(f"---\n{frontmatter}---\n# Card\n", "utf-8")
    return path


def _run(output: Path, body: Callable[[], None]) -> Graph:
    with loom.run(output):
        body()
    graph: Graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    return graph


def _package(graph: Graph, name: str) -> dict[str, Any]:
    (found,) = [
        e for e in graph if e["type"] == "dataset_DatasetPackage" and e["name"] == name
    ]
    return found


def _declared(graph: Graph, name: str) -> list[tuple[str, str]]:
    """``(licence type, value)`` of each ``hasDeclaredLicense`` from the
    dataset *name*; an individual as ``("individual", its SPDX name)``."""
    package_id = _package(graph, name)["spdxId"]
    by_id = {e.get("spdxId"): e for e in graph}
    out: list[tuple[str, str]] = []
    for rel in graph:
        if (
            rel.get("relationshipType") != "hasDeclaredLicense"
            or rel["from"] != package_id
        ):
            continue
        for target in rel["to"]:
            if target in INDIVIDUAL_BY_REFERENCE:
                out.append(("individual", INDIVIDUAL_BY_REFERENCE[target].spdx_name))
                continue
            element = by_id[target]
            value = element.get("simplelicensing_licenseExpression") or element.get(
                "simplelicensing_licenseText"
            )
            out.append((str(element["type"]), str(value)))
    return out


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    ("licence", "expected"),
    [
        ({"license": "Apache-2.0"}, [(_EXPRESSION, "Apache-2.0")]),
        ({"license": "Research use only"}, [(_TEXT, "Research use only")]),
        ({"license": _LINK}, [(_TEXT, _LINK)]),
        ({}, []),
        ({"license": "unknown"}, []),
        ({"license": "NOASSERTION"}, []),
        ({"license": "other"}, []),
        ({"license": " "}, []),
    ],
    ids=["expression", "text", "url", "absent", "unknown", "na", "other", "blank"],
)
def test_croissant_licence(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    licence: dict[str, str],
    expected: list[tuple[str, str]],
) -> None:
    """A Croissant licence is the dataset's declared licence, its shape by
    its value, its provenance naming the file; a placeholder or no licence
    writes nothing and logs nothing. The declared name and type stay."""
    croissant = _croissant(project / "c.json", **licence)
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        graph = _run(
            project / "out.json",
            lambda: loom.add_dataset("t.txt", "image", croissant=croissant),
        )
    assert _declared(graph, "t.txt") == expected
    package = _package(graph, "t.txt")
    assert package["dataset_datasetType"] == ["image"]
    stated = "license: Source: c.json | Field: license"
    assert (stated in package["comment"]) is bool(expected)
    assert not _warnings(caplog)
    assert_spdx3_valid(project / "out.json")


@pytest.mark.parametrize(
    ("frontmatter", "expected"),
    [
        ("license: cc-by-4.0\n", [(_EXPRESSION, "CC-BY-4.0")]),
        (
            f"license: other\nlicense_name: Foo\nlicense_link: {_LINK}\n",
            [(_TEXT, f"Foo ({_LINK})")],
        ),
        (f"license: other\nlicense_link: {_LINK}\n", [(_TEXT, _LINK)]),
        ("license: other\n", []),
        ("pretty_name: X\n", []),
        (None, []),
    ],
    ids=["expression", "other-name-link", "other-link", "other", "absent", "no-card"],
)
def test_card_licence(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    frontmatter: str | None,
    expected: list[tuple[str, str]],
) -> None:
    """A directory dataset's card states its licence; its ``pretty_name``
    does not rename the declared dataset."""
    _dir_dataset(project / "corpus", frontmatter)
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        graph = _run(project / "out.json", lambda: loom.add_dataset("corpus"))
    assert _declared(graph, "corpus") == expected
    assert not _warnings(caplog)


def test_declared_beats_croissant_beats_card(project: Path) -> None:
    """Field by field: ``declared_license=``, then Croissant, then the
    card; a field only a later source states is still taken from it."""
    corpus = _dir_dataset(project / "corpus", "license: mit\nversion: '3'\n")
    _croissant(
        project / "c.json",
        license="Apache-2.0",
        description="described",
        creator={"name": "ACME"},
    )

    def body() -> None:
        loom.add_dataset("corpus", croissant="c.json", declared_license="GPL-2.0-only")
        loom.add_validation_dataset("t.txt", croissant="c.json")

    graph = _run(project / "out.json", body)
    assert corpus.is_dir()
    assert _declared(graph, "corpus") == [(_EXPRESSION, "GPL-2.0-only")]
    assert _declared(graph, "t.txt") == [(_EXPRESSION, "Apache-2.0")]
    package = _package(graph, "corpus")
    assert (package["software_packageVersion"], package["description"]) == (
        "3",
        "described",
    )
    comment = package["comment"]
    assert "Field: declared_license" in comment
    assert "version: Source: corpus/README.md | Field: version" in comment
    assert "description: Source: c.json | Field: description" in comment
    agents = {e["name"] for e in graph if e["type"] == "Agent"}
    assert "ACME" in agents


def test_declared_placeholder_is_recorded(project: Path) -> None:
    """A caller's own ``NOASSERTION`` is their statement, written as the
    individual; it is not replaced by a source's licence."""
    _croissant(project / "c.json", license="MIT")
    graph = _run(
        project / "out.json",
        lambda: loom.add_dataset(
            "t.txt", croissant="c.json", declared_license="NOASSERTION"
        ),
    )
    assert _declared(graph, "t.txt") == [("individual", "NOASSERTION")]


def test_declared_preprocessing_beats_croissant(project: Path) -> None:
    _croissant(
        project / "c.json",
        license="MIT",
        **{"rai:dataPreprocessingProtocol": ["from croissant"]},
    )
    graph = _run(
        project / "out.json",
        lambda: loom.add_output_dataset(
            "t.txt", data_preprocessing=["declared"], croissant="c.json"
        ),
    )
    package = _package(graph, "t.txt")
    assert package["dataset_dataPreprocessing"] == ["declared"]
    assert "data_preprocessing" not in package["comment"]


def test_a_later_declaration_adds_its_sources(project: Path) -> None:
    """One package per dataset: a repeat declaration's Croissant fills what
    the first did not state, once."""
    _croissant(project / "c.json", license="MIT")

    def body() -> None:
        loom.add_input_dataset("t.txt")
        loom.add_output_dataset("t.txt", croissant="c.json")

    graph = _run(project / "out.json", body)
    assert _declared(graph, "t.txt") == [(_EXPRESSION, "MIT")]


@pytest.mark.parametrize(
    ("croissant", "match"),
    [
        ("https://example.org/c.json", "only a local file is read"),
        ("missing.json", "Cannot read source 'missing.json'"),
        ("bad.json", "not valid JSON"),
        ("noname.json", "has no 'name' field"),
    ],
    ids=["url", "missing", "malformed", "no-name"],
)
def test_unreadable_croissant_raises(project: Path, croissant: str, match: str) -> None:
    """A ``croissant=`` the caller named but that cannot be read fails the
    declaration: nothing is silently dropped, and no network is read."""
    (project / "bad.json").write_bytes(b"{not json")
    (project / "noname.json").write_text('{"license": "MIT"}', "utf-8")
    with patch("urllib.request.urlopen", autospec=True) as urlopen:
        with pytest.raises(ValueError, match=match):
            with loom.run(project / "out.json"):
                loom.add_dataset("t.txt", croissant=croissant)
    urlopen.assert_not_called()
    assert not (project / "out.json").exists()


def test_display_controls_are_escaped_with_one_warning(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _croissant(project / "c.json", license="Terms\u202e", description="d\u200b")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        graph = _run(
            project / "out.json",
            lambda: loom.add_dataset("t.txt", croissant="c.json"),
        )
    assert _declared(graph, "t.txt") == [(_TEXT, "Terms\\u202e")]
    assert _package(graph, "t.txt")["description"] == "d\\u200b"
    (message,) = _warnings(caplog)
    assert "dataset description" in message and "license " in message


def test_two_runs_give_identical_bytes(project: Path) -> None:
    """Same sources, same fragment, byte for byte (the run's random
    document uuid and clock held)."""
    _croissant(project / "c.json", license="MIT", version="1")
    _dir_dataset(project / "corpus", "license: other\nlicense_link: x\n")
    fixed = uuid.UUID(int=7)
    outputs: list[bytes] = []
    for index in range(2):
        output = project / f"out{index}.json"
        with patch("pitloom._loom_active_run.uuid4", return_value=fixed):
            with loom.run(
                output,
                creation_metadata=CreationMetadata(
                    creation_datetime="2026-01-01T00:00:00Z"
                ),
            ):
                loom.add_dataset("t.txt", croissant="c.json")
                loom.add_dataset("corpus")
        outputs.append(output.read_bytes())
    assert b"hasDeclaredLicense" in outputs[0]
    assert outputs[0] == outputs[1]


def test_merged_fragment_keeps_the_licence(project: Path) -> None:
    """A project build merging the run's fragment keeps the dataset's
    declared licence and its provenance."""
    _croissant(project / "c.json", license="Apache-2.0")
    fragment = project / "frag.json"
    _run(fragment, lambda: loom.add_dataset("t.txt", croissant="c.json"))
    exporter = Spdx3JsonExporter()
    merge_fragments(project, [FragmentConfig(path="frag.json")], exporter)
    graph: Graph = json.loads(exporter.to_json())["@graph"]
    assert _declared(graph, "t.txt") == [(_EXPRESSION, "Apache-2.0")]
