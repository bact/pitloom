# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM format detection (from raw bytes), each format's recommended file
extension, and cross-checking an SBOM's declared subject name/version
against a wheel's own METADATA.

Independent of PEP 770/wheel-embedding mechanics; see
:mod:`pitloom._wheel_sbom_location` for locating an *embedded* SBOM's bytes.
`verify-wheel` (on an already-built wheel) and `embed-wheel` (on an
externally supplied ``--sbom``, before embedding) both use
:func:`check_spdx3_name_version`, so they agree on what counts as a mismatch
and what a skip. It returns data, not prose: each mismatch an
:class:`~pitloom.messages.wheel_sboms.IdentityMismatch`, each check not made
a :class:`~pitloom.messages.wheel_sboms.CrossCheckGap`, which the catalogue
says (:func:`~pitloom.messages.wheel_sboms.say_identity_mismatches`,
:func:`~pitloom.messages.wheel_sboms.warn_cross_check_gaps`).
"""

from __future__ import annotations

import codecs
import dataclasses
import json
from pathlib import Path
from typing import Any, NamedTuple

from packaging.utils import canonicalize_name

from pitloom.core.given_file import read_given_bytes
from pitloom.core.internal_error import reraise_internal
from pitloom.core.pep440 import parse_version
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.messages import CodedValueError
from pitloom.messages.files import SBOM_USE, file_unreadable_error
from pitloom.messages.targets import (
    SBOM_DUPLICATE_KEY_LINE,
    SBOM_GRAPH_ELEMENT_LINE,
    SBOM_GRAPH_NOT_LIST_LINE,
    SBOM_INVALID,
    SBOM_WRONG_FORMAT,
)
from pitloom.messages.text import JSON_MALFORMED
from pitloom.messages.wheel_sboms import (
    GAP_BOTH_PART_MISSING,
    GAP_NO_DOCUMENT,
    GAP_NO_DOCUMENT_ROOT,
    GAP_NO_SBOM_ROOT,
    GAP_NO_WHEEL_IDENTITY,
    GAP_NOT_SPDX3,
    GAP_SBOM_PART_MISSING,
    GAP_SBOM_VERSION_INVALID,
    GAP_SUBJECT_NOT_PACKAGE,
    GAP_WHEEL_PART_MISSING,
    GAP_WHEEL_VERSION_INVALID,
    CrossCheckGap,
    IdentityMismatch,
)


def _looks_like_spdx3_jsonld(data: bytes) -> bool:
    """Sniff whether *data* is an SPDX 3 JSON-LD document.

    Unlike :func:`pitloom._embed_stale.looks_like_pitloom_sbom`, this
    doesn't check for a Pitloom-authored ``Tool``/``SoftwareAgent`` -- it
    only checks the generic JSON-LD shape (``@context`` + ``@graph``) so a
    third-party (non-Pitloom) SPDX3 SBOM embedded via ``--sbom`` is also
    recognised.
    """
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        reraise_internal(exc)
        return False
    return (
        isinstance(doc, dict)
        and "@context" in doc
        and isinstance(doc.get("@graph"), list)
    )


#: Recommended file extension per detected SBOM format; only SPDX 3 JSON-LD
#: is detected.
#:
#: The full convention (artifact `foo-1.0.0.tar.gz` ->
#: SBOM `foo-1.0.0.tar.gz.<ext>`):
#:   CycloneDX JSON    .cdx.json
#:   CycloneDX XML     .cdx.xml
#:   SPDX tag:value    .spdx
#:   SPDX JSON         .spdx.json
#:   SPDX XML          .spdx.xml
#:   SPDX YAML         .spdx.yml (or .yaml)
#:   SPDX RDF/XML      .spdx.rdf
#:   SPDX 3 JSON       .spdx3.json
#:   SPDX 3 RDF/XML    .spdx3.rdf
RECOMMENDED_EXTENSIONS: dict[str, str] = {"spdx3-jsonld": SPDX3_JSONLD_EXTENSION}

#: Formats `validate-wheel` has a registered schema/SHACL validator for.
#: Its own literal, not derived from `RECOMMENDED_EXTENSIONS`: a format can
#: have a recommended extension without a validator. Add a format here only
#: when `validate_wheel.py` has a validator wired up for it.
VALIDATED_FORMATS: frozenset[str] = frozenset({"spdx3-jsonld"})


def detect_sbom_format(data: bytes) -> str | None:
    """Return a short format id for *data*, or ``None`` if unrecognised."""
    if _looks_like_spdx3_jsonld(data):
        return "spdx3-jsonld"
    return None


@dataclasses.dataclass(frozen=True)
class _SbomSubjectIdentity:
    """An SBOM's declared subject name/version, or why it couldn't be
    extracted (*gap*)."""

    name: str | None
    version: str | None
    gap: CrossCheckGap | None = None


def _parse_jsonld_graph(data: bytes) -> list[Any] | None:
    """Parse *data* as JSON and return its ``@graph`` list, or ``None`` if
    *data* isn't recognisable JSON-LD (bad JSON, or no list ``@graph``)."""
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        reraise_internal(exc)
        return None
    graph = doc.get("@graph") if isinstance(doc, dict) else None
    return graph if isinstance(graph, list) else None


