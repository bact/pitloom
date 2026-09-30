# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the base document identity of
:func:`pitloom.assemble.enrich_model`'s ``project_target``.

See also: :func:`pitloom.assemble.spdx3.document.build`, which computes a
base SBOM's real ``doc_uuid`` -- ``enrich_model`` must derive the same
value from the same :class:`~pitloom.core.project.ProjectMetadata`, or its
fragment references a ``doc_uuid`` the base document never actually used
(see :mod:`tests.core.test_fragments_dangling_refs`).
"""

from __future__ import annotations

from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.document import build
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import get_wheel_files
from pitloom.extract.project import read_project
from tests.assemble.enrich_identity_shared import enrich_base_namespace
from tests.fixtures.locked_deps import write_locked_deps_project

FIXTURES = Path(__file__).parent.parent / "fixtures" / "projects"
POETRY_FIXTURE = FIXTURES / "sampleproject-poetry"


def _real_build_namespace(doc: DocumentModel) -> str:
    """Build *doc* for real via :func:`~pitloom.assemble.spdx3.document.build`
    and return its ``SpdxDocument`` element's ``spdxId`` -- not a second,
    independently-maintained ``compute_doc_uuid()`` call that could drift
    from ``build()``'s own formula without either test noticing."""
    exporter = build(doc, offline=True)
    spdx_doc = next(
        o for o in exporter.object_set.objects if isinstance(o, spdx3.SpdxDocument)
    )
    assert spdx_doc.spdxId is not None
    return spdx_doc.spdxId


def test_enrich_identity_matches_build_doc_uuid_with_locked_dependencies(
    tmp_path: Path,
) -> None:
    """For a Poetry project with a ``poetry.lock`` (non-empty
    ``locked_dependencies``), ``enrich_model``'s base ``doc_uuid`` must
    match what :func:`~pitloom.assemble.spdx3.document.build` computes for
    the same project -- both derive from the same
    :class:`~pitloom.core.project.ProjectMetadata` and ``merkle_root``.
    Regression test: this identity used to omit
    ``locked_dependencies`` (and later, ``locked_dependencies``'
    provenance) from its ``compute_doc_uuid`` call, diverging from
    ``build()``'s doc_uuid for any project with a lock file."""
    project_metadata, _config, _config_path = read_project(POETRY_FIXTURE)
    assert project_metadata.locked_dependencies  # guard: fixture must exercise this

    merkle_root, project_files, _ = get_wheel_files(POETRY_FIXTURE)
    project_metadata.files = project_files
    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=CreationMetadata(
            creation_datetime="2026-01-01T00:00:00+00:00"
        ),
    )
    expected = _real_build_namespace(doc)

    namespace = enrich_base_namespace(POETRY_FIXTURE, tmp_path / "model")

    assert namespace == expected


def test_enrich_identity_matches_build_doc_uuid_with_use_lockfile_disabled(
    tmp_path: Path,
) -> None:
    """An explicit ``use_lockfile=False`` on both sides -- base generation
    and ``enrich_model`` -- must still agree: a base SBOM
    generated with ``--no-use-lockfile`` and a fragment built via
    ``loom enrich --use-lockfile=False --project-dir DIR`` must reference
    the same ``doc_uuid``."""
    project = write_locked_deps_project(tmp_path / "proj")

    project_metadata, _config, _config_path = read_project(
        project, include_locked_dependencies=False
    )
    assert not project_metadata.locked_dependencies

    merkle_root, project_files, _ = get_wheel_files(project)
    project_metadata.files = project_files
    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=CreationMetadata(
            creation_datetime="2026-01-01T00:00:00+00:00"
        ),
    )
    expected = _real_build_namespace(doc)

    namespace = enrich_base_namespace(project, tmp_path / "model", use_lockfile=False)

    assert namespace == expected


def test_enrich_identity_auto_matches_config_default(tmp_path: Path) -> None:
    """No explicit ``use_lockfile`` argument -- ``enrich_model``
    must auto-match *project_dir*'s own ``[tool.pitloom] use-lockfile``
    config, so ``loom enrich --project-dir DIR`` (no matching flag) still
    references the correct ``doc_uuid`` for a base SBOM generated purely
    from that project's config default."""
    project = write_locked_deps_project(
        tmp_path / "proj", disable_cascade_in_config=True
    )

    project_metadata, pitloom_config, _config_path = read_project(
        project, include_locked_dependencies=False
    )
    assert pitloom_config.use_lockfile is False
    assert not project_metadata.locked_dependencies

    merkle_root, project_files, _ = get_wheel_files(project)
    project_metadata.files = project_files
    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=CreationMetadata(
            creation_datetime="2026-01-01T00:00:00+00:00"
        ),
    )
    expected = _real_build_namespace(doc)

    namespace = enrich_base_namespace(project, tmp_path / "model")

    assert namespace == expected
