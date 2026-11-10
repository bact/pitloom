# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Public SBOM-generation entry points: :func:`generate` and the per-target
generators it dispatches to.

See also:
- :mod:`pitloom.assemble._generators` for the project/sdist generator.
- :mod:`pitloom.assemble._generators_git` for the remote Git repository
  generator, and :mod:`pitloom.assemble._generators_pypi` for the wheel or
  sdist of a release named by a PyPI URL.
- :mod:`pitloom.assemble._generators_wheel` /
  :mod:`pitloom.assemble._generators_env` for the wheel and environment
  generators, and :mod:`pitloom.assemble._generators_shared` for what they share.
- :mod:`pitloom.assemble._model_generator` for AI model SBOM generation and enrichment.
- :mod:`pitloom.assemble._generators_merge` for merging a fragment directory.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pitloom.assemble._generators import generate_project_sbom
from pitloom.assemble._generators_env import generate_env_sbom
from pitloom.assemble._generators_git import (
    generate_git_project_sbom,
    generate_git_sbom,
)
from pitloom.assemble._generators_merge import generate_merged_sbom
from pitloom.assemble._generators_pypi import (
    PypiSbom,
    generate_pypi_sbom,
    generate_pypi_sbom_with_download,
)
from pitloom.assemble._generators_wheel import (
    generate_wheel_sbom,
    generate_wheel_sbom_with_metadata,
)
from pitloom.assemble._model_generator import (
    enrich_model,
    generate_model_sbom,
    project_document_id,
)
from pitloom.assemble.spdx3.fragments import FragmentMergeError, merge_fragments
from pitloom.core.build_options import NON_PROJECT_TARGET_REASON, BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import (
    ConfigOverrides,
    require_download_override,
    require_model_extract_override,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.inert_options import (
    ENV,
    GIT,
    HF,
    MODEL_FILE,
    WHEEL,
    forward_options,
    project_target_kind,
)
from pitloom.core.project_markers import has_project_config
from pitloom.core.provenance import ProvenanceConfig
from pitloom.core.wheel_dist_info import looks_like_wheel_path
from pitloom.embed import (
    RECOMMENDED_EXTENSIONS,
    VALIDATED_FORMATS,
    EmbeddedSbomLocation,
    detect_sbom_format,
    embed_sbom_in_wheel,
    embed_wheel_sbom,
    find_embedded_sbom,
)
from pitloom.extract.model_target import AUTO, is_model_file_target, resolve_sbom_target
from pitloom.extract.remote import (
    is_git_url,
    is_huggingface_source,
    is_unfetchable_remote,
)
from pitloom.extract.remote.pypi import WHEEL as WHEEL_FILE
from pitloom.extract.remote.pypi import sdist_hint
from pitloom.extract.remote.pypi_url import is_pypi_url
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import configure_logging

__all__ = [
    "BuildOptions",
    "ConfigOverrides",
    "EmbeddedSbomLocation",
    "FragmentMergeError",
    "ProvenanceConfig",
    "PypiSbom",
    "RECOMMENDED_EXTENSIONS",
    "VALIDATED_FORMATS",
    "detect_sbom_format",
    "embed_sbom_in_wheel",
    "embed_wheel_sbom",
    "enrich_model",
    "find_embedded_sbom",
    "generate",
    "generate_env_sbom",
    "generate_git_project_sbom",
    "generate_git_sbom",
    "generate_merged_sbom",
    "generate_model_sbom",
    "generate_project_sbom",
    "generate_pypi_sbom",
    "generate_pypi_sbom_with_download",
    "generate_wheel_sbom",
    "generate_wheel_sbom_with_metadata",
    "merge_fragments",
    "project_document_id",
    "target_is_git_url",
    "target_is_pypi_url",
    "target_resolves_to_project",
]


def _classify_target(target: Path | str) -> str:
    """Classify *target* into ``"env"``, ``"pypi"`` (a PyPI project or
    release URL, ``http`` too, so that it is refused as one), ``"wheel"``,
    ``"hf"``, ``"git"`` (a remote Git repository URL), ``"model_file"`` (a
    model by its suffix or content:
    :func:`~pitloom.extract.model_target.is_model_file_target`),
    ``"model_folder"`` (a directory with no project config, read for its one
    model file), or ``"project"`` (a project directory, an sdist archive, or
    a path that does not exist).

    The one classification behind :func:`generate`'s dispatch,
    :func:`target_is_pypi_url`, :func:`target_is_git_url` and
    :func:`target_resolves_to_project`. A PyPI URL is asked before a Git
    one, which it would also pass for. Silent: a CLI run asks it more than
    once.
    """
    target_str = str(target).strip()
    if target_str.lower() in ("env", "environment", "--env"):
        return "env"
    if is_pypi_url(target_str):
        return "pypi"
    if looks_like_wheel_path(target_str):
        return "wheel"
    if is_huggingface_source(target_str):
        return "hf"
    if is_git_url(target_str) or is_unfetchable_remote(target_str):
        return "git"
    return _local_kind(target_str)


def _local_kind(target: str) -> str:
    """``"model_file"``, ``"model_folder"`` or ``"project"`` for the local
    path *target* (see :func:`_classify_target`)."""
    if is_model_file_target(target):
        return "model_file"
    if os.path.isdir(target) and not has_project_config(target):
        return "model_folder"
    return "project"


def target_is_pypi_url(target: Path | str) -> bool:
    """Return whether :func:`generate` reads *target* as a PyPI project or
    release URL (:func:`generate_pypi_sbom`), which a CLI command routes to
    its PyPI download before any Git or local-path handling."""
    return _classify_target(target) == "pypi"


def target_is_git_url(target: Path | str) -> bool:
    """Return whether :func:`generate` reads *target* as the URL of a remote
    Git repository (or of one of its web pages), which
    ``pitloom.cli.commands.generate._run_generate_command`` routes to the
    code path ``loom project <url>`` and ``loom model <url>`` share."""
    return _classify_target(target) == "git"


def target_resolves_to_project(target: Path | str) -> bool:
    """Return whether :func:`generate`'s dispatch reaches
    :func:`~pitloom.assemble._generators.generate_project_sbom` (a plain
    project directory or sdist archive) for *target*, rather than the
    env/wheel/Hugging-Face/model-file branches. A directory with no project
    config is no project: it is read for its one model file.

    ``pitloom.cli.commands.generate._run_generate_command`` calls it to
    route a project target through the same code path as ``loom project``
    and every other target through :func:`generate`.
    """
    return _classify_target(target) == "project"


def _model_file_of(target: str) -> Path:
    """The model file *target* names, or for a folder with no project its
    one model file (:func:`~pitloom.extract.model_target.resolve_sbom_target`).

    Raises:
        pitloom.messages.CodedValueError: The folder holds no model file
            (``project-or-model-not-found``), or several.
    """
    if not os.path.isdir(target):
        return Path(target)
    found = resolve_sbom_target(target, subject=target, mode=AUTO)
    # A project config made since the folder was classified: the model
    # generator reads the folder for its model file all the same.
    return Path(target) if found.model is None else found.model.path


def _generate_remote(
    classification: str,
    target: str,
    options: dict[str, Any],
    build_options: BuildOptions,
    check_url: Callable[[str], None] | None,
) -> str:
    """:func:`generate` for a ``"pypi"`` or ``"git"`` *target*: a PyPI URL
    is read as ``loom wheel`` reads it, then one ``INFO:`` names the
    library's sdist route; a Git URL as :func:`generate_git_sbom` reads
    it."""
    if classification == "pypi":
        # Every option is one generate_pypi_sbom() accepts and settles.
        sbom = generate_pypi_sbom(
            target,
            kind=WHEEL_FILE,
            **options,
            build_options=build_options,
            check_url=check_url,
        )
        sdist_hint(target, library=True)
        return sbom
    return generate_git_sbom(
        target,
        sbom_kind=AUTO,
        **forward_options(GIT, target, generate_git_sbom, options),
        build_options=build_options,
        check_url=check_url,
    )


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
    trust_model_files: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    update_id_registry: bool | None = None,
    use_lockfile: bool | None = None,
    build_options: BuildOptions = BuildOptions(),
    max_source_metadata_bytes: int | None = None,
    max_model_extract_bytes: int | None = None,
    pitloom_config: PitloomConfig | None = None,
    project_dir: Path | str | None = None,
    check_url: Callable[[str], None] | None = None,
    max_download_bytes: int | None = None,
) -> str:
    """Smart unified entrypoint for generating SPDX 3 SBOMs across all target types.

    ``build_options`` (see :class:`~pitloom.core.build_options.BuildOptions`)
    takes effect for a project directory target only. Env, wheel, model and
    Hugging Face targets log one ``WARNING:`` per given build flag here,
    before dispatching; a Git URL, a PyPI URL and an sdist archive are
    settled by :func:`generate_git_project_sbom`, :func:`generate_pypi_sbom`
    and :func:`generate_project_sbom`.

    *project_dir* (the project directory an sdist or a wheel was built
    from, for its registry keys) reaches the sdist and wheel delegates; any
    other target warns that it has no effect. So does
    *max_model_extract_bytes* on any target but a wheel, and
    *max_download_bytes* on any target but a PyPI URL, a Git URL or a
    Hugging Face model; an invalid value of either raises ``ValueError``
    whatever the target. *offline*, *max_download_bytes* and *check_url*
    resolve for every remote target as
    :func:`~pitloom.core.config_cascade.resolve_fetch_policy` resolves
    them.

    A PyPI project or release URL is read as ``loom wheel`` reads it: the
    release's wheel that best matches the running environment is
    downloaded, verified and read (:func:`generate_pypi_sbom`), then one
    ``INFO:`` names :func:`generate_pypi_sbom` with ``kind="sdist"`` for
    the sdist.
    *check_url* is called with every URL of the release lookup and the
    download before it is requested (the PyPI lookup of a dependency's
    licence and originator, made unless *offline* is true, does not pass
    through it); *max_download_bytes* caps the file.

    A target that is the ``http`` or ``https`` URL of a Git repository (or of
    one of its web pages) is fetched and read as a project, or as the model
    file it names or its folder's one model file
    (:func:`generate_git_sbom`); *check_url* is its address policy,
    called with every redirect target before it is requested. A local
    target does not use it. *max_download_bytes* caps the disk the checkout
    takes, as it caps a PyPI download.

    A Hugging Face model URL or id is read by :func:`generate_model_sbom`:
    *check_url* is called with the URL of each metadata file it downloads
    and each redirect target, and *max_download_bytes* caps each file.

    A local directory with no project config is read for its one model
    file; one with no model file either is refused
    (``project-or-model-not-found``).
    """
    # Before the no-effect warnings below, which precede any delegate's own
    # configure_logging() call.
    configure_logging()
    if max_model_extract_bytes is not None:
        require_model_extract_override(max_model_extract_bytes)  # even if inert
    if max_download_bytes is not None:
        require_download_override(max_download_bytes)  # even if inert
    target_str = str(target).strip()
    classification = _classify_target(target_str)

    if classification not in ("project", "git", "pypi"):
        # Warns once and resets to defaults, as every
        # settle_not_applicable() call does.
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
        "trust_model_files": trust_model_files,
        "content_type": content_type,
        "content_type_method": content_type_method,
        "update_id_registry": update_id_registry,
        "max_source_metadata_bytes": max_source_metadata_bytes,
        "max_model_extract_bytes": max_model_extract_bytes,
        "pitloom_config": pitloom_config,
        "use_lockfile": use_lockfile,
        "project_dir": project_dir,
        "max_download_bytes": max_download_bytes,
    }
    # Each delegate gets what it accepts; an option it does not accept is
    # settled here, once, with the target kind's reason.
    if classification in ("pypi", "git"):
        return _generate_remote(
            classification, target_str, options, build_options, check_url
        )
    if classification == "env":
        return generate_env_sbom(
            **forward_options(ENV, target_str, generate_env_sbom, options)
        )
    if classification == "wheel":
        return generate_wheel_sbom(
            target_str,
            **forward_options(WHEEL, target_str, generate_wheel_sbom, options),
            check_url=check_url,
        )
    if classification == "hf":
        return generate_model_sbom(
            target_str,
            **forward_options(HF, target_str, generate_model_sbom, options),
            check_url=check_url,
        )
    if classification in ("model_file", "model_folder"):
        forwarded = forward_options(
            MODEL_FILE, target_str, generate_model_sbom, options
        )
        # A local file does not use check_url; passed as to every delegate.
        return generate_model_sbom(
            _model_file_of(target_str), **forwarded, check_url=check_url
        )
    project_target = Path(target_str)
    kind = project_target_kind(project_target)
    return generate_project_sbom(
        project_target,
        **forward_options(kind, project_target, generate_project_sbom, options),
        build_options=build_options,
        check_url=check_url,
    )
