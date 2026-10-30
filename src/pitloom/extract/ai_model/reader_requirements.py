# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The optional library each model reader needs, and the one error every
caller gives when it is missing (``library-missing``).

A reader raises it when its import fails; the scanner asks first
(:func:`require_library`), so a wheel scan does not copy a model out of the
archive just to report that its reader cannot run.

See also: :mod:`pitloom.extract.scanner` and
:mod:`pitloom.core.optional_libraries` (every optional library).
"""

from __future__ import annotations

import importlib.util

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.optional_libraries import Requirement, missing

# Formats not listed (CRFsuite, Keras v3, PyTorch, PT2) read through the
# standard library; PyTorch's fickling is optional and its absence is not an error.
REQUIREMENTS: dict[AiModelFormat, Requirement] = {
    AiModelFormat.FASTTEXT: Requirement("fasttext", "fasttext"),
    AiModelFormat.GGUF: Requirement("gguf", "gguf"),
    AiModelFormat.HDF5: Requirement("h5py", "hdf5"),
    AiModelFormat.NUMPY: Requirement("numpy", "numpy"),
    AiModelFormat.ONNX: Requirement("onnx", "onnx"),
    AiModelFormat.SAFETENSORS: Requirement("safetensors", "safetensors"),
}


def missing_library(fmt: AiModelFormat) -> ImportError:
    """The error a reader of *fmt* raises when its library cannot be
    imported (:func:`~pitloom.core.optional_libraries.missing`)."""
    return missing(REQUIREMENTS[fmt])


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
