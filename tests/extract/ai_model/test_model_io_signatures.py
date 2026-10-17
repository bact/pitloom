# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model's ``inputs`` and ``outputs`` are what its format states as its
signature, never its weights.

The SBOM writes them as ``ai_informationAboutApplication``, which G7 reads as
how the model is used; a Safetensors file's tensor keys once went there as
``inputs``. Only the formats below state a signature, so a format added later
must be listed here on purpose.

See also: tests/assemble/test_ai_package_io.py (the SBOM side).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_ai_model

_AIMODELS = Path(__file__).resolve().parents[2] / "fixtures" / "aimodels"
#: Fixture folder -> what the format states: ONNX, Keras/HDF5 and PT2 an input
#: signature; ONNX and PT2 an output signature; CRFsuite and fastText the shape
#: of their output (a label sequence, label probabilities).
_INPUTS = {"onnx", "keras", "hdf5", "pytorch_pt2"}
_OUTPUTS = {"onnx", "pytorch_pt2", "crfsuite", "fasttext"}
_SUFFIXES = {ext for fmt in AiModelFormat for ext in fmt.extensions}
_FILES = sorted(
    p
    for p in _AIMODELS.glob("*/*")
    if p.suffix in _SUFFIXES and p.parent.name not in ("hostile", "details")
)


def test_the_fixtures_are_found() -> None:
    folders = {p.parent.name for p in _FILES}
    assert (_INPUTS | _OUTPUTS | {"safetensors", "numpy", "gguf"}) <= folders


@pytest.mark.parametrize("path", _FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_only_formats_with_a_signature_have_inputs_or_outputs(path: Path) -> None:
    try:
        meta = read_ai_model(path)
    except ImportError:
        pytest.skip("the format's library is not installed")
    folder = path.parent.name
    assert bool(meta.inputs) <= (folder in _INPUTS), meta.inputs[:2]
    assert bool(meta.outputs) <= (folder in _OUTPUTS), meta.outputs[:2]
    # What is recorded says where it came from.
    assert ("inputs" in meta.provenance) is bool(meta.inputs)
    assert ("outputs" in meta.provenance) is bool(meta.outputs)
