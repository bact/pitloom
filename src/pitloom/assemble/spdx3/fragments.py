# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Merging of pre-generated SPDX 3 fragment files into an SBOM document.

See also: :mod:`pitloom.assemble.spdx3._fragments_unify` for internal unification logic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_unify import (
    _ENVELOPE_TYPES,
    _HASHABLE_TYPES,
    _KEYED_DICT_PROPS,
    _SKIP_MERGE_PROPS,
    _STRUCTURAL_TYPES,
    _as_element,
    _class_properties,
    _is_empty,
    _merge_comment,
    _merge_dictionary_entries,
    _merge_fragment_set,
    _merge_list,
    _merge_properties,
    _merge_scalar,
    _MergeIndex,
    _normalize_value,
    _paths_suffix_match,
    _record_unification,
    _remap_object_refs,
    _sha256_hash,
    _signature,
    _stable_key,
    _UnificationEvents,
    _warn_if_same_name_different_hash,
)
from pitloom.assemble.spdx3.provenance import build_unification_annotation
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.logging_config import configure_logging

log = logging.getLogger(__name__)

__all__ = [
    "_ENVELOPE_TYPES",
    "_HASHABLE_TYPES",
    "_KEYED_DICT_PROPS",
    "_SKIP_MERGE_PROPS",
    "_STRUCTURAL_TYPES",
    "_MergeIndex",
    "_UnificationEvents",
    "_add_fragment_imports",
    "_add_model_sbom",
    "_as_element",
    "_class_properties",
    "_dangling_refs_for_object",
    "_declared_external_ids",
    "_dedupe_relationships",
    "_emit_unification_annotations",
    "_endpoint_id",
    "_find_dangling_references",
    "_find_fragment_document_id",
    "_find_main_document",
    "_is_dangling",
    "_is_empty",
    "_merge_comment",
    "_merge_dictionary_entries",
    "_merge_fragment_set",
    "_merge_list",
    "_merge_properties",
    "_merge_scalar",
    "_mint_extra_id",
    "_normalize_value",
    "_paths_suffix_match",
    "_raise_on_dangling_references",
    "_record_unification",
    "_remap_object_refs",
    "_sha256_hash",
    "_signature",
    "_stable_key",
    "_update_profile_conformance",
    "_warn_if_same_name_different_hash",
    "FragmentMergeError",
    "merge_fragments",
]


class FragmentMergeError(ValueError):
    """Raised when merging fragments would produce a referentially-broken
    SBOM -- a ``Relationship``/``Annotation`` endpoint that resolves to
    neither an object in the merged graph nor a declared external
    reference. Merging must not silently succeed in that case; see
    :func:`_raise_on_dangling_references`."""


def _endpoint_id(value: str | spdx3.Element | None) -> str | None:
    """Return a ``Relationship`` endpoint's id."""
    if value is None or isinstance(value, str):
        return value
    return str(value.spdxId) if value.spdxId else None


def _dedupe_relationships(exporter: Spdx3JsonExporter) -> None:
    """Drop duplicate ``Relationship`` elements."""
    seen: set[tuple[Any, Any, frozenset[Any]]] = set()
    duplicates: list[spdx3.Relationship] = []

    for obj in sorted(exporter.object_set.objects, key=_stable_key):
        if not isinstance(obj, spdx3.Relationship):
            continue
        from_id = _endpoint_id(obj.from_)
        to_ids = frozenset(_endpoint_id(t) for t in obj.to)
        key = (from_id, obj.relationshipType, to_ids)
        if key in seen:
            duplicates.append(obj)
        else:
            seen.add(key)

    for dup in duplicates:
        exporter.object_set.objects.remove(dup)


