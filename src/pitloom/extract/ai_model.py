# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for model metadata from AI model files.

Supports fastText, GGUF, HDF5/Keras, NumPy, ONNX, PyTorch, and Safetensors
formats via optional dependencies.

    pip install pitloom[fasttext]    # for fastText support
    pip install pitloom[gguf]        # for GGUF support
    pip install pitloom[hdf5]        # for HDF5/Keras support
    pip install pitloom[numpy]       # for NumPy support
    pip install pitloom[onnx]        # for ONNX support
    pip install pitloom[pytorch]     # for PyTorch support (fickling)
    pip install pitloom[safetensors] # for Safetensors support
    pip install pitloom[aimodel]     # for all model formats
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract._fasttext import read_fasttext
from pitloom.extract._gguf import read_gguf
from pitloom.extract._hdf5 import read_hdf5
from pitloom.extract._numpy import read_numpy
from pitloom.extract._onnx import read_onnx
from pitloom.extract._pytorch import read_pytorch
from pitloom.extract._pytorch_pt2 import read_pytorch_pt2
from pitloom.extract._safetensors import read_safetensors

__all__ = [
    "AiModelFormat",
    "AiModelMetadata",
    "FormatInfo",
    "REGISTRY",
    "detect_ai_model_format",
    "read_ai_model",
    "read_fasttext",
    "read_gguf",
    "read_hdf5",
    "read_numpy",
    "read_onnx",
    "read_pytorch",
    "read_pytorch_pt2",
    "read_safetensors",
]


@dataclass(frozen=True)
class FormatInfo:
    """Describes a supported AI model file format.

    This is the single source of truth for format detection and dispatch.
    The :data:`REGISTRY` tuple collects one :class:`FormatInfo` per format.

    Attributes:
        format: The :class:`~pitloom.core.ai_metadata.AiModelFormat` value.
        extensions: File extensions (lowercase, with leading dot) that
            unambiguously identify this format and are used as the
            extension-fallback detection step.  Extensions shared across
            formats (e.g. ``.bin``) are omitted here; those files are
            detected by magic bytes instead.
        magic: Fixed magic-byte prefix at byte offset 0, or ``None`` when
            the format has no fixed file-level signature (ONNX, Safetensors,
            NumPy ``.npz``, PyTorch ``.pt``/``.pth``/``.pt2``).
        reader: Callable that extracts :class:`AiModelMetadata` from a file
            of this format, or ``None`` if no reader is registered yet.
    """

    format: AiModelFormat
    extensions: tuple[str, ...]
    magic: bytes | None = None
    reader: Callable[[Path], AiModelMetadata] | None = None


# Registry of all supported AI model formats — ordered alphabetically by name.
#
# Notes on detection:
# - fastText .bin files are detected by magic; .ftz is fastText-specific extension.
#   .bin is excluded from extensions: it is too generic (word2vec, BERT vocab, …).
# - NumPy .npy has magic b'\x93NUMPY'; .npz is a ZIP archive with no NumPy magic
#   and is detected by extension fallback.
# - PT2 Archive (.pt2) and classic PyTorch (.pt/.pth) are both ZIP archives;
#   ZIP magic b'PK\x03\x04' is shared with other formats, so detection falls
#   back to extension.
# - Safetensors has no fixed magic: it uses an 8-byte LE uint64 header-size
#   followed by an opening '{'.  This heuristic lives in _match_magic.
REGISTRY: tuple[FormatInfo, ...] = (
    FormatInfo(
        format=AiModelFormat.FASTTEXT,
        extensions=(".ftz",),
        magic=b"\xba\x16\x4f\x2f",
        reader=read_fasttext,
    ),
    FormatInfo(
        format=AiModelFormat.GGUF,
        extensions=(".gguf",),
        magic=b"GGUF",
        reader=read_gguf,
    ),
    FormatInfo(
        format=AiModelFormat.HDF5,
        extensions=(".h5", ".hdf5"),
        magic=b"\x89HDF\r\n\x1a\n",
        reader=read_hdf5,
    ),
    FormatInfo(
        format=AiModelFormat.NUMPY,
        extensions=(".npy", ".npz"),
        magic=b"\x93NUMPY",
        reader=read_numpy,
    ),
    FormatInfo(
        format=AiModelFormat.ONNX,
        extensions=(".onnx",),
        magic=None,
        reader=read_onnx,
    ),
    FormatInfo(
        format=AiModelFormat.PYTORCH,
        extensions=(".pt", ".pth"),
        magic=None,
        reader=read_pytorch,
    ),
    FormatInfo(
        format=AiModelFormat.PYTORCH_PT2,
        extensions=(".pt2",),
        magic=None,
        reader=read_pytorch_pt2,
    ),
    FormatInfo(
        format=AiModelFormat.SAFETENSORS,
        extensions=(".safetensors",),
        magic=None,
        reader=read_safetensors,
    ),
)

