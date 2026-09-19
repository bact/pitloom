# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Project, wheel, and environment SBOM generators."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3_bindings

from pitloom.assemble._model_generator import (
    _resolve_local_offline_default,
    _write_output_file,
)
from pitloom.assemble.spdx3.document import build, build_deployed
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core._models_wheel_dispatch import _noop_cleanup
from pitloom.core.build_options import SDIST_TARGET_REASON, BuildOptions
from pitloom.core.build_signals import TerminationGuard
from pitloom.core.config import VALID_CONTENT_TYPE_METHODS, PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich import run_enrichers_for_models
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract._license import resolve_license_file_entries
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.env import read_environment
from pitloom.extract.project import resolve_project_with_lockfile
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.extract.wheel import read_wheel
from pitloom.ids import IdRegistry, resolve_registry
from pitloom.logging_config import configure_logging

log = logging.getLogger(__name__)

# ai_AIPackage is deliberately excluded from auto-harvest: its correct
# registry key is the model file's stem (only ever registered via the
# extras-free `loom ids generate`), not its `.name`, which is
# extraction-dependent and varies with whether AI-format libraries are
# installed. Harvesting it by name would write entries that never match
# future lookups (see `_lookup_ai_model_entity`,
# pitloom.assemble.spdx3._ai_package) instead of just doing nothing.
#
# dataset_DatasetPackage is excluded for a related but simpler reason:
# `_build_dataset_package` (pitloom.assemble.spdx3.dataset) never consults
# the registry at all -- every dataset spdxId is freshly minted every run,
# with no lookup path to match a harvested entry against. Harvesting it
# would just write a dead, silently-overwritten entry every run.
_AUTO_HARVEST_EXCLUDED_TYPES = frozenset({"ai_AIPackage", "dataset_DatasetPackage"})


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