def _find_dangling_references(
    exporter: Spdx3JsonExporter,
) -> list[tuple[str, str, str]]:
    """Return ``(referencing element id, property name, missing target id)``
    for every ``Relationship``/``Annotation`` endpoint that doesn't resolve
    to an object actually present in *exporter*'s merged graph, and isn't
    a legitimate external reference either (an id declared via the main
    document's own ``import_`` -- see :func:`_add_fragment_imports`).

    Catches, among other causes, a fragment merged against a stale base
    SBOM -- e.g. one generated before a Pitloom upgrade changed file
    discovery for this project's backend (see
    :func:`pitloom.assemble._model_generator._project_doc_identity`'s
    docstring): the fragment's element references were minted against a
    ``doc_uuid`` the current base document no longer uses, so they land
    in the merged graph pointing at nothing.
    """
    known_ids = set(exporter.object_set.obj_by_id.keys())
    external_ids = _declared_external_ids(exporter.object_set)
    dangling: list[tuple[str, str, str]] = []
    for obj in exporter.object_set.objects:
        dangling.extend(_dangling_refs_for_object(obj, known_ids, external_ids))
    return dangling


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
    a declared external reference -- i.e. is genuinely dangling."""
    return (
        endpoint_id is not None
        and endpoint_id not in known_ids
        and endpoint_id not in external_ids
    )


def _raise_on_dangling_references(exporter: Spdx3JsonExporter) -> None:
    """Log one ``WARNING:`` per dangling reference found by
    :func:`_find_dangling_references`, then raise :class:`FragmentMergeError`
    if any were found -- a merge that leaves the graph referentially
    broken must not silently succeed (see ``working-docs/design/roadmap.md``
    and the ``sbom-enrich`` skill's "If a base SBOM already exists" step
    for the doc_uuid-staleness scenario this guards against)."""
    dangling = _find_dangling_references(exporter)
    for obj_id, prop, target_id in dangling:
        log.warning(
            "%s's %s references %s, which isn't part of this document -- "
            "likely a fragment merged against an outdated base SBOM "
            "(regenerate the base SBOM, then re-run enrichment, before "
            "merging again)",
            obj_id,
            prop,
            target_id,
        )
    if dangling:
        raise FragmentMergeError(
            f"{len(dangling)} dangling reference(s) after fragment merge -- "
            "regenerate the base SBOM, then re-run enrichment, before "
            "merging again"
        )


def _find_main_document(object_set: spdx3.SHACLObjectSet) -> spdx3.SpdxDocument | None:
    for obj in object_set.objects:
        if isinstance(obj, spdx3.SpdxDocument):
            return obj
    return None


def _update_profile_conformance(
    main_doc: spdx3.SpdxDocument, exporter: Spdx3JsonExporter
) -> None:
    """Append ``ai``/``dataset`` to profileConformance when present."""
    conformance = list(main_doc.profileConformance or [])
    has_ai = any(isinstance(o, spdx3.ai_AIPackage) for o in exporter.object_set.objects)
    has_dataset = any(
        isinstance(o, spdx3.dataset_DatasetPackage) for o in exporter.object_set.objects
    )
    if has_ai and spdx3.ProfileIdentifierType.ai not in conformance:
        conformance.append(spdx3.ProfileIdentifierType.ai)
    if has_dataset and spdx3.ProfileIdentifierType.dataset not in conformance:
        conformance.append(spdx3.ProfileIdentifierType.dataset)
    main_doc.profileConformance = conformance


def _mint_extra_id(namespace: str, prefix: str, existing_ids: set[str]) -> str:
    """Mint a fresh ``<namespace>#<prefix>-<n>`` id not in existing_ids."""
    n = 1
    while True:
        candidate = f"{namespace}#{prefix}-{n}"
        if candidate not in existing_ids:
            return candidate
        n += 1


def _find_fragment_document_id(fragment_set: spdx3.SHACLObjectSet) -> str | None:
    """Return the ``spdxId`` of the ``SpdxDocument`` envelope in *fragment_set*."""
    for obj in fragment_set.objects:
        if isinstance(obj, spdx3.SpdxDocument):
            spdx_id = getattr(obj, "spdxId", None)
            if spdx_id:
                return str(spdx_id)
    return None


def _add_fragment_imports(
    main_doc: spdx3.SpdxDocument,
    fragment_imports: list[spdx3.ExternalMap],
) -> None:
    """Populate ``main_doc.import_`` with ``ExternalMap`` entries."""
    if not fragment_imports:
        return
    existing_imports = list(main_doc.import_ or [])
    existing_ids: set[str] = set()
    for item in existing_imports:
        if isinstance(item, spdx3.ExternalMap) and item.externalSpdxId:
            existing_ids.add(item.externalSpdxId)
        elif isinstance(item, str):
            existing_ids.add(item)

    for ext_map in fragment_imports:
        if ext_map.externalSpdxId and ext_map.externalSpdxId not in existing_ids:
            existing_imports.append(ext_map)
            existing_ids.add(ext_map.externalSpdxId)
    main_doc.import_ = existing_imports


