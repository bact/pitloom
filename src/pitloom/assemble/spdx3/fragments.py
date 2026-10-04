# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Merging of pre-generated SPDX 3 fragment files into an SBOM document.

See also: :mod:`pitloom.assemble.spdx3._fragments_unify` for internal unification
logic and :mod:`pitloom.assemble.spdx3._fragments_refs` for the dangling-reference
check.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_refs import (
    _dangling_refs_for_object,
    _declared_external_ids,
    _endpoint_id,
    _find_dangling_references,
    _find_main_document,
    _is_dangling,
)
from pitloom.assemble.spdx3._fragments_unify import (
    _ENVELOPE_TYPES,
    _HASHABLE_TYPES,
    _KEYED_DICT_PROPS,
    _SKIP_MERGE_PROPS,
    _STRUCTURAL_TYPES,
    _as_element,
    _canonical_merge_key,
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
    _UnificationEvents,
    _warn_if_same_name_different_hash,
)
from pitloom.assemble.spdx3._licensing_profiles import apply_licensing_profiles
from pitloom.assemble.spdx3.provenance import build_unification_annotation
from pitloom.core.config import FragmentConfig
from pitloom.core.path_probe import is_missing_errno
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
    "_fragment_is_missing",
    "_fragment_read_failure_message",
    "_is_dangling",
    "_is_empty",
    "_merge_comment",
    "_merge_dictionary_entries",
    "_merge_fragment_set",
    "_merge_list",
    "_merge_properties",
    "_merge_scalar",
    "_mint_extra_id",
    "_missing_fragment_message",
    "_normalize_value",
    "_paths_suffix_match",
    "_raise_on_dangling_references",
    "_record_unification",
    "_remap_object_refs",
    "_sha256_hash",
    "_signature",
    "_canonical_merge_key",
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


def _fragment_is_missing(fragment_path: Path) -> bool:
    """Return True when *fragment_path* is genuinely absent, matching
    ``Path.exists()``'s own classification -- unlike a bare
    ``Path.exists()`` call, a permission-denied or other real access
    failure is reported as *not* missing (the caller's own read attempt
    then reports that failure accurately) rather than propagating an
    uncaught ``OSError``."""
    try:
        fragment_path.stat()
    except OSError as exc:
        return is_missing_errno(exc)
    return False


def _dedupe_relationships(exporter: Spdx3JsonExporter) -> None:
    """Drop duplicate ``Relationship`` elements."""
    seen: set[tuple[Any, Any, frozenset[Any]]] = set()
    duplicates: list[spdx3.Relationship] = []

    for obj in sorted(exporter.object_set.objects, key=_canonical_merge_key):
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


def _raise_on_dangling_references(exporter: Spdx3JsonExporter) -> None:
    """Log one ``WARNING:`` per dangling reference found by
    :func:`_find_dangling_references`, then raise :class:`FragmentMergeError`
    if any were found -- a merge that leaves the graph referentially
    broken must not silently succeed (see the ``sbom-enrich`` skill's
    "Troubleshooting: dangling references" section for the causes this
    guards against, e.g. a stale ``doc_uuid``)."""
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


def _update_profile_conformance(
    main_doc: spdx3.SpdxDocument, exporter: Spdx3JsonExporter
) -> None:
    """Append ``ai``/``dataset`` and the licensing profiles to
    profileConformance when present."""
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
    apply_licensing_profiles(main_doc, exporter.object_set.objects)


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


def _missing_fragment_message(fragment_path: Path, *, required: bool) -> str:
    """Wording for a configured fragment file that doesn't exist on disk --
    shared by the real merge and ``pitloom fragment list``'s diagnostic
    pass, so the same condition reads identically on both surfaces."""
    if required:
        return f"Required SBOM fragment {fragment_path} not found -- merge will fail."
    return f"Configured SBOM fragment {fragment_path} not found."


def _fragment_read_failure_message(
    fragment_path: Path, exc: Exception, *, required: bool
) -> str:
    """Wording for a fragment file that exists but couldn't be read/parsed
    -- shared the same way as :func:`_missing_fragment_message`. Says
    "read", not "ingest": accurate for both the real merge (which parses
    the file as SPDX 3 JSON-LD) and ``fragment list`` (which only needs a
    plain JSON parse for an element count) -- the file's problem is the
    same regardless of which caller noticed it."""
    suffix = " -- merge will fail." if required else ""
    return f"Failed to read SBOM fragment {fragment_path}: {exc}{suffix}"


def merge_fragments(
    project_dir: Path,
    fragments: list[FragmentConfig],
    exporter: Spdx3JsonExporter,
) -> None:
    """Load SPDX 3 JSON-LD fragment files and merge them into the exporter.

    Raises :class:`FragmentMergeError` if any ``required=True`` fragment
    (see :class:`~pitloom.core.config.FragmentConfig`) is missing or
    couldn't be read, or if the merge leaves the graph referentially
    broken (see :func:`_raise_on_dangling_references`) -- the latter is
    skipped when *fragments* is empty or none of it could be ingested,
    since there is then nothing new whose references could be dangling.
    """
    configure_logging()
    index = _MergeIndex(exporter)
    events: _UnificationEvents = {}
    fragment_imports: list[spdx3.ExternalMap] = []
    seen_import_ids: set[str] = set()
    merged_any = False
    unmet_required: list[str] = []

    for frag in fragments:
        fragment_path = Path(frag.base_dir or project_dir) / frag.path
        if _fragment_is_missing(fragment_path):
            log.warning(
                _missing_fragment_message(fragment_path, required=frag.required)
            )
            if frag.required:
                unmet_required.append(frag.path)
            continue
        try:
            with open(fragment_path, "rb") as f:
                fragment_set = spdx3.SHACLObjectSet()
                spdx3.JSONLDDeserializer().read(f, fragment_set)
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:
            log.warning(
                _fragment_read_failure_message(
                    fragment_path, exc, required=frag.required
                )
            )
            if frag.required:
                unmet_required.append(frag.path)
            continue

        frag_doc_id = _find_fragment_document_id(fragment_set)
        if frag_doc_id and frag_doc_id not in seen_import_ids:
            seen_import_ids.add(frag_doc_id)
            fragment_imports.append(
                spdx3.ExternalMap(
                    externalSpdxId=frag_doc_id,
                    locationHint=frag.path,
                )
            )

        _merge_fragment_set(fragment_set, index, frag.path, events)
        merged_any = True

    _dedupe_relationships(exporter)

    main_doc = _find_main_document(exporter.object_set)
    if main_doc is not None:
        _update_profile_conformance(main_doc, exporter)
        _add_fragment_imports(main_doc, fragment_imports)
        _emit_unification_annotations(events, main_doc, exporter)
        _add_model_sbom(main_doc, exporter)

    # Checked unconditionally -- NOT gated by `merged_any`. A required
    # fragment that's missing is exactly the scenario most likely to leave
    # merged_any False (nothing else may have merged either), so gating
    # this on merged_any would silently suppress the one case it exists to
    # catch. Checked before the dangling-references raise below: a missing
    # required fragment is usually the *root cause* of any dangling
    # references the rest of the graph would otherwise show (other
    # fragments' relationships pointing at elements the missing required
    # fragment was supposed to supply) -- report the root cause, not the
    # downstream symptom, when both would otherwise fire in the same run.
    if unmet_required:
        raise FragmentMergeError(
            f"{len(unmet_required)} required fragment(s) could not be "
            f"merged: {', '.join(unmet_required)} -- check the configured "
            "path(s) under [tool.pitloom.fragment]"
        )

    if merged_any:
        _raise_on_dangling_references(exporter)
