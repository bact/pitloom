# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Embed SPDX 3 SBOMs into built Python wheels (PEP 770).

See also: :mod:`pitloom._embed_wheel` for ZIP archive manipulation and RECORD updating.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._embed_wheel import (
    _DEFAULT_FILE_ATTR,
    _INVALID_FILENAME_CHARS,
    _ZIP_EPOCH_FLOOR,
    _calculate_record_hash,
    _derive_wheel_sbom_filename,
    _looks_like_pitloom_sbom,
    _plan_embed,
    _resolve_zip_timestamp,
    _rewrite_wheel_archive,
    _update_record_lines,
    _validate_sbom_filename,
    embed_sbom_in_wheel,
)
from pitloom._sbom_format import (
    _RECOMMENDED_EXTENSIONS,
    _VALIDATED_FORMATS,
    _detect_sbom_format,
)
from pitloom._wheel_sbom_location import (
    EmbeddedSbomLocation,
    _find_dist_info_prefix,
    find_embedded_sbom,
)
from pitloom.assemble.spdx3.document import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import VALID_CONTENT_TYPE_METHODS, PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import _build_merkle_tree, get_wheel_files
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich import run_enrichers_for_models
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.project import read_project
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.extract.wheel import read_wheel
from pitloom.ids import IdRegistry, resolve_registry
from pitloom.logging_config import configure_logging

__all__ = [
    "ConfigOverrides",
    "EmbeddedSbomLocation",
    "_DEFAULT_FILE_ATTR",
    "_INVALID_FILENAME_CHARS",
    "_RECOMMENDED_EXTENSIONS",
    "_VALIDATED_FORMATS",
    "_ZIP_EPOCH_FLOOR",
    "_apply_config_overrides",
    "_build_sbom_from_project_and_wheel",
    "_build_sbom_standalone_wheel",
    "_calculate_record_hash",
    "_derive_wheel_sbom_filename",
    "_detect_sbom_format",
    "_find_dist_info_prefix",
    "_generate_embed_sbom_json",
    "_looks_like_pitloom_sbom",
    "_plan_embed",
    "_resolve_zip_timestamp",
    "_rewrite_wheel_archive",
    "_update_record_lines",
    "_validate_sbom_filename",
    "embed_sbom_in_wheel",
    "embed_wheel_sbom",
    "find_embedded_sbom",
]


def _merge_file_extras(
    wheel_files: list[ProjectFile], project_files: list[ProjectFile]
) -> list[ProjectFile]:
    """Layer re-scanned content-type/header data onto the wheel's own files.

    ``wheel_files`` (from :func:`pitloom.extract.wheel.read_wheel`) is the
    source of truth for what the already-built wheel actually contains --
    including ``.dist-info/*`` entries and any build-hook-injected files
    that never existed in ``project_dir`` -- so it is kept intact,
    including its hashes computed from the wheel's own bytes.
    ``project_files`` (from :func:`~pitloom.core.models.get_wheel_files`)
    only supplies the content-type/file-header extras it computed by
    re-scanning the sources, adopted for files present in both lists.
    """
    extras_by_path = {f.distribution_path: f for f in project_files}
    merged: list[ProjectFile] = []
    for wheel_file in wheel_files:
        extra = extras_by_path.get(wheel_file.distribution_path)
        if extra is None:
            merged.append(wheel_file)
            continue
        merged.append(
            dataclasses.replace(
                wheel_file,
                copyright_text=extra.copyright_text,
                copyright_source=extra.copyright_source,
                file_contributors=extra.file_contributors,
                file_type=extra.file_type,
                spdx_license_identifier=extra.spdx_license_identifier,
                content_type=extra.content_type,
                content_type_method=extra.content_type_method,
            )
        )
    return merged


def _compute_wheel_merkle_root(files: list[ProjectFile]) -> str | None:
    """Merkle root over *files*' own digests -- the wheel's truth, not a rescan.

    Mirrors :func:`pitloom.core._models_wheel.get_wheel_files`'s ordering
    (sort by ``distribution_path``) and hashing convention so the result is
    reproducible the same way, but computed from files whose
    ``digest_sha256`` already reflects the wheel's own bytes (post-merge)
    instead of a fresh ``project_dir`` rescan that can diverge from them.
    """
    if not files:
        return None
    ordered = sorted(files, key=lambda f: f.distribution_path)
    leaf_hashes = [bytes.fromhex(f.digest_sha256) for f in ordered]
    return _build_merkle_tree(leaf_hashes)


