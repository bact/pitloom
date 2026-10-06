# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Emit a conflict Annotation per :attr:`ProjectMetadata.field_conflicts`
entry on the main project package.

See also: :mod:`pitloom.assemble.spdx3.deps_license`'s
:func:`~pitloom.assemble.spdx3.deps_license.attach_main_package_license`,
whose declared/concluded license conflict wiring this generalizes to any
:class:`~pitloom.core.project.ProjectMetadata` field (e.g. a field an
in-tree ``.egg-info``/``.dist-info`` disagreed with, see
:mod:`pitloom.extract.project.installed`).
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import build_conflict_annotation
from pitloom.core.models import generate_spdx_id
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id


def attach_metadata_field_conflicts(
    metadata: ProjectMetadata,
    main_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Emit one conflict Annotation per ``metadata.field_conflicts``
    entry on the main project package.

    Iterates ``metadata.field_conflicts.items()`` in the dict's own
    insertion order -- deterministic because each producer
    (:func:`pitloom.extract.project._installed_reconcile.reconcile_installed_metadata`,
    :func:`pitloom.extract.project._setuptools_options.record_setuptools_conflicts`)
    adds in a fixed field order, never a ``set``'s iteration order.
    """
    if not metadata.field_conflicts:
        return
    package_spdx_id = require_spdx_id(main_package)
    for field_name, candidates in metadata.field_conflicts.items():
        exporter.add_annotation(
            build_conflict_annotation(
                subject_spdx_id=package_spdx_id,
                field=field_name,
                candidates=candidates,
                creation_info=creation_info,
                annotation_spdx_id=generate_spdx_id(
                    "Annotation", doc_name=metadata.name, doc_uuid=doc_uuid
                ),
            )
        )


__all__ = ["attach_metadata_field_conflicts"]
