# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.export._spdx3_credentials` on Pitloom's own
provenance comment (``[tool.pitloom.provenance] format = "comment"``): its
``Note:`` segments are read as whole values, as the annotation's notes are;
any other comment line is prose, never read.

See also: tests/export/test_spdx3_credentials.py (every other field read).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import provenance as assemble_provenance
from pitloom.assemble.spdx3._provenance_encoders import PitloomV1Encoder
from pitloom.core.config import PitloomConfig
from pitloom.core.credential_policy import CredentialPolicy, fingerprint
from pitloom.core.provenance import provenance_note
from pitloom.export._spdx3_credentials import (
    PROVENANCE_COMMENT_PREFIX,
    GraphFinding,
    check_graph_credentials,
    find_graph_credentials,
)
from pitloom.messages import code_of

_SECRET = "S3CRET"
_URL = f"https://u:{_SECRET}@h.example/x"
_DEP = f"foo @ {_URL}"
_FIELD = "declared_constraint"
_POINTER = f"/comment/{_FIELD}/note"


def _comment(*deps: str, field: str = _FIELD) -> str:
    """The comment the assembler writes for *deps*, as written."""
    provenance = {field: " | ".join(provenance_note(dep) for dep in deps)}
    comment = assemble_provenance.build_provenance_comment(provenance)
    assert comment is not None
    return comment


def _annotation(*deps: str) -> dict[str, Any]:
    """The annotation the assembler writes for *deps*, as JSON."""
    provenance = {_FIELD: " | ".join(provenance_note(dep) for dep in deps)}
    return {
        "spdxId": "urn:n",
        "contentType": PitloomV1Encoder.content_type,
        "statement": PitloomV1Encoder().encode(provenance),
    }


def _one(graph: list[dict[str, Any]]) -> GraphFinding:
    """The one finding of *graph*."""
    found = find_graph_credentials(graph)
    assert len(found) == 1, found
    return found[0]


def test_the_prefix_is_the_assemblers() -> None:
    """A drift guard: ``export`` cannot import ``assemble``."""
    assert PROVENANCE_COMMENT_PREFIX == assemble_provenance.PROVENANCE_COMMENT_PREFIX


def test_a_provenance_comment_note_is_refused_with_its_place(
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = [{"spdxId": "urn:a", "comment": _comment(_DEP)}]
    found = _one(graph)
    assert (found.element, found.pointer) == ("urn:a", _POINTER)
    assert found.value == _DEP and found.fingerprint == fingerprint(_DEP)
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError) as caught:
        check_graph_credentials(graph, CredentialPolicy())
    assert code_of(caught.value) == "credentials-unsafe/refused"
    assert f" {_POINTER}, sha256:" in caplog.text and _SECRET not in caplog.text


def test_the_comment_and_the_annotation_state_one_value_one_fingerprint() -> None:
    """``format = "both"``: one finding, at the first place, so one
    fingerprint accepts the value in both forms."""
    graph = [{"spdxId": "urn:a", "comment": _comment(_DEP)}, _annotation(_DEP)]
    found = _one(graph)
    assert found.pointer == _POINTER
    assert _one([_annotation(_DEP)]).fingerprint == found.fingerprint
    accepted = CredentialPolicy(accepted=frozenset({found.fingerprint}))
    check_graph_credentials(graph, accepted)


def test_a_comment_after_other_lines_is_read_and_each_note_is_a_value() -> None:
    """The assembler appends its line to a comment already there; two
    declared requirements of one dependency are two values, in either form
    (joined, the second would hide behind the first's URL)."""
    deps = ("bar @ https://h.example/b", _DEP)
    comment = f"extras: a\n{_comment(*deps)}"
    found = _one([{"spdxId": "urn:a", "comment": comment}])
    assert found.pointer == _POINTER
    assert found.value == _one([_annotation(*deps)]).value == _DEP


