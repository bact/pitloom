# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A GGUF file with a 262,144-token tokeniser (the Gemma 4 family, issue
#514) is read whole: 1,301,338 array elements in all, none of them parsed.

See also: :mod:`tests.extract.ai_model.test_gguf_bounds`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.extract.ai_model.gguf import read_gguf
from tests.extract.ai_model.gguf_builders import (
    STRING,
    gguf_with_tensors,
    kv,
    string,
    tensor_info,
    tokeniser,
)
from tests.warning_helpers import logged_warnings

pytestmark = pytest.mark.platform  # a 20 MB file, memory-mapped

_TOKENS = 262_144
_MERGES = 514_906


def test_a_gemma_4_sized_tokeniser_is_read_whole(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pytest.importorskip("gguf")
    body = (
        kv(b"general.architecture", STRING, string("gemma4"))
        + kv(b"general.name", STRING, string("Gemma 4 shape"))
        + tokeniser(_TOKENS, _MERGES)
    )
    tensors = [tensor_info("token_embd.weight", (64, 4)), tensor_info("out", (4,))]
    path = tmp_path / "gemma-4.gguf"
    path.write_bytes(gguf_with_tensors(tensors, 6, body, data_bytes=4 * 260))
    meta = read_gguf(path)
    assert (meta.name, meta.architecture) == ("Gemma 4 shape", "gemma4")
    assert meta.parameter_count == 260
    for key, length, kind in [
        ("tokens", _TOKENS, "STRING"),
        ("scores", _TOKENS, "FLOAT32"),
        ("token_type", _TOKENS, "INT32"),
        ("merges", _MERGES, "STRING"),
    ]:
        assert meta.properties[f"tokenizer.ggml.{key}.length"] == str(length)
        provenance = meta.provenance[f"properties.tokenizer.ggml.{key}.length"]
        assert "Evidence" not in provenance  # walked to its end: measured
        assert meta.raw_metadata[f"tokenizer.ggml.{key}"] == {
            "length": str(length),
            "type": kind,
        }
    assert not logged_warnings(caplog)
