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
from pitloom.extract.ai_model.safetensors import (
    SAFETENSORS_FORMAT_MAX_HEADER_BYTES,
    read_safetensors,
)

__all__ = [
    "AiModelFormat",
    "AiModelMetadata",
    "FormatInfo",
    "REGISTRY",
    "NOT_A_MODEL_MESSAGE",
    "NotAModel",
    "SNIFF_BYTES",
    "contradicted_format",
    "detect_ai_model_format",
    "detect_ai_model_format_from_header",
    "detect_ai_model_format_from_name",
    "is_git_lfs_pointer",
    "not_a_model_reason",
    "refusal_reason",
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

# What a Git LFS pointer file opens with: the line ``version <spec URL>``, per
# the git-lfs pointer spec (docs/spec.md) and its decoder, which compares the
# whole value (and still accepts the URLs of the two earlier spec versions).
_GIT_LFS_OPENINGS = tuple(
    url + eol
    for url in (
        b"version https://git-lfs.github.com/spec/v1",
        b"version https://hawser.github.com/spec/v1",
        b"version http://git-media.io/v/2",
    )
    for eol in (b"\n", b"\r\n")
)

# Number of bytes needed to run all header checks: the longest Git LFS
# opening line; the magic checks (8-byte HDF5 + 1 for Safetensors) need fewer.
SNIFF_BYTES: int = max(map(len, _GIT_LFS_OPENINGS))

# Derived lookups - built from AiModelFormat enum members and REGISTRY.
_EXTENSION_TO_FORMAT: dict[str, AiModelFormat] = {
    ext: fmt for fmt in AiModelFormat.__members__.values() for ext in fmt.extensions
}
# What ``torch.save`` writes: a ZIP local header, or (legacy) a pickle opening
# with the PROTO opcode and protocol 2..5. An archive with no member (an empty
# ``np.savez``) opens with the end-of-central-directory record instead.
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06")
_PICKLE_PROTO_OPCODE = 0x80
_PICKLE_PROTOCOLS = range(2, 6)
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
        if (
            0 < header_size <= SAFETENSORS_FORMAT_MAX_HEADER_BYTES
            and header[8:9] == b"{"
        ):
            return AiModelFormat.SAFETENSORS

    return AiModelFormat.UNKNOWN


def _is_zip(header: bytes) -> bool:
    """Whether *header* opens a ZIP archive."""
    return header[:4] in _ZIP_SIGNATURES


def is_git_lfs_pointer(header: bytes) -> bool:
    """Whether *header* opens a Git LFS pointer: text standing in for a file
    not fetched, never a model whatever its suffix. The ``version`` line must
    be complete (``/spec/v1x`` is not one)."""
    return header.startswith(_GIT_LFS_OPENINGS)


def _looks_like_pytorch(header: bytes) -> bool:
    """Whether *header* opens a ZIP archive or a protocol 2..5 pickle.

    A ``.pth`` can also be a Python path-configuration file (plain text).
    """
    return _is_zip(header) or (
        len(header) >= 2
        and header[0] == _PICKLE_PROTO_OPCODE
        and header[1] in _PICKLE_PROTOCOLS
    )


def _any(_header: bytes) -> bool:
    """A suffix whose format has no signature at offset 0."""
    return True


# Suffix -> whether a non-empty header without a magic match still admits the
# format. A suffix absent here (``.gguf``, ``.ftz``, ``.npy``,
# ``.safetensors``) needs its magic (or the Safetensors heuristic in
# _match_magic). ONNX (protobuf) has no signature; HDF5 may start with a
# userblock, which moves its signature to 512, 1024, ... bytes.
_EXTENSION_ADMITS: dict[str, Callable[[bytes], bool]] = {
    ".keras": _is_zip,
    ".pt2": _is_zip,
    ".npz": _is_zip,
    ".pt": _looks_like_pytorch,
    ".pth": _looks_like_pytorch,
    ".onnx": _any,
    ".h5": _any,
    ".hdf5": _any,
}


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


def detect_ai_model_format_from_name(name: str) -> AiModelFormat:
    """Detect a model format from the suffix of *name* alone.

    For a file whose bytes cannot be read. Case-insensitive; *name* is a file
    name or POSIX archive name, and only its suffix is used.
    """
    return _EXTENSION_TO_FORMAT.get(
        PurePosixPath(name).suffix.lower(), AiModelFormat.UNKNOWN
    )


def detect_ai_model_format_from_header(header: bytes, name: str) -> AiModelFormat:
    """Detect a model format from its leading bytes and its file name.

    A file is a model of the format its header proves, or of the format its
    suffix names when the header does not contradict it. In order:

    1. **Magic bytes** - match *header* against known signatures from
       :class:`AiModelFormat` members.  This is reliable even when the file
       extension is wrong or absent.
    2. **File extension** - a case-insensitive suffix lookup of *name*,
       admitted by a header check per suffix: ZIP formats (``.keras``,
       ``.pt2``, ``.npz``) need a ZIP header, PyTorch (``.pt``, ``.pth``) a
       ZIP header or a protocol 2..5 pickle (``.pth`` is also the suffix of
       Python path-configuration files), ONNX and HDF5 any non-empty header
       (no signature at offset 0). A suffix whose format has a magic
       (GGUF, fastText ``.ftz``, NumPy ``.npy``, Safetensors) is not a
       model without it: a Git LFS pointer is text.

    An empty *header* (an absent, empty or non-regular file) and a Git LFS
    pointer (see :func:`is_git_lfs_pointer`) are never a model, whatever the
    suffix.

    Args:
        header: Up to :data:`SNIFF_BYTES` leading bytes of the file.
        name: A file name or POSIX archive name; only its suffix is used.

    Returns:
        Detected :class:`AiModelFormat`, or :attr:`AiModelFormat.UNKNOWN`.
    """
    if is_git_lfs_pointer(header):
        return AiModelFormat.UNKNOWN
    fmt = _match_magic(header)
    if fmt != AiModelFormat.UNKNOWN or not header:
        return fmt
    admits = _EXTENSION_ADMITS.get(PurePosixPath(name).suffix.lower())
    if admits is not None and admits(header):
        return detect_ai_model_format_from_name(name)
    return AiModelFormat.UNKNOWN


def contradicted_format(header: bytes, name: str) -> AiModelFormat | None:
    """The format the suffix of *name* names when *header* contradicts it.

    ``None`` when the header is empty, the suffix names no format, the file
    is a model (of any format), or the suffix has a legitimate non-model use
    (``.pt``, ``.pth``: path-configuration text), unless the header is a Git
    LFS pointer, which no suffix excuses. For a pointer named ``x.gguf``,
    ``GGUF``.
    """
    named = detect_ai_model_format_from_name(name)
    if not header or named == AiModelFormat.UNKNOWN:
        return None
    if is_git_lfs_pointer(header):
        return named
    if (
        named == AiModelFormat.PYTORCH
        or detect_ai_model_format_from_header(header, name) != AiModelFormat.UNKNOWN
    ):
        return None
    return named


#: What a refused file with no more specific reason is said to be.
NOT_A_MODEL_MESSAGE = "not an AI model file of a supported format"


def not_a_model_reason(header: bytes, name: str) -> str | None:
    """Why *header* and the suffix of *name* make the file not a model, when
    they contradict each other: ``header is a Git LFS pointer`` or ``header
    is not <format>``; ``None`` otherwise (see :func:`contradicted_format`)."""
    if is_git_lfs_pointer(header):
        return "header is a Git LFS pointer"
    named = contradicted_format(header, name)
    return None if named is None else f"header is not {named}"


def refusal_reason(header: bytes, name: str, *, is_file: bool) -> str | None:
    """Why a file is not read as a model, in the words every surface uses: the
    reason of :func:`not_a_model_reason`, or ``file is empty`` for an empty
    regular file whose suffix names a format; ``None`` when there is no
    specific reason (the caller words that)."""
    reason = not_a_model_reason(header, name)
    if reason is None and is_file and not header:
        if detect_ai_model_format_from_name(name) != AiModelFormat.UNKNOWN:
            reason = "file is empty"
    return reason


class NotAModel(Exception):
    """Raised by ``pitloom.extract.scanner.read_model_candidate`` for a file
    that is not a model.

    Attributes:
        model_format: The format the file's suffix names when its header
            contradicts it (a Git LFS pointer named ``x.gguf``); ``None``
            when the suffix names none (a pointer named ``x.bin``) or the
            file is simply not a model.
        reason: ``header is not <model_format>`` or ``header is a Git LFS
            pointer`` (:func:`not_a_model_reason`),
            which merit a warning; ``None`` for a file that is empty, absent or
            of an unknown format, which does not.
        message: The text of the exception, which every surface that refuses
            the file prints (:func:`refusal_reason`,
            else ``not an AI model file of a supported format``).
    """

    def __init__(
        self,
        model_format: AiModelFormat | None = None,
        reason: str | None = None,
        message: str | None = None,
    ) -> None:
        self.model_format = model_format
        self.reason = reason
        super().__init__(message or reason or NOT_A_MODEL_MESSAGE)


def detect_ai_model_format(model_path: Path) -> AiModelFormat:
    """Detect the format of an AI model file.

    Magic bytes first, then the file extension; see
    :func:`detect_ai_model_format_from_header`. Never raises on an
    unreadable file: a file that is absent, not a regular file or cannot be
    read falls back to the extension alone, as ``read_ai_model`` reports
    absence itself.
    """
    try:
        header = read_ai_model_header(model_path)
    except OSError:
        return detect_ai_model_format_from_name(model_path.name)
    if not header and not os.path.isfile(model_path):
        return detect_ai_model_format_from_name(model_path.name)
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
        ImportError: If the format's optional library is not installed.
        pitloom.extract.ai_model.limits.ModelLimitExceeded: The file is over
            a bound.
    """
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    if not os.path.isfile(model_path):
        raise ValueError(f"{model_path}: {NOT_A_MODEL_MESSAGE}")

    if model_format is None:
        model_format = detect_ai_model_format(model_path)
    reader = _READERS.get(model_format)
    if reader is None:
        raise ValueError(_unsupported_message(model_path))
    return reader(model_path)


def _unsupported_message(model_path: Path) -> str:
    """Why *model_path* is not read: :func:`refusal_reason`, else its suffix
    is not a supported one."""
    try:
        header = read_ai_model_header(model_path)
    except OSError:
        header = b""
    reason = refusal_reason(header, model_path.name, is_file=True)
    if reason is not None:
        return f"{model_path}: {reason}"
    return (
        f"Unsupported model format for file: {model_path}. "
        f"Supported extensions: {', '.join(_EXTENSION_TO_FORMAT)}"
    )
