# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for model metadata from AI model files.

Supports fastText, GGUF, HDF5, Keras, NumPy, ONNX, PyTorch,
PyTorch PT2, and Safetensors formats.

Per-format extractors in this subpackage are internal implementation
modules; callers should use the facade functions exported below.
"""

from __future__ import annotations

from pitloom.extract.ai_model.reader import (
    REGISTRY,
    SNIFF_BYTES,
    AiModelFormat,
    AiModelMetadata,
    FormatInfo,
    detect_ai_model_format,
    detect_ai_model_format_from_header,
    detect_ai_model_format_from_name,
    read_ai_model,
    read_ai_model_header,
)

__all__ = [
    "REGISTRY",
    "SNIFF_BYTES",
    "AiModelFormat",
    "AiModelMetadata",
    "FormatInfo",
    "detect_ai_model_format",
    "detect_ai_model_format_from_header",
    "detect_ai_model_format_from_name",
    "read_ai_model",
    "read_ai_model_header",
]
