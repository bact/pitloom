# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Embed SPDX 3 SBOMs into built Python wheels (PEP 770).

See also: :mod:`pitloom._embed_wheel` for ZIP archive manipulation and
RECORD updating; :mod:`pitloom._embed_build_sbom` for the Build SBOM made
from a project directory's rescan and the wheel's own files.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._embed_build_sbom import (
    EmbedFileCache,
    _build_sbom_from_project_and_wheel,
)
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
    RECOMMENDED_EXTENSIONS,
    VALIDATED_FORMATS,
    check_spdx3_name_version,
    detect_sbom_format,
    format_name_version_mismatch,
)
from pitloom._wheel_sbom_location import (
    EmbeddedSbomLocation,
    _find_dist_info_prefix,
    find_embedded_sbom,
)
from pitloom.assemble.spdx3.document import build as assemble_spdx3
from pitloom.core.build_options import (
    EXTERNAL_SBOM_REASON,
    NO_PROJECT_DIR_REASON,
    BuildOptions,
)
from pitloom.core.config import VALID_CONTENT_TYPE_METHODS, PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.project import read_project
from pitloom.extract.wheel import read_wheel
from pitloom.ids import IdRegistry, resolve_registry
from pitloom.logging_config import configure_logging

log = logging.getLogger(__name__)

