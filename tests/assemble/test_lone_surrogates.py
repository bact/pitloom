# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A lone surrogate read from a model, a Hugging Face card or a model card
(``json.loads``/YAML accept ``"\\ud800"``) is written as text, with one
``WARNING:``, and never takes down the SBOM.

See also: :mod:`tests.core.test_untrusted_text` (the escape itself).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom import __main__
from pitloom.assemble import enrich_model, generate_model_sbom, generate_project_sbom
from pitloom.extract.remote.huggingface import read_huggingface
from tests.id_registry.surfaces_base import demo_project
from tests.warning_helpers import logged_warnings

# config.json as a file holds it: JSON escapes, decoded by json.loads.
_CONFIG = (
    '{"class_name": "Sequential", "config": '
    '{"name": "a\\ud800b", "x\\udc00": "v\\ud800"}}'
)


def _keras(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metadata.json", '{"keras_version": "3.0.0"}')
        zf.writestr("config.json", _CONFIG)
        zf.writestr("model.weights.h5", b"")
    return path


def _surrogate_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [m for m in logged_warnings(caplog) if "lone surrogates" in m]


def _ai_package(sbom: str) -> dict[str, Any]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    return package


@pytest.mark.parametrize("surface", ["library-model", "cli-model", "library-project"])
def test_a_keras_model_with_a_lone_surrogate_still_gives_an_sbom(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # 1980-01-01, the ZIP date floor: Python 3.14's writestr() stamps from
    # SOURCE_DATE_EPOCH, and an earlier one raises struct.error.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "315532800")
    if surface == "library-project":
        root = demo_project(tmp_path)
        _keras(root / "demo" / "m.keras")
        sbom = generate_project_sbom(root, offline=True)
        where = "demo/m.keras"
    elif surface == "cli-model":
        path = _keras(tmp_path / "m.keras")
        out = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", ["loom", "model", str(path), "-o", str(out)])
        assert __main__.main() == 0
        sbom = out.read_text(encoding="utf-8")
        where = str(path)
    else:
        path = _keras(tmp_path / "m.keras")
        sbom = generate_model_sbom(path)
        where = str(path)
    assert _ai_package(sbom)["name"] == "a\\ud800b"
    assert "\\udc00" in sbom  # the annotation's key, written as text too
    sbom.encode("utf-8")
    assert _surrogate_warnings(caplog) == [
        f"FORMAT=keras FILE={where}: lone surrogates written as \\uXXXX"
    ]


def test_a_hub_card_with_a_lone_surrogate_is_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    hf_data = {
        "config": {"model_type": "x\ud800"},
        "tokenizer_config": None,
        "generation_config": None,
        "card_text": "---\nlicense: mit\n---\n",
        "card_data": {"license": "mit", "datasets": ["o/d\udc00"]},
        "hub_info": {"sha": "1", "tags": []},
    }
    with patch(
        "pitloom.extract.remote.huggingface._fetch_all_hf_data", return_value=hf_data
    ):
        meta = read_huggingface("https://huggingface.co/o/m")
    assert meta.type_of_model == "x\\ud800"
    assert [ref.metadata.name for ref in meta.datasets] == ["o/d\\udc00"]
    assert _surrogate_warnings(caplog) == [
        "FORMAT=huggingface FILE=https://huggingface.co/o/m: lone surrogates "
        "written as \\uXXXX"
    ]


def test_a_model_card_with_a_lone_surrogate_is_enriched(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    model = tmp_path / "m.keras"
    _keras(model)
    card = tmp_path / "README.md"
    card.write_text(
        '---\nlicense: "a\\ud800"\ndatasets: ["d\\udc00"]\n---\n', encoding="utf-8"
    )
    fragment = enrich_model(model)
    fragment.encode("utf-8")
    assert "d\\\\udc00" in fragment
    assert f"FILE={card}: lone surrogates written as \\uXXXX" in (
        _surrogate_warnings(caplog)
    )
