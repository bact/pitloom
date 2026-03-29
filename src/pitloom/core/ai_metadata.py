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
    """Supported AI model file formats.

    Attributes:
        extensions: File extensions (lowercase, with leading dot) that
            unambiguously identify this format and are used as the
            extension-fallback detection step.  Extensions shared across
            formats (e.g. ``.bin``) are omitted; those files are identified
            by magic bytes instead.
        magic: Fixed magic-byte prefix at byte offset 0, or ``None`` when
            the format has no fixed file-level signature or shares its
            signature with other formats (like ZIP-based formats).
    """

    # Declare instance attributes so static type checkers recognise them.
    extensions: tuple[str, ...]
    magic: bytes | None

    def __new__(
        cls,
        value: str,
        extensions: tuple[str, ...] = (),
        magic: bytes | None = None,
    ) -> AiModelFormat:
        obj = str.__new__(cls, value)
        obj._value_ = value
        return obj

    def __init__(
        self,
        value: str,  # pylint: disable=unused-argument  # consumed by __new__
        extensions: tuple[str, ...] = (),
        magic: bytes | None = None,
    ) -> None:
        self.extensions = extensions
        self.magic = magic

    def __str__(self) -> str:
        return str(self.value)

    UNKNOWN = "unknown"
    FASTTEXT = ("fasttext", (".ftz",), b"\xba\x16\x4f\x2f")
    GGUF = ("gguf", (".gguf",), b"GGUF")
    HDF5 = ("hdf5", (".h5", ".hdf5"), b"\x89HDF\r\n\x1a\n")
    KERAS = ("keras", (".keras",))
    NUMPY = ("numpy", (".npy", ".npz"), b"\x93NUMPY")
    ONNX = ("onnx", (".onnx",))
    PYTORCH = ("pytorch", (".pt", ".pth"))
    PYTORCH_PT2 = ("pytorch_pt2", (".pt2",))
    SAFETENSORS = ("safetensors", (".safetensors",))


@dataclass
class AiModelMetadata:
    """Metadata extracted from an AI model file.

    Fields align with the SPDX 3.0 AI profile where applicable.
    See: https://spdx.github.io/spdx-spec/v3.0/model/AI/Classes/AIPackage/
    """

    format: AiModelFormat = AiModelFormat.UNKNOWN

    # Version of the model file format (e.g. "v2" for Keras v2, "1.0" for NumPy 1.0)
    format_version: str | None = None

    # Framework that produced the model or is expected to consume it
    # (e.g. "keras", "pytorch", "llama.cpp")
    framework: str | None = None

    # Version of the framework/library used to produce the model
    # (e.g. "2.15.0" for Keras 2.15.0, "2.7.1" for PyTorch 2.7.1)
    framework_version: str | None = None

    # Core identification (maps to SPDX Core: name, description)
    name: str | None = None
    description: str | None = None
    version: str | None = None
    license: str | None = None  # SPDX license expression if available

    # SPDX AI profile: typeOfModel (e.g. "neural network", "transformer")
    type_of_model: str | None = None

    # SPDX AI profile: hyperparameter — model configuration values
    hyperparameters: dict[str, Any] = field(default_factory=dict)

    # Format-specific key/value metadata (e.g. GGUF general.*, ONNX metadata_props)
    properties: dict[str, str] = field(default_factory=dict)

    # Input and output tensor specifications
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)

    # Provenance tracking: field name -> source description
    provenance: dict[str, str] = field(default_factory=dict)
