# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Project, wheel, and environment SBOM generators."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3_bindings

from pitloom.assemble._model_generator import (
    _resolve_local_offline_default,
    _write_output_file,
)
from pitloom.assemble.spdx3.document import build, build_deployed
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import VALID_CONTENT_TYPE_METHODS, PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich import run_enrichers_for_models
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.env import read_environment
from pitloom.extract.project import read_project
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.extract.wheel import read_wheel
from pitloom.ids import IdRegistry, resolve_registry

log = logging.getLogger(__name__)

# ai_AIPackage is deliberately excluded from auto-harvest: its correct
# registry key is the model file's stem (only ever registered via the
# extras-free `pitloom ids generate`), not its `.name`, which is
# extraction-dependent and varies with whether AI-format libraries are
# installed. Harvesting it by name would write entries that never match
# future lookups (see `_lookup_ai_model_entity`,
# pitloom.assemble.spdx3._ai_package) instead of just doing nothing.
_AUTO_HARVEST_EXCLUDED_TYPES = frozenset({"ai_AIPackage"})


def _require_valid_content_type_method(value: str) -> None:
    """Raise ``ValueError`` unless *value* is a valid content-type method."""
    if value not in VALID_CONTENT_TYPE_METHODS:
        valid = ", ".join(sorted(VALID_CONTENT_TYPE_METHODS))
        raise ValueError(f"content_type_method must be one of {valid}, got {value!r}")


def _harvestable(obj: Any) -> bool:
    """Return whether *obj* is safe for auto-harvest (see module docstring)."""
    get_compact_type = getattr(obj, "get_compact_type", None)
    compact_type = get_compact_type() if get_compact_type is not None else None
    return compact_type not in _AUTO_HARVEST_EXCLUDED_TYPES


def _sync_registry(
    exporter: Spdx3JsonExporter,
    registry: IdRegistry | None,
    update_registry: bool,
) -> None:
    """Harvest newly-minted ids from *exporter* back into *registry*.

    No-op when no registry was resolved, auto-update was disabled, or the
    registry has no on-disk path to save to. A save failure is logged as a
    ``WARNING`` and otherwise ignored -- it must never break SBOM
    generation itself.
    """
    if registry is None or not update_registry:
        return
    if registry.path is None:
        log.warning("Registry: no file path resolved; skipping auto-update.")
        return

    filtered = spdx3_bindings.SHACLObjectSet()
    for obj in exporter.object_set.objects:
        if _harvestable(obj):
            filtered.add(obj)

    new_files, new_entities = registry.harvest(filtered)
    if not new_files and not new_entities:
        return
    try:
        registry.save()
    except OSError as exc:
        log.warning("Registry: failed to save %s: %s", registry.path, exc)
        return
    log.info(
        "Registry: added %d new file(s), %d new entit(y/ies) to %s",
        new_files,
        new_entities,
        registry.path,
    )


# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def generate_project_sbom(
    project_target: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    project_metadata: ProjectMetadata | None = None,
    pitloom_config: PitloomConfig | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    offline: bool | None = None,
    update_registry: bool | None = None,
) -> str:
    """Generate a Source SPDX 3 SBOM for a Python project or sdist archive."""
    target_path = Path(project_target)
    if project_metadata is None or pitloom_config is None:
        project_metadata, pitloom_config, _ = read_project(target_path)

    effective_pretty: bool = pitloom_config.pretty if pretty is None else pretty
    effective_describe: bool = bool(
        pitloom_config.describe_relationship
        if describe_relationship is None
        else describe_relationship
    )
    effective_provenance: ProvenanceConfig = provenance or pitloom_config.provenance
    effective_enrich_config: EnrichConfig = (
        dataclasses.replace(pitloom_config.enrich, local=enrich)
        if enrich is not None
        else pitloom_config.enrich
    )
    effective_extract_file_header: bool = (
        pitloom_config.extract_file_header
        if extract_file_header is None
        else extract_file_header
    )
    effective_content_type: bool = (
        pitloom_config.content_type.enabled if content_type is None else content_type
    )
    effective_content_type_method: str = (
        pitloom_config.content_type.method
        if content_type_method is None
        else content_type_method
    )
    _require_valid_content_type_method(effective_content_type_method)
    effective_offline: bool = pitloom_config.offline if offline is None else offline
    effective_update_registry: bool = (
        pitloom_config.update_registry if update_registry is None else update_registry
    )

    if target_path.is_file():
        merkle_root = None
        project_files = project_metadata.files
        search_root = target_path.parent
    else:
        merkle_root, project_files = get_wheel_files(
            target_path,
            scan_file_headers=effective_extract_file_header,
            detect_content_type=effective_content_type,
            content_type_method=effective_content_type_method,
            content_type_overrides=pitloom_config.content_type.overrides,
        )
        project_metadata.files = project_files
        search_root = target_path

    ai_models = (
        scan_project_for_ai_models(target_path, project_files)
        if target_path.is_dir()
        else []
    )

    enrichment_results_by_model = run_enrichers_for_models(
        ai_models, effective_enrich_config, target_path
    )

    resolved_registry = resolve_registry(
        search_root, registry if registry is not None else pitloom_config.ids_file
    )

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=ai_models,
    )
    exporter = build(
        doc,
        merkle_root=merkle_root,
        sbom_type=spdx3_bindings.software_SbomType.source,
        registry=resolved_registry,
        provenance=effective_provenance,
        enrichment_results_by_model=enrichment_results_by_model,
        offline=effective_offline,
        content_type_method=effective_content_type_method,
    )

    if target_path.is_dir():
        merge_fragments(target_path, pitloom_config.fragments, exporter)

    _sync_registry(exporter, resolved_registry, effective_update_registry)

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json


def generate_wheel_sbom(
    wheel_path: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    offline: bool | None = None,
    update_registry: bool | None = None,
) -> str:
    """Generate an Analyzed SPDX 3 SBOM for a built Python wheel."""
    effective_pretty = False if pretty is None else pretty
    effective_describe = (
        False if describe_relationship is None else describe_relationship
    )
    effective_update_registry = True if update_registry is None else update_registry
    wheel_path_obj = Path(wheel_path)
    project_metadata, project_files = read_wheel(wheel_path_obj)
    phantom_deps = find_phantom_dependencies(project_files)

    cwd = Path.cwd()
    effective_offline = (
        _resolve_local_offline_default(cwd) if offline is None else offline
    )
    resolved_registry = resolve_registry(cwd, registry)

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=[],
        phantom_dependencies=phantom_deps,
    )
    exporter = build(
        doc,
        merkle_root=None,
        sbom_type=spdx3_bindings.software_SbomType.analyzed,
        registry=resolved_registry,
        provenance=provenance,
        offline=effective_offline,
    )

    _sync_registry(exporter, resolved_registry, effective_update_registry)

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json


def generate_env_sbom(
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    offline: bool | None = None,
    update_registry: bool | None = None,
) -> str:
    """Generate a Deployed SPDX 3 SBOM for the current installed environment."""
    effective_pretty = False if pretty is None else pretty
    effective_describe = (
        False if describe_relationship is None else describe_relationship
    )
    effective_update_registry = True if update_registry is None else update_registry
    project_metadata, env_tree = read_environment()

    cwd = Path.cwd()
    effective_offline = (
        _resolve_local_offline_default(cwd) if offline is None else offline
    )
    resolved_registry = resolve_registry(cwd, registry)

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=[],
    )
    exporter = build_deployed(
        doc,
        env_tree=env_tree,
        registry=resolved_registry,
        provenance=provenance,
        offline=effective_offline,
    )

    _sync_registry(exporter, resolved_registry, effective_update_registry)

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json
