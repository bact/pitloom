# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read the provenance of a serialised SPDX 3 document: what a benign and a
hostile run of one surface must agree on.

A provenance string is split on ``|`` into ``Key: value`` segments, and a
consumer acts on the keys it finds (``Evidence``, ``Source``). So a hostile
external name must leave the *key set* of every entry as a benign run has it.

See also: tests/test_provenance_hostile_project.py (the project surfaces).
"""

from __future__ import annotations

import json
from typing import Any

from pitloom.core.provenance import parse_provenance_value
from pitloom.core.untrusted_text import DISPLAY_CONTROLS

_COMMENT_PREFIX = "Metadata provenance: "

#: ``(where, field, sorted keys)`` of one provenance entry.
Shape = list[tuple[str, str, tuple[str, ...]]]


def _graph(sbom: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _annotation_fields(sbom: str) -> list[dict[str, Any]]:
    """The ``fields`` table of every provenance Annotation."""
    out: list[dict[str, Any]] = []
    for element in _graph(sbom):
        if element.get("type") == "Annotation":
            statement = json.loads(element["statement"])
            if isinstance(statement, dict) and "fields" in statement:
                out.append(statement["fields"])
    return out


def _comment_entries(sbom: str) -> list[tuple[str, str]]:
    """``(field, provenance string)`` of every entry of every provenance
    comment (entries are separated by ``"; "``)."""
    out: list[tuple[str, str]] = []
    for element in _graph(sbom):
        comment = element.get("comment")
        if isinstance(comment, str) and comment.startswith(_COMMENT_PREFIX):
            for entry in comment[len(_COMMENT_PREFIX) :].split("; "):
                field, _, text = entry.partition(": ")
                out.append((field, text))
    return out


def provenance_shape(sbom: str) -> Shape:
    """The key set of every provenance entry of *sbom*: from the Annotations
    (the keys of each field's table) and from the comments (the keys
    :func:`~pitloom.core.provenance.parse_provenance_value` finds), sorted."""
    shape: Shape = [
        ("annotation", field, tuple(sorted(table)))
        for fields in _annotation_fields(sbom)
        for field, table in fields.items()
    ]
    shape += [
        ("comment", field, tuple(sorted(parse_provenance_value(text))))
        for field, text in _comment_entries(sbom)
    ]
    return sorted(shape)


def provenance_texts(sbom: str) -> list[str]:
    """Every text a provenance entry of *sbom* holds: the values of the
    Annotation tables and the comment entries."""
    texts = [
        value
        for fields in _annotation_fields(sbom)
        for table in fields.values()
        for value in table.values()
        if isinstance(value, str)
    ]
    return texts + [text for _, text in _comment_entries(sbom)]


def keys_of(strings: list[str]) -> list[tuple[str, ...]]:
    """The sorted key set of each provenance string, in order."""
    return [tuple(sorted(parse_provenance_value(text))) for text in strings]


def assert_escaped(texts: list[str], expected: str) -> None:
    """*expected* (a hostile name, sanitised) is among *texts*, and no text
    holds a display control (other than a line break or TAB) unescaped."""
    assert any(expected in text for text in texts), (expected, texts)
    for text in texts:
        assert not DISPLAY_CONTROLS & set(text) - {"\n", "\r", "\t"}, text
