# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 JSON-LD exporter for generating SBOM documents."""

from __future__ import annotations

import io
import json
from collections import defaultdict
from typing import TYPE_CHECKING, Any, NamedTuple

import rfc8785
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._sbom_io import write_text_lf
from pitloom.core.canonical_json import canonical_json_indented
from pitloom.core.file_hash import HexDigests
from pitloom.core.lfs_pointer import size_text
from pitloom.core.license_individuals import INDIVIDUAL_BY_COMPACT_NAME
from pitloom.export.spdx3_describe import describe_graph_element, describe_value

if TYPE_CHECKING:
    from pitloom.core.lfs_pointer import LfsPointer

# Pitloom's own file-naming convention for this exporter's output -- SPDX 3
# itself doesn't mandate an extension. Canonical home for every module that
# needs to name or recognize an SPDX3 JSON-LD SBOM file.
SPDX3_JSONLD_EXTENSION = ".spdx3.json"

# Lower value = earlier in @graph. Types not listed here get priority 4.
# Order rationale:
#   0 CreationInfo  -- blank node referenced by every element; must resolve first
#   1 SpdxDocument  -- document envelope; carries profileConformance for validation
#   2 Bom           -- Core profile BOM root (base class of software_Sbom)
#   3 software_Sbom -- Software profile BOM; root element pointer and sbomType
_GRAPH_TYPE_PRIORITY: dict[str, int] = {
    "CreationInfo": 0,
    "SpdxDocument": 1,
    "Bom": 2,
    "software_Sbom": 3,
}


def require_spdx_id(element: spdx3.Element) -> str:
    """Return *element*'s ``spdxId``, narrowing away the ``None`` case.

    ``spdxId`` is typed ``str | None`` upstream because the SHACL model
    allows an Element to be constructed without one, but every element
    pitloom builds is always given an explicit ``spdxId`` at construction
    time (see :func:`pitloom.core.models.generate_spdx_id`). This helper
    exists only to satisfy mypy at the many call sites that pass an
    element's ``spdxId`` on to APIs expecting a plain ``str``.

    Raises:
        ValueError: If *element* has no ``spdxId`` assigned, which would
            indicate a bug in how the element was constructed.
    """
    if element.spdxId is None:
        raise ValueError(f"{describe_value(element)} has no spdxId assigned")
    return str(element.spdxId)


def sha256_hash(hex_digest: str, *, comment: str | None = None) -> spdx3.Hash:
    """Build a ``verifiedUsing`` SHA-256 ``Hash`` element for *hex_digest*.

    Single source of truth for the ``algorithm=sha256`` convention used by
    every ``verifiedUsing`` assertion pitloom emits (package files, dependency
    packages, and the main package's own Merkle-root hash), so the convention
    only needs fixing in one place.
    """
    return _hash(spdx3.HashAlgorithm.sha256, hex_digest, comment)


def sha512_hash(hex_digest: str, *, comment: str | None = None) -> spdx3.Hash:
    """Build a ``verifiedUsing`` SHA-512 ``Hash`` element for *hex_digest*:
    the :func:`sha256_hash` convention, ``algorithm=sha512``."""
    return _hash(spdx3.HashAlgorithm.sha512, hex_digest, comment)


def file_hashes(digests: HexDigests) -> list[spdx3.Hash]:
    """The ``verifiedUsing`` of a file whose bytes Pitloom read (or of the
    package standing for it): its SHA-256, then its SHA-512 when known, in
    that order. A dependency's copied hash or a Merkle root is not a file's
    digest: build those with :func:`sha256_hash` alone."""
    hashes = [sha256_hash(digests.sha256)]
    if digests.sha512 is not None:
        hashes.append(sha512_hash(digests.sha512))
    return hashes


def lfs_pointer_hashes(pointer: LfsPointer) -> list[spdx3.Hash]:
    """The ``verifiedUsing`` of a checkout's Git LFS pointer, whose content
    Pitloom did not read: the ``oid`` as the SHA-256, no SHA-512, and a
    comment saying so with the stated size (SPDX 3 has no file size)."""
    comment = f"Git LFS pointer oid; content not read; size {size_text(pointer.size)}"
    return [sha256_hash(pointer.oid, comment=comment)]


