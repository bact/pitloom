# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model SBOM and enrichment fragment generators."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble.spdx3.document import build_enrichment_fragment, build_model
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides, resolve_standalone_config
from pitloom.core.creation import CreationMetadata
from pitloom.core.inert_options import (
    ENRICH_STANDALONE,
    HF,
    MODEL_FILE,
    SDIST,
    settle_inert,
)
from pitloom.core.models import compute_doc_uuid, get_wheel_files
from pitloom.core.project import ProjectMetadata, is_sdist_archive
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich import run_enrichers
from pitloom.enrich.base import EnrichmentResult
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.project import (
    resolve_project_with_lockfile,
)
from pitloom.extract.remote import is_huggingface_source, read_huggingface
from pitloom.id_registry import (
    IdRegistry,
    IdRegistrySession,
    registry_base_dir,
    resolve_registry,
)
from pitloom.logging_config import configure_logging

log = logging.getLogger(__name__)


def _project_doc_identity(
    project_dir: Path,
    *,
    use_lockfile: bool | None = None,
    explicit_config: PitloomConfig | None = None,
) -> tuple[str, str]:
    """Compute ``(doc_name, doc_uuid)`` for a project directory.

    ``doc_uuid`` is content-addressed via ``merkle_root`` (see
    :func:`~pitloom.core.models.compute_doc_uuid`), so it changes
    whenever :func:`~pitloom.core.models.get_wheel_files`'s resolved
    file set changes for this project -- including when a backend's
    file-discovery accuracy improves without any file on disk actually
    changing. Callers merging an enrichment fragment against a
    previously-generated SBOM should regenerate that base SBOM first
    after a Pitloom upgrade that changes file discovery for this
    project's backend, or the fragment's element references may not
    match the base document's spdxIds.

    ``use_lockfile`` must match whatever setting produced the base document
    being merged into, or the computed ``doc_uuid`` will diverge from it
    (see ``pitloom.core.models.compute_doc_uuid``'s use of its own
    ``locked_dependencies`` data). When omitted, it follows
    *explicit_config*'s ``use-lockfile``, else *project_dir*'s own, as
    :func:`~pitloom.extract.project.resolve_project_with_lockfile` decides
    for the base document.
    """
    project_metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
        project_dir, use_lockfile, explicit_config
    )
    return _doc_identity_of(project_dir, project_metadata)


def _doc_identity_of(
    project_dir: Path, project_metadata: ProjectMetadata
) -> tuple[str, str]:
    """``(doc_name, doc_uuid)`` for *project_metadata*, resolved from
    *project_dir* (see :func:`~pitloom.core.models.compute_doc_uuid` for
    the content-addressing this ``doc_uuid`` is built from)."""
    # build_options intentionally omitted (no --allow-build): this doc-identity
    # helper is only reachable from the model/enrich commands, which have
    # no --allow-build CLI flag of their own to read. The returned
    # cleanup is therefore always a no-op; call it immediately.
    merkle_root: str | None = None
    if not project_dir.is_file():  # an sdist has no file walk, as in its SBOM
        merkle_root, project_files, _cleanup = get_wheel_files(project_dir)
        _cleanup()
        project_metadata.files = project_files
    doc_uuid = compute_doc_uuid(
        name=project_metadata.name,
        version=project_metadata.version or "unknown",
        dependencies=project_metadata.dependencies,
        merkle_root=merkle_root,
        locked_dependencies=project_metadata.locked_dependencies,
        locked_dependencies_provenance=project_metadata.provenance.get(
            "locked_dependencies"
        ),
    )
    return project_metadata.name, doc_uuid


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
# pylint: disable=too-many-arguments,too-many-locals
def generate_model_sbom(
    source: Path | str,
    *,
    offline: bool | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    max_source_metadata_bytes: int | None = None,
    pitloom_config: PitloomConfig | None = None,
) -> str:
    """Generate an Analyzed SPDX 3 AIBOM for a local model file or HF repository.

    Settings resolve as :func:`~pitloom.assemble.generate_wheel_sbom`
    describes: arguments, then an explicit *pitloom_config*, then the
    built-in defaults. Nothing is read from the current directory or from
    the model file's own directory.

    Three parameters apply to one source kind only, and warn when given for
    the other (see :data:`pitloom.core.inert_options.INERT`): *offline* for
    a Hugging Face source (a local file never reaches the network), and
    *enrich*/*id_registry* for a local file.
    """
    configure_logging()
    source_str = str(source)
    is_hf = is_huggingface_source(source_str)
    settle_inert(
        HF if is_hf else MODEL_FILE,
        source_str,
        {"offline": offline, "enrich": enrich, "id_registry": id_registry},
    )
    cfg = resolve_standalone_config(
        pitloom_config,
        ConfigOverrides(
            provenance=provenance,
            enrich=enrich,
            offline=offline,
            pretty=pretty,
            describe_relationship=describe_relationship,
            max_source_metadata_bytes=max_source_metadata_bytes,
        ),
    )
    enrichment_results: list[EnrichmentResult] = []

    if is_hf:
        if cfg.offline:
            raise ValueError(
                "Offline mode enabled: cannot fetch remote Hugging Face source "
                f"'{source_str}'"
            )
        model = read_huggingface(source_str)
        entity_spdx_id = None
    else:
        model_path = Path(source)
        # Resolved before read_ai_model()/run_enrichers() below -- a
        # declared-but-missing/malformed registry should fail fast, never
        # after paying for a model read and enrichment first.
        resolved_registry = resolve_registry(id_registry, cfg.id_registry, Path.cwd())
        model = read_ai_model(model_path)
        entity_spdx_id = IdRegistrySession(resolved_registry).entity_id(
            model_path.stem, [model_path.stem], "ai_AIPackage"
        )
        enrichment_results = run_enrichers(model, cfg.enrich, model_path.parent)

    exporter = build_model(
        model,
        creation_metadata or cfg.creation_metadata,
        entity_spdx_id=entity_spdx_id,
        provenance=cfg.provenance,
        enrichment_results=enrichment_results,
    )

    sbom_json = exporter.to_json(
        pretty=cfg.pretty,
        describe_relationship=bool(cfg.describe_relationship),
    )

    write_sbom_output(sbom_json, output_path)

    return sbom_json


