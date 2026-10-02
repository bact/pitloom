# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM assemblers for different output specifications.

See also:
- :mod:`pitloom.assemble._generators` for the project/sdist generator.
- :mod:`pitloom.assemble._generators_wheel` /
  :mod:`pitloom.assemble._generators_env` for the wheel and environment
  generators, and :mod:`pitloom.assemble._generators_shared` for what they share.
- :mod:`pitloom.assemble._model_generator` for AI model SBOM generation and enrichment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.assemble._generators import generate_project_sbom
from pitloom.assemble._generators_env import generate_env_sbom
from pitloom.assemble._generators_wheel import (
    generate_wheel_sbom,
    generate_wheel_sbom_with_metadata,
)
from pitloom.assemble._model_generator import (
    enrich_model,
    generate_model_sbom,
)
from pitloom.assemble.spdx3.fragments import FragmentMergeError, merge_fragments
from pitloom.core.build_options import NON_PROJECT_TARGET_REASON, BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides
from pitloom.core.creation import CreationMetadata
from pitloom.core.inert_options import ENV, HF, MODEL_FILE, WHEEL, forward_options
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import (
    RECOMMENDED_EXTENSIONS,
    VALIDATED_FORMATS,
    EmbeddedSbomLocation,
    detect_sbom_format,
    embed_sbom_in_wheel,
    embed_wheel_sbom,
    find_embedded_sbom,
)
from pitloom.extract.remote import is_huggingface_source
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import configure_logging

__all__ = [
    "BuildOptions",
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
    "generate_wheel_sbom_with_metadata",
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


def _classify_target(target: Path | str) -> str:
    """Classify *target* into ``"env"``, ``"wheel"``, ``"hf"``,
    ``"model_file"``, or ``"project"`` (plain directory or sdist archive).

    Single source of truth for :func:`generate`'s own dispatch and for
    :func:`target_resolves_to_project` -- one shared check instead of two
    independently-maintained classifications drifting apart.
    """
    target_str = str(target).strip()
    if target_str.lower() in ("env", "environment", "--env"):
        return "env"
    if target_str.lower().endswith(".whl"):
        return "wheel"
    if is_huggingface_source(target_str):
        return "hf"
    target_path = Path(target_str)
    if target_path.is_file() and target_path.name.lower().endswith(
        _MODEL_FILE_EXTENSIONS
    ):
        return "model_file"
    return "project"


def target_resolves_to_project(target: Path | str) -> bool:
    """Return whether :func:`generate`'s dispatch reaches
    :func:`~pitloom.assemble._generators.generate_project_sbom` (a plain
    project directory or sdist archive) for *target*, rather than the
    env/wheel/Hugging-Face/model-file branches.

    ``pitloom.cli.commands.generate._run_generate_command`` calls it to
    route a project target through the same code path as ``loom project``
    and every other target through :func:`generate`.
    """
    return _classify_target(target) == "project"


# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def generate(
    target: Path | str = ".",
    *,
    offline: bool | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    scan_model_usage: bool | None = None,
    trust_wheel_model: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    update_id_registry: bool | None = None,
    use_lockfile: bool | None = None,
    build_options: BuildOptions = BuildOptions(),
    max_source_metadata_bytes: int | None = None,
    pitloom_config: PitloomConfig | None = None,
) -> str:
    """Smart unified entrypoint for generating SPDX 3 SBOMs across all target types.

    ``build_options`` (see :class:`~pitloom.core.build_options.BuildOptions`)
    only takes effect for a project directory target (the
    ``generate_project_sbom()`` dispatch below); any other target logs
    one ``WARNING:`` per given build flag here, immediately, before
    dispatching. A "project" classification covers both a project
    directory and an sdist archive (the two aren't told apart until
    ``generate_project_sbom()`` itself checks), so that dispatch settles/
    warns about ``build_options`` on its own, right before its own
    metadata read -- not repeated here.
    """
    # Before the no-effect warnings below, which precede any delegate's own
    # configure_logging() call.
    configure_logging()
    target_str = str(target).strip()
    classification = _classify_target(target_str)

    if classification != "project":
        # Reset to defaults too (not just warn): nothing below reuses
        # build_options for a non-project classification, but this keeps
        # the same "warn once, reset to defaults" contract every other
        # settle_not_applicable() call site follows, so a future caller
        # added here can't accidentally double-warn.
        build_options = build_options.settle_not_applicable(
            target_str, NON_PROJECT_TARGET_REASON
        )

    options: dict[str, Any] = {
        "output_path": output_path,
        "creation_metadata": creation_metadata,
        "pretty": pretty,
        "describe_relationship": describe_relationship,
        "id_registry": id_registry,
        "provenance": provenance,
        "offline": offline,
        "enrich": enrich,
        "extract_file_header": extract_file_header,
        "scan_model_usage": scan_model_usage,
        "trust_wheel_model": trust_wheel_model,
        "content_type": content_type,
        "content_type_method": content_type_method,
        "update_id_registry": update_id_registry,
        "max_source_metadata_bytes": max_source_metadata_bytes,
        "pitloom_config": pitloom_config,
        "use_lockfile": use_lockfile,
    }
    # Each delegate gets what it accepts; an option it does not accept is
    # settled here, once, with the target kind's reason.
    if classification == "env":
        return generate_env_sbom(
            **forward_options(ENV, target_str, generate_env_sbom, options)
        )
    if classification == "wheel":
        return generate_wheel_sbom(
            target_str,
            **forward_options(WHEEL, target_str, generate_wheel_sbom, options),
        )
    if classification == "hf":
        return generate_model_sbom(
            target_str,
            **forward_options(HF, target_str, generate_model_sbom, options),
        )
    if classification == "model_file":
        return generate_model_sbom(
            Path(target_str),
            **forward_options(MODEL_FILE, target_str, generate_model_sbom, options),
        )
    return generate_project_sbom(
        Path(target_str),
        **options,
        build_options=build_options,
    )
