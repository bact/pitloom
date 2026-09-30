# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for model metadata from AI model files.

Supports fastText, GGUF, HDF5, Keras, NumPy, ONNX, PyTorch,
PyTorch PT2, and Safetensors formats.

Some formats require optional dependencies to read metadata:

    pip install pitloom[ai]          # for all model formats
    pip install pitloom[fasttext]    # for fastText support
    pip install pitloom[gguf]        # for GGUF support
    pip install pitloom[hdf5]        # for HDF5 support
    pip install pitloom[numpy]       # for NumPy support
    pip install pitloom[onnx]        # for ONNX support
    pip install pitloom[pytorch]     # for PyTorch support
    pip install pitloom[safetensors] # for Safetensors support
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model.fasttext import read_fasttext
from pitloom.extract.ai_model.gguf import read_gguf
from pitloom.extract.ai_model.hdf5 import read_hdf5
from pitloom.extract.ai_model.keras import read_keras
from pitloom.extract.ai_model.numpy import read_numpy
from pitloom.extract.ai_model.onnx import read_onnx
from pitloom.extract.ai_model.pytorch import read_pytorch
from pitloom.extract.ai_model.pytorch_pt2 import read_pytorch_pt2
from pitloom.extract.ai_model.safetensors import read_safetensors

__all__ = [
    "AiModelFormat",
    "AiModelMetadata",
    "FormatInfo",
    "REGISTRY",
    "SNIFF_BYTES",
    "detect_ai_model_format",
    "detect_ai_model_format_from_header",
    "read_ai_model",
    "read_ai_model_header",
]


@dataclass(frozen=True)
class FormatInfo:
    """Associates an :class:`AiModelFormat` with its metadata reader function.

    Format identification metadata (extensions, magic bytes) lives on the
    :class:`AiModelFormat` enum member itself.  :class:`FormatInfo` only
    registers the reader/extractor for a given format.

    Attributes:
        format: The :class:`~pitloom.core.ai_metadata.AiModelFormat` value.
        reader: Callable that extracts :class:`AiModelMetadata` from a file
            of this format, or ``None`` if no reader is registered yet.
    """

    format: AiModelFormat
    reader: Callable[[Path], AiModelMetadata] | None = None


# Registry of all supported AI model formats - ordered alphabetically by name.
# Format identification metadata (extensions, magic bytes) is on AiModelFormat.
# Safetensors has no fixed magic: it uses an 8-byte LE uint64 header-size
# followed by an opening '{'; this heuristic lives in _match_magic.
REGISTRY: tuple[FormatInfo, ...] = (
    FormatInfo(format=AiModelFormat.FASTTEXT, reader=read_fasttext),
    FormatInfo(format=AiModelFormat.GGUF, reader=read_gguf),
    FormatInfo(format=AiModelFormat.HDF5, reader=read_hdf5),
    FormatInfo(format=AiModelFormat.KERAS, reader=read_keras),
    FormatInfo(format=AiModelFormat.NUMPY, reader=read_numpy),
    FormatInfo(format=AiModelFormat.ONNX, reader=read_onnx),
    FormatInfo(format=AiModelFormat.PYTORCH, reader=read_pytorch),
    FormatInfo(format=AiModelFormat.PYTORCH_PT2, reader=read_pytorch_pt2),
    FormatInfo(format=AiModelFormat.SAFETENSORS, reader=read_safetensors),
)

# Safetensors header JSON is bounded in practice; 100 MB is a generous upper limit.
_SAFETENSORS_MAX_HEADER: int = 100_000_000
# Number of bytes needed to run all magic checks (8-byte HDF5 + 1 for Safetensors).
SNIFF_BYTES: int = 9

# Derived lookups - built from AiModelFormat enum members and REGISTRY.
_EXTENSION_TO_FORMAT: dict[str, AiModelFormat] = {
    ext: fmt for fmt in AiModelFormat.__members__.values() for ext in fmt.extensions
}
_READERS: dict[AiModelFormat, Callable[[Path], AiModelMetadata]] = {
    info.format: info.reader for info in REGISTRY if info.reader is not None
}


