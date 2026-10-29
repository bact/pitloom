# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the rules a loom dataset's sources follow
(:mod:`pitloom._loom_dataset_meta`): precedence across declarations, the
caller's placeholders, presence against emptiness, how a source path is
opened and named, and the ids of the provenance record.

See also: test_loom_dataset_sources.py (each source written),
_loom_dataset_sources_shared.py (the helpers).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.core.ai_metadata import MAX_MODEL_NAME_CHARS
from pitloom.core.creation import CreationMetadata
from pitloom.extract.dataset.croissant import CROISSANT_MAX_NESTING
from tests._spdx3_validate import assert_spdx3_valid
from tests._symlink import CAN_SYMLINK
from tests.core._loom_dataset_sources_shared import (
    EXPRESSION,
    Graph,
    croissant_file,
    declared,
    dir_dataset,
    enter_project,
    package_of,
    run_graph,
    warnings_of,
)

#: Whether ``link/..`` is resolved through the link at the open: Win32
#: collapses ``..`` lexically first.
_DOTDOT_FOLLOWS_LINKS = CAN_SYMLINK and os.name != "nt"


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return enter_project(tmp_path, monkeypatch)


def _annotation_of(graph: Graph, subject: str) -> dict[str, Any]:
    (found,) = [
        e for e in graph if e["type"] == "Annotation" and e["subject"] == subject
    ]
    return found


@pytest.mark.parametrize(
    "value", ["unknown", "UNKNOWN", " ", "", "other", "Other"], ids=str.strip
)
def test_a_caller_placeholder_is_no_licence(
    project: Path, caplog: pytest.LogCaptureFixture, value: str
) -> None:
    """The caller's ``unknown``, blank or bare ``other`` is weak as from any
    source: the Croissant licence is written, silently."""
    croissant_file(project / "c.json", license="MIT")
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        graph = run_graph(
            project / "out.json",
            lambda: loom.add_dataset(
                "t.txt", croissant="c.json", declared_license=value
            ),
        )
    assert declared(graph, "t.txt") == [(EXPRESSION, "MIT")]
    assert "declared_license" not in package_of(graph, "t.txt")["comment"]
    assert not warnings_of(caplog)


@pytest.mark.parametrize(
    "calls",
    [
        [("Apache-2.0", None), (None, "MIT")],
        [(None, "MIT"), ("Apache-2.0", None)],
        [(None, "MIT"), (None, "Apache-2.0")],
        [("MIT", None), ("Apache-2.0", None)],
    ],
    ids=["declared-later", "declared-first", "two-declared", "two-croissants"],
)
def test_precedence_across_declarations(
    project: Path, calls: list[tuple[str | None, str | None]]
) -> None:
    """A ``declared_license=`` on any declaration beats every Croissant
    file, whichever came first; of two of a kind, the first declaration's
    wins. Each call is ``(Croissant licence, declared licence)``."""
    adders = (loom.add_dataset, loom.add_validation_dataset)

    def body() -> None:
        for index, (licence, stated) in enumerate(calls):
            croissant = None
            if licence is not None:
                croissant = croissant_file(project / f"c{index}.json", license=licence)
            adders[index]("t.txt", croissant=croissant, declared_license=stated)

    graph = run_graph(project / "out.json", body)
    assert declared(graph, "t.txt") == [(EXPRESSION, "MIT")]


@pytest.mark.parametrize("value", [123, True, b"MIT", ["MIT"]], ids=repr)
def test_a_declared_licence_not_a_string_raises(project: Path, value: object) -> None:
    with pytest.raises(TypeError, match="declared_license must be a str, not"):
        with loom.run(project / "out.json"):
            loom.add_dataset("t.txt", declared_license=value)  # type: ignore[arg-type]


def test_each_field_from_the_first_source_stating_it(project: Path) -> None:
    """A source leaving a field at its default (``[]``) does not hide a
    later source's value."""
    croissant_file(project / "c.json", **{"rai:dataBiases": ["biased"]})
    graph = run_graph(
        project / "out.json",
        lambda: loom.add_dataset("t.txt", croissant="c.json", declared_license="MIT"),
    )
    package = package_of(graph, "t.txt")
    assert package["dataset_knownBias"] == ["biased"]
    assert declared(graph, "t.txt") == [(EXPRESSION, "MIT")]


@pytest.mark.parametrize(
    ("stated", "expected"),
    [(None, ["from croissant"]), ([], None), (["declared"], ["declared"])],
    ids=["absent", "empty", "declared"],
)
def test_declared_preprocessing_beats_croissant(
    project: Path, stated: list[str] | None, expected: list[str] | None
) -> None:
    """``data_preprocessing=`` given on the call, even ``[]``, keeps the
    Croissant file's out, with its provenance; absent, the file's is
    written, also when the call that gives the file comes later."""
    croissant_file(
        project / "c.json",
        license="MIT",
        **{"rai:dataPreprocessingProtocol": ["from croissant"]},
    )

    def body() -> None:
        loom.add_output_dataset("t.txt", data_preprocessing=stated)
        loom.add_dataset("t.txt", croissant="c.json")

    graph = run_graph(project / "out.json", body)
    package = package_of(graph, "t.txt")
    assert package.get("dataset_dataPreprocessing") == expected
    assert ("data_preprocessing" in package["comment"]) is (stated is None)
    assert declared(graph, "t.txt") == [(EXPRESSION, "MIT")]