# pylint: disable=too-many-arguments,too-many-locals
def enrich_model(
    source: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    enrich: bool | None = None,
    project_target: Path | str | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    use_lockfile: bool | None = None,
    pitloom_config: PitloomConfig | None = None,
) -> str:
    """Run enrichment only for a local model file.

    Settings come from the arguments, then an explicit *pitloom_config*,
    then the built-in defaults; nothing is read from the current directory
    or from the model file's directory. The registry is *id_registry*,
    else the explicit config's ``id-registry``; with *project_target*, the
    project's own ``id-registry`` key applies instead, since that project
    is the document the fragment will merge into.
    """
    configure_logging()
    source_str = str(source)
    if is_huggingface_source(source_str):
        raise ValueError(
            f"'{source_str}' is a Hugging Face source; local enrichment "
            "does not apply there -- Hugging Face model cards are already "
            "parsed natively when generating the SBOM."
        )
    # The CLI passes use_lockfile through, so this is the one layer that
    # settles it, before any work (an sdist project target as a project).
    if project_target is None:
        settle_inert(ENRICH_STANDALONE, source_str, {"use_lockfile": use_lockfile})
    elif is_sdist_archive(Path(project_target)):
        settle_inert(SDIST, project_target, {"use_lockfile": use_lockfile})
    cfg = resolve_standalone_config(pitloom_config, ConfigOverrides(pretty=pretty))

    model_path = Path(source)
    # Registry resolved before read_ai_model()/run_enrichers() below -- a
    # declared-but-missing/malformed registry should fail fast, never
    # after paying for a model read and enrichment first.
    if project_target is None:
        base_doc_identity = None
        resolved_registry = resolve_registry(id_registry, cfg.id_registry, Path.cwd())
    else:
        # The project the fragment merges into, resolved as its base SBOM
        # is: its identity and registry come from the config that SBOM
        # used (an explicit config, else the project's own). Registry
        # resolved right after resolve_project_with_lockfile(), before
        # _doc_identity_of()'s own file walk.
        project_dir = Path(project_target)
        base_metadata, base_config, _ = resolve_project_with_lockfile(
            project_dir, use_lockfile, pitloom_config
        )
        # An sdist's directory is not its project, as in its base SBOM.
        resolved_registry = resolve_registry(
            id_registry,
            base_config.id_registry,
            registry_base_dir(project_dir),
        )
        base_doc_identity = _doc_identity_of(project_dir, base_metadata)

    model = read_ai_model(model_path)
    # Unlike generate_model_sbom()/generate_project_sbom(), the config's
    # enrich setting is NOT an "off by default" gate here: calling
    # enrich_model() at all is itself the opt-in (see
    # test_enrich_model_writes_bare_graph_fragment's docstring). Only an
    # explicit enrich=False turns it back off.
    enrich_config = dataclasses.replace(cfg.enrich, local=enrich is not False)
    results = run_enrichers(model, enrich_config, model_path.parent)

    entity_spdx_id = IdRegistrySession(resolved_registry).entity_id(
        model_path.stem, [model_path.stem], "ai_AIPackage"
    )

    exporter = build_enrichment_fragment(
        model,
        results,
        creation_metadata or cfg.creation_metadata,
        entity_spdx_id=entity_spdx_id,
        base_doc_identity=base_doc_identity,
    )

    fragment_json = exporter.to_json(pretty=cfg.pretty)

    write_sbom_output(fragment_json, output_path)

    return fragment_json
