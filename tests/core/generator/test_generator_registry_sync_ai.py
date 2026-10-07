# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression test for the AI-model id-mint-collision fix:
:func:`pitloom.assemble.spdx3.ai.resolve_ai_model_entity_hits` must be
reserved before the first mint, or a registry hit claimed via
:class:`~pitloom.id_registry.IdRegistrySession` over
:func:`~pitloom.assemble.spdx3._ai_package._ai_model_entity_candidates`
(e.g. after ``pitloom id import`` of the document's own earlier SBOM)
can be handed out again by a sibling model's fresh mint under the same
``(doc_uuid, "AIPackage-<name>")`` counter.

See also: :mod:`tests.core.generator.test_generator_model` for
``build()``'s basic (single-call) ``ai_AIPackage`` registry-reuse tests.
"""

from __future__ import annotations

from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.document import build
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.id_registry import EntityEntry, IdRegistry


def _numpy_models() -> list[AiModelMetadata]:
    """10 unnamed NumPy-format models, ``m00/numpy.npy`` to
    ``m09/numpy.npy``. Every model's ``name`` is unset, so
    ``ai_package_name()`` falls back to the shared file stem ("numpy") for
    *all ten*: they all mint under the identical
    ``(doc_uuid, "AIPackage-numpy")`` counter regardless of their
    different paths."""
    return [
        AiModelMetadata(
            format_info=AiModelFormatInfo(
                file_name="numpy.npy",
                file_path_relative=f"m{i:02d}/numpy.npy",
                model_format=AiModelFormat.NUMPY,
            ),
        )
        for i in range(10)
    ]


def _assert_ten_distinct_ai_package_ids(exporter: object) -> None:
    """Count ``ai_AIPackage`` objects directly on the exporter's own
    in-memory object set, never via serialized JSON-LD: serialization
    itself does not merge by id, but Pitloom's own
    ``_deduplicate_named_elements`` (``export/spdx3_json.py``) drops a
    second element sharing a ``spdxId`` with an earlier one whenever every
    field is identical -- which two same-prefix, same-fallback-name AI
    model elements colliding on one id often are, masking exactly the
    collision this test exists to catch. Asserting on ``to_json()``
    output alone would pass even with a real duplicate."""
    ai_pkgs = [
        obj
        for obj in exporter.object_set.objects  # type: ignore[attr-defined]
        if isinstance(obj, spdx3.ai_AIPackage)
    ]
    ids = [str(obj.spdxId) for obj in ai_pkgs]
    assert len(ai_pkgs) == 10, f"expected 10 ai_AIPackage objects, got {len(ai_pkgs)}"
    assert len(ids) == len(set(ids)), f"duplicate ai_AIPackage spdxId: {sorted(ids)}"


def test_ai_models_sharing_a_mint_prefix_never_duplicate_ids_after_import(
    tmp_path: Path,
) -> None:
    """Run 1 builds 10 same-prefix AI models with no registry. Its own
    SBOM is imported into a fresh registry (``pitloom id import``'s
    mechanism) and a stale ``numpy`` entry is pinned, then run 2 rebuilds
    against that registry -- the earlier
    (buggy) behaviour let a lookup hit for one model's file stem go
    unreserved, so a sibling model's later fresh mint could land on the
    exact same number: ``AIPackage-numpy-9`` twice, since
    ``_sorted_by_spdx_id``'s string sort makes harvest keep the entity
    from the ``-9`` element, not the highest-numbered ``-10`` one."""
    project = ProjectMetadata(name="ai-collision-project", version="0.1.0")
    ai_models = _numpy_models()
    creation_metadata = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")
    doc_run1 = DocumentModel(
        project=project, creation_metadata=creation_metadata, ai_models=ai_models
    )

    first_exporter = build(doc_run1)
    _assert_ten_distinct_ai_package_ids(first_exporter)

    sbom_path = tmp_path / "run1.spdx.json"
    sbom_path.write_text(first_exporter.to_json(), encoding="utf-8")
    registry = IdRegistry.new("ai-collision-project")
    registry.import_sbom(sbom_path)
    # Ten elements share the name "numpy", so harvest leaves it unpinned;
    # pin the id the old harvest kept (the last in string order) by hand.
    assert ("ai_AIPackage", "numpy") not in registry.entities
    stale_id = max(
        str(obj.spdxId)
        for obj in first_exporter.object_set.objects
        if isinstance(obj, spdx3.ai_AIPackage)
    )
    registry.entities[("ai_AIPackage", "numpy")] = EntityEntry(stale_id)

    doc_run2 = DocumentModel(
        project=project, creation_metadata=creation_metadata, ai_models=ai_models
    )
    second_exporter = build(doc_run2, registry=registry)
    _assert_ten_distinct_ai_package_ids(second_exporter)
