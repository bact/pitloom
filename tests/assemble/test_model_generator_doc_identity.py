# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.assemble._model_generator._project_doc_identity`.

See also: :func:`pitloom.assemble.spdx3.document.build`, which computes a
base SBOM's real ``doc_uuid`` -- ``_project_doc_identity`` must derive the
same value from the same :class:`~pitloom.core.project.ProjectMetadata`,
or an enrichment fragment built against it references a ``doc_uuid`` the
base document never actually used (see
:mod:`tests.core.test_fragments_dangling_refs`).
"""

from __future__ import annotations

from pathlib import Path

from pitloom.assemble._model_generator import _project_doc_identity
from pitloom.core.models import compute_doc_uuid, get_wheel_files
from pitloom.extract.project import read_project

FIXTURES = Path(__file__).parent.parent / "fixtures" / "projects"
POETRY_FIXTURE = FIXTURES / "sampleproject-poetry"


def test_project_doc_identity_matches_build_doc_uuid_with_locked_dependencies() -> None:
    """For a Poetry project with a ``poetry.lock`` (non-empty
    ``locked_dependencies``), ``_project_doc_identity``'s ``doc_uuid`` must
    match what :func:`~pitloom.assemble.spdx3.document.build` computes for
    the same project -- both derive from the same
    :class:`~pitloom.core.project.ProjectMetadata` and ``merkle_root``.
    Regression test: ``_project_doc_identity`` used to omit
    ``locked_dependencies`` from its ``compute_doc_uuid`` call, diverging
    from ``build()``'s doc_uuid for any project with a lock file."""
    project_metadata, _config, _config_path = read_project(POETRY_FIXTURE)
    assert project_metadata.locked_dependencies  # guard: fixture must exercise this

    merkle_root, _project_files = get_wheel_files(POETRY_FIXTURE)
    expected_doc_uuid = compute_doc_uuid(
        name=project_metadata.name,
        version=project_metadata.version or "unknown",
        dependencies=project_metadata.dependencies,
        merkle_root=merkle_root,
        locked_dependencies=project_metadata.locked_dependencies,
    )

    _doc_name, doc_uuid = _project_doc_identity(POETRY_FIXTURE)

    assert doc_uuid == expected_doc_uuid
