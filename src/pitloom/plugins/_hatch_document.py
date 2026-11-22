# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The format-neutral document the build hook assembles the SBOM from.

See also: :mod:`pitloom.plugins.hatch` (the build hook that calls it).
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pitloom.assemble.spdx3.creation_info import to_spdx3_datetime
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata, resolve_source_date_epoch
from pitloom.core.document import DocumentModel
from pitloom.core.file_names import default_sbom_basename
from pitloom.core.models import get_wheel_files
from pitloom.core.project import FilesOrigin
from pitloom.enrich import run_enrichers_for_models
from pitloom.enrich.base import EnrichmentResult
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.project.hatchling import metadata_from_hatchling
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.id_registry import IdRegistry, registry_file_path
from pitloom.messages import emit
from pitloom.messages.config import DATETIME_UNPINNED

log = logging.getLogger(__name__)


def resolve_build_datetime(pitloom_config: PitloomConfig) -> str:
    """Resolve the ``builtTime`` stamped on the main package.

    Priority: a pinned ``[tool.pitloom.creation]`` ``creation-datetime``
    (a deliberate, explicit pin -- more specific than an ambient env var,
    so it wins), then the standard reproducible-builds ``SOURCE_DATE_EPOCH``
    environment variable, then the current UTC time (with one ``INFO:``
    saying so).  With either of the first two, repeated builds of unchanged
    sources produce byte-identical SBOMs (and therefore byte-identical
    wheels).

    Raises:
        ValueError: ``SOURCE_DATE_EPOCH`` is set and not a valid timestamp
            (see :func:`~pitloom.core.creation.resolve_source_date_epoch`).
    """
    # Read first, so a malformed value fails whether or not a date is pinned.
    epoch_dt = resolve_source_date_epoch()
    if pitloom_config.creation_datetime:
        return pitloom_config.creation_datetime
    if epoch_dt is not None:
        return to_spdx3_datetime(epoch_dt).isoformat()
    emit(log, DATETIME_UNPINNED, logging.INFO)
    return to_spdx3_datetime(datetime.now(timezone.utc)).isoformat()


def build_creation_metadata(pitloom_config: PitloomConfig) -> CreationMetadata:
    """Build creation metadata from ``[[tool.pitloom.creator]]`` /
    ``[[tool.pitloom.creation-tool]]`` / ``[tool.pitloom.creation]``.

    Unset fields take :class:`CreationMetadata`'s defaults, as the CLI does:
    no named creators (the assembler emits the ``SoftwareAgent`` "Pitloom")
    and ``tools`` of ``[Pitloom]``. ``creation-comment`` defaults to a note
    naming the build hook, and ``builtTime`` is
    :func:`resolve_build_datetime`.
    """
    comment = pitloom_config.creation_comment
    return dataclasses.replace(
        pitloom_config.creation_metadata,
        creation_comment=(
            comment
            if comment is not None
            else "Generated via Pitloom Hatchling build hook (PEP 770)"
        ),
        build_datetime=resolve_build_datetime(pitloom_config),
    )


def build_document_model(
    project_dir: Path,
    hatch_metadata: Any,
    pitloom_config: PitloomConfig,
    registry: IdRegistry | None,
) -> tuple[DocumentModel, str | None, list[list[EnrichmentResult]]]:
    """Load project metadata and assemble the format-neutral document.

    Project metadata (name, version, dependencies, license, urls, authors)
    comes from Hatchling's own resolved ``hatch_metadata`` -- not from
    re-parsing ``pyproject.toml`` -- so dynamic fields (e.g. a ``hatch-vcs``
    version, or dependencies added by ``hatch-requirements-txt``) are
    correctly reflected in the SBOM.

    Also runs enrichment for each discovered AI model, gated by the
    project's own ``[tool.pitloom] enrich`` (the hook has no key of its own,
    see :func:`~pitloom.plugins._hatch_config.validate_config`), through the same
    ``run_enrichers_for_models()`` call as
    :func:`~pitloom.assemble.generate_project_sbom`, so the hook and
    ``loom project`` enrich a project alike.
    """
    metadata = metadata_from_hatchling(hatch_metadata, project_dir)
    creation_metadata = build_creation_metadata(pitloom_config)
    # No build_options: the backend is Hatchling, never a build-and-read
    # candidate, so the returned cleanup is a no-op.
    merkle_root, project_files, _cleanup = get_wheel_files(
        project_dir,
        scan_file_headers=pitloom_config.extract_file_header,
        detect_content_type=pitloom_config.content_type.enabled,
        content_type_method=pitloom_config.content_type.method,
        content_type_overrides=pitloom_config.content_type.overrides,
        # Skips get_wheel_files()'s pyproject.toml re-parse and backend
        # detection.
        assume_backend="hatchling",
        # The wheel ships a Git LFS pointer's text: its RECORD hashes that.
        bytes_as_is=True,
        exclude_path=registry_file_path(registry),
    )
    _cleanup()
    metadata.files = project_files
    ai_models = scan_project_for_ai_models(
        project_dir,
        project_files,
        scan_usage=pitloom_config.scan_model_usage is True,
        usage_hint=lambda: pitloom_config.scan_model_usage is None,
    )
    phantom_deps = find_phantom_dependencies(project_files)
    enrichment_results_by_model = run_enrichers_for_models(
        ai_models, pitloom_config.enrich, project_dir
    )
    document = DocumentModel(
        project=metadata,
        creation_metadata=creation_metadata,
        ai_models=ai_models,
        phantom_dependencies=phantom_deps,
        files_origin=FilesOrigin(project_dir=project_dir),
    )
    return document, merkle_root, enrichment_results_by_model


def default_hook_sbom_basename(hatch_metadata: Any) -> str:
    """Derive the default embedded-SBOM basename from package name/version.

    The final wheel filename's platform/ABI/Python tags aren't resolved
    yet at hook ``initialize()`` time, so this can't reproduce the exact
    wheel filename -- only ``<name>-<version>``, matching what ``loom
    project``'s own default (``_resolve_output_path``) uses.
    """
    name = hatch_metadata.core.raw_name
    version = str(hatch_metadata.version) if hatch_metadata.version else None
    return default_sbom_basename(name, version)