def _build_sbom_from_project_and_wheel(
    project_dir: Path,
    wheel_metadata: ProjectMetadata,
    pitloom_config: PitloomConfig,
    registry: IdRegistry | None,
    creation_metadata: CreationMetadata | None,
) -> str:
    """Generate a canonical Build SBOM from project sources and wheel files."""
    # merkle_root (the rescan's own, over project_dir's on-disk bytes) is
    # deliberately discarded here -- see _compute_wheel_merkle_root below,
    # which recomputes it from the wheel's own (post-merge) file hashes so
    # it can't diverge from what merged_files actually reports.
    _, project_files = get_wheel_files(
        project_dir,
        scan_file_headers=pitloom_config.extract_file_header,
        detect_content_type=pitloom_config.content_type.enabled,
        content_type_method=pitloom_config.content_type.method,
        content_type_overrides=pitloom_config.content_type.overrides,
    )
    # Layer content-type/file-header extras onto the wheel's own file
    # records rather than replacing them outright: replacing would drop
    # .dist-info entries and any build-hook-injected files (e.g. compiled
    # extensions, auditwheel-repaired shared libraries) that read_wheel()
    # found in the actual wheel but that a source-tree rescan can't see.
    merged_files = _merge_file_extras(wheel_metadata.files, project_files)
    # dataclasses.replace, not an in-place `.files =` assignment, so the
    # caller's wheel_metadata (e.g. embed_wheel_sbom's read_wheel() result)
    # isn't silently mutated as a side effect of building this SBOM.
    project_metadata = dataclasses.replace(wheel_metadata, files=merged_files)
    merkle_root = _compute_wheel_merkle_root(merged_files)
    ai_models = scan_project_for_ai_models(project_dir, project_files)
    phantom_deps = find_phantom_dependencies(merged_files)
    enrichment_results = run_enrichers_for_models(
        ai_models, pitloom_config.enrich, project_dir
    )

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=ai_models,
        phantom_dependencies=phantom_deps,
    )
    exporter = assemble_spdx3(
        doc,
        merkle_root=merkle_root,
        sbom_type=spdx3.software_SbomType.build,
        registry=registry,
        provenance=pitloom_config.provenance,
        enrichment_results_by_model=enrichment_results,
        offline=pitloom_config.offline,
    )
    merge_fragments(project_dir, pitloom_config.fragments, exporter)
    return exporter.to_json(pretty=False)


@dataclasses.dataclass(frozen=True)
class ConfigOverrides:
    """Per-run overrides layered onto a project's ``[tool.pitloom]`` config."""

    provenance: ProvenanceConfig | None = None
    enrich: bool | None = None
    extract_file_header: bool | None = None
    content_type: bool | None = None
    content_type_method: str | None = None
    offline: bool | None = None


# pylint: disable=too-many-arguments
# pylint: disable-next=too-many-locals
def embed_wheel_sbom(
    wheel_path: Path | str,
    *,
    project_dir: Path | str | None = None,
    pitloom_config: PitloomConfig | None = None,
    sbom_path: Path | str | None = None,
    output_path: Path | str | None = None,
    sbom_basename: str | None = None,
    creation_metadata: CreationMetadata | None = None,
    registry: str | Path | IdRegistry | None = None,
    overrides: ConfigOverrides | None = None,
) -> tuple[Path, str, str, tuple[str, ...], bool]:
    """Generate and embed a PEP 770 SBOM into a built Python wheel."""
    configure_logging()
    wheel_obj = Path(wheel_path).resolve()
    wheel_metadata, _ = read_wheel(wheel_obj)
    eff_overrides = overrides if overrides is not None else ConfigOverrides()

    sbom_json, eff_basename = _generate_embed_sbom_json(
        wheel_metadata,
        project_dir=project_dir,
        pitloom_config=pitloom_config,
        sbom_path=sbom_path,
        sbom_basename=sbom_basename,
        creation_metadata=creation_metadata,
        registry=registry,
        overrides=eff_overrides,
    )
    target_filename = (
        f"{eff_basename.removesuffix(SPDX3_JSONLD_EXTENSION)}{SPDX3_JSONLD_EXTENSION}"
        if eff_basename
        else None
    )

    res_path, arcname, removed_arcnames, timestamp_floored = embed_sbom_in_wheel(
        wheel_obj, sbom_json, sbom_filename=target_filename
    )

    if output_path is not None:
        Path(output_path).write_text(sbom_json, encoding="utf-8")

    return res_path, arcname, sbom_json, removed_arcnames, timestamp_floored


