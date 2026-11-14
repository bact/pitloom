# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM generator for a project or an AI model file in a remote Git
repository.

See also:
- :mod:`pitloom.assemble._generators` and
  :mod:`pitloom.assemble._model_generator` for the local generators it
  delegates to.
- :mod:`pitloom.extract.remote.git` for how the repository is fetched, and
  :mod:`pitloom.extract.remote.git_target` for what its SBOM describes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pitloom.assemble._generators import generate_project_sbom
from pitloom.assemble._model_generator import generate_model_sbom
from pitloom.core.build_options import REMOTE_REPOSITORY_REASON, BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import resolve_fetch_policy
from pitloom.core.creation import CreationMetadata
from pitloom.core.given_file import GivenPath, given_spelling
from pitloom.core.inert_options import GIT_MODEL, forward_options
from pitloom.core.internal_error import InternalError
from pitloom.core.no_effect import warn_no_effect
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.extract.model_target import AUTO, MODEL, PROJECT
from pitloom.extract.remote.git import fetch_git_project
from pitloom.extract.remote.git_target import resolve_git_target
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import configure_logging
from pitloom.messages import emit
from pitloom.messages.targets import (
    CONFIG_UNSAFE,
    CONFIG_UNSAFE_REMOTE_LINE,
)

log = logging.getLogger(__name__)

_SBOM_KINDS = (AUTO, PROJECT, MODEL)


def _git_model_sbom(
    url: str, model_path: Path, shown: str, options: dict[str, Any]
) -> str:
    """The SBOM of the model file *model_path* of the checkout of *url*
    (named *shown* in messages), each of *options* the model cannot use
    said once against *url*."""
    project_metadata = options.pop("project_metadata")
    if project_metadata is not None:
        warn_no_effect(
            url,
            ("project_metadata",),
            "for an AI model file (it is not a Python project)",
        )
    return generate_model_sbom(
        model_path,
        shown=shown,
        **forward_options(GIT_MODEL, url, generate_model_sbom, options),
    )


# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def generate_git_sbom(
    url: str,
    *,
    sbom_kind: str = AUTO,
    check_url: Callable[[str], None] | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    pitloom_config: PitloomConfig | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    scan_model_usage: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    offline: bool | None = None,
    max_download_bytes: int | None = None,
    trust_model_files: bool | None = None,
    update_id_registry: bool | None = None,
    use_lockfile: bool | None = None,
    build_options: BuildOptions = BuildOptions(),
    max_source_metadata_bytes: int | None = None,
    project_metadata: ProjectMetadata | None = None,
) -> str:
    """Generate an SPDX 3 SBOM for the project or the AI model file at a Git
    URL.

    *url* is fetched as :func:`generate_git_project_sbom` describes, every
    option meaning what it means there. *sbom_kind* says what the SBOM
    describes (:func:`~pitloom.extract.remote.git_target.resolve_git_target`):

    - ``"auto"``: a model file the URL names (whatever the folder holds),
      else the folder's Python project, else the folder's one AI model file;
    - ``"project"``: the folder's project only;
    - ``"model"``: the named model file, else the folder's one model file.

    A model file of a clone, and each model file in its project's build
    file list, is read as a local one, except that a format whose reader a
    hostile file could crash or hang (fastText, GGUF, HDF5, ONNX, PyTorch)
    is listed without metadata, said in one ``INFO:`` per SBOM, unless
    *trust_model_files* (see :func:`generate_git_project_sbom`). A model
    file's messages name it by its path in the repository; an option a
    model SBOM cannot use warns once.

    Raises:
        pitloom.core.internal_error.InternalError: *sbom_kind* is none of
            the three (a :class:`ValueError`).
        ValueError: *max_download_bytes* (or the config's) is not an
            integer of at least 1.
        pitloom.extract.remote.errors.RemoteSourceError: the repository could
            not be fetched, the named file is not in it
            (``git.path-not-found``), or ``git.no-project``.
        pitloom.messages.CodedValueError: no model file to read
            (``model-wrong-format``, ``project-or-model-not-found``), several
            (``model-ambiguous``), or a Git LFS pointer (``lfs-pointer``).
    """
    configure_logging()
    if sbom_kind not in _SBOM_KINDS:
        raise InternalError(
            f"sbom_kind must be one of {_SBOM_KINDS}, got {sbom_kind!r}"
        )
    policy = resolve_fetch_policy(
        pitloom_config,
        offline=offline,
        max_download_bytes=max_download_bytes,
        check_url=check_url,
    )
    build_options.settle_not_applicable(url, REMOTE_REPOSITORY_REASON)
    if isinstance(id_registry, (str, Path)):
        # A relative path means the caller's directory, not the checkout's;
        # a message still names it as given.
        id_registry = GivenPath(
            Path(id_registry).absolute(), given_spelling(id_registry)
        )
    with fetch_git_project(
        url, policy=policy, trust_model_files=trust_model_files is True
    ) as checkout:
        with checkout.reading():
            target = resolve_git_target(checkout, sbom_kind, url)
            if target.model is not None:
                # The fetch consumed offline: the model read uses no network.
                return _git_model_sbom(
                    url,
                    target.model.path,
                    target.model.shown,
                    {
                        "output_path": output_path,
                        "creation_metadata": creation_metadata,
                        "pretty": pretty,
                        "describe_relationship": describe_relationship,
                        "pitloom_config": pitloom_config,
                        "id_registry": id_registry,
                        "provenance": provenance,
                        "enrich": enrich,
                        "extract_file_header": extract_file_header,
                        "scan_model_usage": scan_model_usage,
                        "content_type": content_type,
                        "content_type_method": content_type_method,
                        "update_id_registry": update_id_registry,
                        "use_lockfile": use_lockfile,
                        "max_source_metadata_bytes": max_source_metadata_bytes,
                        "project_metadata": project_metadata,
                    },
                )
            if pitloom_config is None:
                emit(log, CONFIG_UNSAFE, logging.INFO, line=CONFIG_UNSAFE_REMOTE_LINE)
            return generate_project_sbom(
                checkout.folder,
                output_path=output_path,
                creation_metadata=creation_metadata,
                pretty=pretty,
                describe_relationship=describe_relationship,
                project_metadata=project_metadata,
                pitloom_config=PitloomConfig()
                if pitloom_config is None
                else pitloom_config,
                id_registry=id_registry,
                provenance=provenance,
                enrich=enrich,
                extract_file_header=extract_file_header,
                scan_model_usage=scan_model_usage,
                content_type=content_type,
                content_type_method=content_type_method,
                offline=offline,
                update_id_registry=update_id_registry,
                use_lockfile=use_lockfile,
                max_source_metadata_bytes=max_source_metadata_bytes,
            )


# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def generate_git_project_sbom(
    url: str,
    *,
    check_url: Callable[[str], None] | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    pitloom_config: PitloomConfig | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    scan_model_usage: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    offline: bool | None = None,
    max_download_bytes: int | None = None,
    trust_model_files: bool | None = None,
    update_id_registry: bool | None = None,
    use_lockfile: bool | None = None,
    build_options: BuildOptions = BuildOptions(),
    max_source_metadata_bytes: int | None = None,
    project_metadata: ProjectMetadata | None = None,
) -> str:
    """Generate a Source SPDX 3 SBOM for the project at a Git URL.

    *url* is a clone URL or the address of a repository web page, naming a
    branch, tag or commit and a folder (see
    :func:`~pitloom.extract.remote.git.fetch_git_project`, which fetches it).
    The repository is shallow-cloned into a temporary directory that is
    removed on return.

    *check_url* is called with every redirect target before it is requested
    (the caller's address policy; Pitloom does not check the URL itself).

    The repository is untrusted: its own ``[tool.pitloom]`` is ignored (a
    repository must not name host paths such as fragments or an ID registry)
    unless the caller passes *pitloom_config*, and its build backend is never
    run (a build flag in *build_options* warns once and has no effect). With
    *offline* (else *pitloom_config*'s ``offline``) true nothing is fetched
    (``git.offline``, ``offline-unusable``). The fetch is stopped once the
    checkout takes more disk than *max_download_bytes* (else
    *pitloom_config*'s ``max-download-bytes``, else 512 MiB;
    ``git.too-large``, ``over-cap``). The three resolve as every remote
    route resolves them
    (:func:`~pitloom.core.config_cascade.resolve_fetch_policy`).

    A model file of the repository in a format whose reader a hostile file
    could crash or hang (fastText, GGUF, HDF5, ONNX, PyTorch) is listed
    without metadata, with one ``INFO:`` (``reader-unsafe/remote``). With
    *trust_model_files* the caller vouches for the repository's model files
    and those readers run. Never set it from a request a third party can
    make (a service that takes repository URLs): a hostile file can crash
    or hang the process, and Ctrl-C cannot interrupt it. No configuration
    file can set it. When the folder
    holds no Python project but folders below it do, the failure names them
    (``git.no-project``); when it holds files that may be AI models instead,
    the failure says to ask for a model SBOM (:func:`generate_git_sbom`).

    Raises:
        pitloom.extract.remote.errors.RemoteSourceError: the repository could
            not be fetched, or ``git.no-project``.
    """
    configure_logging()
    return generate_git_sbom(
        url,
        sbom_kind=PROJECT,
        check_url=check_url,
        output_path=output_path,
        creation_metadata=creation_metadata,
        pretty=pretty,
        describe_relationship=describe_relationship,
        pitloom_config=pitloom_config,
        id_registry=id_registry,
        provenance=provenance,
        enrich=enrich,
        extract_file_header=extract_file_header,
        scan_model_usage=scan_model_usage,
        content_type=content_type,
        content_type_method=content_type_method,
        offline=offline,
        max_download_bytes=max_download_bytes,
        trust_model_files=trust_model_files,
        update_id_registry=update_id_registry,
        use_lockfile=use_lockfile,
        build_options=build_options,
        max_source_metadata_bytes=max_source_metadata_bytes,
        project_metadata=project_metadata,
    )
