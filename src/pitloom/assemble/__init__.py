# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM assemblers for different output specifications."""

from __future__ import annotations

import sys
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3_bindings

from pitloom.assemble.spdx3.document import build, build_deployed, build_model
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import PitloomConfig, read_pitloom_config
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich import run_enrichers
from pitloom.enrich.base import EnrichmentResult
from pitloom.extract._huggingface import is_huggingface_source, read_huggingface
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.env import read_environment
from pitloom.extract.project import read_project
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.extract.wheel import read_wheel
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

    if target_path.is_file():
        merkle_root = None
        project_files = project_metadata.files
        search_root = target_path.parent
    else:
        merkle_root, project_files = get_wheel_files(target_path)
        project_metadata.files = project_files
        search_root = target_path

    ai_models = (
        scan_project_for_ai_models(target_path, project_files)
        if target_path.is_dir()
        else []
    )

    resolved_registry = (
        registry
        if isinstance(registry, IdRegistry)
        else IdRegistry.load(search_root / registry)
        if registry is not None
        else resolve_registry(search_root, pitloom_config.ids_file)
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
    )

    if target_path.is_dir():
        merge_fragments(target_path, pitloom_config.fragments, exporter)

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
) -> str:
    """Generate an Analyzed SPDX 3 SBOM for a built Python wheel."""
    effective_pretty = False if pretty is None else pretty
    effective_describe = (
        False if describe_relationship is None else describe_relationship
    )
    wheel_path_obj = Path(wheel_path)
    project_metadata, project_files = read_wheel(wheel_path_obj)
    phantom_deps = find_phantom_dependencies(project_files)

    cwd = Path.cwd()
    resolved_registry = (
        registry
        if isinstance(registry, IdRegistry)
        else IdRegistry.load(cwd / registry)
        if registry is not None
        else resolve_registry(cwd, None)
    )

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
    )

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json


def generate_model_sbom(
    source: Path | str,
    *,
    offline: bool = False,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
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
        if offline:
            raise ValueError(
                "Offline mode enabled: cannot fetch remote Hugging Face source "
                f"'{source_str}'"
            )
        model = read_huggingface(source_str)
        entity_spdx_id = None
    else:
        model_path = Path(source)
        model = read_ai_model(model_path)
        resolved_registry = (
            registry
            if isinstance(registry, IdRegistry)
            else IdRegistry.load(Path(registry))
            if registry is not None
            else IdRegistry.find()
        )
        entity_spdx_id = (
            resolved_registry.lookup_entity(model_path.stem, "ai_AIPackage")
            if resolved_registry is not None
            else None
        )

        model_dir = model_path.parent
        try:
            enrich_config = read_pitloom_config(model_dir / "pyproject.toml").enrich
        except FileNotFoundError:
            enrich_config = EnrichConfig()
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


def generate_env_sbom(
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
) -> str:
    """Generate a Deployed SPDX 3 SBOM for the current installed environment."""
    effective_pretty = False if pretty is None else pretty
    effective_describe = (
        False if describe_relationship is None else describe_relationship
    )
    project_metadata, env_tree = read_environment()

    cwd = Path.cwd()
    resolved_registry = (
        registry
        if isinstance(registry, IdRegistry)
        else IdRegistry.load(cwd / registry)
        if registry is not None
        else resolve_registry(cwd, None)
    )

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
    )

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json


def generate(
    target: Path | str = ".",
    *,
    offline: bool = False,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
) -> str:
    """Smart unified entrypoint for generating SPDX 3 SBOMs across all target types."""
    target_str = str(target).strip()

    if target_str.lower() in ("env", "environment", "--env"):
        return generate_env_sbom(
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=registry,
            provenance=provenance,
        )

    if target_str.lower().endswith(".whl"):
        return generate_wheel_sbom(
            target_str,
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=registry,
            provenance=provenance,
        )

    if is_huggingface_source(target_str):
        return generate_model_sbom(
            target_str,
            offline=offline,
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=registry,
            provenance=provenance,
        )

    target_path = Path(target)
    if target_path.is_file():
        name_lower = target_path.name.lower()
        if any(
            name_lower.endswith(ext)
            for ext in (
                ".gguf",
                ".safetensors",
                ".onnx",
                ".pt",
                ".pth",
                ".h5",
                ".hdf5",
                ".keras",
                ".npy",
                ".npz",
                ".bin",
                ".ftz",
            )
        ):
            return generate_model_sbom(
                target_path,
                offline=offline,
                output_path=output_path,
                creation_metadata=creation_metadata,
                pretty=pretty,
                describe_relationship=describe_relationship,
                registry=registry,
                provenance=provenance,
            )

    return generate_project_sbom(
        target_path,
        output_path=output_path,
        creation_metadata=creation_metadata,
        pretty=pretty,
        describe_relationship=describe_relationship,
        registry=registry,
        provenance=provenance,
    )


__all__ = [
    "ProvenanceConfig",
    "generate",
    "generate_env_sbom",
    "generate_model_sbom",
    "generate_project_sbom",
    "generate_wheel_sbom",
    "merge_fragments",
]
