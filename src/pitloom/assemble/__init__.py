# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE

"""SBOM assemblers for different output specifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.assemble.spdx3.document import build, build_deployed, build_model
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.assemble.spdx3.provenance import DEFAULT_SCHEMA_ID
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectMetadata
from pitloom.extract._huggingface import read_huggingface
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.env import read_environment
from pitloom.extract.project import read_project
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.extract.wheel import read_wheel
from pitloom.ids import IdRegistry, resolve_registry


def generate_sbom(
    project_dir: Path,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    project_metadata: ProjectMetadata | None = None,
    pitloom_config: PitloomConfig | None = None,
    registry: str | Path | IdRegistry | None = None,
) -> str:
    """Generate an SPDX 3 SBOM for a Python project.

    Args:
        project_dir: Path to the project directory.  Supports PEP 621
            ``[project]`` and Poetry ``[tool.poetry]`` in ``pyproject.toml``
            (``[project]`` wins field-by-field when both are present), or
            ``setup.cfg``/``setup.py`` when no ``pyproject.toml`` exists.
        output_path: If given, the JSON-LD output is also written to this path.
        creation_metadata: Creator and timestamp metadata for the SBOM document.
            When ``None`` a default :class:`~pitloom.core.creation.CreationMetadata`
            is used -- no named creator (the assembler emits the ``SoftwareAgent``
            ``"Pitloom"`` in ``createdBy``), current UTC time.
        pretty: If ``True``, indent the JSON output with 2 spaces.
            If ``False``, produce compact output (no extra whitespace).
            If ``None`` (default), read the setting from ``[tool.pitloom] pretty``
            in ``pyproject.toml`` (which itself defaults to ``False``).
        project_metadata: Pre-parsed project metadata, e.g. already loaded by
            a caller such as the CLI. When ``None`` (default), parsed from
            *project_dir* via :func:`~pitloom.extract.project.read_project`.
            Must be supplied together with *pitloom_config* -- if only one
            of the two is given, both are re-derived from *project_dir*
            instead. Mutated in place: its ``.files`` attribute is set from
            the wheel file scan.
        pitloom_config: Pre-parsed ``[tool.pitloom]`` settings, paired with
            *project_metadata* (see above).
        registry: A :class:`~pitloom.ids.IdRegistry`, a path to a registry
            JSON file, or ``None`` (default) to resolve one from
            ``[tool.pitloom.ids] file`` / auto-discovery -- see
            :func:`~pitloom.ids.resolve_registry`. Consulted so that wheel
            files reuse ids shared with ``pitloom.loom`` fragments.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.

    Raises:
        FileNotFoundError: If none of ``pyproject.toml``, ``setup.cfg``, or
            ``setup.py`` is found in ``project_dir`` (only checked when
            *metadata*/*pitloom_config* are not supplied).
        ValueError: If required project metadata (e.g., ``name``) is missing.
    """
    if project_metadata is None or pitloom_config is None:
        project_metadata, pitloom_config, _ = read_project(project_dir)
    effective_pretty: bool = pitloom_config.pretty if pretty is None else pretty
    effective_describe: bool = bool(
        pitloom_config.describe_relationship
        if describe_relationship is None
        else describe_relationship
    )

    # Compute Merkle root via hatchling's own file discovery so the UUID
    # matches the build-hook path exactly (same WheelBuilder, same file set).
    merkle_root, project_files = get_wheel_files(project_dir)
    project_metadata.files = project_files

    ai_models = scan_project_for_ai_models(project_dir, project_files)

    resolved_registry = (
        registry
        if isinstance(registry, IdRegistry)
        else IdRegistry.load(project_dir / registry)
        if registry is not None
        else resolve_registry(project_dir, pitloom_config.ids_file)
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
    )
    merge_fragments(project_dir, pitloom_config.fragments, exporter)

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


def generate_ai_model_sbom(
    model_path: Path,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool = False,
    describe_relationship: bool = False,
    registry: str | Path | IdRegistry | None = None,
    provenance_format: str = "both",
    provenance_schema: str = DEFAULT_SCHEMA_ID,
) -> str:
    """Generate a standalone SPDX 3 SBOM for a single AI model file.

    The model is treated as an ``ai_AIPackage`` root element - no surrounding
    Python project is required.

    Args:
        model_path: Path to the AI model file (GGUF, ONNX, Safetensors, etc.).
        output_path: If given, the JSON-LD output is also written to this path.
        creation_metadata: Creator and timestamp metadata.  Defaults to a
            ``CreationMetadata`` with no named creator (the assembler emits
            the ``SoftwareAgent`` ``"Pitloom"`` in ``createdBy``) and current
            UTC time.
        pretty: Indent JSON output with 2 spaces when ``True``.
        describe_relationship: Add human-readable text to SPDX relationships.
        registry: A :class:`~pitloom.ids.IdRegistry`, a path to a registry
            JSON file, or ``None`` (default) to auto-discover
            ``loom-ids.json`` from the current working directory. The
            model's file stem (e.g. ``"sentimentdemo"`` for
            ``models/sentimentdemo.bin``) is looked up as an ``ai_AIPackage``
            entity; a match reuses that registered ``spdxId`` so this SBOM's
            model and a ``pitloom.loom`` fragment's model can be unified at
            merge time.
        provenance_format: How to record metadata provenance -- see
            :mod:`pitloom.assemble.spdx3.provenance`.
        provenance_schema: Schema id for the provenance Annotation statement.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.

    Raises:
        FileNotFoundError: If *model_path* does not exist.
        ValueError: If the model format is unsupported or cannot be parsed.
    """
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
    )

    sbom_json = exporter.to_json(
        pretty=pretty,
        describe_relationship=describe_relationship,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


def generate_huggingface_sbom(
    model_source: str,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool = False,
    describe_relationship: bool = False,
    provenance_format: str = "both",
    provenance_schema: str = DEFAULT_SCHEMA_ID,
) -> str:
    """Generate a standalone SPDX 3 SBOM for a Hugging Face model repository.

    Fetches metadata from the Hugging Face Hub (``config.json``, model card,
    ``tokenizer_config.json``, etc.) and assembles an ``ai_AIPackage`` SBOM.
    No local model file is required.

    Args:
        model_source: Full HF URL
            (e.g. ``https://huggingface.co/mistralai/Mistral-7B-v0.1``)
            or bare model ID (e.g. ``Qwen/Qwen3-235B-A22B``).
        output_path: If given, the JSON-LD output is also written to this path.
        creation_metadata: Creator and timestamp metadata.  Defaults to a
            ``CreationMetadata`` with no named creator (the assembler emits
            the ``SoftwareAgent`` ``"Pitloom"`` in ``createdBy``) and current
            UTC time.
        pretty: Indent JSON output with 2 spaces when ``True``.
        describe_relationship: Add human-readable text to SPDX relationships.
        provenance_format: How to record metadata provenance -- see
            :mod:`pitloom.assemble.spdx3.provenance`.
        provenance_schema: Schema id for the provenance Annotation statement.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.

    Raises:
        ImportError: If ``huggingface_hub`` is not installed.
        ValueError: If *model_source* is not a valid Hugging Face URL or model ID.
    """
    model = read_huggingface(model_source)
    exporter = build_model(
        model,
        creation_metadata or CreationMetadata(),
        provenance_format=provenance_format,
        provenance_schema=provenance_schema,
    )

    sbom_json = exporter.to_json(
        pretty=pretty,
        describe_relationship=describe_relationship,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


def generate_analyzed_sbom(
    wheel_path: Path,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool = False,
    describe_relationship: bool = False,
    registry: str | Path | IdRegistry | None = None,
    provenance_format: str = "both",
    provenance_schema: str = DEFAULT_SCHEMA_ID,
) -> str:
    """Generate an Analyzed SPDX 3 SBOM for a built Python wheel.

    Args:
        wheel_path: Path to the .whl file.
        output_path: If given, the JSON-LD output is also written to this path.
        creation_metadata: Creator and timestamp metadata for the SBOM document.
        pretty: Indent JSON output with 2 spaces when True.
        describe_relationship: Add human-readable text to SPDX relationships.
        registry: A stable file/entity id registry (see IdRegistry).
        provenance_format: How to record metadata provenance -- see
            :mod:`pitloom.assemble.spdx3.provenance`.
        provenance_schema: Schema id for the provenance Annotation statement.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.
    """
    project_metadata, project_files = read_wheel(wheel_path)

    # The wheel file itself is the artifact identity here; no separate
    # source-tree Merkle root applies.
    merkle_root = None

    # AI model detection scans a source directory tree; wheel contents are
    # not scanned for models, so this is always empty for an Analyzed SBOM.
    ai_models: list[Any] = []

    phantom_deps = find_phantom_dependencies(project_files)

    # No project_dir is available to walk up from for loom-ids.json
    # auto-discovery, so the current directory is used as the search root.
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
        ai_models=ai_models,
        phantom_dependencies=phantom_deps,
    )
    exporter = build(
        doc,
        merkle_root=merkle_root,
        registry=resolved_registry,
        provenance_format=provenance_format,
        provenance_schema=provenance_schema,
    )

    sbom_json = exporter.to_json(
        pretty=pretty,
        describe_relationship=describe_relationship,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


def generate_deployed_sbom(
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool = False,
    describe_relationship: bool = False,
    registry: str | Path | IdRegistry | None = None,
    provenance_format: str = "both",
    provenance_schema: str = DEFAULT_SCHEMA_ID,
) -> str:
    """Generate a Deployed SPDX 3 SBOM for the current Python environment.

    Args:
        output_path: If given, the JSON-LD output is also written to this path.
        creation_metadata: Creator and timestamp metadata for the SBOM document.
        pretty: Indent JSON output with 2 spaces when True.
        describe_relationship: Add human-readable text to SPDX relationships.
        registry: A stable file/entity id registry (see IdRegistry).
        provenance_format: How to record metadata provenance -- see
            :mod:`pitloom.assemble.spdx3.provenance`.
        provenance_schema: Schema id for the provenance Annotation statement.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.
    """
    project_metadata, env_tree = read_environment()

    # No project_dir applies to a deployed-environment scan, so the current
    # directory is used as the loom-ids.json search root.
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
    )

    sbom_json = exporter.to_json(
        pretty=pretty,
        describe_relationship=describe_relationship,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


__all__ = [
    "generate_ai_model_sbom",
    "generate_analyzed_sbom",
    "generate_deployed_sbom",
    "generate_huggingface_sbom",
    "generate_sbom",
]