def test_card_tags_are_not_recorded(project: Path) -> None:
    """Tags have no SPDX 3.0.1 dataset property: neither they nor their
    provenance are written, while the card's licence is."""
    dir_dataset(project / "corpus", "license: mit\ntags: [nlp]\n")
    graph = run_graph(project / "out.json", lambda: loom.add_dataset("corpus"))
    package = package_of(graph, "corpus")
    assert declared(graph, "corpus") == [(EXPRESSION, "MIT")]
    assert "corpus/README.md" in package["comment"]
    assert "keywords" not in package["comment"]
    assert "keywords" not in _annotation_of(graph, package["spdxId"])["statement"]


@pytest.mark.parametrize("croissant", [False, True], ids=["no-source", "croissant"])
def test_annotation_ids_follow_declaration_order(
    project: Path, croissant: bool
) -> None:
    """A dataset's provenance record takes its id when it is declared, as
    the model's does, though it is written when the run ends."""
    croissant_file(project / "c.json", license="MIT")

    def body() -> None:
        loom.add_dataset("t.txt", croissant="c.json" if croissant else None)
        loom.set_model("m")

    graph = run_graph(project / "out.json", body)
    model = next(e for e in graph if e["type"] == "ai_AIPackage")
    numbers = [
        int(_annotation_of(graph, subject)["spdxId"].rsplit("-", 1)[1])
        for subject in (package_of(graph, "t.txt")["spdxId"], model["spdxId"])
    ]
    assert numbers == sorted(numbers) and len(set(numbers)) == 2


@pytest.mark.skipif(not _DOTDOT_FOLLOWS_LINKS, reason="link/.. is lexical here")
def test_a_source_is_opened_as_given(project: Path) -> None:
    """``link/../c.json`` is the file the OS opens through the link, not
    the lexical ``c.json``; so is a card directory. Provenance names the
    file opened."""
    sub = project / "sub"
    (sub / "inner").mkdir(parents=True)
    (project / "link").symlink_to(sub / "inner", target_is_directory=True)
    croissant_file(sub / "c.json", license="MIT")
    croissant_file(project / "c.json", license="GPL-3.0-only")
    dir_dataset(sub / "corpus", "license: mit\n")
    dir_dataset(project / "corpus", "license: gpl-3.0-only\n")

    def body() -> None:
        loom.add_dataset("t.txt", croissant="link/../c.json")
        loom.add_dataset("link/../corpus")

    graph = run_graph(project / "out.json", body)
    assert declared(graph, "t.txt") == [(EXPRESSION, "MIT")]
    assert declared(graph, "link/../corpus") == [(EXPRESSION, "MIT")]
    assert (
        "Source: sub/c.json | Field: license" in package_of(graph, "t.txt")["comment"]
    )
    corpus = package_of(graph, "link/../corpus")["comment"]
    assert "Source: sub/corpus/README.md | Field: license" in corpus


