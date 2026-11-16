# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The walk of an SBOM graph for the values that hold a credential
(:mod:`pitloom.export._spdx3_credentials`): each read field of each
element, each string of a JSON statement Pitloom writes and each segment of
its provenance comment, at its RFC 6901 pointer.

See also: :mod:`pitloom.export._spdx3_credentials._fields` (what is read)
and :mod:`pitloom.export._spdx3_credentials._check` (the check that warns
or refuses).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pitloom.core.credential_policy import fingerprint
from pitloom.core.provenance import parse_provenance_value
from pitloom.core.untrusted_text import unescape_display_controls
from pitloom.core.url_masking import find_url_credentials, masked_given_path
from pitloom.export._spdx3_credentials._fields import (
    ENTRY_SEPARATOR,
    FIELD_SEPARATOR,
    FIELD_UNESCAPES,
    JSON_CONTENT_TYPE,
    NOTE_READING,
    NOTE_SEPARATOR,
    PITLOOM_SCHEMA_PREFIX,
    PROVENANCE_COMMENT_PREFIX,
    PROVENANCE_SCHEMA,
    SOURCE_UNESCAPES,
    UNESCAPE_RE,
    URL_FIELDS,
    URL_READING,
    Reading,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from pitloom.core.url_masking import Finding

__all__ = ["GraphFinding", "element_name", "find_graph_credentials"]


@dataclass(frozen=True)
class GraphFinding:
    """A credential found in a URL-typed value of a graph: the first place
    it stands. Its ``repr`` shows no credential."""

    #: The spdxId (or ``@id``) of the element holding it, masked.
    element: str
    #: Where in that element (RFC 6901); for a statement or provenance
    #: comment, on into the statement's JSON (``/statement/metadata/<key>``)
    #: or the comment's provenance entry (``/comment/<field>/note``): the
    #: last part names no JSON value of the element.
    pointer: str
    #: :func:`pitloom.core.credential_policy.fingerprint` of the whole value.
    fingerprint: str
    #: The detector's finding: the first one not weak, else the first.
    finding: Finding
    #: The whole value as written: it holds the credential, so it is never
    #: printed.
    value: str = field(repr=False)
    #: The value as the detector read it (a format character's escape
    #: written back, :attr:`Reading.escaped`): what a line shows, masked,
    #: so the masker sees what the detector saw. *value* when the same.
    read: str = field(default="", repr=False)

    @property
    def shown(self) -> str:
        """What a line names the value by, before masking."""
        return self.read or self.value


def _escape(token: str) -> str:
    """*token*, a key, as an RFC 6901 reference token. One that escaping
    changes is masked first (:func:`~pitloom.core.url_masking.masked_given_path`):
    a key that is a URL (an artifact metadata key, a field name) shows no
    credential once its ``/`` is written ``~1``, which the masker of the
    whole line no longer reads as a URL's. Any other key is masked with the
    line."""
    if "/" not in token and "~" not in token:
        return token
    return masked_given_path(token).replace("~", "~0").replace("/", "~1")


def _split_notes(note: object) -> list[str]:
    """Each note of *note*, a ``note`` value of a parsed provenance string:
    :func:`~pitloom.core.provenance.parse_provenance_value` joins several
    with ``" | "``, and no value holds a ``|`` of its own
    (:func:`~pitloom.core.provenance.sanitize_provenance_text`), so each is
    one whole value (two declared requirements of one dependency). Not a
    string: none."""
    return note.split(NOTE_SEPARATOR) if isinstance(note, str) else []


def _json_strings(data: object) -> Iterator[tuple[str, str]]:
    """Each ``(pointer, string)`` of *data*, a decoded JSON value: every
    string in it, in key order, at its RFC 6901 pointer. Iterative: no
    nesting exhausts the stack (``json.loads`` bounds the depth)."""
    stack: list[tuple[str, object]] = [("", data)]
    while stack:
        pointer, node = stack.pop()
        if isinstance(node, dict):
            stack.extend(
                (f"{pointer}/{_escape(str(key))}", node[key])
                for key in sorted(node, key=str, reverse=True)
            )
        elif isinstance(node, list):
            stack.extend(
                (f"{pointer}/{index}", node[index])
                for index in range(len(node) - 1, -1, -1)
            )
        elif isinstance(node, str):
            yield pointer, node


def _statement_values(statement: str) -> Iterator[tuple[str, str]]:
    """Each ``(pointer, value)`` of *statement*, a JSON statement Pitloom
    writes (its ``schema`` under :data:`PITLOOM_SCHEMA_PREFIX`): every
    string in it, a field provenance note split into its notes. Any other
    statement has none."""
    try:
        data = json.loads(statement)
    except (ValueError, RecursionError):
        return
    if not isinstance(data, dict):
        return
    schema = data.get("schema")
    if not isinstance(schema, str) or not schema.startswith(PITLOOM_SCHEMA_PREFIX):
        return
    notes = schema == PROVENANCE_SCHEMA
    for pointer, value in _json_strings(data):
        if notes and pointer.startswith("/fields/") and pointer.endswith("/note"):
            for one in _split_notes(value):
                yield f"/statement{pointer}", one
        else:
            yield f"/statement{pointer}", value


def _unescape(text: str, table: Mapping[str, str]) -> str:
    """*text*, one part of a provenance comment entry, with the writer's
    escapes of *table* undone."""
    return UNESCAPE_RE.sub(lambda match: table.get(match[0], match[0]), text)


def _comment_values(comment: str) -> Iterator[tuple[str, str]]:
    """Each ``(pointer, value)`` of *comment*: of each line that is
    Pitloom's provenance comment (:data:`PROVENANCE_COMMENT_PREFIX`), each
    entry's segments, read from its source by
    :func:`~pitloom.core.provenance.parse_provenance_value` as the
    annotation's ``fields.<field>`` is (the same values, so the same
    fingerprints; its notes split); the pointer is ``/<field>/<key>``,
    below the comment's. Any other line is prose, not read. A value cannot
    forge an entry or a segment: the builders write its ``|`` as ``/``
    (:func:`~pitloom.core.provenance.sanitize_provenance_text`) and its
    ``;``, CR and LF escaped. The writer does not escape a backslash, so a
    source holding the literal text of an escape (``\\u003b``) reads back
    as its character: not the annotation's value then (another
    fingerprint), still read."""
    for line in comment.split("\n"):
        if not line.startswith(PROVENANCE_COMMENT_PREFIX):
            continue
        body = line[len(PROVENANCE_COMMENT_PREFIX) :]
        for entry in body.split(ENTRY_SEPARATOR):
            name, sep, source = entry.partition(FIELD_SEPARATOR)
            if not sep:
                continue
            parsed = parse_provenance_value(_unescape(source, SOURCE_UNESCAPES))
            at = _escape(_unescape(name, FIELD_UNESCAPES))
            for key in sorted(parsed):
                values = _split_notes(parsed[key]) if key == "note" else [parsed[key]]
                for value in values:
                    yield f"/{at}/{_escape(key)}", value


def _values(
    element: dict[str, Any], every_string: bool
) -> Iterator[tuple[str, str, Reading]]:
    """Each ``(pointer, value, reading)`` of *element* read, in key order
    (as the output writes it); with *every_string*, each other string of
    it too, as a URL field (:func:`check_graph_credentials`). Iterative: a
    merged document's nesting cannot exhaust the stack."""
    stack: list[tuple[str, str, Any, dict[str, Any]]] = [("", "", element, {})]
    while stack:
        pointer, key, node, parent = stack.pop()
        if isinstance(node, dict):
            stack.extend(
                (f"{pointer}/{_escape(k)}", k, node[k], node)
                for k in sorted(node, reverse=True)
            )
        elif isinstance(node, list):
            stack.extend(
                (f"{pointer}/{index}", key, node[index], parent)
                for index in range(len(node) - 1, -1, -1)
            )
        elif isinstance(node, str):
            yield from _string_values(pointer, key, node, parent)
            if every_string and key not in URL_FIELDS:
                yield pointer, node, URL_READING


def _string_values(
    pointer: str, key: str, node: str, parent: dict[str, Any]
) -> Iterator[tuple[str, str, Reading]]:
    """The values :func:`_values` reads in the string *node* of *key* at
    *pointer*, *parent* the object holding it."""
    if key in URL_FIELDS:
        yield pointer, node, URL_FIELDS[key]
    elif key == "statement" and parent.get("contentType") == JSON_CONTENT_TYPE:
        for at, value in _statement_values(node):
            yield at, value, NOTE_READING
    elif key == "comment":
        for at, value in _comment_values(node):
            yield f"{pointer}{at}", value, NOTE_READING


def element_name(element: dict[str, Any]) -> str:
    """*element*'s id, masked; for one without, its type."""
    name = element.get("spdxId") or element.get("@id")
    if not name and "@context" in element:
        return "(the document's top level)"
    if not name:
        kind = element.get("type") or "an element"
        return masked_given_path(f"({kind} without an id)")
    return masked_given_path(name if isinstance(name, str) else str(name))


def find_graph_credentials(
    graph: list[dict[str, Any]], *, every_string: bool = False
) -> list[GraphFinding]:
    """Each distinct value of a read field of *graph* that holds a
    credential (a weak one included), at the first place it stands, in
    graph order: a value stated in two fields is one finding. With
    *every_string*, every string is read (:func:`check_graph_credentials`)."""
    found: dict[str, GraphFinding] = {}
    for element in graph:
        for pointer, value, reading in _values(element, every_string):
            if value in found and not found[value].finding.weak:
                continue
            read = unescape_display_controls(value) if reading.escaped else value
            hits = find_url_credentials(
                read,
                scp=reading.scp,
                account=reading.account,
                embedded=reading.embedded,
            )
            if not hits:
                continue
            first = next((hit for hit in hits if not hit.weak), hits[0])
            if value in found and first.weak:
                continue
            found[value] = GraphFinding(
                element_name(element),
                pointer,
                fingerprint(value),
                first,
                value,
                read if read != value else "",
            )
    return list(found.values())