#: Node types this extractor accepts as an SBOM's actual subject, once the
#: SpdxDocument/software_Sbom hop(s) above are resolved. Deliberately an
#: allowlist, not "anything with a name field" -- a SoftwareAgent/Person/
#: CreationInfo node can carry a `name` too, and treating one of those as
#: the subject would silently cross-check against the wrong identity.
_SUBJECT_TYPES: frozenset[str] = frozenset({"software_Package", "ai_AIPackage"})


def extract_spdx3_subject_identity(data: bytes) -> _SbomSubjectIdentity | None:
    """Extract the subject package's ``name``/``software_packageVersion``
    from an SPDX 3 JSON-LD SBOM's ``@graph``.

    Follows ``SpdxDocument.rootElement[0]`` to a node, then:

    - if that node is a ``software_Sbom``, follows *its own*
      ``rootElement[0]`` one more hop to the actual subject -- the
      two-hop chain :mod:`pitloom.assemble.spdx3.document` builds
      (`build_main_package`, `build()`) for every Pitloom-generated SBOM;
    - otherwise treats that first node itself as the subject -- a
      hand-authored/third-party SBOM (the case ``--sbom`` exists for)
      may declare its subject as the document's root element directly,
      with no intermediate ``software_Sbom`` wrapper; SPDX 3 doesn't
      require one.

    Either way, the resolved subject node's ``type`` must be in
    `_SUBJECT_TYPES` -- a non-package node (e.g. a `SoftwareAgent` that
    happens to carry a `name` field) is rejected with an error rather
    than silently mined for `name`/`software_packageVersion`.

    Returns ``None`` if *data* isn't even recognisable JSON-LD (callers
    should already have checked via `detect_sbom_format`); returns an
    `_SbomSubjectIdentity` with a non-``None`` `.gap` and both fields
    ``None`` if the graph shape doesn't match what's expected (missing
    `SpdxDocument` node, empty/dangling `rootElement`, a resolved subject
    of the wrong type, etc.) -- callers must treat that as "skip the
    check, warn why," not as a mismatch.

    Only the first element of each ``rootElement`` list is followed --
    production code (`document.py`) always constructs single-element
    lists; a hand-authored/third-party SBOM with multiple SBOM subjects is
    not supported by this extractor (a documented limitation, not a
    silent wrong answer).

    A subject with no ``software_packageVersion`` at all (e.g. an
    `ai_AIPackage` node, which doesn't carry that field) yields
    ``version=None`` without being an error -- the caller's version
    comparison half is simply skipped.
    """
    graph = _parse_jsonld_graph(data)
    if graph is None:
        return None

    by_id: dict[str, dict[str, Any]] = {
        node["spdxId"]: node
        for node in graph
        if isinstance(node, dict) and isinstance(node.get("spdxId"), str)
    }

    spdx_doc = next(
        (n for n in graph if isinstance(n, dict) and n.get("type") == "SpdxDocument"),
        None,
    )
    if spdx_doc is None:
        return _SbomSubjectIdentity(None, None, CrossCheckGap(GAP_NO_DOCUMENT))
    root = spdx_doc.get("rootElement")
    if not isinstance(root, list) or not root or root[0] not in by_id:
        return _SbomSubjectIdentity(None, None, CrossCheckGap(GAP_NO_DOCUMENT_ROOT))

    subject = by_id[root[0]]
    if subject.get("type") == "software_Sbom":
        sbom_root = subject.get("rootElement")
        if (
            not isinstance(sbom_root, list)
            or not sbom_root
            or sbom_root[0] not in by_id
        ):
            return _SbomSubjectIdentity(None, None, CrossCheckGap(GAP_NO_SBOM_ROOT))
        subject = by_id[sbom_root[0]]

    subject_type = subject.get("type")
    if subject_type not in _SUBJECT_TYPES:
        return _SbomSubjectIdentity(
            None, None, CrossCheckGap(GAP_SUBJECT_NOT_PACKAGE, value=subject_type)
        )

    name = subject.get("name")
    version = subject.get("software_packageVersion")
    return _SbomSubjectIdentity(
        name if isinstance(name, str) else None,
        version if isinstance(version, str) else None,
    )