def test_provenance_holds_no_machine_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source outside the current directory is named by its bare name:
    two projects in different places give the same bytes."""
    outputs: list[bytes] = []
    for place in ("a", "b/deeper"):
        root = enter_project(tmp_path / place, monkeypatch)
        outside = croissant_file(root.parent / "c.json", license="MIT")
        with patch("pitloom._loom_active_run.uuid4", return_value=uuid.UUID(int=7)):
            with loom.run(
                root / "out.json",
                creation_metadata=CreationMetadata(
                    creation_datetime="2026-01-01T00:00:00Z"
                ),
            ):
                loom.add_dataset("t.txt", croissant=str(outside))
        outputs.append((root / "out.json").read_bytes())
    assert b"Source: c.json | Field: license" in outputs[0]
    assert json.dumps(str(tmp_path))[1:-1].encode() not in outputs[0]
    assert outputs[0] == outputs[1]


def test_a_long_creator_name_is_cut(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A Croissant creator's name is cut as a model's own name is, with one
    ``WARNING:``."""
    croissant_file(
        project / "c.json", creator={"name": "x" * (MAX_MODEL_NAME_CHARS + 1)}
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        graph = run_graph(
            project / "out.json",
            lambda: loom.add_dataset("t.txt", croissant="c.json"),
        )
    (agent,) = [e for e in graph if e["type"] == "Agent" and e["name"][0] == "x"]
    assert len(agent["name"]) == MAX_MODEL_NAME_CHARS
    (message,) = warnings_of(caplog)
    assert message.startswith("DATASET=t.txt: ")
    assert message.endswith("; dataset creator name cut")


@pytest.mark.parametrize(
    ("frontmatter", "licence"),
    [
        ("last_updated: 2024-02-30\n", []),
        ("version: " + "1" * 5000 + "\n", []),
        ("version: 0x" + "f" * 5000 + "\n", [(EXPRESSION, "MIT")]),
        ("version: " + ":".join(["1"] * 3000) + "\n", [(EXPRESSION, "MIT")]),
        ("version: 1:1:1\n", [(EXPRESSION, "MIT")]),
        ("x: " + "[" * 5000 + "]" * 5000 + "\n", []),
        ("x: " + "{a: " * 3000 + "1" + "}" * 3000 + "\n", []),
    ],
    ids=[
        "impossible-date",
        "huge-int",
        "huge-hex",
        "huge-base-60",
        "base-60",
        "deep-list",
        "deep-mapping",
    ],
)
def test_an_unusable_card_is_one_warning(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    frontmatter: str,
    licence: list[tuple[str, str]],
) -> None:
    """A card YAML cannot load is skipped, one with a version too long to
    write keeps its other fields; either way one ``WARNING:``, and the run
    completes."""
    dir_dataset(project / "corpus", "license: mit\n" + frontmatter)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        graph = run_graph(project / "out.json", lambda: loom.add_dataset("corpus"))
    assert declared(graph, "corpus") == licence
    assert "software_packageVersion" not in package_of(graph, "corpus")
    assert len(warnings_of(caplog)) == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"cr:totalItems": 5000},
        {"totalItems": "1500"},
        {"cr:totalItems": 0},
        {"cr:totalItems": -5},
        {"cr:totalItems": True},
        {"cr:totalItems": 10**20},
        {"recordSet": [{"cr:totalItems": 10**63}] * 20},
    ],
    ids=["count", "bare", "zero", "negative", "bool", "huge", "record-sets"],
)
def test_a_croissant_total_items_is_not_a_size(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    fields: dict[str, object],
) -> None:
    """``totalItems`` is a record count, not Croissant's and not bytes: it is
    not written as ``dataset_datasetSize``, has no provenance and no warning,
    and the fragment is valid SPDX 3."""
    croissant_file(project / "c.json", license="MIT", **fields)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        graph = run_graph(
            project / "out.json", lambda: loom.add_dataset("t.txt", croissant="c.json")
        )
    assert "dataset_datasetSize" not in package_of(graph, "t.txt")
    raw = (project / "out.json").read_bytes()
    assert not [word for word in (b"totalItems", b"byte_size") if word in raw]
    assert declared(graph, "t.txt") == [(EXPRESSION, "MIT")]
    assert not warnings_of(caplog)
    assert_spdx3_valid(project / "out.json")


def test_a_card_that_fails_to_read_is_skipped(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The card is a source the caller did not name: whatever reading it
    raises skips it with one ``WARNING:``, and the other sources stay."""
    dir_dataset(project / "corpus", "license: mit\n")
    croissant_file(project / "c.json", license="Apache-2.0", description="d")
    with (
        caplog.at_level(logging.WARNING, logger="pitloom"),
        patch(
            "pitloom._loom_dataset_meta.read_dataset_card",
            side_effect=MemoryError("hostile"),
        ),
    ):
        graph = run_graph(
            project / "out.json",
            lambda: loom.add_dataset("corpus", croissant="c.json"),
        )
    assert declared(graph, "corpus") == [(EXPRESSION, "Apache-2.0")]
    (message,) = warnings_of(caplog)
    assert message.startswith("loom: dataset 'corpus': dataset card skipped: ")


@pytest.mark.parametrize(
    ("depth", "read"),
    [
        (CROISSANT_MAX_NESTING, True),
        (CROISSANT_MAX_NESTING + 1, False),
        (100000, False),
    ],
    ids=["at-cap", "over-cap", "far-over"],
)
def test_a_deep_croissant_is_read_or_refused_by_its_cap(
    project: Path, depth: int, read: bool
) -> None:
    """The nesting cap alone decides, whatever the Python version's JSON
    depth limit: a file at it is read, one over it refused as the
    documented ``ValueError`` naming the file and the cap."""
    levels = depth - 1  # the document's own object is the first level
    body = '{"name": "x", "license": "MIT", "recordSet": '
    (project / "c.json").write_text(body + "[" * levels + "]" * levels + "}")

    def body_() -> None:
        loom.add_dataset("t.txt", croissant="c.json")

    if read:
        graph = run_graph(project / "out.json", body_)
        assert declared(graph, "t.txt") == [(EXPRESSION, "MIT")]
        return
    with pytest.raises(ValueError) as caught:
        run_graph(project / "out.json", body_)
    assert str(caught.value) == (
        "Croissant source 'c.json' is larger than the "
        f"{CROISSANT_MAX_NESTING}-level Croissant-nesting cap"
    )


def test_any_croissant_failure_is_a_value_error_naming_it(project: Path) -> None:
    croissant_file(project / "c.json", license="MIT")
    with patch(
        "pitloom.extract.dataset.croissant._extract_croissant_rai_fields",
        side_effect=RecursionError("deep"),
    ):
        with pytest.raises(
            ValueError,
            match="^Croissant source 'c.json' cannot be read: RecursionError: deep",
        ):
            run_graph(
                project / "out.json",
                lambda: loom.add_dataset("t.txt", croissant="c.json"),
            )