def _hash(algorithm: str, hex_digest: str, comment: str | None) -> spdx3.Hash:
    hash_element = spdx3.Hash(algorithm=algorithm, hashValue=hex_digest.lower())
    if comment:
        hash_element.comment = comment
    return hash_element


def _graph_sort_key(element: dict[str, Any]) -> tuple[int, str, str]:
    """Return a deterministic sort key for a @graph element.

    Primary key: type-priority tier (see _GRAPH_TYPE_PRIORITY).
    Secondary key: spdxId or @id, lexicographic -- puts root Package-1 before
    Package-2, etc., and gives stable order within every other type.
    Tertiary key: JCS canonical form of the element, used only when two
    elements share the same priority and identifier (e.g. conflicting
    duplicates retained by :func:`_deduplicate_named_elements`).
    """
    priority = _GRAPH_TYPE_PRIORITY.get(element.get("type", ""), 4)
    node_id = element.get("spdxId") or element.get("@id") or ""
    content_key = rfc8785.dumps(element).decode("utf-8")
    return (priority, node_id, content_key)


def _creation_info_fingerprint(element: dict[str, Any]) -> tuple[str, ...]:
    """Return a content-based fingerprint for a CreationInfo @graph entry.

    Covers all user-visible fields while excluding the blank-node @id, which
    is an implementation artefact assigned at serialization time and not part
    of the semantic content.  List fields are sorted so that two nodes whose
    createdBy/createdUsing lists differ only in order are still considered
    identical.
    """
    return (
        element.get("specVersion", ""),
        element.get("created", ""),
        ",".join(sorted(element.get("createdBy", []))),
        ",".join(sorted(element.get("createdUsing", []))),
        element.get("comment", ""),
    )