@pytest.mark.parametrize(
    "dep",
    [
        f"foo @ https://h.example/x; evil: Note: {_URL}",
        f"foo @ https://h.example/x | Field: evil | Note: {_URL}",
        f"foo\n{PROVENANCE_COMMENT_PREFIX}evil: Note: {_URL}",
        f"foo\r\n{PROVENANCE_COMMENT_PREFIX}evil: Note: {_URL}",
    ],
    ids=["entry-separator", "segment-bar", "line-feed-marker", "crlf-marker"],
)
def test_a_value_cannot_forge_an_entry_or_a_segment(dep: str) -> None:
    """A separator or the marker inside a value stays inside it: the value
    is read whole, in either form, so the URL after the forged separator,
    refused as a note of its own, is no note of its own here."""
    comment = _comment(dep)
    assert "\n" not in comment and "; " not in comment
    assert _one([{"comment": _comment(_URL)}]).value == _URL
    assert not find_graph_credentials([{"spdxId": "urn:a", "comment": comment}])
    assert not find_graph_credentials([_annotation(dep)])


def test_an_escaped_field_name_is_read_back_into_the_pointer() -> None:
    graph = [{"comment": _comment(_DEP, field="a/b:c;d")}]
    assert _one(graph).pointer == "/comment/a~1b:c;d/note"


def test_every_segment_of_a_provenance_entry_is_read() -> None:
    """A ``Value:`` segment (a downloaded archive's URL) is read as the
    annotation's ``fields.<field>.value`` is, at its own pointer."""
    source = f"Source: README | Value: {_URL}"
    comment = assemble_provenance.build_provenance_comment({_FIELD: source})
    assert comment is not None
    found = _one([{"spdxId": "urn:a", "comment": comment}])
    assert (found.pointer, found.value) == (f"/comment/{_FIELD}/value", _URL)


def test_a_literal_escape_in_a_source_reads_back_as_its_character() -> None:
    """The writer escapes ``;`` but not a backslash, so a source holding the
    literal text of an escape cannot be told from an escaped ``;``: the
    comment's value then differs from the annotation's (two fingerprints,
    each refused); a credential is found in either."""
    literal = "\\u003b"
    dep = f"foo @ {_URL}{literal}"
    in_comment = _one([{"spdxId": "urn:a", "comment": _comment(dep)}])
    in_annotation = _one([_annotation(dep)])
    assert in_annotation.value == dep
    assert in_comment.value == dep.replace(literal, ";")
    assert in_comment.fingerprint != in_annotation.fingerprint


@pytest.mark.parametrize(
    "comment",
    [
        f"See {_URL} for the mirror",
        f"Note: {_DEP}",
        f"Built from {PROVENANCE_COMMENT_PREFIX}{_FIELD}: Note: {_DEP}",
        f" {PROVENANCE_COMMENT_PREFIX}{_FIELD}: Note: {_DEP}",
        f"{PROVENANCE_COMMENT_PREFIX}{_FIELD}: Source: README",
        f"{PROVENANCE_COMMENT_PREFIX}no separator {_URL}",
    ],
    ids=[
        "prose",
        "note-shaped-prose",
        "marker-mid-line",
        "marker-indented",
        "provenance-without-note",
        "entry-without-field",
    ],
)
def test_an_ordinary_comment_is_never_read(comment: str) -> None:
    check_graph_credentials(
        [{"spdxId": "urn:a", "comment": comment}], CredentialPolicy()
    )


@pytest.mark.platform
@pytest.mark.parametrize("provenance_format", ["comment", "annotation", "both"])
def test_every_provenance_format_is_refused_end_to_end(
    provenance_format: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    proj = tmp_path / "proj"
    (proj / "testpkg").mkdir(parents=True)
    (proj / "testpkg" / "__init__.py").write_bytes(b"")
    (proj / "pyproject.toml").write_bytes(
        b"[project]\nname = 'testpkg'\nversion = '0.1.0'\n"
        + f"dependencies = ['{_DEP}']\n".encode()
    )
    config = PitloomConfig(provenance_format=provenance_format)
    out = tmp_path / "o.json"
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError) as caught:
        generate_project_sbom(
            proj, output_path=out, offline=True, pitloom_config=config
        )
    assert code_of(caught.value) == "credentials-unsafe/refused"
    assert not out.exists() and _SECRET not in caplog.text
    # With both, the value is one finding, at the annotation (first in order).
    pointer = _POINTER if provenance_format == "comment" else "/statement/fields/"
    assert pointer in caplog.text and caplog.text.count("holds a credential") == 1
