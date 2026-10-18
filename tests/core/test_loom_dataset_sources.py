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
(the package itself), test_loom_dataset_sources_rules.py (precedence, presence,
paths and robustness).
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.creation import CreationMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests._spdx3_validate import assert_spdx3_valid
from tests.core._loom_dataset_sources_shared import (
    EXPRESSION,
    LINK,
    TEXT,
    Graph,
    croissant_file,
    declared,
    dir_dataset,
    enter_project,
    package_of,
    run_graph,
    warnings_of,
)


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return enter_project(tmp_path, monkeypatch)


@pytest.mark.parametrize(
    ("licence", "expected"),
    [
        ({"license": "Apache-2.0"}, [(EXPRESSION, "Apache-2.0")]),
        ({"license": "Research use only"}, [(TEXT, "Research use only")]),
        ({"license": LINK}, [(TEXT, LINK)]),
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
    croissant = croissant_file(project / "c.json", **licence)
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        graph = run_graph(
            project / "out.json",
            lambda: loom.add_dataset("t.txt", "image", croissant=croissant),
        )
    assert declared(graph, "t.txt") == expected
    package = package_of(graph, "t.txt")
    assert package["dataset_datasetType"] == ["image"]
    stated = "license: Source: c.json | Field: license"
    assert (stated in package["comment"]) is bool(expected)
    assert not warnings_of(caplog)
    assert_spdx3_valid(project / "out.json")


@pytest.mark.parametrize(
    ("frontmatter", "expected"),
    [
        ("license: cc-by-4.0\n", [(EXPRESSION, "CC-BY-4.0")]),
        (
            f"license: other\nlicense_name: Foo\nlicense_link: {LINK}\n",
            [(TEXT, f"Foo ({LINK})")],
        ),
        (f"license: other\nlicense_link: {LINK}\n", [(TEXT, LINK)]),
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
    dir_dataset(project / "corpus", frontmatter)
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        graph = run_graph(project / "out.json", lambda: loom.add_dataset("corpus"))
    assert declared(graph, "corpus") == expected
    assert not warnings_of(caplog)


def test_declared_beats_croissant_beats_card(project: Path) -> None:
    """Field by field: ``declared_license=``, then Croissant, then the
    card; a field only a later source states is still taken from it."""
    corpus = dir_dataset(project / "corpus", "license: mit\nversion: '3'\n")
    croissant_file(
        project / "c.json",
        license="Apache-2.0",
        description="described",
        creator={"name": "ACME"},
    )

    def body() -> None:
        loom.add_dataset("corpus", croissant="c.json", declared_license="GPL-2.0-only")
        loom.add_validation_dataset("t.txt", croissant="c.json")

    graph = run_graph(project / "out.json", body)
    assert corpus.is_dir()
    assert declared(graph, "corpus") == [(EXPRESSION, "GPL-2.0-only")]
    assert declared(graph, "t.txt") == [(EXPRESSION, "Apache-2.0")]
    package = package_of(graph, "corpus")
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


@pytest.mark.parametrize("value", ["NOASSERTION", "noassertion", " NoAssertion "])
def test_declared_placeholder_is_recorded(project: Path, value: str) -> None:
    """A caller's own ``NOASSERTION`` (any case) is their statement,
    written as the individual; it is not replaced by a source's licence."""
    croissant_file(project / "c.json", license="MIT")
    graph = run_graph(
        project / "out.json",
        lambda: loom.add_dataset("t.txt", croissant="c.json", declared_license=value),
    )
    assert declared(graph, "t.txt") == [("individual", "NOASSERTION")]


def test_a_later_declaration_adds_its_sources(project: Path) -> None:
    """One package per dataset: a repeat declaration's Croissant fills what
    the first did not state, once."""
    croissant_file(project / "c.json", license="MIT")

    def body() -> None:
        loom.add_input_dataset("t.txt")
        loom.add_output_dataset("t.txt", croissant="c.json")

    graph = run_graph(project / "out.json", body)
    assert declared(graph, "t.txt") == [(EXPRESSION, "MIT")]


@pytest.mark.parametrize(
    ("croissant", "match"),
    [
        ("https://example.org/c.json", "only a local file is read"),
        ("missing.json", "Cannot read source 'missing.json'"),
        ("bad.json", "not valid JSON"),
        ("noname.json", "has no 'name' field"),
        ("latin1.json", "Croissant source 'latin1.json' is not valid JSON"),
        ("adir", "Croissant source 'adir' is not a regular file"),
        ("HTTPS://example.org/c.json", "only a local file is read"),
        (Path("https://example.org/c.json"), "only a local file is read"),
    ],
    ids=[
        "url",
        "missing",
        "malformed",
        "no-name",
        "not-utf8",
        "directory",
        "url-upper-case",
        "url-as-path",
    ],
)
def test_unreadable_croissant_raises(
    project: Path, croissant: str | Path, match: str
) -> None:
    """A ``croissant=`` the caller named but that cannot be read fails the
    declaration, naming it: nothing is silently dropped, and no network is
    read, whatever the URL's case or a ``Path`` made of it."""
    (project / "bad.json").write_bytes(b"{not json")
    (project / "latin1.json").write_bytes(b'{"name": "caf\xe9"}')
    (project / "adir").mkdir()
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
    croissant_file(project / "c.json", license="Terms\u202e", description="d\u200b")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        graph = run_graph(
            project / "out.json",
            lambda: loom.add_dataset("t.txt", croissant="c.json"),
        )
    assert declared(graph, "t.txt") == [(TEXT, "Terms\\u202e")]
    assert package_of(graph, "t.txt")["description"] == "d\\u200b"
    (message,) = warnings_of(caplog)
    assert "dataset description" in message and "license " in message


def test_two_runs_give_identical_bytes(project: Path) -> None:
    """Same sources, same fragment, byte for byte (the run's random
    document uuid and clock held)."""
    croissant_file(project / "c.json", license="MIT", version="1")
    dir_dataset(project / "corpus", "license: other\nlicense_link: x\n")
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
    croissant_file(project / "c.json", license="Apache-2.0")
    fragment = project / "frag.json"
    run_graph(fragment, lambda: loom.add_dataset("t.txt", croissant="c.json"))
    exporter = Spdx3JsonExporter()
    merge_fragments(project, [FragmentConfig(path="frag.json")], exporter)
    graph: Graph = json.loads(exporter.to_json())["@graph"]
    assert declared(graph, "t.txt") == [(EXPRESSION, "Apache-2.0")]
