# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 JSON-LD exporter for generating SBOM documents."""

from __future__ import annotations

import io
import json
from collections import defaultdict
from typing import Any

import rfc8785
from spdx_python_model import v3_0_1 as spdx3

# Lower value = earlier in @graph. Types not listed here get priority 4.
# Order rationale:
#   0 CreationInfo  — blank node referenced by every element; must resolve first
#   1 SpdxDocument  — document envelope; carries profileConformance for validation
#   2 Bom           — Core profile BOM root (base class of software_Sbom)
#   3 software_Sbom — Software profile BOM; root element pointer and sbomType
_GRAPH_TYPE_PRIORITY: dict[str, int] = {
    "CreationInfo": 0,
    "SpdxDocument": 1,
    "Bom": 2,
    "software_Sbom": 3,
}


def _graph_sort_key(element: dict[str, Any]) -> tuple[int, str, str]:
    """Return a deterministic sort key for a @graph element.

    Primary key: type-priority tier (see _GRAPH_TYPE_PRIORITY).
    Secondary key: spdxId or @id, lexicographic — puts root Package-1 before
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

    Returns a new graph list with duplicates removed and all intra-document
    references to removed nodes redirected to the surviving canonical node.
    """
    # First pass: elect one canonical @id per unique fingerprint; record
    # every other @id that carries the same content as a redirect target.
    canonical: dict[tuple[str, ...], str] = {}  # fingerprint -> kept @id
    redirect: dict[str, str] = {}  # dropped @id -> canonical @id

    for element in graph:
        if element.get("type") != "CreationInfo":
            continue
        blank_id: str = element.get("@id", "")
        fp = _creation_info_fingerprint(element)
        if fp in canonical:
            redirect[blank_id] = canonical[fp]
        else:
            canonical[fp] = blank_id

    if not redirect:
        return graph

    # Second pass: drop duplicate nodes and rewrite string references.
    def _remap(value: Any) -> Any:
        return redirect.get(value, value) if isinstance(value, str) else value

    result = []
    for element in graph:
        if element.get("type") == "CreationInfo" and element.get("@id") in redirect:
            continue  # discard this duplicate
        result.append(
            {
                k: ([_remap(v) for v in val] if isinstance(val, list) else _remap(val))
                for k, val in element.items()
            }
        )
    return result


def _deduplicate_named_elements(
    graph: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove exact-duplicate named elements that share the same spdxId.

    When SPDX fragments are merged, the same named element (e.g. a shared
    licence text or a common dependency package) may appear more than once
    with an identical spdxId.  An element is removed only when every field
    of every copy is semantically identical to the first copy seen (deep
    JSON-object equality, key-ordering-independent) — the 100 % certainty
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
            result.append(copies[0])  # all identical — keep one
        else:
            result.extend(copies)  # conflict — retain all, do not guess
    return result


class Spdx3JsonExporter:
    """Exports SPDX 3 data structures to JSON-LD format using spdx-python-model."""

    def __init__(self) -> None:
        self.object_set = spdx3.SHACLObjectSet()
        # Maps simplelicensing_licenseText -> spdxId for deduplication.
        self._license_index: dict[str, str] = {}

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

    def add_package(self, package: spdx3.software_Package) -> None:
        """Add a software package to the document.

        Args:
            package: The software_Package object
        """
        self.object_set.add(package)

    def find_license(self, license_id: str) -> str | None:
        """Return the spdxId of an existing SimpleLicensingText with the given
        ``simplelicensing_licenseText``, or ``None`` if not yet added.

        Args:
            license_id: The license text value to look up (e.g. ``"Apache-2.0"``).
        """
        return self._license_index.get(license_id)

    def add_license(
        self, simple_licensing_text: spdx3.simplelicensing_SimpleLicensingText
    ) -> None:
        """Add a SimpleLicensingText element to the document.

        Updates the internal license index so subsequent calls to
        :meth:`find_license` with the same ``simplelicensing_licenseText``
        return this element's spdxId.

        Args:
            license_text: The simplelicensing_SimpleLicensingText object
        """
        self.object_set.add(simple_licensing_text)
        license_id: str | None = simple_licensing_text.simplelicensing_licenseText
        if license_id:
            self._license_index[license_id] = simple_licensing_text.spdxId

    def add_relationship(self, relationship: spdx3.Relationship) -> None:
        """Add a relationship to the document.

        Args:
            relationship: The Relationship object
        """
        self.object_set.add(relationship)

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

    def to_json(self, pretty: bool = False) -> str:
        """Export to JSON-LD string.

        Args:
            pretty: If True, indent output with 2 spaces for human readability,
                    with keys sorted alphabetically within each object.
                    If False (default), produce RFC 8785 (JCS) canonical output:
                    compact, no extra whitespace, keys lexicographically sorted —
                    suitable for machine consumption, hashing, and PEP 770
                    wheel embedding.

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
            data["@graph"].sort(key=_graph_sort_key)
        if pretty:
            return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        return rfc8785.dumps(data).decode("utf-8")

    def to_file(self, file_path: str, pretty: bool = False) -> None:
        """Export to JSON-LD file.

        Args:
            file_path: Path to write the JSON-LD file
            pretty: If True, indent output with 2 spaces for human readability.
                    If False (default), produce RFC 8785 (JCS) canonical output.
        """
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json(pretty=pretty))
