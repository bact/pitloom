# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""End-to-end test for build()'s max_source_metadata_bytes cap on the P1
artifact-metadata Annotation, through the real assembly pipeline.

See also: tests/assemble/test_annotation_metadata_truncation.py, which
unit-tests build_source_metadata_annotation() directly.
"""

from __future__ import annotations

import json

from pitloom.assemble.spdx3.document import build
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig


def test_build_respects_max_source_metadata_bytes_end_to_end() -> None:
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.GGUF),
        name="tiny-llm",
        version="1.0.0",
        raw_metadata={
            "general.architecture": "llama",
            "tokenizer.ggml.tokens": [f"token_{i}" for i in range(5000)],
        },
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )
    provenance = ProvenanceConfig(
        preserve_source_metadata="always", max_source_metadata_bytes=500
    )

    exporter = build(doc, provenance=provenance)
    output = exporter.to_json(pretty=False)
    data = json.loads(output)  # whole document must still be valid JSON
    graph = data["@graph"]

    annotations = [
        e
        for e in graph
        if e.get("type") == "Annotation" and e.get("contentType") == "application/json"
    ]
    artifact_metadata_anns = [
        a
        for a in annotations
        if json.loads(a["statement"]).get("kind") == "artifact-metadata"
    ]
    assert len(artifact_metadata_anns) == 1
    ann = artifact_metadata_anns[0]

    assert len(ann["statement"].encode("utf-8")) <= 500
    statement = json.loads(ann["statement"])  # must parse cleanly
    assert statement["truncated"] is True
    assert "tokenizer.ggml.tokens" in statement["truncatedKeys"]
    assert statement["metadata"] == {"general.architecture": "llama"}
