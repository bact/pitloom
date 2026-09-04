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

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble._model_generator import _project_doc_identity
from pitloom.assemble.spdx3.document import build
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import get_wheel_files
from pitloom.extract.project import read_project

FIXTURES = Path(__file__).parent.parent / "fixtures" / "projects"
POETRY_FIXTURE = FIXTURES / "sampleproject-poetry"

#: A UUID's canonical string form is always exactly 36 characters
#: (8-4-4-4-12 hex, hyphen-separated) -- long enough that it can't
#: collide with a project name containing hyphens, so slicing the tail
#: off an SpdxDocument's spdxId (``https://spdx.org/spdxdocs/<name>-<uuid>``)
#: recovers the real doc_uuid `build()` used, regardless of `<name>`.
_UUID_LENGTH = 36


def _real_build_doc_uuid(doc: DocumentModel) -> str:
    """Build *doc* for real via :func:`~pitloom.assemble.spdx3.document.build`
    and recover the ``doc_uuid`` it actually used, by reading it back off
    the emitted ``SpdxDocument`` element's ``spdxId`` -- not a second,
    independently-maintained ``compute_doc_uuid()`` call that could drift
    from ``build()``'s own formula without either test noticing."""
    exporter = build(doc, offline=True)
    spdx_doc = next(
        o for o in exporter.object_set.objects if isinstance(o, spdx3.SpdxDocument)
    )
    assert spdx_doc.spdxId is not None
    return spdx_doc.spdxId[-_UUID_LENGTH:]


def test_project_doc_identity_matches_build_doc_uuid_with_locked_dependencies() -> None:
    """For a Poetry project with a ``poetry.lock`` (non-empty
    ``locked_dependencies``), ``_project_doc_identity``'s ``doc_uuid`` must
    match what :func:`~pitloom.assemble.spdx3.document.build` computes for
    the same project -- both derive from the same
    :class:`~pitloom.core.project.ProjectMetadata` and ``merkle_root``.
    Regression test: ``_project_doc_identity`` used to omit
    ``locked_dependencies`` (and later, ``locked_dependencies``'
    provenance) from its ``compute_doc_uuid`` call, diverging from
    ``build()``'s doc_uuid for any project with a lock file."""
    project_metadata, _config, _config_path = read_project(POETRY_FIXTURE)
    assert project_metadata.locked_dependencies  # guard: fixture must exercise this

    merkle_root, project_files = get_wheel_files(POETRY_FIXTURE)
    project_metadata.files = project_files
    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=CreationMetadata(
            creation_datetime="2026-01-01T00:00:00+00:00"
        ),
    )
    expected_doc_uuid = _real_build_doc_uuid(doc)

    _doc_name, doc_uuid = _project_doc_identity(POETRY_FIXTURE)

    assert doc_uuid == expected_doc_uuid