__all__ = [
    "ConfigOverrides",
    "EmbedFileCache",
    "EmbeddedSbomLocation",
    "_DEFAULT_FILE_ATTR",
    "_INVALID_FILENAME_CHARS",
    "RECOMMENDED_EXTENSIONS",
    "VALIDATED_FORMATS",
    "_ZIP_EPOCH_FLOOR",
    "_apply_config_overrides",
    "_build_sbom_from_project_and_wheel",
    "_build_sbom_standalone_wheel",
    "_calculate_record_hash",
    "_derive_wheel_sbom_filename",
    "detect_sbom_format",
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


@dataclasses.dataclass(frozen=True)
class ConfigOverrides:
    """Per-run overrides layered onto a project's ``[tool.pitloom]`` config.

    Attributes:
        build_options: ``--allow-build`` and its companion flags (see
            :class:`~pitloom.core.build_options.BuildOptions`). Unlike
            every other field here, deliberately has no
            ``[tool.pitloom]`` cascade to defer to. Threaded into
            ``_build_sbom_from_project_and_wheel()``'s own project-dir
            rescan, whose only use for the resulting file list is
            layering content-type/file-header extras onto the wheel's
            already-known files (see that function's own comment on
            discarding the rescan's ``merkle_root``/digests) -- so on a
            project whose backend has no static discovery module (or
            whose static discovery fails), enabling this runs a full,
            real, potentially slow PEP 517 build *purely* to compute
            those extras more accurately, not to learn the file list
            itself (the wheel's own ``read_wheel()`` result already has
            that). Deliberate: this is the only way ``embed-wheel``
            avoids silently staying stuck on the Hatchling-heuristic
            rescan for such a project's content-type/header extras.
    """

    provenance: ProvenanceConfig | None = None
    enrich: bool | None = None
    extract_file_header: bool | None = None
    content_type: bool | None = None
    content_type_method: str | None = None
    offline: bool | None = None
    build_options: BuildOptions = BuildOptions()


def _enforce_sbom_name_version(
    wheel_filename: str,
    wheel_name: str | None,
    wheel_version: str | None,
    sbom_json: str,
    *,
    allow_mismatch: bool,
) -> None:
    """Cross-check an externally-supplied ``--sbom``'s declared subject
    name/version against the target wheel's own METADATA, *before*
    anything is written to the wheel.

    Raises ``ValueError`` on a genuine mismatch unless *allow_mismatch* --
    the embed is refused outright rather than writing a known-wrong SBOM
    and relying on a later `verify-wheel`/`--verify` to catch it, since
    nothing is on disk yet to roll back. *allow_mismatch* downgrades a
    mismatch to a `WARNING:` and lets the embed proceed (for CI/automation
    that wants best-effort embedding). Extraction failures (unsupported
    format, unexpected graph shape) are always a non-fatal `WARNING:`,
    regardless of *allow_mismatch* -- "couldn't check" is never escalated
    to "refused."

    Fatal-by-default here, unlike `verify-wheel`'s own WARNING-by-default
    (:func:`pitloom.cli.commands.verify_wheel._check_name_version`) --
    intentional, not an inconsistency: this runs *before* a wheel is
    written, so refusing is cheap (nothing to roll back), whereas
    verify-wheel inspects an already-built wheel after the fact.
    """
    sbom_data = sbom_json.encode("utf-8")
    sbom_format = detect_sbom_format(sbom_data)
    mismatches, warnings = check_spdx3_name_version(
        wheel_name, wheel_version, sbom_data, sbom_format
    )
    for warning in warnings:
        log.warning("%s: %s", wheel_filename, warning)

    if not mismatches:
        return

    message = format_name_version_mismatch(wheel_filename, mismatches)
    if allow_mismatch:
        log.warning(message)
        return
    raise ValueError(message)


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
    allow_mismatch: bool = False,
    file_cache: EmbedFileCache | None = None,
) -> tuple[Path, str, str, tuple[str, ...], bool]:
    """Generate and embed a PEP 770 SBOM into a built Python wheel.

    When *sbom_path* supplies an externally-generated SBOM, its declared
    subject name/version is cross-checked against the wheel's own
    ``.dist-info/METADATA`` before anything is written -- see
    :func:`_enforce_sbom_name_version`. A genuine mismatch raises
    ``ValueError`` unless *allow_mismatch*. A Pitloom-generated SBOM
    (*sbom_path* unset) is never checked -- it's built from this same
    *wheel_metadata*, so it can't diverge.

    *file_cache*: advanced/batch use only -- share one
    :class:`EmbedFileCache` across several calls that target the same
    *project_dir*/*pitloom_config*/``overrides.build_options`` (e.g. one
    wheel per call, in a loop) to resolve *project_dir*'s file list (and
    run any ``--allow-build`` real PEP 517 build) once for the whole
    batch instead of once per call, and to warn about each ineffective
    build flag once for the batch. Left ``None`` (the default), this
    call resolves and cleans up its own file list. When given, *this*
    call does NOT clean up -- make every call of the batch inside one
    ``with EmbedFileCache() as file_cache:`` block, whose exit does; a
    cache used outside its block raises :class:`RuntimeError`.
    """
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
        file_cache=file_cache,
    )
    if sbom_path is not None:
        # wheel_metadata.name defaults to the sentinel "unknown" (never
        # None) when METADATA has no Name header -- comparing that
        # placeholder against the SBOM would either report a bogus
        # mismatch or silently "match" an SBOM literally named "unknown".
        # `provenance` only gains a "name"/"version" key when a real
        # header was found (see `_populate_metadata_from_email`), so it's
        # the correct signal for "was this field actually present" --
        # the same real-None-on-missing semantics `read_wheel_name_version`
        # (verify-wheel's own path) already has.
        wheel_name = (
            wheel_metadata.name if "name" in wheel_metadata.provenance else None
        )
        wheel_version = (
            wheel_metadata.version if "version" in wheel_metadata.provenance else None
        )
        _enforce_sbom_name_version(
            wheel_obj.name,
            wheel_name,
            wheel_version,
            sbom_json,
            allow_mismatch=allow_mismatch,
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


def _settle_build_options(
    build_options: BuildOptions,
    file_cache: EmbedFileCache | None,
    subject: object,
    reason: str | None = None,
) -> BuildOptions:
    """Settle *build_options* for one wheel: once per batch through
    *file_cache* when given (see :meth:`EmbedFileCache.settle`), else
    right here."""
    if file_cache is not None:
        return file_cache.settle(build_options, subject, reason)
    if reason is None:
        return build_options.settle(subject)
    return build_options.settle_not_applicable(subject, reason)


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
    file_cache: EmbedFileCache | None = None,
) -> tuple[str, str | None]:
    """Resolve the SBOM JSON to embed and its effective basename.

    *file_cache*: see :func:`embed_wheel_sbom`'s own docstring -- passed
    through unchanged to :func:`_build_sbom_from_project_and_wheel`,
    the only branch below that reaches file discovery at all.
    """
    if sbom_path is not None:
        _settle_build_options(
            overrides.build_options,
            file_cache,
            wheel_metadata.name,
            EXTERNAL_SBOM_REASON,
        )
        return Path(sbom_path).read_text(encoding="utf-8"), sbom_basename

    if project_dir is None:
        _settle_build_options(
            overrides.build_options,
            file_cache,
            wheel_metadata.name,
            NO_PROJECT_DIR_REASON,
        )
        sbom_json = _build_sbom_standalone_wheel(
            wheel_metadata,
            creation_metadata,
            registry,
            overrides.provenance,
            overrides.offline,
        )
        return sbom_json, sbom_basename

    proj_root = Path(project_dir).resolve()
    # This is the one branch that reaches file discovery, so settle a
    # stray no_isolation/timeout (and warn about it) before the
    # project-config read below -- a direct embed_wheel_sbom() caller
    # that didn't already settle upstream still gets the warning first,
    # ahead of any config-parse WARNING: that read can produce.
    settled_build_options = _settle_build_options(
        overrides.build_options, file_cache, proj_root
    )
    if pitloom_config is None:
        # Only [tool.pitloom] config is used here -- skip the lock/pin
        # cascade (embed-wheel is build-stage; a source-stage lock file's
        # resolved dependencies must never leak into an embedded SBOM) and
        # skip in-tree installed-metadata resolution (same build-stage
        # rationale, and this caller discards the metadata anyway).
        _, cfg, _ = read_project(
            proj_root,
            include_locked_dependencies=False,
            include_installed_metadata=False,
        )
    else:
        cfg = pitloom_config

    cfg = _apply_config_overrides(cfg, overrides)
    eff_registry = registry if registry is not None else cfg.ids_file
    reg = resolve_registry(proj_root, eff_registry)
    sbom_json = _build_sbom_from_project_and_wheel(
        proj_root,
        wheel_metadata,
        cfg,
        reg,
        creation_metadata or cfg.creation_metadata,
        build_options=settled_build_options,
        file_cache=file_cache,
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
