# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Project (and sdist) SBOM generator.

See also:
- :mod:`pitloom.assemble._generators_shared` for the helpers shared with
  the other generators.
- :mod:`pitloom.assemble._generators_wheel` for the built-wheel generator.
- :mod:`pitloom.assemble._generators_env` for the installed-environment
  generator.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3_bindings

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble._generators_shared import _sync_registry
from pitloom.assemble.spdx3.document import build
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core._models_wheel_dispatch import _noop_cleanup
from pitloom.core.build_options import BuildOptions
from pitloom.core.build_signals import TerminationGuard
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides, apply_overrides
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.inert_options import SDIST, settle_inert
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich import run_enrichers_for_models
from pitloom.extract._license import resolve_license_file_entries
from pitloom.extract.project import resolve_project_with_lockfile
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.id_registry import IdRegistry, registry_base_dir, resolve_registry
from pitloom.logging_config import configure_logging

log = logging.getLogger(__name__)


def _warn_if_metadata_without_config(
    project_metadata: ProjectMetadata | None,
    pitloom_config: PitloomConfig | None,
    target_path: Path,
) -> None:
    """Warn when *project_metadata* is pre-supplied without *pitloom_config*
    -- the metadata is re-read from *target_path* and the supplied value
    discarded, so silently doing so would violate "no silent deviations".

    *pitloom_config* alone is supported: it replaces the target's own
    ``[tool.pitloom]`` (an explicit ``--config``).
    """
    if project_metadata is None or pitloom_config is not None:
        return
    log.warning(
        "generate_project_sbom(): project_metadata needs pitloom_config "
        "supplied with it -- the project_metadata you passed alone is "
        "being discarded and re-read from %s",
        target_path,
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
    id_registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    offline: bool | None = None,
    update_id_registry: bool | None = None,
    use_lockfile: bool | None = None,
    build_options: BuildOptions = BuildOptions(),
    max_source_metadata_bytes: int | None = None,
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

    Settings come from the arguments, then *pitloom_config*, then the
    target's own ``[tool.pitloom]``, then the built-in defaults.
    *pitloom_config* alone replaces the target's config (``--config``); the
    project metadata is still read from *project_target*, and its lock-file
    cascade follows ``use_lockfile``, else *pitloom_config*'s
    ``use-lockfile``.

    ``use_lockfile`` only affects metadata resolved by this call: if the
    caller pre-supplies BOTH ``project_metadata`` and ``pitloom_config``
    together, this parameter has no effect -- the lock-file cascade
    decision was already made when that metadata was produced.
    *project_metadata* alone is not supported: it is re-read from
    *project_target*, with a ``WARNING:`` explaining why (see "no silent
    deviations" in AGENTS.md).

    For an sdist archive, ``extract_file_header``/``content_type`` have no
    effect and warn when given (see
    :data:`pitloom.core.inert_options.INERT`).
    """
    configure_logging()
    target_path = Path(project_target)

    # A cheap stat, before any project-metadata/lock-file read, so the
    # build-flag WARNING: is the first thing this call logs.
    build_options = build_options.settle_target(target_path)

    if target_path.is_file():
        # Every option, not only today's inert ones, so a new INERT[SDIST]
        # row entry needs no change here.
        settle_inert(
            SDIST,
            target_path,
            {
                "pretty": pretty,
                "describe_relationship": describe_relationship,
                "enrich": enrich,
                "extract_file_header": extract_file_header,
                "content_type": content_type,
                "content_type_method": content_type_method,
                "max_source_metadata_bytes": max_source_metadata_bytes,
                "offline": offline,
                "id_registry": id_registry,
                "update_id_registry": update_id_registry,
                "creation_metadata": creation_metadata,
                "use_lockfile": use_lockfile,
            },
        )

    if project_metadata is None or pitloom_config is None:
        _warn_if_metadata_without_config(project_metadata, pitloom_config, target_path)
        project_metadata, pitloom_config, _ = resolve_project_with_lockfile(
            target_path, use_lockfile, pitloom_config
        )

    cfg = apply_overrides(
        pitloom_config,
        ConfigOverrides(
            provenance=provenance,
            enrich=enrich,
            extract_file_header=extract_file_header,
            content_type=content_type,
            content_type_method=content_type_method,
            offline=offline,
            pretty=pretty,
            describe_relationship=describe_relationship,
            update_id_registry=update_id_registry,
            max_source_metadata_bytes=max_source_metadata_bytes,
        ),
    )

    resolved_registry = resolve_registry(
        id_registry,
        cfg.id_registry,
        registry_base_dir(target_path),
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
            cleanup_discovery: Callable[[], None] = _noop_cleanup
        else:
            merkle_root, project_files, cleanup_discovery = get_wheel_files(
                target_path,
                scan_file_headers=cfg.extract_file_header,
                detect_content_type=cfg.content_type.enabled,
                content_type_method=cfg.content_type.method,
                content_type_overrides=cfg.content_type.overrides,
                build_options=build_options,
            )

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
                ai_models, cfg.enrich, target_path
            )
        finally:
            cleanup_discovery()

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or cfg.creation_metadata,
        ai_models=ai_models,
    )
    exporter = build(
        doc,
        merkle_root=merkle_root,
        sbom_type=spdx3_bindings.software_SbomType.source,
        registry=resolved_registry,
        enrichment_results_by_model=enrichment_results_by_model,
        **cfg.assemble_options,
    )

    if target_path.is_dir():
        merge_fragments(target_path, cfg.fragments, exporter)

    _sync_registry(exporter, resolved_registry, cfg.update_id_registry)

    sbom_json = exporter.to_json(
        pretty=cfg.pretty,
        describe_relationship=bool(cfg.describe_relationship),
    )

    write_sbom_output(sbom_json, output_path)

    return sbom_json
