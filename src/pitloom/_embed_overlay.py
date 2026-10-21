# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a wheel embed takes from its project directory onto the wheel's own
metadata: the rescan's per-file extras, the concluded licence and the
authors.

See also: :mod:`pitloom._embed_build_sbom` (the Build SBOM that calls
these, importing them under private aliases).
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

from packaging.utils import canonicalize_name

from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.extract._license import resolve_license_concluded
from pitloom.extract.authors import warn_project_authors_unread
from pitloom.extract.project import read_project

__all__ = ["add_concluded_license", "adopt_project_authors", "merge_file_extras"]

log = logging.getLogger(__name__)


def merge_file_extras(
    wheel_files: list[ProjectFile], project_files: list[ProjectFile]
) -> list[ProjectFile]:
    """Layer re-scanned content-type/header data onto the wheel's own files.

    ``wheel_files`` (from :func:`pitloom.extract.wheel.read_wheel`) is the
    source of truth for what the already-built wheel actually contains --
    excluding the wheel's own ``.dist-info`` but including any
    build-hook-injected files that never existed in ``project_dir`` -- so it
    is kept intact, including its hashes computed from the wheel's own bytes.
    ``project_files`` (from :func:`~pitloom.core.models.get_wheel_files`)
    only supplies the content-type/file-header extras it computed by
    re-scanning the sources, adopted for files present in both lists.
    """
    extras_by_path = {f.distribution_path: f for f in project_files}
    merged: list[ProjectFile] = []
    for wheel_file in wheel_files:
        extra = extras_by_path.get(wheel_file.distribution_path)
        if extra is None:
            merged.append(wheel_file)
            continue
        merged.append(
            dataclasses.replace(
                wheel_file,
                copyright_text=extra.copyright_text,
                copyright_source=extra.copyright_source,
                file_contributors=extra.file_contributors,
                file_type=extra.file_type,
                spdx_license_identifier=extra.spdx_license_identifier,
                content_type=extra.content_type,
                content_type_method=extra.content_type_method,
            )
        )
    return merged


def add_concluded_license(metadata: ProjectMetadata, project_dir: Path) -> None:
    """Set *metadata*'s concluded licence from *project_dir*'s own sources.

    Wheel ``METADATA`` carries only the declared licence, so the second
    opinion comes from the project directory, through the same resolver
    ``loom project`` uses, gated on the wheel's declared licence. An sdist
    *project_dir* gets none, though ``loom project`` on that sdist reads
    its licence files.
    """
    if metadata.license_concluded is not None or not project_dir.is_dir():
        return
    concluded, provenance = resolve_license_concluded(
        bool(metadata.license_name), project_dir, stated=metadata.license_name
    )
    if concluded is None or provenance is None:
        return
    metadata.license_concluded = concluded
    metadata.provenance["license_concluded"] = provenance


def adopt_project_authors(
    metadata: ProjectMetadata, project_dir: Path, *, quiet: bool = False
) -> bool:
    """Take *metadata*'s authors from *project_dir* when it declares them;
    whether it did.

    Wheel ``METADATA`` lists the authors with an address before the others
    (see :func:`~pitloom.extract.authors.author_pairs`)
    and a poetry-core wheel only the first one; the project's own metadata
    has every author in declared order, as ``loom project`` reads it. The
    embed's one used read of the project, so it warns unless *quiet* (a
    batch's later wheels).
    """
    try:
        project, _, _ = read_project(
            project_dir,
            include_locked_dependencies=False,
            include_installed_metadata=False,
            quiet=quiet,
            read_config=False,
        )
    except (OSError, ValueError) as exc:
        warn_project_authors_unread(str(project_dir), exc, "wheel METADATA")
        return False
    source = project.provenance.get("authors")
    if source is None:
        return False
    if canonicalize_name(project.name) != canonicalize_name(metadata.name):
        log.warning(
            "%s: project %r is not the wheel's %r; authors from the wheel METADATA",
            project_dir,
            project.name,
            metadata.name,
        )
        return False
    metadata.authors = list(project.authors)
    metadata.provenance["authors"] = source
    return True
