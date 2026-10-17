# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model with no stated signature has no ``ai_informationAboutApplication``
on any route; one with a signature has only the signature (and, from a card,
intended use).

See also: tests/extract/ai_model/test_model_io_signatures.py (the readers).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import (
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from tests._wheel_models import safetensors_bytes, write_model_wheel

_MODEL = "m.safetensors"
_DATA = safetensors_bytes()
_PYPROJECT = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    '[project]\nname = "demo"\nversion = "1.0.0"\nrequires-python = ">=3.10"\n'
)
_FIXTURES = Path(__file__).parents[1] / "fixtures" / "aimodels"


def _package(sbom: str) -> dict[str, Any]:
    graph = json.loads(sbom)["@graph"]
    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    return dict(package)


def _project(tmp: Path) -> str:
    root = tmp / "proj"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"x = 1\n")
    (root / "demo" / _MODEL).write_bytes(_DATA)
    (root / "pyproject.toml").write_bytes(_PYPROJECT.encode())
    return generate_project_sbom(root, creation_metadata=None, offline=True)


def _wheel(tmp: Path) -> str:
    wheel = write_model_wheel(tmp / "dist", {f"demo/{_MODEL}": _DATA})
    return generate_wheel_sbom(wheel, offline=True)


def _model(tmp: Path) -> str:
    path = tmp / _MODEL
    path.write_bytes(_DATA)
    return generate_model_sbom(path)


@pytest.mark.parametrize("route", [_project, _wheel, _model])
def test_safetensors_weights_are_not_written_as_inputs(
    tmp_path: Path, route: Callable[[Path], str]
) -> None:
    sbom = route(tmp_path)
    assert "ai_informationAboutApplication" not in _package(sbom)
    assert (
        "tensor" not in sbom.lower()
        or "weight" not in sbom.lower().split("informationaboutapplication")[0:1][0]
    )


@pytest.mark.parametrize(
    ("fixture", "inputs", "outputs"),
    [
        ("pytorch_pt2/example-model.pt2", ["x"], ["linear"]),
        ("onnx/gpt2-tiny-decoder.onnx", ["input_ids", "attention_mask"], None),
        ("numpy/example-model-v1.npy", None, None),
    ],
    ids=["pt2", "onnx", "numpy"],
)
def test_a_signature_is_written_and_only_a_signature(
    fixture: str, inputs: list[str] | None, outputs: list[str] | None
) -> None:
    package = _package(generate_model_sbom(_FIXTURES / fixture))
    if inputs is None:
        assert "ai_informationAboutApplication" not in package
        return
    info = json.loads(package["ai_informationAboutApplication"])
    assert [i["name"] for i in info["inputs"]] == inputs
    if outputs:
        assert [o["name"] for o in info["outputs"]] == outputs
    assert set(info) <= {"inputs", "outputs"}
