# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for model metadata from AI model files.

Supports CRFsuite, fastText, GGUF, HDF5, Keras, NumPy, ONNX, PyTorch,
PyTorch PT2, and Safetensors formats.

Per-format extractors in this subpackage are internal implementation
modules; callers should use the facade functions exported below.
"""

from __future__ import annotations

from pitloom.extract.ai_model.reader import (
    NOT_A_MODEL_MESSAGE,
    REGISTRY,
    SNIFF_BYTES,
    AiModelFormat,
    AiModelMetadata,
    FormatInfo,
    NotAModel,
    contradicted_format,
    detect_ai_model_format,
    detect_ai_model_format_from_header,
    detect_ai_model_format_from_name,
    is_git_lfs_pointer,
    not_a_model_reason,
    read_ai_model,
    read_ai_model_header,
    refusal_reason,
)

__all__ = [
    "NOT_A_MODEL_MESSAGE",
    "REGISTRY",
    "SNIFF_BYTES",
    "AiModelFormat",
    "AiModelMetadata",
    "FormatInfo",
    "NotAModel",
    "contradicted_format",
    "detect_ai_model_format",
    "detect_ai_model_format_from_header",
    "detect_ai_model_format_from_name",
    "is_git_lfs_pointer",
    "not_a_model_reason",
    "read_ai_model",
    "read_ai_model_header",
    "refusal_reason",
]
