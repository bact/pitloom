# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One real fixture per AI model format, for tests that must hold for every
format alike (tests/extract/test_model_target.py): a guard test fails when a
format is added without one.

See also: ``tests/fixtures/aimodels/README.md`` (the fixtures) and
tests/extract/test_model_target.py (the guard).
"""

from __future__ import annotations

from pathlib import Path

from pitloom.core.ai_metadata import AiModelFormat

_ROOT = Path(__file__).resolve().parent / "fixtures" / "aimodels"

#: Each supported format to its fixture, relative to ``tests/fixtures/aimodels``.
FORMAT_FIXTURES: dict[AiModelFormat, str] = {
    AiModelFormat.CRFSUITE: "crfsuite/complete.crfsuite",
    AiModelFormat.FASTTEXT: "fasttext/sentimentdemo.bin",
    AiModelFormat.GGUF: "gguf/ggml-vocab-bert-bge.gguf",
    AiModelFormat.HDF5: "hdf5/example-model.h5",
    AiModelFormat.KERAS: "keras/example-model.keras",
    AiModelFormat.NUMPY: "numpy/example-model-v1.npy",
    AiModelFormat.ONNX: "onnx/light-inception-v2.onnx",
    AiModelFormat.PYTORCH: "pytorch/example-model.pt",
    AiModelFormat.PYTORCH_PT2: "pytorch_pt2/example-model.pt2",
    AiModelFormat.SAFETENSORS: "safetensors/phi-tiny-random.safetensors",
}

#: Formats the header alone does not confirm: a ZIP (Keras, PT2, PyTorch)
#: or protobuf (ONNX) file needs its suffix, so a copy named ``x.dat`` is
#: not recognised by its content.
NEEDS_SUFFIX: frozenset[AiModelFormat] = frozenset(
    {
        AiModelFormat.KERAS,
        AiModelFormat.ONNX,
        AiModelFormat.PYTORCH,
        AiModelFormat.PYTORCH_PT2,
    }
)

#: The formats, sorted, as ``pytest.mark.parametrize`` values.
FORMATS: tuple[AiModelFormat, ...] = tuple(sorted(FORMAT_FIXTURES, key=str))


def fixture_path(fmt: AiModelFormat) -> Path:
    """The absolute path of *fmt*'s fixture."""
    return _ROOT / FORMAT_FIXTURES[fmt]
