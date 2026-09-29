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

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._embed_build_sbom import (
    EmbedFileCache,
    _build_sbom_from_project_and_wheel,
)
from pitloom._embed_wheel import (
    _DEFAULT_FILE_ATTR,
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
from pitloom._sbom_io import write_text_lf
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
    target_settle_plan,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import (
    ConfigOverrides,
    apply_overrides,
    resolve_standalone_config,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.inert_options import (
    EMBED_PROJECT,
    EMBED_SBOM,
    EMBED_STANDALONE,
    INERT,
    settle_inert,
)
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import normalize_max_source_metadata_bytes
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.project import read_project
from pitloom.extract.wheel import read_wheel
from pitloom.id_registry import IdRegistry, registry_base_dir, resolve_registry
from pitloom.logging_config import configure_logging

log = logging.getLogger(__name__)

__all__ = [
    "ConfigOverrides",
    "EmbedFileCache",
    "EmbeddedSbomLocation",
    "_DEFAULT_FILE_ATTR",
    "RECOMMENDED_EXTENSIONS",
    "VALIDATED_FORMATS",
    "_ZIP_EPOCH_FLOOR",
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
    "embed_filename",
    "embed_sbom_in_wheel",
    "embed_wheel_sbom",
    "find_embedded_sbom",
]


def embed_filename(sbom_basename: str | None) -> str | None:
    """The file name an SBOM is embedded under for *sbom_basename*
    (``--sbom-basename``/``[tool.pitloom] sbom-basename``), or ``None`` for
    the default name. Shared by ``embed-wheel`` and ``wheel --embed``."""
    if not sbom_basename:
        return None
    return (
        f"{sbom_basename.removesuffix(SPDX3_JSONLD_EXTENSION)}{SPDX3_JSONLD_EXTENSION}"
    )


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


def _resolve_embed_registry(
    project_dir: Path | str | None,
    pitloom_config: PitloomConfig | None,
    id_registry: str | Path | IdRegistry | None,
) -> IdRegistry | None:
    """Resolve (and thereby validate) the registry :func:`embed_wheel_sbom`
    would use, without needing ``wheel_metadata`` -- so a declared-but-bad
    registry can be caught before the wheel is read at all. Mirrors the
    two branches :func:`_generate_embed_sbom_json` resolves the registry
    in (standalone vs. project-backed). Raises :class:`ValueError` on a
    bad registry, same as :func:`~pitloom.id_registry.resolve_registry`.

    An explicit *id_registry* always wins, so the project's own config is
    never read for it (skips the peek entirely). Returns the resolved
    :class:`IdRegistry` (or ``None``) so the caller can feed it back in,
    short-circuiting :func:`_generate_embed_sbom_json`'s own resolve
    instead of loading the file a second time.
    """
    base_dir = (
        Path.cwd()
        if project_dir is None
        else registry_base_dir(Path(project_dir).resolve())
    )
    if id_registry is not None:
        return resolve_registry(id_registry, None, base_dir)
    if pitloom_config is not None:
        cfg = pitloom_config
    elif project_dir is None:
        cfg = PitloomConfig()
    else:
        # quiet=True: a discarded peek (only cfg.id_registry is used) --
        # _generate_embed_sbom_json's real re-read emits this WARNING once.
        _, cfg, _ = read_project(
            Path(project_dir).resolve(),
            include_locked_dependencies=False,
            include_installed_metadata=False,
            quiet=True,
        )
    return resolve_registry(None, cfg.id_registry, base_dir)


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
    id_registry: str | Path | IdRegistry | None = None,
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
    eff_overrides = overrides if overrides is not None else ConfigOverrides()
    if sbom_path is None:
        # Fail on a declared-but-bad registry before the wheel is ever
        # read -- a real ``read_wheel()`` opens/parses the archive, work
        # worth skipping when this run cannot proceed anyway. Only when
        # *sbom_path* is unset: with an external SBOM,
        # ``_generate_embed_sbom_json``'s own early-return branch never
        # touches the registry at all (see its docstring), so there is
        # nothing to resolve here. The resolved ``IdRegistry`` (or
        # ``None``) is fed back in as *this call's own* ``id_registry``
        # below, so ``_generate_embed_sbom_json``'s own
        # ``resolve_registry()`` call short-circuits on the
        # already-resolved instance rather than loading the file again.
        id_registry = _resolve_embed_registry(project_dir, pitloom_config, id_registry)
    wheel_metadata, _ = read_wheel(wheel_obj)

    sbom_json, eff_basename = _generate_embed_sbom_json(
        wheel_metadata,
        project_dir=project_dir,
        pitloom_config=pitloom_config,
        sbom_path=sbom_path,
        sbom_basename=sbom_basename,
        creation_metadata=creation_metadata,
        id_registry=id_registry,
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
    res_path, arcname, removed_arcnames, timestamp_floored = embed_sbom_in_wheel(
        wheel_obj, sbom_json, sbom_filename=embed_filename(eff_basename)
    )

    if output_path is not None:
        write_text_lf(output_path, sbom_json)

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


def _settle_embed_options(
    kind: str,
    subject: object,
    given: dict[str, object],
    overrides: ConfigOverrides,
    file_cache: EmbedFileCache | None,
) -> ConfigOverrides:
    """Warn about every option in *given* that *kind* cannot use, and
    normalise the byte cap -- once per batch through *file_cache* when
    given, so a batch warns once, as :meth:`EmbedFileCache.settle` does for
    the build flags. Returns *overrides* with the cap normalised, so the
    per-wheel :func:`apply_overrides` finds nothing left to warn about."""
    given_names = frozenset(name for name, value in given.items() if value is not None)

    def settle() -> None:
        settle_inert(kind, subject, given)

    def normalise() -> int | None:
        value = overrides.max_source_metadata_bytes
        if value is None or "max_source_metadata_bytes" in INERT[kind]:
            return None  # an inert cap warned above; no second warning
        return normalize_max_source_metadata_bytes(value)

    if file_cache is None:
        settle()
        cap = normalise()
    else:
        file_cache.once(("inert", kind, given_names), settle)
        cap = file_cache.once(
            ("max_source_metadata_bytes", overrides.max_source_metadata_bytes),
            normalise,
        )
    return dataclasses.replace(overrides, max_source_metadata_bytes=cap)


# pylint: disable=too-many-arguments
def _generate_embed_sbom_json(
    wheel_metadata: ProjectMetadata,
    *,
    project_dir: Path | str | None,
    pitloom_config: PitloomConfig | None,
    sbom_path: Path | str | None,
    sbom_basename: str | None,
    creation_metadata: CreationMetadata | None,
    id_registry: str | Path | IdRegistry | None,
    overrides: ConfigOverrides,
    file_cache: EmbedFileCache | None = None,
) -> tuple[str, str | None]:
    """Resolve the SBOM JSON to embed and its effective basename.

    *file_cache*: see :func:`embed_wheel_sbom`'s own docstring -- passed
    through unchanged to :func:`_build_sbom_from_project_and_wheel`,
    the only branch below that reaches file discovery at all.
    """
    given = {
        **{
            field.name: getattr(overrides, field.name)
            for field in dataclasses.fields(ConfigOverrides)
        },
        "id_registry": id_registry,
        "creation_metadata": creation_metadata,
        "pitloom_config": pitloom_config,
        "project_dir": project_dir,
    }
    if sbom_path is not None:
        _settle_build_options(
            overrides.build_options,
            file_cache,
            wheel_metadata.name,
            EXTERNAL_SBOM_REASON,
        )
        _settle_embed_options(
            EMBED_SBOM, wheel_metadata.name, given, overrides, file_cache
        )
        return Path(sbom_path).read_text(encoding="utf-8"), sbom_basename

    if project_dir is None:
        _settle_build_options(
            overrides.build_options,
            file_cache,
            wheel_metadata.name,
            NO_PROJECT_DIR_REASON,
        )
        overrides = _settle_embed_options(
            EMBED_STANDALONE, wheel_metadata.name, given, overrides, file_cache
        )
        cfg = resolve_standalone_config(pitloom_config, overrides)
        sbom_json = _build_sbom_standalone_wheel(
            wheel_metadata,
            cfg,
            creation_metadata or cfg.creation_metadata,
            resolve_registry(id_registry, cfg.id_registry, Path.cwd()),
        )
        return sbom_json, sbom_basename or cfg.sbom_basename

    proj_root = Path(project_dir).resolve()
    # This is the one branch that reaches file discovery, so settle a
    # stray no_isolation/timeout (and warn about it) before the
    # project-config read below -- a direct embed_wheel_sbom() caller
    # that didn't already settle upstream still gets the warning first,
    # ahead of any config-parse WARNING: that read can produce. (An
    # earlier, quiet=True peek in _resolve_embed_registry never warns,
    # but still raises there on a malformed config, before this settling.)
    settle, reason = target_settle_plan(proj_root)
    settled_build_options = (
        _settle_build_options(overrides.build_options, file_cache, proj_root, reason)
        if settle
        else overrides.build_options
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

    overrides = _settle_embed_options(
        EMBED_PROJECT, proj_root, given, overrides, file_cache
    )
    cfg = apply_overrides(cfg, overrides)
    sbom_json = _build_sbom_from_project_and_wheel(
        proj_root,
        wheel_metadata,
        cfg,
        resolve_registry(id_registry, cfg.id_registry, registry_base_dir(proj_root)),
        creation_metadata or cfg.creation_metadata,
        build_options=settled_build_options,
        file_cache=file_cache,
    )
    return sbom_json, sbom_basename or cfg.sbom_basename


def _build_sbom_standalone_wheel(
    wheel_metadata: ProjectMetadata,
    cfg: PitloomConfig,
    creation_metadata: CreationMetadata,
    registry: IdRegistry | None,
) -> str:
    """Build the SBOM for a wheel embedded with no source project directory.

    *cfg* holds only explicit settings (an explicitly named config and the
    per-run overrides); nothing is borrowed from the current directory.
    """
    doc = DocumentModel(
        project=wheel_metadata,
        creation_metadata=creation_metadata,
        ai_models=[],
        phantom_dependencies=find_phantom_dependencies(wheel_metadata.files),
    )
    exporter = assemble_spdx3(
        doc,
        merkle_root=None,
        sbom_type=spdx3.software_SbomType.analyzed,
        registry=registry,
        **cfg.assemble_options,
    )
    return exporter.to_json(pretty=False)
