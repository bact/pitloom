# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One real fixture per AI model format, for tests that must hold for every
format alike (tests/extract/test_model_target.py): a guard test fails when a
format is added without one. A spy on the readers tells a read from a
format-only entry whatever libraries are installed.

See also: ``tests/fixtures/aimodels/README.md`` (the fixtures) and
tests/extract/test_model_target.py (the guard).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model import reader as ai_model_reader
from pitloom.extract.ai_model.reader_requirements import require_library

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

#: A Hatchling project whose wheel (its build file list) is package ``demo``.
_PYPROJECT = (
    b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    b'[project]\nname = "demo"\nversion = "1.0"\n'
    b'[tool.hatch.build.targets.wheel]\npackages = ["demo"]\n'
)

#: The formats, sorted, as ``pytest.mark.parametrize`` values.
FORMATS: tuple[AiModelFormat, ...] = tuple(sorted(FORMAT_FIXTURES, key=str))


def fixture_path(fmt: AiModelFormat) -> Path:
    """The absolute path of *fmt*'s fixture."""
    return _ROOT / FORMAT_FIXTURES[fmt]


def write_model_project(folder: Path, models: list[Path]) -> Path:
    """A ``demo`` project in the new *folder* whose package, and so its build
    file list, holds a copy of each of *models*."""
    (folder / "demo").mkdir(parents=True)
    (folder / "demo" / "__init__.py").write_bytes(b"")
    (folder / "pyproject.toml").write_bytes(_PYPROJECT)
    for model in models:
        shutil.copy(model, folder / "demo")
    return folder


def has_reader_library(fmt: AiModelFormat) -> bool:
    """Whether *fmt*'s reader can run here (its optional library, if any, is
    installed): without it a scan does not call the reader."""
    try:
        require_library(fmt)
    except ImportError:
        return False
    return True


def spy_readers(
    monkeypatch: pytest.MonkeyPatch, formats: tuple[AiModelFormat, ...] = FORMATS
) -> list[tuple[AiModelFormat, Path]]:
    """Wrap the reader of each of *formats* in the dispatch every read goes
    through; the list returned records each call, then the read runs."""
    read: list[tuple[AiModelFormat, Path]] = []
    # pylint: disable-next=protected-access
    readers = ai_model_reader._READERS

    def spy(fmt: AiModelFormat) -> Callable[[Path], AiModelMetadata]:
        real = readers[fmt]

        def run(path: Path) -> AiModelMetadata:
            read.append((fmt, path))
            return real(path)

        return run

    for fmt in formats:
        monkeypatch.setitem(readers, fmt, spy(fmt))
    return read