def _warn_if_partial_presupply(
    project_metadata: ProjectMetadata | None,
    pitloom_config: PitloomConfig | None,
    target_path: Path,
) -> None:
    """Warn when exactly one of project_metadata/pitloom_config is
    pre-supplied to generate_project_sbom() -- the pair is re-resolved and
    the one supplied value is discarded either way (see that function's
    docstring), so silently doing so would violate "no silent deviations".

    Only called from within generate_project_sbom()'s own
    ``project_metadata is None or pitloom_config is None`` guard, so
    "both supplied" can never reach here -- no need to re-check it.
    """
    if project_metadata is None and pitloom_config is None:
        return
    log.warning(
        "generate_project_sbom(): project_metadata and pitloom_config "
        "must be supplied together, or neither -- the %s you passed alone "
        "is being discarded and both are re-resolved from %s",
        "project_metadata" if project_metadata is not None else "pitloom_config",
        target_path,
    )


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
    use_lockfile: bool | None = None,
    build_options: BuildOptions = BuildOptions(),
) -> str:
    """Generate a Source SPDX 3 SBOM for a Python project or sdist archive.

    ``build_options`` (see :class:`~pitloom.core.build_options.BuildOptions`),
    unlike every other flag-shaped parameter here, deliberately has no
    ``pitloom_config.*`` fallback to defer to when unset. A caller must
    pass ``BuildOptions(allow=True)`` explicitly every time it wants
    Pitloom to execute the target project's own PEP 517 build backend;
    there is no config-cascade layer for it, since the config file lives
    in the (untrusted) project being scanned and must never be able to
    silently opt itself into code execution. For an sdist archive target
    every given build flag is ignored with one ``WARNING:`` each.

    ``use_lockfile`` only affects metadata resolved by this call: if the
    caller pre-supplies BOTH ``project_metadata`` and ``pitloom_config``
    together, this parameter has no effect -- the lock-file cascade
    decision was already made when that metadata was produced. Supplying
    only one of the two is not a supported combination: both are
    re-resolved from *project_target* and the one you did supply is
    discarded, with a ``WARNING:`` explaining why (see "no silent
    deviations" in AGENTS.md).
    """
    configure_logging()
    target_path = Path(project_target)

    # Both branches below are cheap (a single is_file() stat, no parsing)
    # and run before any project-metadata/lock-file read, so the build-flag
    # WARNING: -- whichever one applies -- is always the first thing this
    # call logs, never something a user has to scroll past later warnings
    # to find. An sdist archive never reaches file discovery, so every
    # given flag (including --allow-build itself) is unconditionally
    # ineffective here; a project directory does reach it, so only a
    # no_isolation/timeout given without allow is resolved now (settle()
    # warns and resets it) -- whether allow itself has an effect depends
    # on file discovery below, not on this cheap up-front check.
    if target_path.is_file():
        build_options = build_options.settle_not_applicable(
            target_path, SDIST_TARGET_REASON
        )
    else:
        build_options = build_options.settle(target_path)

    if project_metadata is None or pitloom_config is None:
        _warn_if_partial_presupply(project_metadata, pitloom_config, target_path)
        project_metadata, pitloom_config, _ = resolve_project_with_lockfile(
            target_path, use_lockfile
        )

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

    # Owns SIGTERM/SIGHUP handling for the whole lifetime of a
    # build-and-read result: once a build ran, a signal until the end of
    # this block removes its extraction directory before the process
    # ends (see pitloom.core.build_signals). Without a build, inert.
    with TerminationGuard():
        if target_path.is_file():
            # Warned above, before metadata resolution -- nothing left to
            # warn about here.
            merkle_root = None
            project_files = project_metadata.files
            search_root = target_path.parent
            cleanup_discovery: Callable[[], None] = _noop_cleanup
        else:
            merkle_root, project_files, cleanup_discovery = get_wheel_files(
                target_path,
                scan_file_headers=effective_extract_file_header,
                detect_content_type=effective_content_type,
                content_type_method=effective_content_type_method,
                content_type_overrides=pitloom_config.content_type.overrides,
                build_options=build_options,
            )
            search_root = target_path

        # cleanup_discovery (a no-op unless --allow-build's build-and-read
        # sourced project_files) must stay alive -- and this whole block
        # must run inside its try -- through every step below that either
        # re-reads a ProjectFile's bytes from disk via physical_path (AI-
        # model scanning, enrichment) or could itself raise before reaching
        # them (license-file resolution, the fresh-containers copy): any of
        # these raising before cleanup_discovery() runs would leak the
        # build-and-read temp directory. Nothing after this block reads
        # file bytes again (document assembly only uses distribution_path/
        # physical_path as string keys, never re-opens the file).
        try:
            if not target_path.is_file():
                # Pitloom's file discovery is, by default, a static
                # config-driven walk, never a real wheel build (the sole
                # opt-in exception is --allow-build's build-and-read
                # mechanism) -- it never reproduces the
                # `.dist-info/licenses/...` entries a real build would add
                # for `[project.license-files]`. Resolve those directly so
                # they still show up in the SBOM's file list, before
                # replace_with_fresh_containers() below makes
                # `project_files` the metadata's authoritative file list
                # for this (directory) target -- every other dict/list
                # field (provenance, field_conflicts, etc.) also gets its
                # own fresh copy, so the caller's own `project_metadata`
                # can never be silently mutated as a side effect of
                # anything downstream.
                project_files = project_files + resolve_license_file_entries(
                    target_path,
                    project_metadata.name,
                    project_metadata.version,
                    project_metadata.license_files,
                )
                project_metadata = project_metadata.replace_with_fresh_containers(
                    files=project_files
                )

            ai_models = (
                scan_project_for_ai_models(target_path, project_files)
                if target_path.is_dir()
                else []
            )

            enrichment_results_by_model = run_enrichers_for_models(
                ai_models, effective_enrich_config, target_path
            )
        finally:
            cleanup_discovery()

    resolved_registry = resolve_registry(
        search_root, registry if registry is not None else pitloom_config.ids_file
    )

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or pitloom_config.creation_metadata,
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
    configure_logging()
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
    configure_logging()
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