def _match_magic(header: bytes) -> AiModelFormat:
    """Match *header* bytes against known magic signatures.

    Checks fixed prefixes from :class:`AiModelFormat` members first, then
    applies the Safetensors heuristic (no fixed magic).

    Args:
        header: The first :data:`SNIFF_BYTES` bytes of a file.

    Returns:
        Detected :class:`AiModelFormat`, or :attr:`AiModelFormat.UNKNOWN`.
    """
    for fmt in AiModelFormat.__members__.values():
        if fmt.magic is not None:
            n = len(fmt.magic)
            if len(header) >= n and header[:n] == fmt.magic:
                return fmt

    # Safetensors: 8-byte LE uint64 header size, then JSON opening brace.
    if len(header) >= 9:
        header_size = int.from_bytes(header[:8], byteorder="little")
        if 0 < header_size < _SAFETENSORS_MAX_HEADER and header[8:9] == b"{":
            return AiModelFormat.SAFETENSORS

    return AiModelFormat.UNKNOWN


def read_ai_model_header(model_path: Path) -> bytes:
    """Return the first :data:`SNIFF_BYTES` bytes of *model_path*.

    Returns ``b""`` when *model_path* is absent or not a regular file.

    Raises:
        OSError: The file exists but cannot be read (e.g. ``PermissionError``,
            including a denied parent directory). Absence is not an error;
            this is.
    """
    try:
        with model_path.open("rb") as fh:
            return fh.read(SNIFF_BYTES)
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return b""
    except PermissionError:
        # Windows raises this for a directory; that is absence, not denial.
        if os.path.isdir(model_path):
            return b""
        raise


def detect_ai_model_format_from_header(header: bytes, name: str) -> AiModelFormat:
    """Detect a model format from its leading bytes and its file name.

    Detection strategy (in order):

    1. **Magic bytes** - match *header* against known signatures from
       :class:`AiModelFormat` members.  This is reliable even when the file
       extension is wrong or absent.
    2. **File extension** - fall back to a case-insensitive extension lookup
       of *name* for formats without a fixed magic signature (ONNX, PyTorch,
       Safetensors, NumPy ``.npz``) and for files that are not accessible
       (empty *header*).

    Args:
        header: Up to :data:`SNIFF_BYTES` leading bytes; ``b""`` when
            unreadable.
        name: A file name or POSIX archive name; only its suffix is used.

    Returns:
        Detected :class:`AiModelFormat`, or :attr:`AiModelFormat.UNKNOWN`.
    """
    fmt = _match_magic(header)
    if fmt != AiModelFormat.UNKNOWN:
        return fmt
    return _EXTENSION_TO_FORMAT.get(
        PurePosixPath(name).suffix.lower(), AiModelFormat.UNKNOWN
    )


def detect_ai_model_format(model_path: Path) -> AiModelFormat:
    """Detect the format of an AI model file.

    Magic bytes first, then the file extension; see
    :func:`detect_ai_model_format_from_header`. Never raises on an
    unreadable file: it falls back to the extension.
    """
    try:
        header = read_ai_model_header(model_path)
    except OSError:
        header = b""
    return detect_ai_model_format_from_header(header, model_path.name)


def read_ai_model(
    model_path: Path, *, model_format: AiModelFormat | None = None
) -> AiModelMetadata:
    """Extract metadata from an AI model file, dispatching by format.

    Args:
        model_path: Path to the model file.
        model_format: Format decided by the caller (e.g. from a header already
            read); ``None`` detects it from *model_path*.

    Returns:
        AiModelMetadata populated with available fields.

    Raises:
        FileNotFoundError: If the model file does not exist.
        ValueError: If the format is unsupported or the file cannot be parsed.
    """
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    if model_format is None:
        model_format = detect_ai_model_format(model_path)
    reader = _READERS.get(model_format)
    if reader is None:
        raise ValueError(
            f"Unsupported model format for file: {model_path}. "
            f"Supported extensions: {', '.join(_EXTENSION_TO_FORMAT)}"
        )
    return reader(model_path)
