# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Format-neutral AI model metadata dataclasses.

These classes are the format-neutral internal representation of AI model
metadata. They have no dependency on any SBOM library or model file format
library, making them easy to test and to consume from any serializer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AiModelFormat(str, Enum):
    """Supported AI model file formats."""

    UNKNOWN = "unknown"
    GGUF = "gguf"
    ONNX = "onnx"
    SAFETENSORS = "safetensors"


@dataclass
class AiModelMetadata:
    """Metadata extracted from an AI model file.

    Fields align with the SPDX 3.0 AI profile where applicable.
    See: https://spdx.github.io/spdx-spec/v3.0/model/AI/Classes/AIPackage/
    """

    format: AiModelFormat = AiModelFormat.UNKNOWN

    # Core identification (maps to SPDX Core: name, description)
    name: str | None = None
    description: str | None = None
    version: str | None = None
    license: str | None = None  # SPDX license expression if available

    # SPDX AI profile: typeOfModel (e.g. "neural network", "transformer")
    type_of_model: str | None = None

    # SPDX AI profile: hyperparameter — model configuration values
    hyperparameters: dict[str, Any] = field(default_factory=dict)

    # Format-specific key/value metadata (e.g. ONNX metadata_props, GGUF general.*)
    properties: dict[str, str] = field(default_factory=dict)

    # Input and output tensor specifications
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)

    # Provenance tracking: field name -> source description
    provenance: dict[str, str] = field(default_factory=dict)
