# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Branch-coverage tests for pitloom.assemble.spdx3.ai's build_relationship()
"no relationship built" exit paths -- these only fire when build_relationship()
returns None, which can't happen through the normal call sites (from_id is
always a valid, already-minted spdxId), so each case here monkeypatches
build_relationship() directly to force the falsy branch.

See also: tests/assemble/test_assembly_edge_cases.py, which covers
_add_ai_model_file_relationships()'s other branch (an unmapped usage file).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.ai import _add_ai_model_file_relationships, add_ai_models
from pitloom.core.ai_metadata import AiModelFormatInfo, AiModelMetadata
from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

from .conftest import _DOC_NAME, _DOC_UUID, _make_ci


def test_add_ai_model_file_relationships_skips_when_build_relationship_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both the "contains" (model file) and "hasDataFile" (usage file)
    relationships must be skipped -- not added -- when build_relationship()
    returns None."""
    monkeypatch.setattr(
        "pitloom.assemble.spdx3.ai.build_relationship",
        lambda *args, **kwargs: None,
    )
    exporter = Spdx3JsonExporter()
    creation_info = _make_ci()
    meta = AiModelMetadata(
        format_info=AiModelFormatInfo(file_path_relative="model.onnx"),
        usage_files=["script.py"],
    )
    _add_ai_model_file_relationships(
        meta,
        "http://spdx.org/spdxdocs/ai-pkg",
        {
            "model.onnx": "http://spdx.org/spdxdocs/file-1",
            "script.py": "http://spdx.org/spdxdocs/file-2",
        },
        creation_info,
        _DOC_NAME,
        _DOC_UUID,
        exporter,
    )
    rels = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.Relationship)
    ]
    assert rels == []


def test_add_single_ai_model_skips_contains_relationship_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """add_ai_models() (via _add_single_ai_model()) must not add the
    main-package -> AI-package "contains" Relationship when
    build_relationship() returns None."""
    monkeypatch.setattr(
        "pitloom.assemble.spdx3.ai.build_relationship",
        lambda *args, **kwargs: None,
    )
    exporter = Spdx3JsonExporter()
    creation_info = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID),
        name="main",
        creationInfo=creation_info,
    )
    exporter.add_package(main_pkg)
    model = AiModelMetadata(name="standalone-model")

    add_ai_models(
        [model],
        require_spdx_id(main_pkg),
        {},
        creation_info,
        _DOC_NAME,
        _DOC_UUID,
        exporter,
    )

    rels = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.Relationship)
    ]
    assert rels == []