# pylint: disable=too-many-arguments
def _generate_embed_sbom_json(
    wheel_metadata: ProjectMetadata,
    *,
    project_dir: Path | str | None,
    pitloom_config: PitloomConfig | None,
    sbom_path: Path | str | None,
    sbom_basename: str | None,
    creation_metadata: CreationMetadata | None,
    registry: str | Path | IdRegistry | None,
    overrides: ConfigOverrides,
) -> tuple[str, str | None]:
    """Resolve the SBOM JSON to embed and its effective basename."""
    if sbom_path is not None:
        return Path(sbom_path).read_text(encoding="utf-8"), sbom_basename

    if project_dir is None:
        sbom_json = _build_sbom_standalone_wheel(
            wheel_metadata,
            creation_metadata,
            registry,
            overrides.provenance,
            overrides.offline,
        )
        return sbom_json, sbom_basename

    proj_root = Path(project_dir).resolve()
    if pitloom_config is None:
        _, cfg, _ = read_project(proj_root)
    else:
        cfg = pitloom_config

    cfg = _apply_config_overrides(cfg, overrides)
    eff_registry = registry if registry is not None else cfg.ids_file
    reg = resolve_registry(proj_root, eff_registry)
    sbom_json = _build_sbom_from_project_and_wheel(
        proj_root, wheel_metadata, cfg, reg, creation_metadata or cfg.creation_metadata
    )
    return sbom_json, sbom_basename or cfg.sbom_basename


def _apply_config_overrides(
    cfg: PitloomConfig, overrides: ConfigOverrides
) -> PitloomConfig:
    """Apply per-run overrides to a PitloomConfig."""
    changes: dict[str, Any] = {}
    if overrides.provenance is not None:
        changes["provenance_format"] = overrides.provenance.format
        changes["provenance_schema"] = overrides.provenance.schema
        changes["provenance_detail"] = overrides.provenance.detail
        changes["provenance_preserve_source_metadata"] = (
            overrides.provenance.preserve_source_metadata
        )
    if overrides.enrich is not None:
        changes["enrich_local"] = overrides.enrich
    if overrides.extract_file_header is not None:
        changes["extract_file_header"] = overrides.extract_file_header
    if overrides.content_type is not None:
        changes["content_type_enabled"] = overrides.content_type
    if overrides.content_type_method is not None:
        if overrides.content_type_method not in VALID_CONTENT_TYPE_METHODS:
            raise ValueError(
                "content_type_method must be one of "
                f"{sorted(VALID_CONTENT_TYPE_METHODS)}, got "
                f"{overrides.content_type_method!r}"
            )
        changes["content_type_method"] = overrides.content_type_method
    if overrides.offline is not None:
        changes["offline"] = overrides.offline
    return dataclasses.replace(cfg, **changes)


def _build_sbom_standalone_wheel(
    wheel_metadata: ProjectMetadata,
    creation_metadata: CreationMetadata | None,
    registry: str | Path | IdRegistry | None,
    provenance: ProvenanceConfig | None,
    offline: bool | None,
) -> str:
    """Build SBOM from standalone wheel when no source project dir is present."""
    reg = resolve_registry(Path.cwd(), registry)
    doc = DocumentModel(
        project=wheel_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=[],
        phantom_dependencies=find_phantom_dependencies(wheel_metadata.files),
    )
    exporter = assemble_spdx3(
        doc,
        merkle_root=None,
        sbom_type=spdx3.software_SbomType.analyzed,
        registry=reg,
        provenance=provenance,
        offline=offline or False,
    )
    return exporter.to_json(pretty=False)
