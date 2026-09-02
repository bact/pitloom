# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM format detection (from raw bytes), each format's recommended file
extension, and cross-checking an SBOM's declared subject name/version
against a wheel's own METADATA.

Independent of PEP 770/wheel-embedding mechanics -- see also
:mod:`pitloom._embed_wheel`, which locates an *embedded* SBOM's bytes but
delegates format detection here; `verify-wheel` (post-hoc, on an
already-built wheel) and `embed-wheel` (pre-embed, on an externally
supplied ``--sbom``) both use :func:`check_spdx3_name_version` so the two
call sites can't drift on what counts as a mismatch vs. a skip.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION


def _looks_like_spdx3_jsonld(data: bytes) -> bool:
    """Sniff whether *data* is an SPDX 3 JSON-LD document.

    Unlike :func:`pitloom._embed_wheel._looks_like_pitloom_sbom`, this
    doesn't check for a Pitloom-authored ``Tool``/``SoftwareAgent`` -- it
    only checks the generic JSON-LD shape (``@context`` + ``@graph``) so a
    third-party (non-Pitloom) SPDX3 SBOM embedded via ``--sbom`` is also
    recognized.
    """
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return False
    return (
        isinstance(doc, dict)
        and "@context" in doc
        and isinstance(doc.get("@graph"), list)
    )


#: Recommended file extension per detected SBOM format. Only one exporter
#: (SPDX3 JSON-LD) exists today -- kept as a small dict, not a plugin
#: registry, so a future format just adds an entry rather than needing new
#: infrastructure.
#:
#: Reference for the full convention (artifact `foo-1.0.0.tar.gz` ->
#: SBOM `foo-1.0.0.tar.gz.<ext>`), for when a new format/detector lands:
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
#: Deliberately its OWN literal, NOT derived from `RECOMMENDED_EXTENSIONS`
#: above -- a future format can get an extension-convention entry long
#: before this project has a validator for it, so deriving one from the
#: other would silently mark that format "validated" the moment its
#: extension entry is added. Add a format here only when
#: `validate_wheel.py` actually has a validator wired up for it.
VALIDATED_FORMATS: frozenset[str] = frozenset({"spdx3-jsonld"})


def detect_sbom_format(data: bytes) -> str | None:
    """Return a short format id for *data*, or ``None`` if unrecognized."""
    if _looks_like_spdx3_jsonld(data):
        return "spdx3-jsonld"
    return None


@dataclasses.dataclass(frozen=True)
class _SbomSubjectIdentity:
    """An SBOM's declared subject name/version, or the reason it couldn't
    be extracted."""

    name: str | None
    version: str | None
    error: str | None = None


def _parse_jsonld_graph(data: bytes) -> list[Any] | None:
    """Parse *data* as JSON and return its ``@graph`` list, or ``None`` if
    *data* isn't recognizable JSON-LD (bad JSON, or no list ``@graph``)."""
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError):
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
      (`_build_main_package`, `build()`) for every Pitloom-generated SBOM;
    - otherwise treats that first node itself as the subject -- a
      hand-authored/third-party SBOM (the case ``--sbom`` exists for)
      may declare its subject as the document's root element directly,
      with no intermediate ``software_Sbom`` wrapper; SPDX 3 doesn't
      require one.

    Either way, the resolved subject node's ``type`` must be in
    `_SUBJECT_TYPES` -- a non-package node (e.g. a `SoftwareAgent` that
    happens to carry a `name` field) is rejected with an error rather
    than silently mined for `name`/`software_packageVersion`.

    Returns ``None`` if *data* isn't even recognizable JSON-LD (callers
    should already have checked via `detect_sbom_format`); returns an
    `_SbomSubjectIdentity` with a non-``None`` `.error` and both fields
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
        return _SbomSubjectIdentity(None, None, "no SpdxDocument node found")
    root = spdx_doc.get("rootElement")
    if not isinstance(root, list) or not root or root[0] not in by_id:
        return _SbomSubjectIdentity(
            None, None, "SpdxDocument has no usable rootElement"
        )

    subject = by_id[root[0]]
    if subject.get("type") == "software_Sbom":
        sbom_root = subject.get("rootElement")
        if (
            not isinstance(sbom_root, list)
            or not sbom_root
            or sbom_root[0] not in by_id
        ):
            return _SbomSubjectIdentity(
                None, None, "Sbom node has no usable rootElement"
            )
        subject = by_id[sbom_root[0]]

    subject_type = subject.get("type")
    if subject_type not in _SUBJECT_TYPES:
        return _SbomSubjectIdentity(
            None,
            None,
            f"SBOM subject is a {subject_type!r} node, not a recognized package type",
        )

    name = subject.get("name")
    version = subject.get("software_packageVersion")
    return _SbomSubjectIdentity(
        name if isinstance(name, str) else None,
        version if isinstance(version, str) else None,
    )


