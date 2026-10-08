# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard: the example in ``docs/metadata-reading-back.md`` is what
Pitloom writes, and a cap comes before the escape.

See also: :mod:`tests.test_docs_examples` (every other doc example).
"""

# pylint: disable=protected-access

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.assemble.spdx3 import _display_text
from pitloom.core.ai_metadata import (
    MAX_MODEL_ENTRIES,
    MAX_MODEL_NAME_CHARS,
    MODEL_NAME_CUT_MARK,
    MODEL_NAME_DIGEST_CHARS,
)
from pitloom.extract.ai_model.formats import Limits
from tests._docs_scan import REPO_ROOT, fenced_blocks
from tests.extract.ai_model.gguf_builders import STRING, UINT32, gguf_file, kv, string

_DOC = REPO_ROOT / "docs" / "metadata-reading-back.md"


def _sbom(path: Path, name: str) -> list[dict[str, Any]]:
    pairs = [
        kv(b"general.name", STRING, string(name)),
        kv(b"llama.context_length", UINT32, struct.pack("<I", 4096)),
    ]
    path.write_bytes(gguf_file(0, len(pairs), b"".join(pairs)))
    graph: list[dict[str, Any]] = json.loads(generate_model_sbom(path))["@graph"]
    return graph


def test_the_example_is_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    graph = _sbom(tmp_path / "demo.gguf", "evil\u202etxt.exe")
    shown, stored = [
        json.loads(b.body) for b in fenced_blocks(_DOC) if b.lang == "json"
    ]
    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    assert {key: package[key] for key in shown} == shown
    (envelope,) = [
        json.loads(e["statement"])
        for e in graph
        if "artifact-metadata" in e.get("statement", "")
    ]
    assert stored["metadata"].items() <= envelope["metadata"].items()
    assert envelope["valueTypes"]["llama.context_length"] == "integer"


def test_an_escaped_name_can_exceed_its_cap(tmp_path: Path) -> None:
    graph = _sbom(tmp_path / "long.gguf", "\u202e" + "a" * 1100)
    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    assert package["name"].startswith("\\u202e" + "a" * 1011 + "...~")
    assert len(package["name"]) == 1024 + 5


@pytest.mark.parametrize(
    ("documented", "value"),
    [
        ("A name over {} characters", MAX_MODEL_NAME_CHARS),
        (
            "cut to its first {}",
            MAX_MODEL_NAME_CHARS
            - len(MODEL_NAME_CUT_MARK + "~")
            - MODEL_NAME_DIGEST_CHARS,
        ),
        ("{} hex digits of the SHA-256", MODEL_NAME_DIGEST_CHARS),
        ("a label over {} bytes", Limits().max_label_bytes),
        ("keeps its first {} entries", MAX_MODEL_ENTRIES),
    ],
    ids=["name-cap", "name-kept", "digest", "label", "entries"],
)
def test_the_documented_caps_are_the_code_constants(
    documented: str, value: int
) -> None:
    text = " ".join(_DOC.read_text(encoding="utf-8").split())
    assert documented.format(value) in text


def test_every_escaped_property_is_documented() -> None:
    """Layer 4 names every property the display escape touches."""
    text = _DOC.read_text(encoding="utf-8")
    props = [prop for prop, _, _ in _display_text._FIELDS]
    props += list(_display_text._ENTRY_FIELDS)
    assert [prop for prop in props if f"`{prop}`" not in text] == []
