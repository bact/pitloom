# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM assemblers for different output specifications.

See also:
- :mod:`pitloom.assemble._generators` for project, wheel, and environment generators.
- :mod:`pitloom.assemble._model_generator` for AI model SBOM generation and enrichment.
"""

from __future__ import annotations

from pathlib import Path

from pitloom.assemble._generators import (
    generate_env_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.assemble._model_generator import (
    enrich_model,
    generate_model_sbom,
)
from pitloom.assemble.spdx3.fragments import FragmentMergeError, merge_fragments
from pitloom.core.creation import CreationMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import (
    RECOMMENDED_EXTENSIONS,
    VALIDATED_FORMATS,
    ConfigOverrides,
    EmbeddedSbomLocation,
    detect_sbom_format,
    embed_sbom_in_wheel,
    embed_wheel_sbom,
    find_embedded_sbom,
)
from pitloom.extract._huggingface import is_huggingface_source
from pitloom.ids import IdRegistry

__all__ = [
    "ConfigOverrides",
    "EmbeddedSbomLocation",
    "FragmentMergeError",
    "ProvenanceConfig",
    "RECOMMENDED_EXTENSIONS",
    "VALIDATED_FORMATS",
    "detect_sbom_format",
    "embed_sbom_in_wheel",
    "embed_wheel_sbom",
    "enrich_model",
    "find_embedded_sbom",
    "generate",
    "generate_env_sbom",
    "generate_model_sbom",
    "generate_project_sbom",
    "generate_wheel_sbom",
    "merge_fragments",
    "target_resolves_to_project",
]

_MODEL_FILE_EXTENSIONS = (
    ".gguf",
    ".safetensors",
    ".onnx",
    ".pt",
    ".pth",
    ".pt2",
    ".h5",
    ".hdf5",
    ".keras",
    ".npy",
    ".npz",
    ".bin",
    ".ftz",
)


def target_resolves_to_project(target: Path | str) -> bool:
    """Return whether :func:`generate`'s dispatch reaches
    :func:`~pitloom.assemble._generators.generate_project_sbom` (a plain
    project directory or sdist archive) for *target*, rather than the
    env/wheel/Hugging-Face/model-file branches.

    The single source of truth for that classification -- :func:`generate`
    itself uses it for its own dispatch, and
    ``pitloom.cli.commands.generate._run_generate_command`` calls it ahead
    of time to decide whether its own config-only project peek
    (:func:`pitloom.cli.options._resolve_common_options`) would otherwise
    duplicate a ``WARNING:`` that :func:`generate_project_sbom`'s real read
    re-emits for the same directory -- one shared check instead of two
    independently-maintained classifications drifting apart.
    """
    target_str = str(target).strip()
    if target_str.lower() in ("env", "environment", "--env"):
        return False
    if target_str.lower().endswith(".whl"):
        return False
    if is_huggingface_source(target_str):
        return False
    target_path = Path(target_str)
    if target_path.is_file() and target_path.name.lower().endswith(
        _MODEL_FILE_EXTENSIONS
    ):
        return False
    return True


# pylint: disable=too-many-arguments,too-many-positional-arguments
def generate(
    target: Path | str = ".",
    *,
    offline: bool | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    update_registry: bool | None = None,
    use_lockfile: bool | None = None,
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
            offline=offline,
            update_registry=update_registry,
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
            offline=offline,
            update_registry=update_registry,
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
            enrich=enrich,
        )

    target_path = Path(target)
    if target_path.is_file():
        name_lower = target_path.name.lower()
        if name_lower.endswith(_MODEL_FILE_EXTENSIONS):
            return generate_model_sbom(
                target_path,
                offline=offline,
                output_path=output_path,
                creation_metadata=creation_metadata,
                pretty=pretty,
                describe_relationship=describe_relationship,
                registry=registry,
                provenance=provenance,
                enrich=enrich,
            )

    return generate_project_sbom(
        target_path,
        output_path=output_path,
        creation_metadata=creation_metadata,
        pretty=pretty,
        describe_relationship=describe_relationship,
        registry=registry,
        provenance=provenance,
        enrich=enrich,
        extract_file_header=extract_file_header,
        content_type=content_type,
        content_type_method=content_type_method,
        offline=offline,
        update_registry=update_registry,
        use_lockfile=use_lockfile,
    )
