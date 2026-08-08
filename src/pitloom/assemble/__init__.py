# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE

"""SBOM assemblers for different output specifications."""

from __future__ import annotations

from pathlib import Path

from pitloom.assemble.spdx3.document import build, build_deployed, build_model
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.assemble.spdx3.provenance import DEFAULT_SCHEMA_ID
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectMetadata
from pitloom.extract._huggingface import is_huggingface_source, read_huggingface
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.env import read_environment
from pitloom.extract.project import read_project
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.extract.wheel import read_wheel
from pitloom.ids import IdRegistry, resolve_registry


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
) -> str:
    """Generate a Source SPDX 3 SBOM for a Python project or sdist archive.

    Args:
        project_target: Path to a project directory or an sdist archive (.tar.gz, .zip).
        output_path: If given, the JSON-LD output is written to this path.
        creation_metadata: Creator and timestamp metadata.
        pretty: Indent JSON output when True.
        describe_relationship: Add human-readable text to SPDX relationships.
        project_metadata: Pre-parsed project metadata.
        pitloom_config: Pre-parsed config settings.
        registry: IdRegistry or path to registry file.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.
    """
    target_path = Path(project_target)
    if project_metadata is None or pitloom_config is None:
        project_metadata, pitloom_config, _ = read_project(target_path)

    effective_pretty: bool = pitloom_config.pretty if pretty is None else pretty
    effective_describe: bool = bool(
        pitloom_config.describe_relationship
        if describe_relationship is None
        else describe_relationship
    )

    if target_path.is_file():
        # Sdist archive case
        merkle_root = None
        project_files = project_metadata.files
        search_root = target_path.parent
    else:
        # Directory case
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
        registry=resolved_registry,
        provenance_format=pitloom_config.provenance_format,
        provenance_schema=pitloom_config.provenance_schema,
        provenance_detail=pitloom_config.provenance_detail,
        provenance_preserve_source_metadata=(
            pitloom_config.provenance_preserve_source_metadata
        ),
    )

    if target_path.is_dir():
        merge_fragments(target_path, pitloom_config.fragments, exporter)

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


