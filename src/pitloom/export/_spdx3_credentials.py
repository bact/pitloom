# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The refusal of an SBOM whose URL-typed fields hold a credential: the one
check every surface's SBOM passes (the exporter's last step, and
``embed-wheel --sbom`` on the file it embeds). A value is never rewritten:
it is stated as written when the run accepts it, else the SBOM is refused.

Only the fields of :data:`URL_FIELDS`, every string of a JSON statement
Pitloom writes (an annotation whose ``schema`` is under
:data:`PITLOOM_SCHEMA_PREFIX`: its field provenance, the artifact metadata
it copies from a model, a conflict's candidates, an enrichment's changes)
and every segment of a ``Metadata provenance:`` comment line are read, each
as a whole value (a string that is not a URL holds no finding); a name, a
description, any other comment line or other prose is not (a README example
must not block a build; finding secrets in prose is a secret scanner's
job).

See also: :mod:`pitloom.export.spdx3_json` (the exporter),
:func:`pitloom.core.url_masking.find_url_credentials` (the detector),
:class:`pitloom.core.credential_policy.CredentialPolicy` (what a run
accepts) and :mod:`pitloom.messages.url_credentials` (the lines said).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from pitloom.core.credential_policy import fingerprint, full_fingerprint
from pitloom.core.provenance import (
    escape_provenance_comment_part,
    parse_provenance_value,
)
from pitloom.core.url_masking import find_url_credentials, masked_given_path
from pitloom.messages.url_credentials import (
    refused_error,
    say_accepted,
    say_refused,
    say_stale_fingerprint,
    say_weak,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from pitloom.core.credential_policy import CredentialPolicy
    from pitloom.core.url_masking import Finding

__all__ = [
    "NOT_READ",
    "PITLOOM_SCHEMA_PREFIX",
    "PROVENANCE_COMMENT_PREFIX",
    "URL_FIELDS",
    "GraphFinding",
    "check_graph_credentials",
    "find_graph_credentials",
]


@dataclass(frozen=True)
class _Reading:
    """How the detector reads a field
    (:func:`~pitloom.core.url_masking.find_url_credentials`)."""

    scp: bool = True
    account: bool = True
    embedded: bool = False


#: An identifier Pitloom or a merged document stores: read for a URL or a
#: token anywhere in it, an ``ssh`` account name a credential (the ID
#: registry's rule for an id and a namespace).
_IDENTIFIER: Final = _Reading(account=False, embedded=True)
#: A URL field of an SBOM.
_URL: Final = _Reading()

#: Each field read, by compact JSON-LD name, wherever it stands in an
#: element (a nested ``ExternalRef`` or ``NamespaceMap`` included), and how.
#: ``identifier`` is read whatever its ``externalIdentifierType``: a model's
#: DOI is ``other``, and no CPE, SWID, gitoid, SWHID, email address or
#: advisory id is a URL holding a credential as a whole value.
URL_FIELDS: Final[dict[str, _Reading]] = {
    "spdxId": _IDENTIFIER,
    "@id": _IDENTIFIER,
    "externalSpdxId": _IDENTIFIER,
    "namespace": _IDENTIFIER,
    # A location hint may be a file path such as ``meet-10:30@ab:c.json``.
    "locationHint": _Reading(scp=False),
    "software_downloadLocation": _URL,
    "software_homePage": _URL,
    "software_packageUrl": _URL,
    "software_contentIdentifierValue": _URL,
    "locator": _URL,
    "identifierLocator": _URL,
    "identifier": _URL,
    "expandedlicensing_seeAlso": _URL,
    "build_configSourceUri": _URL,
    "build_buildType": _URL,
    "security_locator": _URL,
}

#: The ``anyURI`` fields of the SPDX 3.0.1 model not read, each with why.
#: Every ``anyURI`` field is in :data:`URL_FIELDS` or here (a drift test).
NOT_READ: Final[dict[str, str]] = {}

#: How every ``schema`` of a JSON statement Pitloom writes starts
#: (:mod:`pitloom.assemble.spdx3.provenance`,
#: :class:`pitloom.assemble.spdx3._provenance_encoders.PitloomV1Encoder`; a
#: test keeps them under it). A statement of another schema is not read.
PITLOOM_SCHEMA_PREFIX: Final = "https://pitloom.dev/"
_JSON_CONTENT_TYPE: Final = "application/json"
#: Pitloom's field provenance statement, whose notes are joined
#: (:data:`_NOTE_SEPARATOR`).
_PROVENANCE_SCHEMA: Final = "https://pitloom.dev/provenance/fields/1"
#: A string of Pitloom's statement or provenance comment is read as a URL
#: field: a dependency's direct reference (``foo @ https://h/x``) is stated
#: whole in a note, a model's ``source_url`` in its artifact metadata.
_NOTE: Final = _URL
#: How :func:`pitloom.core.provenance.parse_provenance_value` joins notes.
_NOTE_SEPARATOR: Final = " | "

#: How Pitloom's provenance comment line starts
#: (:data:`pitloom.assemble.spdx3.provenance.PROVENANCE_COMMENT_PREFIX`; not
#: imported, since ``assemble`` imports this package; a test keeps the two
#: equal). A comment line that does not start with it is prose, never read.
PROVENANCE_COMMENT_PREFIX: Final = "Metadata provenance: "
#: How that line joins its ``field: source`` entries, and each field to its
#: source (:func:`pitloom.assemble.spdx3.provenance.provenance_comment_line`).
_ENTRY_SEPARATOR: Final = "; "
_FIELD_SEPARATOR: Final = ": "
#: The writer's escapes
#: (:func:`pitloom.core.provenance.escape_provenance_comment_part`), each
#: mapped back to its character: a ``;``, CR or LF in a source, and a ``:``
#: in a field name too, is written escaped, so each separator above and
#: each line break is the writer's own.
_SOURCE_UNESCAPES: Final = {
    escape_provenance_comment_part(char): char for char in ";\r\n"
}
_FIELD_UNESCAPES: Final = {
    escape_provenance_comment_part(char, field=True): char for char in ";\r\n:"
}
_UNESCAPE_RE: Final = re.compile("|".join(map(re.escape, _FIELD_UNESCAPES)))


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


def _escape(token: str) -> str:
    """*token* as an RFC 6901 reference token."""
    return token.replace("~", "~0").replace("/", "~1")


def _split_notes(note: object) -> list[str]:
    """Each note of *note*, a ``note`` value of a parsed provenance string:
    :func:`~pitloom.core.provenance.parse_provenance_value` joins several
    with ``" | "``, and no value holds a ``|`` of its own
    (:func:`~pitloom.core.provenance.sanitize_provenance_text`), so each is
    one whole value (two declared requirements of one dependency). Not a
    string: none."""
    return note.split(_NOTE_SEPARATOR) if isinstance(note, str) else []


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
    notes = schema == _PROVENANCE_SCHEMA
    for pointer, value in _json_strings(data):
        if notes and pointer.startswith("/fields/") and pointer.endswith("/note"):
            for one in _split_notes(value):
                yield f"/statement{pointer}", one
        else:
            yield f"/statement{pointer}", value


def _unescape(text: str, table: Mapping[str, str]) -> str:
    """*text*, one part of a provenance comment entry, with the writer's
    escapes of *table* undone."""
    return _UNESCAPE_RE.sub(lambda match: table.get(match[0], match[0]), text)


def _comment_values(comment: str) -> Iterator[tuple[str, str]]:
    """Each ``(pointer, value)`` of *comment*: of each line that is
    Pitloom's provenance comment (:data:`PROVENANCE_COMMENT_PREFIX`), each
    entry's segments, read from its source by
    :func:`~pitloom.core.provenance.parse_provenance_value` as the
    annotation's ``fields.<field>`` is (the same values, so the same
    fingerprints; its notes split); the pointer is ``/<field>/<key>``,
    below the comment's. Any other line is prose, not read. A value cannot forge an entry or a
    segment: the builders write its ``|`` as ``/``
    (:func:`~pitloom.core.provenance.sanitize_provenance_text`) and its
    ``;``, CR and LF escaped."""
    for line in comment.split("\n"):
        if not line.startswith(PROVENANCE_COMMENT_PREFIX):
            continue
        body = line[len(PROVENANCE_COMMENT_PREFIX) :]
        for entry in body.split(_ENTRY_SEPARATOR):
            name, sep, source = entry.partition(_FIELD_SEPARATOR)
            if not sep:
                continue
            parsed = parse_provenance_value(_unescape(source, _SOURCE_UNESCAPES))
            at = _escape(_unescape(name, _FIELD_UNESCAPES))
            for key in sorted(parsed):
                values = _split_notes(parsed[key]) if key == "note" else [parsed[key]]
                for value in values:
                    yield f"/{at}/{_escape(key)}", value


def _values(element: dict[str, Any]) -> Iterator[tuple[str, str, _Reading]]:
    """Each ``(pointer, value, reading)`` of *element* read, in key order
    (as the output writes it). Iterative: a merged document's nesting
    cannot exhaust the stack."""
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
            if key in URL_FIELDS:
                yield pointer, node, URL_FIELDS[key]
            elif key == "statement" and parent.get("contentType") == _JSON_CONTENT_TYPE:
                for at, value in _statement_values(node):
                    yield at, value, _NOTE
            elif key == "comment":
                for at, value in _comment_values(node):
                    yield f"{pointer}{at}", value, _NOTE


def _element_name(element: dict[str, Any]) -> str:
    """*element*'s id, masked; for one without, its type."""
    name = element.get("spdxId") or element.get("@id")
    if not name:
        kind = element.get("type") or "an element"
        return masked_given_path(f"({kind} without an id)")
    return masked_given_path(name if isinstance(name, str) else str(name))


def find_graph_credentials(graph: list[dict[str, Any]]) -> list[GraphFinding]:
    """Each distinct value of a read field of *graph* that holds a
    credential (a weak one included), at the first place it stands, in
    graph order: a value stated in two fields is one finding."""
    found: dict[str, GraphFinding] = {}
    for element in graph:
        for pointer, value, reading in _values(element):
            if value in found and not found[value].finding.weak:
                continue
            hits = find_url_credentials(
                value,
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
                _element_name(element), pointer, fingerprint(value), first, value
            )
    return list(found.values())


def check_graph_credentials(
    graph: list[dict[str, Any]], policy: CredentialPolicy
) -> None:
    """Refuse *graph* when a read field holds a credential *policy* does not
    accept: one ``ERROR:`` per distinct value, in graph order, then the
    error. A value accepted (by its fingerprint, or by
    ``policy.allow_all``) is stated as written with a ``WARNING:``; a weak
    one (a parameter of a weak name, an ``ssh`` account name) is only
    warned of. An accepted fingerprint that matches no value found is
    warned of too. *graph* is never changed.

    Raises:
        pitloom.messages.CodedValueError: ``credentials-unsafe/refused``;
            its text and ``args`` name no URL, and it has no context.
    """
    findings = find_graph_credentials(graph)
    refused: list[GraphFinding] = []
    for item in findings:
        if item.finding.weak:
            say_weak(item.value)
        elif policy.accepts_value(item.value):
            say_accepted(item.value, item.fingerprint)
        elif policy.allow_all:
            say_accepted(item.value, None)
        else:
            refused.append(item)
    _warn_stale(policy, findings)
    if refused:
        for item in refused:
            say_refused(item.value, item.element, item.pointer, item.fingerprint)
        raise refused_error(len(refused)) from None


def _warn_stale(policy: CredentialPolicy, findings: list[GraphFinding]) -> None:
    """Warn of each accepted fingerprint that is a prefix of no value's full
    fingerprint among *findings* (the values a run could need to accept)."""
    digests = [full_fingerprint(item.value) for item in findings]
    for entry in sorted(policy.accepted):
        if not any(digest.startswith(entry) for digest in digests):
            say_stale_fingerprint(entry)
