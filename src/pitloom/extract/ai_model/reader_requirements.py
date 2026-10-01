# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The optional library each model reader needs, and the one message every
caller gives when it is missing.

A reader raises it when its import fails; the scanner asks first
(:func:`require_library`), so a wheel scan does not copy a model out of the
archive just to report that its reader cannot run.

See also: :mod:`pitloom.extract.scanner`.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from pitloom.core.ai_metadata import AiModelFormat


@dataclass(frozen=True)
class Requirement:
    """A reader's library.

    Attributes:
        module: Top-level module that is imported.
        message: What an :class:`ImportError` says when it is missing.
    """

    module: str
    message: str


def _package(module: str, what: str) -> Requirement:
    return Requirement(
        module,
        f"The '{module}' package is required to extract {what} model "
        f"metadata. Install it with: pip install {module}",
    )


# Formats not listed (Keras v3, PyTorch, PT2) read through the standard
# library; PyTorch's fickling is optional and its absence is not an error.
REQUIREMENTS: dict[AiModelFormat, Requirement] = {
    AiModelFormat.FASTTEXT: Requirement(
        "fasttext",
        "The 'fasttext' module is required to extract fastText model "
        "metadata. Install it with: pip install fasttext-community",
    ),
    AiModelFormat.GGUF: _package("gguf", "GGUF"),
    AiModelFormat.HDF5: _package("h5py", "HDF5"),
    AiModelFormat.NUMPY: _package("numpy", "NumPy"),
    AiModelFormat.ONNX: _package("onnx", "ONNX"),
    AiModelFormat.SAFETENSORS: _package("safetensors", "Safetensors"),
}


def missing_library(fmt: AiModelFormat) -> ImportError:
    """The error a reader of *fmt* raises when its library cannot be
    imported."""
    return ImportError(REQUIREMENTS[fmt].message)


def require_library(fmt: AiModelFormat) -> None:
    """Raise :func:`missing_library`'s error when *fmt*'s library is not
    installed; nothing is imported. A format with no entry needs none."""
    requirement = REQUIREMENTS.get(fmt)
    if requirement is None:
        return
    try:
        found = importlib.util.find_spec(requirement.module) is not None
    except ValueError:  # already imported, with no spec
        found = True
    if not found:
        raise missing_library(fmt)