def compare_name_version(
    wheel_name: str | None,
    wheel_version: str | None,
    sbom_name: str | None,
    sbom_version: str | None,
) -> tuple[list[IdentityMismatch], list[CrossCheckGap]]:
    """Compare a wheel's METADATA name/version against an SBOM subject's,
    after PEP 503 (name) / PEP 440 (version) normalisation.

    Returns ``(mismatches, gaps)``, name before version: data, not text --
    callers say them (:mod:`pitloom.messages.wheel_sboms`) at the severity
    they choose. An unparseable version on either side, or a missing
    name/version on *either* side, yields a gap (that half of the check is
    skipped) rather than a mismatch -- "can't compare" is a different
    finding from "compared and differs," and is never silently dropped: a
    missing wheel-side value is a gap exactly like a missing SBOM-side one;
    a wheel with neither is one gap.
    """
    if not wheel_name and not wheel_version:
        return [], [CrossCheckGap(GAP_NO_WHEEL_IDENTITY)]
    mismatches: list[IdentityMismatch] = []
    gaps: list[CrossCheckGap] = []

    if wheel_name and sbom_name:
        if canonicalize_name(wheel_name) != canonicalize_name(sbom_name):
            mismatches.append(IdentityMismatch("name", wheel_name, sbom_name))
    else:
        gaps.append(_missing_side_gap("name", wheel_name, sbom_name))

    if wheel_version and sbom_version:
        wheel_v = parse_version(wheel_version)
        sbom_v = parse_version(sbom_version)
        if wheel_v is None:
            gaps.append(CrossCheckGap(GAP_WHEEL_VERSION_INVALID, value=wheel_version))
        elif sbom_v is None:
            gaps.append(CrossCheckGap(GAP_SBOM_VERSION_INVALID, value=sbom_version))
        elif wheel_v != sbom_v:
            mismatches.append(IdentityMismatch("version", wheel_version, sbom_version))
    else:
        gaps.append(_missing_side_gap("version", wheel_version, sbom_version))

    return mismatches, gaps


def _missing_side_gap(
    part: str, wheel_value: str | None, sbom_value: str | None
) -> CrossCheckGap:
    """The gap of *part* (``name`` or ``version``) when at least one of
    *wheel_value*/*sbom_value* is falsy -- naming which side(s) lack it, so
    a skip is never unexplained."""
    if not wheel_value and not sbom_value:
        return CrossCheckGap(GAP_BOTH_PART_MISSING, part=part)
    if not wheel_value:
        return CrossCheckGap(GAP_WHEEL_PART_MISSING, part=part)
    return CrossCheckGap(GAP_SBOM_PART_MISSING, part=part)


def check_spdx3_name_version(
    wheel_name: str | None,
    wheel_version: str | None,
    sbom_data: bytes,
    sbom_format: str | None,
) -> tuple[list[IdentityMismatch], list[CrossCheckGap]]:
    """Cross-check an embedded/to-be-embedded SBOM's declared subject
    name/version against *wheel_name*/*wheel_version* (a wheel's own
    METADATA).

    Returns ``(mismatches, gaps)``, as :func:`compare_name_version`. Only
    ``"spdx3-jsonld"`` is supported -- any other *sbom_format* (including
    ``None``, unrecognised) or a graph shape
    :func:`extract_spdx3_subject_identity` can't follow yields a single gap
    naming why and no mismatch -- "couldn't check" is never escalated to a
    mismatch.
    """
    if sbom_format != "spdx3-jsonld":
        return [], [CrossCheckGap(GAP_NOT_SPDX3)]

    identity = extract_spdx3_subject_identity(sbom_data)
    if identity is None:
        # detect_sbom_format() read it as SPDX 3 JSON-LD, so this is not
        # reached; said as the format's gap all the same.
        return [], [CrossCheckGap(GAP_NOT_SPDX3)]
    if identity.gap is not None:
        return [], [identity.gap]

    return compare_name_version(
        wheel_name, wheel_version, identity.name, identity.version
    )


class _NonJsonConstant(ValueError):
    """``NaN``, ``Infinity`` or ``-Infinity`` in a given SBOM: its text is the
    failure (the DETAIL) of the ``json-malformed`` line
    :func:`refuse_unusable_given_sbom` says."""


def _reject_constant(name: str) -> object:
    """``json.loads``' hook for ``NaN``/``Infinity``: Python reads them, RFC 8259
    does not have them."""
    raise _NonJsonConstant(f"{name} is not a JSON value")


