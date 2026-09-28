# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for AI metadata preservation, blobs, and entity lookup.

See also: :mod:`tests.assemble.test_assemble_ai`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pitloom.assemble.spdx3.ai import (
    _lookup_ai_model_entity,
    _should_preserve_metadata,
    _source_metadata_blob,
)
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.ids import EntityEntry, IdRegistry

from ..conftest import fake_build_and_read_path


def test_should_preserve_metadata_always() -> None:
    model = AiModelMetadata()
    assert _should_preserve_metadata(model, {}, "always") is True


def test_should_preserve_metadata_never() -> None:
    model = AiModelMetadata()
    assert _should_preserve_metadata(model, {}, "never") is False


def test_should_preserve_metadata_auto_not_shipped() -> None:
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(file_path_relative="model.gguf")
    )
    assert _should_preserve_metadata(model, {}, "auto") is True


def test_should_preserve_metadata_auto_shipped() -> None:
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(file_path_relative="model.gguf")
    )
    file_spdx_ids = {"model.gguf": "urn:doc#File-model"}
    assert _should_preserve_metadata(model, file_spdx_ids, "auto") is False


def test_should_preserve_metadata_auto_no_relative_path() -> None:
    model = AiModelMetadata()
    assert _should_preserve_metadata(model, {}, "auto") is True


def test_source_metadata_blob_prefers_raw_metadata() -> None:
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.GGUF),
        raw_metadata={"general.name": "test-model"},
        properties={"ignored": "yes"},
    )
    fmt, blob = _source_metadata_blob(model)
    assert fmt == "gguf"
    assert blob == {"general.name": "test-model"}


def test_source_metadata_blob_falls_back_to_properties_and_extras() -> None:
    model = AiModelMetadata(
        properties={"p": "1"},
        extra_data={"hf.sha": "abc123"},
        extra_lists={"hf.tags": ["a", "b"]},
    )
    fmt, blob = _source_metadata_blob(model)
    assert fmt == "huggingface"
    assert blob == {"p": "1", "hf.sha": "abc123", "hf.tags": ["a", "b"]}


def test_source_metadata_blob_unknown_format_no_extras_stays_unknown() -> None:
    model = AiModelMetadata(properties={"p": "1"})
    fmt, _blob = _source_metadata_blob(model)
    assert fmt == "unknown"


def test_lookup_ai_model_entity_no_registry_returns_none() -> None:
    model = AiModelMetadata(name="mymodel")
    assert _lookup_ai_model_entity(model, None) is None


def test_lookup_ai_model_entity_not_found_returns_none() -> None:
    registry = IdRegistry(namespace="urn:doc")
    model = AiModelMetadata(name="unregistered")
    assert _lookup_ai_model_entity(model, registry) is None


def test_lookup_ai_model_entity_found_by_name() -> None:
    registry = IdRegistry(
        namespace="urn:doc",
        entities={
            ("ai_AIPackage", "mymodel"): EntityEntry(spdx_id="urn:doc#AIPackage-1")
        },
    )
    model = AiModelMetadata(name="mymodel")
    assert _lookup_ai_model_entity(model, registry) == "urn:doc#AIPackage-1"


def test_lookup_ai_model_entity_found_by_physical_path() -> None:
    registry = IdRegistry(
        namespace="urn:doc",
        entities={
            ("ai_AIPackage", "src/model.gguf"): EntityEntry(
                spdx_id="urn:doc#AIPackage-2"
            )
        },
    )
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(physical_path="src/model.gguf")
    )
    assert _lookup_ai_model_entity(model, registry) == "urn:doc#AIPackage-2"


def test_lookup_ai_model_entity_found_by_file_stem() -> None:
    registry = IdRegistry(
        namespace="urn:doc",
        entities={
            ("ai_AIPackage", "model"): EntityEntry(spdx_id="urn:doc#AIPackage-3")
        },
    )
    model = AiModelMetadata(format_info=AiModelFormatInfo(file_name="model.gguf"))
    assert _lookup_ai_model_entity(model, registry) == "urn:doc#AIPackage-3"


def test_lookup_ai_model_entity_falls_back_when_physical_path_absolute() -> None:
    """Regression: a build-and-read (--allow-build) discovered model has
    an absolute physical_path (a fresh tempfile.mkdtemp() extraction
    dir -- see ProjectFile.physical_path's docstring), which never
    matches a registry entry keyed by a project-relative path. Falls
    back to file_path_relative, the same rule _document_files.py's
    determinism fix and enrich's _resolve_model_search_dir already
    apply for this identical hazard."""
    registry = IdRegistry(
        namespace="urn:doc",
        entities={
            ("ai_AIPackage", "src/model.gguf"): EntityEntry(
                spdx_id="urn:doc#AIPackage-4"
            )
        },
    )
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            physical_path=fake_build_and_read_path("src", "model.gguf"),
            file_path_relative="src/model.gguf",
        )
    )
    assert _lookup_ai_model_entity(model, registry) == "urn:doc#AIPackage-4"


def test_lookup_ai_model_entity_absolute_path_no_fallback_skips_candidate() -> None:
    """When physical_path is absolute and file_path_relative is also
    unset, no candidate is added for it at all (not a bare empty-string
    lookup) -- falls through to the next candidate (file stem)."""
    registry = IdRegistry(
        namespace="urn:doc",
        entities={
            ("ai_AIPackage", "model"): EntityEntry(spdx_id="urn:doc#AIPackage-5")
        },
    )
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            physical_path=fake_build_and_read_path("model.gguf"),
            file_name="model.gguf",
        )
    )
    assert _lookup_ai_model_entity(model, registry) == "urn:doc#AIPackage-5"