# Safetensors header JSON is bounded in practice; 100 MB is a generous upper limit.
_SAFETENSORS_MAX_HEADER: int = 100_000_000
# Number of bytes needed to run all magic checks (8-byte HDF5 + 1 for Safetensors).
_SNIFF_BYTES: int = 9

# Derived lookups built from REGISTRY — do not edit these directly.
_EXTENSION_TO_FORMAT: dict[str, AiModelFormat] = {
    ext: info.format for info in REGISTRY for ext in info.extensions
}
_READERS: dict[AiModelFormat, Callable[[Path], AiModelMetadata]] = {
    info.format: info.reader for info in REGISTRY if info.reader is not None
}


def _match_magic(header: bytes) -> AiModelFormat:
    """Match *header* bytes against known magic signatures.

    Checks fixed prefixes from :data:`REGISTRY` first, then applies the
    Safetensors heuristic (no fixed magic).

    Args:
        header: The first :data:`_SNIFF_BYTES` bytes of a file.

    Returns:
        Detected :class:`AiModelFormat`, or :attr:`AiModelFormat.UNKNOWN`.
    """
    for info in REGISTRY:
        if info.magic is not None:
            n = len(info.magic)
            if len(header) >= n and header[:n] == info.magic:
                return info.format

    # Safetensors: 8-byte LE uint64 header size, then JSON opening brace.
    if len(header) >= 9:
        header_size = int.from_bytes(header[:8], byteorder="little")
        if 0 < header_size < _SAFETENSORS_MAX_HEADER and header[8:9] == b"{":
            return AiModelFormat.SAFETENSORS

    return AiModelFormat.UNKNOWN


def _sniff_format(model_path: Path) -> AiModelFormat:
    """Return the format detected from the first few bytes of *model_path*.

    Reads at most :data:`_SNIFF_BYTES` bytes.  Returns
    :attr:`AiModelFormat.UNKNOWN` on any I/O error or unrecognised signature.
    """
    try:
        with model_path.open("rb") as fh:
            header = fh.read(_SNIFF_BYTES)
    except OSError:
        return AiModelFormat.UNKNOWN

    return _match_magic(header)


def detect_ai_model_format(model_path: Path) -> AiModelFormat:
    """Detect the format of an AI model file.

    Detection strategy (in order):

    1. **Magic bytes** — if *model_path* is an existing file, read the first
       :data:`_SNIFF_BYTES` bytes and match known signatures via
       :data:`REGISTRY`.  This is reliable even when the file extension is
       wrong or absent.
    2. **File extension** — fall back to a case-insensitive extension lookup
       derived from :data:`REGISTRY` for formats without a fixed magic
       signature (ONNX, PyTorch, Safetensors, NumPy ``.npz``) and for paths
       that are not yet accessible on disk.

    Args:
        model_path: Path to the model file.

    Returns:
        Detected :class:`AiModelFormat`, or :attr:`AiModelFormat.UNKNOWN`.
    """
    if model_path.is_file():
        fmt = _sniff_format(model_path)
        if fmt != AiModelFormat.UNKNOWN:
            return fmt

    return _EXTENSION_TO_FORMAT.get(model_path.suffix.lower(), AiModelFormat.UNKNOWN)


def read_ai_model(model_path: Path) -> AiModelMetadata:
    """Extract metadata from an AI model file, dispatching by format.

    Args:
        model_path: Path to the model file.

    Returns:
        AiModelMetadata populated with available fields.

    Raises:
        FileNotFoundError: If the model file does not exist.
        ValueError: If the format is unsupported or the file cannot be parsed.
    """
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    reader = _READERS.get(detect_ai_model_format(model_path))
    if reader is None:
        raise ValueError(
            f"Unsupported model format for file: {model_path}. "
            f"Supported extensions: {', '.join(_EXTENSION_TO_FORMAT)}"
        )
    return reader(model_path)