class _DuplicateKey(Exception):
    """A JSON object of a given SBOM names one key twice."""


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """The JSON object of *pairs*, each key once.

    Raises:
        _DuplicateKey: A key is given twice: Python's reader keeps the last
            value, another reader may keep the first, so the value checked
            (a URL credential, a name) need not be the one another reader
            of the embedded bytes sees.
    """
    document = dict(pairs)
    if len(document) != len(pairs):
        raise _DuplicateKey
    return document


def refuse_unusable_given_sbom(sbom_path: Path | str, text: str) -> dict[str, Any]:
    """Refuse an SBOM file the user named that cannot be what they gave it as;
    else return its JSON object.

    *text* is the file's content. Raises ``ValueError`` when it is not valid
    JSON (empty included; ``NaN`` and ``Infinity`` are not JSON) or is JSON but
    not an object (``json-malformed``), has an object naming one key twice
    or an ``@graph`` that is not a list of objects (``sbom-invalid``;
    :func:`_unique_keys`, :func:`_require_graph_list`), or is named
    ``.spdx3.json`` and is not SPDX 3 JSON-LD (``sbom-wrong-format``). A
    JSON object in another format under another name (a CycloneDX
    ``bom.json``) is left to the name/version cross-check, which skips it with
    a ``WARNING:``.
    """
    try:
        document = json.loads(
            text, parse_constant=_reject_constant, object_pairs_hook=_unique_keys
        )
    except _DuplicateKey:
        raise CodedValueError(
            SBOM_INVALID, line=SBOM_DUPLICATE_KEY_LINE, file=sbom_path
        ) from None
    except (ValueError, RecursionError) as exc:
        reraise_internal(exc)
        raise CodedValueError(
            JSON_MALFORMED, file=sbom_path, use=SBOM_USE, failure=exc
        ) from exc
    if not isinstance(document, dict):
        raise CodedValueError(JSON_MALFORMED, file=sbom_path, use=SBOM_USE)
    # Before the format: an @graph of the wrong shape is a broken SPDX 3
    # document, whatever the name, not another format.
    _require_graph_list(document, sbom_path)
    if str(sbom_path).lower().endswith(SPDX3_JSONLD_EXTENSION) and (
        detect_sbom_format(text.encode("utf-8")) != "spdx3-jsonld"
    ):
        raise CodedValueError(SBOM_WRONG_FORMAT, file=sbom_path)
    return document


def _require_graph_list(document: dict[str, Any], sbom_path: Path | str) -> None:
    """Raise ``ValueError`` when the JSON object *document*, read from
    *sbom_path*, has an ``@graph`` that is not a list, or holds a non-object
    (``sbom-invalid``, naming *sbom_path*): no SPDX 3 reader can follow it,
    and the deserialiser would leak a ``TypeError``. No ``@graph`` (another
    format) passes."""
    graph = document.get("@graph", [])
    if not isinstance(graph, list):
        raise CodedValueError(
            SBOM_INVALID, line=SBOM_GRAPH_NOT_LIST_LINE, file=sbom_path
        )
    if not all(isinstance(element, dict) for element in graph):
        raise CodedValueError(
            SBOM_INVALID, line=SBOM_GRAPH_ELEMENT_LINE, file=sbom_path
        )


class GivenSbom(NamedTuple):
    """An SBOM file the user named, as :func:`read_given_sbom` read it."""

    #: Its bytes decoded as UTF-8, a byte order mark dropped.
    text: str
    #: Its JSON object.
    document: dict[str, Any]
    #: Whether a UTF-8 byte order mark was dropped (JSON text must not
    #: carry one); the caller that writes *text* out says so.
    dropped_bom: bool


def read_given_sbom(sbom_path: Path | str) -> GivenSbom:
    """The SBOM file the user named at *sbom_path*, for ``embed-wheel
    --sbom`` and ``loom id import`` alike: its bytes decoded as strict UTF-8
    and nothing else (no newline translation; UTF-16 and -32 are refused,
    as RFC 8259 section 8.1 wants UTF-8), a UTF-8 byte order mark dropped,
    and its JSON object.

    Raises:
        pitloom.messages.CodedFileNotFoundError: Nothing is there, or not a
            regular file (``input-not-found``).
        ValueError: The file cannot be read (``file-unreadable``), is over
            the read cap (``over-cap``), is not UTF-8
            (``file-unreadable/not-utf8``), or is refused by
            :func:`refuse_unusable_given_sbom`.
    """
    raw = read_given_bytes(sbom_path, kind="SBOM file", use=SBOM_USE)
    dropped_bom = raw.startswith(codecs.BOM_UTF8)
    try:
        text = raw[len(codecs.BOM_UTF8) if dropped_bom else 0 :].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise file_unreadable_error(exc, file=sbom_path, use=SBOM_USE) from exc
    return GivenSbom(text, refuse_unusable_given_sbom(sbom_path, text), dropped_bom)
