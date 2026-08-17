# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model SBOM and enrichment fragment generators."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

from pitloom.assemble.spdx3.document import build_enrichment_fragment, build_model
from pitloom.core.config import read_pitloom_config
from pitloom.core.creation import CreationMetadata
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.models import compute_doc_uuid, get_wheel_files
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich import run_enrichers
from pitloom.enrich.base import EnrichmentResult
from pitloom.extract._huggingface import is_huggingface_source, read_huggingface
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.project import read_project
from pitloom.ids import IdRegistry, resolve_registry


def _write_output_file(sbom_json: str, output_path: Path | None) -> None:
    """Write SBOM output to file or stdout if output_path is '-'."""
    if output_path is None:
        return
    if str(output_path) == "-":
        sys.stdout.write(sbom_json)
        if not sbom_json.endswith("\n"):
            sys.stdout.write("\n")
    else:
        output_path.write_text(sbom_json, encoding="utf-8")


def _resolve_local_offline_default(directory: Path) -> bool:
    """Read ``[tool.pitloom] offline`` from *directory*'s pyproject.toml."""
    try:
        return read_pitloom_config(directory / "pyproject.toml").offline
    except FileNotFoundError:
        return False


def _resolve_model_enrich_config(model_dir: Path) -> EnrichConfig:
    """Read ``[tool.pitloom] enrich`` from a ``pyproject.toml`` in *model_dir*."""
    try:
        return read_pitloom_config(model_dir / "pyproject.toml").enrich
    except FileNotFoundError:
        return EnrichConfig()


def _project_doc_identity(project_dir: Path) -> tuple[str, str]:
    """Compute ``(doc_name, doc_uuid)`` for a project directory."""
    project_metadata, _pitloom_config, _config_path = read_project(project_dir)
    merkle_root, project_files = get_wheel_files(project_dir)
    project_metadata.files = project_files
    doc_uuid = compute_doc_uuid(
        name=project_metadata.name,
        version=project_metadata.version or "unknown",
        dependencies=project_metadata.dependencies,
        merkle_root=merkle_root,
    )
    return project_metadata.name, doc_uuid


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def generate_model_sbom(
    source: Path | str,
    *,
    offline: bool | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
) -> str:
    """Generate an Analyzed SPDX 3 AIBOM for a local model file or HF repository."""
    effective_pretty = False if pretty is None else pretty
    effective_describe = (
        False if describe_relationship is None else describe_relationship
    )
    source_str = str(source)
    is_hf = is_huggingface_source(source_str)
    enrichment_results: list[EnrichmentResult] = []

    if is_hf:
        effective_offline = (
            _resolve_local_offline_default(Path.cwd()) if offline is None else offline
        )
        if effective_offline:
            raise ValueError(
                "Offline mode enabled: cannot fetch remote Hugging Face source "
                f"'{source_str}'"
            )
        model = read_huggingface(source_str)
        entity_spdx_id = None
    else:
        model_path = Path(source)
        model = read_ai_model(model_path)
        resolved_registry = resolve_registry(Path.cwd(), registry)
        entity_spdx_id = (
            resolved_registry.lookup_entity(model_path.stem, "ai_AIPackage")
            if resolved_registry is not None
            else None
        )

        model_dir = model_path.parent
        enrich_config = _resolve_model_enrich_config(model_dir)
        if enrich is not None:
            enrich_config = dataclasses.replace(enrich_config, local=enrich)
        enrichment_results = run_enrichers(model, enrich_config, model_dir)

    exporter = build_model(
        model,
        creation_metadata or CreationMetadata(),
        entity_spdx_id=entity_spdx_id,
        provenance=provenance,
        enrichment_results=enrichment_results,
    )

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def enrich_model(
    source: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    enrich: bool | None = None,
    project_target: Path | str | None = None,
    registry: str | Path | IdRegistry | None = None,
) -> str:
    """Run enrichment only for a local model file."""
    effective_pretty = False if pretty is None else pretty
    source_str = str(source)
    if is_huggingface_source(source_str):
        raise ValueError(
            f"'{source_str}' is a Hugging Face source; local enrichment "
            "does not apply there -- Hugging Face model cards are already "
            "parsed natively when generating the SBOM."
        )

    model_path = Path(source)
    model = read_ai_model(model_path)
    model_dir = model_path.parent
    enrich_config = dataclasses.replace(
        _resolve_model_enrich_config(model_dir), local=enrich is not False
    )
    results = run_enrichers(model, enrich_config, model_dir)

    base_doc_identity = (
        _project_doc_identity(Path(project_target))
        if project_target is not None
        else None
    )
    resolved_registry = resolve_registry(Path.cwd(), registry)
    entity_spdx_id = (
        resolved_registry.lookup_entity(model_path.stem, "ai_AIPackage")
        if resolved_registry is not None
        else None
    )

    exporter = build_enrichment_fragment(
        model,
        results,
        creation_metadata or CreationMetadata(),
        entity_spdx_id=entity_spdx_id,
        base_doc_identity=base_doc_identity,
    )

    fragment_json = exporter.to_json(pretty=effective_pretty)

    _write_output_file(fragment_json, output_path)

    return fragment_json