# pylint: disable=too-many-arguments
def generate_wheel_sbom(
    wheel_path: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool = False,
    describe_relationship: bool = False,
    registry: str | Path | IdRegistry | None = None,
    provenance_format: str = "both",
    provenance_schema: str = DEFAULT_SCHEMA_ID,
    provenance_detail: str = "minimal",
    provenance_preserve_source_metadata: str = "auto",
) -> str:
    """Generate an Analyzed SPDX 3 SBOM for a built Python wheel.

    Args:
        wheel_path: Path to the .whl file.
        output_path: If given, JSON-LD output is written to this path.
        creation_metadata: Creator and timestamp metadata.
        pretty: Indent JSON output when True.
        describe_relationship: Add human-readable text to SPDX relationships.
        registry: IdRegistry or path to registry file.
        provenance_format: Metadata provenance format.
        provenance_schema: Schema id for provenance Annotations.
        provenance_detail: Provenance detail level ("minimal" or "full").
        provenance_preserve_source_metadata: How to preserve source metadata.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.
    """
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
        registry=resolved_registry,
        provenance_format=provenance_format,
        provenance_schema=provenance_schema,
        provenance_detail=provenance_detail,
        provenance_preserve_source_metadata=provenance_preserve_source_metadata,
    )

    sbom_json = exporter.to_json(
        pretty=pretty,
        describe_relationship=describe_relationship,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


# pylint: disable=too-many-arguments,too-many-positional-arguments
def generate_model_sbom(
    source: Path | str,
    *,
    offline: bool = False,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool = False,
    describe_relationship: bool = False,
    registry: str | Path | IdRegistry | None = None,
    provenance_format: str = "both",
    provenance_schema: str = DEFAULT_SCHEMA_ID,
    provenance_detail: str = "minimal",
    provenance_preserve_source_metadata: str = "auto",
) -> str:
    """Generate an Analyzed SPDX 3 AIBOM for a local model file or HF repository.

    Args:
        source: Path to local model file (GGUF, ONNX, Safetensors, etc.) OR
            Hugging Face URL / bare model ID.
        offline: If True, forbids network requests (raises ValueError for HF targets).
        output_path: If given, JSON-LD output is written to this path.
        creation_metadata: Creator and timestamp metadata.
        pretty: Indent JSON output when True.
        describe_relationship: Add human-readable text to SPDX relationships.
        registry: IdRegistry or path to registry file.
        provenance_format: Metadata provenance format.
        provenance_schema: Schema id for provenance Annotations.
        provenance_detail: Provenance detail level.
        provenance_preserve_source_metadata: How to preserve source metadata.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.
    """
    source_str = str(source)
    is_hf = is_huggingface_source(source_str)

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

    exporter = build_model(
        model,
        creation_metadata or CreationMetadata(),
        entity_spdx_id=entity_spdx_id,
        provenance_format=provenance_format,
        provenance_schema=provenance_schema,
        provenance_detail=provenance_detail,
        provenance_preserve_source_metadata=provenance_preserve_source_metadata,
    )

    sbom_json = exporter.to_json(
        pretty=pretty,
        describe_relationship=describe_relationship,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


# pylint: disable=too-many-arguments
def generate_env_sbom(
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool = False,
    describe_relationship: bool = False,
    registry: str | Path | IdRegistry | None = None,
    provenance_format: str = "both",
    provenance_schema: str = DEFAULT_SCHEMA_ID,
    provenance_detail: str = "minimal",
) -> str:
    """Generate a Deployed SPDX 3 SBOM for the current installed environment.

    Args:
        output_path: If given, JSON-LD output is written to this path.
        creation_metadata: Creator and timestamp metadata.
        pretty: Indent JSON output when True.
        describe_relationship: Add human-readable text to SPDX relationships.
        registry: IdRegistry or path to registry file.
        provenance_format: Metadata provenance format.
        provenance_schema: Schema id for provenance Annotations.
        provenance_detail: Provenance detail level.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.
    """
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
        provenance_format=provenance_format,
        provenance_schema=provenance_schema,
        provenance_detail=provenance_detail,
    )

    sbom_json = exporter.to_json(
        pretty=pretty,
        describe_relationship=describe_relationship,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


# pylint: disable=too-many-arguments
def generate(
    target: Path | str = ".",
    *,
    offline: bool = False,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool = False,
    describe_relationship: bool = False,
    registry: str | Path | IdRegistry | None = None,
) -> str:
    """Smart unified entrypoint for generating SPDX 3 SBOMs across all target types.

    Auto-detects target type:
    - `"env"` / `"environment"` -> Deployed SBOM for current environment.
    - `.whl` file -> Analyzed Wheel SBOM.
    - Local model file / HF URL -> Analyzed AI Model SBOM.
    - Directory or sdist archive -> Source SBOM.

    Args:
        target: Target path, HF URL/ID, or "env". Defaults to current directory.
        offline: If True, forbids network requests for remote targets.
        output_path: Optional file path to write output.
        creation_metadata: Creator and timestamp metadata.
        pretty: Indent JSON output when True.
        describe_relationship: Add human-readable text to SPDX relationships.
        registry: IdRegistry or path to registry file.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.
    """
    target_str = str(target).strip()

    if target_str.lower() in ("env", "environment", "--env"):
        return generate_env_sbom(
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=registry,
        )

    if target_str.lower().endswith(".whl"):
        return generate_wheel_sbom(
            target_str,
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=registry,
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
        )

    target_path = Path(target)
    if target_path.is_file():
        # Check if local model file vs sdist archive
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
            )

    return generate_project_sbom(
        target_path,
        output_path=output_path,
        creation_metadata=creation_metadata,
        pretty=pretty,
        describe_relationship=describe_relationship,
        registry=registry,
    )


__all__ = [
    "generate",
    "generate_env_sbom",
    "generate_model_sbom",
    "generate_project_sbom",
    "generate_wheel_sbom",
]
