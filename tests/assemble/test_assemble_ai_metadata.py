# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for AI metadata preservation, blobs, and entity lookup.

See also: :mod:`tests.assemble.test_assemble_ai`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import math
from unittest.mock import create_autospec

import pytest
import rfc8785
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.ai import (
    _emit_source_metadata,
    _should_preserve_metadata,
    _source_metadata_blob,
    lookup_model_id,
    model_lookup_key,
)
from pitloom.core.ai_metadata import (
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    SourceMetadata,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import AI_PACKAGE_TYPE, IdRegistrySession, LookupKey
from pitloom.id_registry.keys import Alias
from tests.registry_helpers import make_registry

from ..conftest import fake_build_and_read_path
from .conftest import _DOC_NAME, _DOC_UUID, _make_ci


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
        raw_metadata={"general.name": "test-model", "n": "1"},
        raw_metadata_types={"n": "integer"},
        properties={"ignored": "yes"},
    )
    fmt, blob = _source_metadata_blob(model)
    assert fmt == "gguf"
    assert blob == SourceMetadata(
        raw_metadata={"general.name": "test-model", "n": "1"},
        raw_metadata_types={"n": "integer"},
    )


def test_source_metadata_blob_of_a_model_file_never_falls_back() -> None:
    """A model file's annotation is its reader's ``raw_metadata`` only:
    ``properties`` is a text map, never copied in its place."""
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
        properties={"p": "1"},
    )
    empty = SourceMetadata(raw_metadata={}, raw_metadata_types={})
    assert _source_metadata_blob(model) == ("onnx", empty)


def test_source_metadata_blob_falls_back_to_properties_and_extras() -> None:
    model = AiModelMetadata(
        properties={"p": "1"},
        extra_data={"hf.sha": "abc123"},
        extra_lists={"hf.tags": ["a", "b"]},
    )
    fmt, blob = _source_metadata_blob(model)
    assert fmt == "huggingface"
    assert blob["raw_metadata"] == {"p": "1", "hf.sha": "abc123", "hf.tags": ["a", "b"]}


def test_huggingface_annotation_is_text_typed_canonical_json() -> None:
    """A Hugging Face model's annotation follows the same ``/2`` rules as a
    model file's: scalars text, typed in ``valueTypes``, an integer past
    2**53 and an infinity never reach the canonical serialiser as numbers."""
    model = AiModelMetadata(
        properties={"p": "1"},
        extra_data={
            "hf.tokenizer_max_length": 2**60,
            "hf.lr": 1e-7,
            "hf.limit": math.inf,
            "hf.gated": True,
            "hf.config": {"layers": 2, "tied": False, "eps": None},
        },
        extra_lists={"hf.dims": [1, 0.5]},
    )
    ai_pkg = spdx3.ai_AIPackage(spdxId="urn:doc#ai_AIPackage-1", name="m")
    exporter = create_autospec(Spdx3JsonExporter, instance=True)
    _emit_source_metadata(
        model, ai_pkg, {}, "always", 0, _make_ci(), _DOC_NAME, _DOC_UUID, exporter
    )
    statement_text = exporter.add_annotation.call_args.args[0].statement
    statement = json.loads(statement_text)
    assert statement_text == rfc8785.dumps(statement).decode("utf-8")
    assert statement["format"] == "huggingface"
    assert statement["metadata"] == {
        "p": "1",
        "hf.tokenizer_max_length": "1152921504606846976",
        "hf.lr": "1e-7",
        "hf.limit": "INF",
        "hf.gated": "true",
        "hf.config": {"layers": "2", "tied": "false", "eps": "null"},
        "hf.dims": ["1", "0.5"],
    }
    assert statement["valueTypes"] == {
        "hf.gated": "boolean",
        "hf.limit": "float",
        "hf.lr": "float",
        "hf.tokenizer_max_length": "integer",
    }


def test_source_metadata_blob_unknown_format_no_extras_stays_unknown() -> None:
    model = AiModelMetadata(properties={"p": "1"})
    fmt, _blob = _source_metadata_blob(model)
    assert fmt == "unknown"


_IN_DOC = LookupKey("src/m/bert.gguf", Alias.CANONICAL, path=True)


@pytest.mark.parametrize(
    ("name", "physical", "keys", "prefix", "expected"),
    [
        ("BERT", "src/m/bert.gguf", {"m/bert.gguf": _IN_DOC}, "", _IN_DOC),
        ("BERT", "src/m/bert.gguf", {}, "pkgs/p", ("pkgs/p/src/m/bert.gguf", True)),
        ("BERT", "src/m/bert.gguf", {}, None, ("BERT", False)),
        (" BERT ", "../bert.gguf", {}, "", ("BERT", False)),
        ("  ", fake_build_and_read_path("m", "bert.gguf"), {}, "", ("bert", False)),
        (None, None, {}, "", ("bert", False)),
    ],
    ids=["own-file", "joined", "no-prefix", "outside", "absolute", "stem"],
)
def test_model_lookup_key(
    name: str | None,
    physical: str | None,
    keys: dict[str, LookupKey],
    prefix: str | None,
    expected: LookupKey | tuple[str, bool],
) -> None:
    """The one model rule: its own file's key in the document (alias
    included); else its project path joined to the prefix; else the name
    the SBOM shows (stripped, a blank one is no name: the stem)."""
    model = AiModelMetadata(
        name=name,
        format_info=AiModelFormatInfo(
            file_name="bert.gguf",
            file_path_relative="m/bert.gguf",
            physical_path=physical,
            model_format=AiModelFormat.GGUF,
        ),
    )
    lookup = model_lookup_key(model, keys, prefix)
    if isinstance(expected, LookupKey):
        assert lookup is expected
    else:
        assert (lookup.key, lookup.path, lookup.alias) == (*expected, Alias.NONE)


@pytest.mark.parametrize(
    ("held", "digest", "hit"),
    [
        (("m", None), None, True),
        (("m", "a" * 64), "a" * 64, True),
        (("m", "b" * 64), "a" * 64, False),
        (("other", None), None, False),
    ],
    ids=["ungated", "gated-hit", "gated-miss", "absent"],
)
def test_lookup_model_id_records_the_key_of_a_hit(
    held: tuple[str, str | None], digest: str | None, hit: bool
) -> None:
    """A hit is claimed and its key recorded; a gated lookup misses an entry
    recording another SHA-256."""
    registry = make_registry(
        {(AI_PACKAGE_TYPE, held[0]): ("urn:doc#AIPackage-1", held[1])},
        namespace="urn:doc",
    )
    session = IdRegistrySession(registry)
    got = lookup_model_id(session, "m", LookupKey("m"), digest)
    assert (got == "urn:doc#AIPackage-1") is hit
    recorded = {"urn:doc#AIPackage-1": (AI_PACKAGE_TYPE, "m")} if hit else {}
    assert dict(session.recorded_keys()) == recorded
    assert lookup_model_id(IdRegistrySession(None), "m", LookupKey("m"), None) is None
