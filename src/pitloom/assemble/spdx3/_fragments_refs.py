# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Referential-integrity check for a merged SPDX 3 graph: which
``Relationship``/``Annotation`` endpoints resolve to nothing.

An endpoint resolves when it is an object in the graph, an id declared
external by the main document's ``import_``, or a named individual of the
SPDX 3 model (``NoAssertionElement``, ``NoAssertionLicense``, ...), which
is defined by the specification and never has an element of its own.

See also: :mod:`pitloom.assemble.spdx3.fragments` (the merge that raises on
what this finds; it re-exports the helpers here).
"""

from __future__ import annotations

import inspect

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export.spdx3_json import Spdx3JsonExporter


def _named_individual_ids() -> frozenset[str]:
    """The IRI of every named individual of an SPDX 3 ``Element`` class,
    read from the bindings. Enumeration values (``HashAlgorithm.sha256``
    ...) are not elements and cannot be an endpoint."""
    ids: set[str] = set()
    for _, cls in inspect.getmembers(spdx3, inspect.isclass):
        if issubclass(cls, spdx3.Element):
            ids.update(getattr(cls, "NAMED_INDIVIDUALS", {}).values())
    return frozenset(ids)


#: Deserialising compact (``"NoAssertionElement"``) or full-IRI JSON gives
#: the full IRI, so the full IRI is the only form an endpoint takes.
NAMED_INDIVIDUAL_IDS = _named_individual_ids()


def _endpoint_id(value: str | spdx3.Element | None) -> str | None:
    """Return a ``Relationship`` endpoint's id."""
    if value is None or isinstance(value, str):
        return value
    return str(value.spdxId) if value.spdxId else None


def _find_dangling_references(
    exporter: Spdx3JsonExporter,
) -> list[tuple[str, str, str]]:
    """Return ``(referencing element id, property name, missing target id)``
    for every ``Relationship``/``Annotation`` endpoint that doesn't resolve
    to an object actually present in *exporter*'s merged graph, and isn't
    a legitimate external reference either (an id declared via the main
    document's own ``import_`` -- see
    :func:`pitloom.assemble.spdx3.fragments._add_fragment_imports`) or a
    named individual of the SPDX 3 model.

    Catches, among other causes, a fragment merged against a stale base
    SBOM -- e.g. one generated before a Pitloom upgrade changed file
    discovery for this project's backend (see
    :func:`pitloom.assemble._model_generator._doc_identity_of`'s
    docstring): the fragment's element references were minted against a
    ``doc_uuid`` the current base document no longer uses, so they land
    in the merged graph pointing at nothing.
    """
    known_ids = set(exporter.object_set.obj_by_id.keys())
    external_ids = _declared_external_ids(exporter.object_set)
    namespace = _document_namespace(exporter)  # once: it scans the graph
    dangling: list[tuple[str, str, str]] = []
    for obj in exporter.object_set.objects:
        dangling.extend(_dangling_refs_for_object(obj, known_ids, external_ids))
        dangling.extend(_dangling_custom_ids(obj, known_ids, namespace))
    return dangling


def _document_namespace(exporter: Spdx3JsonExporter) -> str | None:
    """The prefix of the main document's own element ids (its id, less any
    fragment, and ``#``), or ``None`` without a document."""
    main_doc = _find_main_document(exporter.object_set)
    spdx_id = str(main_doc.spdxId or "") if main_doc else ""
    return spdx_id.split("#", 1)[0] + "#" if spdx_id else None


def _dangling_custom_ids(
    obj: spdx3.SHACLObject, known_ids: set[str], namespace: str | None
) -> list[tuple[str, str, str]]:
    """A ``LicenseExpression``'s ``customIdToUri`` values in this document's
    own namespace that resolve to nothing; a value elsewhere is an external
    licence URI, not checked."""
    if namespace is None or not isinstance(
        obj, spdx3.simplelicensing_LicenseExpression
    ):
        return []
    obj_id = str(obj.spdxId or "<unknown>")
    targets = [
        str(entry.value)
        for entry in obj.simplelicensing_customIdToUri
        if isinstance(entry, spdx3.DictionaryEntry) and entry.value
    ]
    return [
        (obj_id, "simplelicensing_customIdToUri", target)
        for target in targets
        if target.startswith(namespace) and target not in known_ids
    ]


def _declared_external_ids(object_set: spdx3.SHACLObjectSet) -> set[str]:
    """Ids declared as legitimate external references via the main
    document's own ``import_`` (``ExternalMap.externalSpdxId``)."""
    main_doc = _find_main_document(object_set)
    if main_doc is None:
        return set()
    return {
        ext_map.externalSpdxId
        for ext_map in (main_doc.import_ or [])
        if isinstance(ext_map, spdx3.ExternalMap) and ext_map.externalSpdxId
    }


def _dangling_refs_for_object(
    obj: spdx3.SHACLObject, known_ids: set[str], external_ids: set[str]
) -> list[tuple[str, str, str]]:
    """Dangling ``(referencing id, property name, missing target id)``
    entries for one ``Relationship``'s or ``Annotation``'s endpoints."""
    obj_id = str(getattr(obj, "spdxId", None) or "<unknown>")
    found: list[tuple[str, str, str]] = []
    if isinstance(obj, spdx3.Relationship):
        from_id = _endpoint_id(obj.from_)
        if _is_dangling(from_id, known_ids, external_ids):
            found.append((obj_id, "from", from_id or ""))
        for to in obj.to:
            to_id = _endpoint_id(to)
            if _is_dangling(to_id, known_ids, external_ids):
                found.append((obj_id, "to", to_id or ""))
    elif isinstance(obj, spdx3.Annotation):
        subject_id = _endpoint_id(obj.subject)
        if _is_dangling(subject_id, known_ids, external_ids):
            found.append((obj_id, "subject", subject_id or ""))
    return found


def _is_dangling(
    endpoint_id: str | None, known_ids: set[str], external_ids: set[str]
) -> bool:
    """Whether *endpoint_id* resolves to neither a known local object nor
    a declared external reference, nor a named individual of the SPDX 3
    model -- i.e. is genuinely dangling."""
    return (
        endpoint_id is not None
        and endpoint_id not in known_ids
        and endpoint_id not in external_ids
        and endpoint_id not in NAMED_INDIVIDUAL_IDS
    )


def _find_main_document(object_set: spdx3.SHACLObjectSet) -> spdx3.SpdxDocument | None:
    for obj in object_set.objects:
        if isinstance(obj, spdx3.SpdxDocument):
            return obj
    return None