def _deduplicate_creation_infos(
    graph: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Consolidate CreationInfo blank nodes with identical content.

    When SPDX fragments from different sources are merged into the same
    object set, each fragment may contribute its own CreationInfo blank node
    carrying identical data.  Keeping only one canonical node per unique
    content fingerprint eliminates redundancy and is a prerequisite for
    reproducibility.

    Returns a new graph list with duplicates and any CreationInfo without
    an ``@id`` removed, and every element's ``creationInfo`` reference to a
    removed node redirected to the surviving canonical node.
    """
    # First pass: elect one canonical @id per unique fingerprint; record
    # every other @id that carries the same content as a redirect target.
    # A CreationInfo without an @id (nothing refers to it) is dropped: it
    # has no identity to elect or redirect.
    canonical: dict[tuple[str, ...], str] = {}  # fingerprint -> kept @id
    redirect: dict[str, str] = {}  # dropped @id -> canonical @id

    for element in graph:
        blank_id = element.get("@id")
        if element.get("type") != "CreationInfo" or not blank_id:
            continue
        fp = _creation_info_fingerprint(element)
        if fp in canonical:
            redirect[blank_id] = canonical[fp]
        else:
            canonical[fp] = blank_id

    orphans = [e for e in graph if e.get("type") == "CreationInfo" and not e.get("@id")]
    if not redirect and not orphans:
        return graph

    # Second pass: drop duplicate and orphan nodes and rewrite the
    # references to a dropped one (an element's ``creationInfo`` only: any
    # other string equal to a blank-node id is plain text).
    def _remap(element: dict[str, Any]) -> dict[str, Any]:
        reference = element.get("creationInfo")
        if not isinstance(reference, str) or reference not in redirect:
            return element
        return {**element, "creationInfo": redirect[reference]}

    return [
        _remap(element)
        for element in graph
        if element.get("type") != "CreationInfo"
        or (element.get("@id") and element["@id"] not in redirect)
    ]


def _deduplicate_named_elements(
    graph: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove exact-duplicate named elements that share the same spdxId.

    When SPDX fragments are merged, the same named element (e.g. a shared
    licence text or a common dependency package) may appear more than once
    with an identical spdxId.  An element is removed only when every field
    of every copy is semantically identical to the first copy seen (deep
    JSON-object equality, key-ordering-independent) -- the 100 % certainty
    threshold.  If any two copies with the same spdxId differ in even one
    field, all copies are retained unchanged so that no data is silently lost.

    Blank nodes (CreationInfo, which uses ``@id`` instead of ``spdxId``) are
    handled separately by :func:`_deduplicate_creation_infos` and are passed
    through here without modification.
    """
    # Group elements by spdxId; elements without spdxId pass straight through.
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    no_id: list[dict[str, Any]] = []

    for element in graph:
        spdx_id = element.get("spdxId")
        if spdx_id:
            groups[spdx_id].append(element)
        else:
            no_id.append(element)

    result: list[dict[str, Any]] = list(no_id)
    for copies in groups.values():
        if len(copies) == 1:
            result.append(copies[0])
            continue
        # Python dict == performs deep equality with key-order independence for
        # nested dicts, which is the right semantics for JSON objects.
        if all(c == copies[0] for c in copies[1:]):
            result.append(copies[0])  # all identical -- keep one
        else:
            result.extend(copies)  # conflict -- retain all, do not guess
    return result


def _check_no_duplicate_spdx_ids(graph: list[dict[str, Any]]) -> None:
    """Raise ``RuntimeError`` if two elements of *graph* share a
    ``spdxId`` after :func:`_deduplicate_named_elements` has run.

    Runs on that pass's output, not on :attr:`Spdx3JsonExporter.object_set`:
    byte-identical same-id elements (``set_model()`` called twice, a file
    added as both input and training dataset) are expected and collapse to
    one copy. What reaches here is the "conflict, retain all" branch: same-id
    elements that differ in content. A last-resort net for what
    :class:`~pitloom.id_registry.IdRegistrySession` claims exist to prevent;
    see ``working-docs/implementation/id-registry-autosync.md``.
    """
    seen: dict[str, dict[str, Any]] = {}
    for element in graph:
        spdx_id = element.get("spdxId")
        if not spdx_id:
            continue
        first = seen.get(spdx_id)
        if first is not None:
            raise RuntimeError(
                f"Duplicate spdxId {spdx_id!r}: "
                f"{describe_graph_element(first)} and "
                f"{describe_graph_element(element)}"
            )
        seen[spdx_id] = element


def _resolve_element_name(el: dict[str, Any], spdx_id: str) -> str:
    """Derive human-friendly name for an SPDX element."""
    name = el.get("name")
    if not name:
        name = el.get("simplelicensing_licenseExpression") or el.get("description")
    if not name:
        name = spdx_id.split("#")[-1]
    return name if isinstance(name, str) else str(name)


def _build_id_to_name_map(graph: list[dict[str, Any]]) -> dict[str, str]:
    """Build mapping from spdxId to human-readable element name."""
    id_to_name: dict[str, str] = {
        name: individual.spdx_name
        for name, individual in INDIVIDUAL_BY_COMPACT_NAME.items()
    }
    for el in graph:
        spdx_id = el.get("spdxId") or el.get("@id")
        if spdx_id:
            id_to_name[spdx_id] = _resolve_element_name(el, spdx_id)
    return id_to_name


def _annotate_single_relationship(
    node: dict[str, Any], id_to_name: dict[str, str]
) -> None:
    """Format and set description on a relationship node, unless it already
    has one (an empty one included)."""
    if "description" in node:
        return
    rel_type = node.get("relationshipType")
    from_id = node.get("from")
    to_ids = node.get("to")
    if not (rel_type and from_id and isinstance(to_ids, list)):
        return
    from_name = id_to_name.get(from_id, from_id.rsplit("#", maxsplit=1)[-1])
    to_names = [
        id_to_name.get(str(tid)) or str(tid).rsplit("#", maxsplit=1)[-1]
        for tid in to_ids
    ]
    node["description"] = f"{from_name} {rel_type}: {', '.join(to_names)}"


def _annotate_relationships(graph: list[dict[str, Any]]) -> None:
    """Add a descriptive 'description' field to Relationship elements
    to ease human reading.

    Format: <name of from Element> <relationship type>: <name of to Elements>
    """
    id_to_name = _build_id_to_name_map(graph)
    for node in graph:
        if isinstance(node, dict) and "relationshipType" in node:
            _annotate_single_relationship(node, id_to_name)


class AgentKey(NamedTuple):
    """An Agent's identity in :class:`Spdx3JsonExporter`'s Agent index;
    build one with :func:`agent_key`."""

    agent_type: str
    name: str
    email: str
    scope: str


def agent_key(
    agent_cls: type[spdx3.Agent],
    name: str | None,
    email: str | None,
    scope: str = "",
) -> AgentKey:
    """The identity two Agents share when they are the same agent: the
    SPDX 3 class (a Person and an Organization of one name are two agents),
    the stripped name and email, and *scope* (e.g. the package a
    contributor group belongs to)."""
    return AgentKey(
        agent_cls.__name__, (name or "").strip(), (email or "").strip(), scope
    )


class Spdx3JsonExporter:
    """Exports SPDX 3 data structures to JSON-LD format using spdx-python-model."""

    def __init__(self) -> None:
        self.object_set = spdx3.SHACLObjectSet()
        # Maps (kind, value) -> spdxId for licence deduplication: kind is
        # "expression" or "text", so the same string as each stays apart.
        self._license_index: dict[tuple[str, str], str] = {}
        # Maps an agent_key() -> spdxId, for deduplicating Agents built
        # from external metadata (e.g. two dependencies sharing an author).
        self._agent_index: dict[AgentKey, str] = {}
        #: spdxIds of packages built without an ID registry lookup because
        #: another package of this document owns their name (see
        #: :mod:`pitloom.assemble.spdx3._package_ids`). Run auto-harvest
        #: neither counts nor writes them.
        self.registry_non_readers: set[str] = set()
        #: spdxId -> (compact type, raw key) the document's registry
        #: lookups recorded (``IdRegistrySession.recorded_keys``): run
        #: auto-harvest writes each element under its id's key here, else
        #: under its name. Empty when no registry applies.
        self.registry_keys: dict[str, tuple[str, str]] = {}

    def add_creation_info(self, creation_info: spdx3.CreationInfo) -> None:
        """Add creation info to the document.

        Args:
            creation_info: The CreationInfo object
        """
        self.object_set.add(creation_info)

    def add_person(self, person: spdx3.Person) -> None:
        """Add a person to the document.

        Args:
            person: The Person object
        """
        self.object_set.add(person)

    def add_agent(self, agent: spdx3.Agent, *, key: AgentKey | None = None) -> None:
        """Add a creator Agent (Person, Organization, SoftwareAgent, or the
        generic Agent).

        Args:
            agent: Any ``Agent`` subclass used in ``CreationInfo.createdBy``
                or elsewhere (e.g. a dependency's ``suppliedBy``).
            key: Optional dedup key from :func:`agent_key`. When given,
                updates the internal agent index so a subsequent
                :meth:`find_agent` call with the same key returns this
                agent's spdxId instead of a caller minting a duplicate.
        """
        self.object_set.add(agent)
        if key:
            self._agent_index[key] = require_spdx_id(agent)

    def find_agent(self, key: AgentKey) -> str | None:
        """Return the spdxId of an existing Agent registered under *key* via
        :meth:`add_agent`, or ``None`` if not yet added."""
        return self._agent_index.get(key)

    def add_package(self, package: spdx3.software_Package) -> None:
        """Add a software package to the document.

        Args:
            package: The software_Package object
        """
        self.object_set.add(package)

    def add_file(self, file_obj: spdx3.software_File) -> None:
        """Add a software file to the document.

        Args:
            file_obj: The software_File object
        """
        self.object_set.add(file_obj)

    def find_license(self, kind: str, value: str) -> str | None:
        """Return the spdxId of an existing licence element of *kind*
        (``"expression"`` for a ``LicenseExpression``, ``"text"`` for a
        ``SimpleLicensingText``) holding *value*, or ``None``.

        Args:
            kind: ``"expression"`` or ``"text"``.
            value: The expression, or the text stripped (a text is indexed
                by its stripped form, though stored as written).
        """
        return self._license_index.get((kind, value))

    def add_license(
        self,
        license_element: (
            spdx3.simplelicensing_LicenseExpression
            | spdx3.simplelicensing_SimpleLicensingText
        ),
        *,
        key: tuple[str, str] | None = None,
    ) -> None:
        """Add a licence element and index it for :meth:`find_license`.

        Args:
            license_element: A ``LicenseExpression`` or ``SimpleLicensingText``.
            key: The ``(kind, value)`` to index it under; by default its own
                expression, or its text stripped. A fragment merge passes the
                canonical key (see
                :func:`pitloom.assemble.spdx3._license_elements.license_key`).
        """
        self.object_set.add(license_element)
        if key is not None:
            self._license_index.setdefault(key, require_spdx_id(license_element))
            return
        if isinstance(license_element, spdx3.simplelicensing_LicenseExpression):
            kind, value = (
                "expression",
                license_element.simplelicensing_licenseExpression,
            )
        else:
            kind = "text"
            value = (license_element.simplelicensing_licenseText or "").strip()
        if value:
            self._license_index[(kind, value)] = require_spdx_id(license_element)

    def add_relationship(self, relationship: spdx3.Relationship) -> None:
        """Add a relationship to the document.

        Args:
            relationship: The Relationship object
        """
        self.object_set.add(relationship)

    def add_annotation(self, annotation: spdx3.Annotation) -> None:
        """Add a provenance (or other) annotation to the document.

        Args:
            annotation: The Annotation object
        """
        self.object_set.add(annotation)

    def add_sbom(self, sbom: spdx3.software_Sbom) -> None:
        """Add an SBOM to the document.

        Args:
            sbom: The software_Sbom object
        """
        self.object_set.add(sbom)

    def add_document(self, document: spdx3.SpdxDocument) -> None:
        """Add an SPDX document to the graph.

        Args:
            document: The SpdxDocument object
        """
        self.object_set.add(document)

    def to_json(self, pretty: bool = False, describe_relationship: bool = False) -> str:
        """Export to JSON-LD string.

        Args:
            pretty: If True, indent output with 2 spaces for human readability,
                    with keys sorted alphabetically within each object.
                    If False (default), produce RFC 8785 (JCS) canonical output:
                    compact, no extra whitespace, keys lexicographically sorted --
                    suitable for machine consumption, hashing, and PEP 770
                    wheel embedding.
            describe_relationship: If True, add a ``description`` of the form
                ``<from name> <relationship type>: <to names>`` to every
                ``Relationship``.

        Returns:
            str: JSON-LD representation
        """
        out_f = io.BytesIO()
        serializer = spdx3.JSONLDSerializer()
        serializer.write(self.object_set, out_f)
        data = json.loads(out_f.getvalue())
        if "@graph" in data:
            data["@graph"] = _deduplicate_creation_infos(data["@graph"])
            data["@graph"] = _deduplicate_named_elements(data["@graph"])
            _check_no_duplicate_spdx_ids(data["@graph"])
            if describe_relationship:
                _annotate_relationships(data["@graph"])
            data["@graph"].sort(key=_graph_sort_key)
        if pretty:
            return canonical_json_indented(data)
        return rfc8785.dumps(data).decode("utf-8")

    def to_file(self, file_path: str, pretty: bool = False) -> None:
        """Export to JSON-LD file.

        Args:
            file_path: Path to write the JSON-LD file
            pretty: If True, indent output with 2 spaces for human readability.
                    If False (default), produce RFC 8785 (JCS) canonical output.
        """
        write_text_lf(file_path, self.to_json(pretty=pretty))