def _try_parse_version(raw: str) -> Version | None:
    """``Version(raw)``, or ``None`` on ``InvalidVersion`` -- never raises."""
    try:
        return Version(raw)
    except InvalidVersion:
        return None


def compare_name_version(
    wheel_name: str | None,
    wheel_version: str | None,
    sbom_name: str | None,
    sbom_version: str | None,
) -> tuple[list[str], list[str]]:
    """Compare a wheel's METADATA name/version against an SBOM subject's,
    after PEP 503 (name) / PEP 440 (version) normalization.

    Returns ``(mismatches, warnings)`` as human-readable fragments (no
    wheel-name prefix, no `WARNING:`/`ERROR:` tag) -- callers decide how
    to log/report them and at what severity. An unparseable version on
    either side, or a missing name/version on *either* side, yields a
    `warnings` fragment (skip that half of the check) rather than a
    `mismatches` one -- "can't compare" is a different finding from
    "compared and differs," and is never silently dropped: a missing
    wheel-side value warns exactly like a missing SBOM-side one.
    """
    mismatches: list[str] = []
    warnings: list[str] = []

    if wheel_name and sbom_name:
        if canonicalize_name(wheel_name) != canonicalize_name(sbom_name):
            mismatches.append(
                f"name: wheel declares {wheel_name!r}, SBOM declares {sbom_name!r}"
            )
    else:
        warnings.append(_missing_side_warning("name", wheel_name, sbom_name))

    if wheel_version and sbom_version:
        wheel_v = _try_parse_version(wheel_version)
        sbom_v = _try_parse_version(sbom_version)
        if wheel_v is None:
            warnings.append(
                f"wheel METADATA version {wheel_version!r} isn't a valid PEP "
                "440 version; skipping version cross-check"
            )
        elif sbom_v is None:
            warnings.append(
                f"SBOM subject version {sbom_version!r} isn't a valid PEP "
                "440 version; skipping version cross-check"
            )
        elif wheel_v != sbom_v:
            mismatches.append(
                f"version: wheel declares {wheel_version!r}, SBOM declares "
                f"{sbom_version!r}"
            )
    else:
        warnings.append(_missing_side_warning("version", wheel_version, sbom_version))

    return mismatches, warnings


def _missing_side_warning(
    field: str, wheel_value: str | None, sbom_value: str | None
) -> str:
    """Build the "can't compare" warning fragment for `field` ("name" or
    "version") when at least one of *wheel_value*/*sbom_value* is falsy --
    names which side(s) are missing so a skip is never unexplained."""
    if not wheel_value and not sbom_value:
        return f"neither the wheel nor the SBOM subject has a {field} to cross-check"
    if not wheel_value:
        return f"wheel METADATA has no {field} to cross-check"
    return f"SBOM subject has no {field} to cross-check"


def format_name_version_mismatch(subject: str, mismatches: list[str]) -> str:
    """Format `compare_name_version`/`check_spdx3_name_version`'s
    `mismatches` list into one human-readable line prefixed with
    *subject* (typically a wheel filename) -- the shared wording both
    `verify-wheel` (`cli/commands/verify_wheel.py`) and `embed-wheel`
    (`embed.py`'s pre-embed enforcement) log/raise, so a wording tweak
    can't silently diverge between the two.
    """
    return f"{subject}: SBOM/wheel " + "; ".join(mismatches)


def check_spdx3_name_version(
    wheel_name: str | None,
    wheel_version: str | None,
    sbom_data: bytes,
    sbom_format: str | None,
) -> tuple[list[str], list[str]]:
    """Cross-check an embedded/to-be-embedded SBOM's declared subject
    name/version against *wheel_name*/*wheel_version* (a wheel's own
    METADATA).

    Returns ``(mismatches, warnings)``, same shape as
    :func:`compare_name_version`. Only ``"spdx3-jsonld"`` is supported --
    any other *sbom_format* (including ``None``, unrecognized) or a
    graph shape :func:`extract_spdx3_subject_identity` can't follow
    yields a single `warnings` fragment naming why and an empty
    `mismatches` -- "couldn't check" is never escalated to a mismatch.
    """
    if sbom_format != "spdx3-jsonld":
        return [], [
            f"cannot cross-check name/version for unsupported SBOM format "
            f"{sbom_format!r}"
        ]

    identity = extract_spdx3_subject_identity(sbom_data)
    if identity is None or identity.error is not None:
        reason = identity.error if identity is not None else "unrecognized SBOM content"
        return [], [f"cannot cross-check SBOM name/version ({reason})"]

    return compare_name_version(
        wheel_name, wheel_version, identity.name, identity.version
    )