def _emit_unification_annotations(
    events: _UnificationEvents,
    main_doc: spdx3.SpdxDocument,
    exporter: Spdx3JsonExporter,
) -> None:
    """Emit one ``unification`` Annotation per (survivor, criterion) in *events*."""
    if not events:
        return
    namespace = main_doc.spdxId
    creation_info = main_doc.creationInfo
    if namespace is None or not isinstance(creation_info, spdx3.CreationInfo):
        return
    existing_ids = set(exporter.object_set.obj_by_id.keys())
    for survivor_id in sorted(events):
        for criterion in sorted(events[survivor_id]):
            rec = events[survivor_id][criterion]
            ann_id = _mint_extra_id(namespace, "Annotation-unification", existing_ids)
            existing_ids.add(ann_id)
            exporter.add_annotation(
                build_unification_annotation(
                    subject_spdx_id=survivor_id,
                    criterion=criterion,
                    unified_ids=list(rec["unified"]),
                    fragments=list(rec["fragments"]),
                    creation_info=creation_info,
                    annotation_spdx_id=ann_id,
                )
            )


def _add_model_sbom(main_doc: spdx3.SpdxDocument, exporter: Spdx3JsonExporter) -> None:
    """Add a second ``software_Sbom`` rooted at the merged ``ai_AIPackage``."""
    ai_packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.ai_AIPackage)
    ]
    if not ai_packages:
        return

    root_pkg = min(ai_packages, key=require_spdx_id)

    namespace = main_doc.spdxId
    if namespace is None:
        return
    existing_ids = set(exporter.object_set.obj_by_id.keys())
    sbom_id = _mint_extra_id(namespace, "Sbom", existing_ids)

    model_sbom = spdx3.software_Sbom(
        spdxId=sbom_id,
        creationInfo=main_doc.creationInfo,
        rootElement=[require_spdx_id(root_pkg)],
    )
    model_sbom.software_sbomType = [spdx3.software_SbomType.build]
    exporter.add_sbom(model_sbom)

    root_elements = list(main_doc.rootElement or [])
    root_elements.append(require_spdx_id(model_sbom))
    main_doc.rootElement = root_elements


def merge_fragments(
    project_dir: Path,
    fragment_files: list[str],
    exporter: Spdx3JsonExporter,
) -> None:
    """Load SPDX 3 JSON-LD fragment files and merge them into the exporter.

    Raises :class:`FragmentMergeError` if the merge leaves the graph
    referentially broken (see :func:`_raise_on_dangling_references`) --
    skipped when *fragment_files* is empty or none of it could be
    ingested, since there is then nothing new whose references could be
    dangling.
    """
    configure_logging()
    index = _MergeIndex(exporter)
    events: _UnificationEvents = {}
    fragment_imports: list[spdx3.ExternalMap] = []
    seen_import_ids: set[str] = set()
    merged_any = False

    for fragment_file in fragment_files:
        fragment_path = project_dir / fragment_file
        if not fragment_path.exists():
            log.warning("Configured SBOM fragment %s not found.", fragment_path)
            continue
        try:
            with open(fragment_path, "rb") as f:
                fragment_set = spdx3.SHACLObjectSet()
                spdx3.JSONLDDeserializer().read(f, fragment_set)
        # pylint: disable=broad-exception-caught
        except Exception as exc:
            log.warning("Failed to ingest SBOM fragment %s: %s", fragment_path, exc)
            continue

        frag_doc_id = _find_fragment_document_id(fragment_set)
        if frag_doc_id and frag_doc_id not in seen_import_ids:
            seen_import_ids.add(frag_doc_id)
            fragment_imports.append(
                spdx3.ExternalMap(
                    externalSpdxId=frag_doc_id,
                    locationHint=fragment_file,
                )
            )

        _merge_fragment_set(fragment_set, index, fragment_file, events)
        merged_any = True

    _dedupe_relationships(exporter)

    main_doc = _find_main_document(exporter.object_set)
    if main_doc is not None:
        _update_profile_conformance(main_doc, exporter)
        _add_fragment_imports(main_doc, fragment_imports)
        _emit_unification_annotations(events, main_doc, exporter)
        _add_model_sbom(main_doc, exporter)

    if merged_any:
        _raise_on_dangling_references(exporter)
