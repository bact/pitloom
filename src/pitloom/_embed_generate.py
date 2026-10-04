# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generate the SBOM JSON a wheel embed writes: the early registry
resolve, the per-batch option settling, and the standalone (wheel-only)
or project-backed SBOM.

See also: :mod:`pitloom.embed` (the public embed API, which calls
:func:`_resolve_embed_registry` and :func:`_generate_embed_sbom_json`)
and :mod:`pitloom._embed_build_sbom` (the project-backed Build SBOM and
:class:`~pitloom._embed_build_sbom.EmbedFileCache`).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._embed_build_sbom import (
    EmbedFileCache,
    _build_sbom_from_project_and_wheel,
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
from pitloom.core.models import merkle_root_of_files
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import require_max_source_metadata_bytes
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.project import read_project
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from pitloom.id_registry import IdRegistry, registry_base_dir, resolve_registry


def _resolve_embed_registry(
    project_dir: Path | str | None,
    pitloom_config: PitloomConfig | None,
    id_registry: str | Path | IdRegistry | None,
) -> IdRegistry | None:
    """Resolve (and thereby validate) the registry
    :func:`~pitloom.embed.embed_wheel_sbom` would use, without needing
    ``wheel_metadata`` -- so a declared-but-bad registry can be caught
    before the wheel is read at all. Mirrors the
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
    validate the byte cap -- once per batch through *file_cache* when
    given, so a batch warns once, as :meth:`EmbedFileCache.settle` does for
    the build flags. Returns *overrides* with the cap validated, so the
    per-wheel :func:`apply_overrides` finds nothing left to warn about."""
    given_names = frozenset(name for name, value in given.items() if value is not None)

    def settle() -> None:
        settle_inert(kind, subject, given)

    def normalise() -> int | None:
        value = overrides.max_source_metadata_bytes
        if value is None:
            return None
        valid = require_max_source_metadata_bytes(value)  # even if inert
        if "max_source_metadata_bytes" in INERT[kind]:
            return None  # an inert cap is warned about by settle()
        return valid

    # The cap is checked first: an invalid one is an error, not an inert warning.
    if file_cache is None:
        cap = normalise()
        settle()
    else:
        cap = file_cache.once(
            ("max_source_metadata_bytes", overrides.max_source_metadata_bytes),
            normalise,
        )
        file_cache.once(("inert", kind, given_names), settle)
    return dataclasses.replace(overrides, max_source_metadata_bytes=cap)


# pylint: disable=too-many-arguments
def _generate_embed_sbom_json(
    wheel_metadata: ProjectMetadata,
    *,
    wheel_path: Path,
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

    *file_cache*: see :func:`~pitloom.embed.embed_wheel_sbom`'s own
    docstring -- passed through unchanged to
    :func:`_build_sbom_from_project_and_wheel`, the only branch below that
    reaches file discovery at all.
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
            wheel_path,
            wheel_metadata,
            cfg,
            creation_metadata or cfg.creation_metadata,
            resolve_registry(id_registry, cfg.id_registry, Path.cwd()),
            (file_cache, overrides.trust_wheel_model is True),
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
    wheel_path: Path,
    wheel_metadata: ProjectMetadata,
    cfg: PitloomConfig,
    creation_metadata: CreationMetadata,
    registry: IdRegistry | None,
    batch: tuple[EmbedFileCache | None, bool],
) -> str:
    """Build the SBOM for a wheel embedded with no source project directory.

    *batch*: the :class:`~pitloom.embed.EmbedFileCache` (``None`` outside a
    batch) and whether the wheel's models are read with every reader
    (``--trust-wheel-model``).

    *cfg* holds only explicit settings (an explicitly named config and the
    per-run overrides); nothing is borrowed from the current directory. The
    AI models are the ones inside the wheel. A batch (the cache in *batch*) hints at
    ``--scan-model-usage`` once, from the first wheel that has models, and
    likewise says once per format that a gated model was listed without
    metadata.
    """
    file_cache, trust = batch
    ai_models = scan_wheel_for_ai_models(
        wheel_path,
        scan_usage=cfg.scan_model_usage is True,
        usage_hint=lambda: (
            cfg.scan_model_usage is None
            and (
                file_cache is None
                or file_cache.first_use(("scan-usage-hint", "standalone"))
            )
        ),
        max_bytes=cfg.max_model_extract_bytes,
        trust=trust,
        gate_hint=lambda fmt: (
            file_cache is None or file_cache.first_use(("gate-hint", str(fmt)))
        ),
    )
    doc = DocumentModel(
        project=wheel_metadata,
        creation_metadata=creation_metadata,
        ai_models=ai_models,
        phantom_dependencies=find_phantom_dependencies(wheel_metadata.files),
    )
    exporter = assemble_spdx3(
        doc,
        merkle_root=merkle_root_of_files(wheel_metadata.files),
        sbom_type=spdx3.software_SbomType.analyzed,
        registry=registry,
        **cfg.assemble_options,
    )
    return exporter.to_json(pretty=False)
