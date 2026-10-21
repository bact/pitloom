# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Source SBOM generator for a project in a remote Git repository.

See also:
- :mod:`pitloom.assemble._generators` for the local project generator it
  delegates to.
- :mod:`pitloom.extract.remote.git` for how the repository is fetched.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from pitloom.assemble._generators import generate_project_sbom
from pitloom.core.build_options import REMOTE_REPOSITORY_REASON, BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.extract.remote.git import CONFIG_IGNORED_INFO, fetch_git_project
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import configure_logging

log = logging.getLogger(__name__)


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
    *offline* true nothing is fetched (``git.offline``). When the folder
    holds no Python project but folders below it do, the failure names them
    (``git.no-project``).

    Raises:
        pitloom.extract.remote.errors.RemoteSourceError: the repository could
            not be fetched, or ``git.no-project``.
    """
    configure_logging()
    build_options.settle_not_applicable(url, REMOTE_REPOSITORY_REASON)
    if isinstance(id_registry, (str, Path)):
        # A relative path means the caller's directory, not the checkout's.
        id_registry = Path(id_registry).absolute()
    with fetch_git_project(url, check_url=check_url, offline=offline) as checkout:
        if pitloom_config is None:
            log.info(CONFIG_IGNORED_INFO)
        with checkout.explaining_failures():
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
