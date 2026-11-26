# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom's adapter to the GGUF header reader
(:mod:`pitloom.extract.ai_model.formats.gguf_header`).

:func:`load_gguf_header` maps the file, reads its pairs and tensor infos
under :data:`GGUF_LIMITS`, and turns the reader's failures into Pitloom's: a
count beyond the file or a version the ``gguf`` package reads and the
reader does not is a :class:`~pitloom.extract.ai_model.limits.ModelLimitExceeded`
(``model-unreadable``); anything else malformed is a :class:`ValueError`. It
also refuses a tensor whose data runs past the end of the file, as the
``gguf`` package's reader does, for every tensor type that package knows.
A bound reached is no failure: the header comes back read in part, and
:func:`stop_cap` names the cap for the ``over-cap`` warning.

See also: :mod:`pitloom.extract.ai_model.gguf`.
"""

from __future__ import annotations

import mmap
import os
from pathlib import Path

from pitloom.core.ai_metadata import model_cap
from pitloom.core.internal_error import reraise_internal
from pitloom.extract.ai_model.formats import FormatError, Limits
from pitloom.extract.ai_model.formats.gguf_header import (
    DeclaredBeyondFile,
    GgufHeader,
    GgufStop,
    GgufTensor,
    UnknownVersion,
    read_gguf_header,
)
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from pitloom.messages.files import Cap
from pitloom.messages.models import (
    LIMIT_GGUF_ARRAY,
    LIMIT_GGUF_PAIRS,
    LIMIT_GGUF_TENSORS,
    LIMIT_GGUF_VERSION,
)

#: The bounds of a GGUF header read (the defaults of
#: :class:`~pitloom.extract.ai_model.formats.Limits`).
GGUF_LIMITS = Limits()

# The cap each bound is said as: unit and name.
_CAPS = {
    "max_gguf_parsed": ("unit", "GGUF-header"),
    "max_gguf_skipped_elements": ("element", "GGUF-skipped-element"),
    "max_gguf_string_bytes": ("byte", "GGUF-string"),
    "max_gguf_total_string_bytes": ("byte", "GGUF-strings"),
    "max_gguf_nesting": ("level", "GGUF-array-nesting"),
}


def _reader_accepts(version: int) -> bool:
    """Whether the ``gguf`` package reads *version*; ``True`` when that
    cannot be told, so that an unknown version is refused as unbounded."""
    try:
        # pylint: disable-next=import-outside-toplevel
        from gguf.gguf_reader import READER_SUPPORTED_VERSIONS
    except ImportError:
        return True
    return version in READER_SUPPORTED_VERSIONS


def stop_cap(stop: GgufStop) -> Cap:
    """The cap a partial read's *stop* is said as."""
    unit, purpose = _CAPS[stop.bound]
    return model_cap(Cap(stop.limit, unit, purpose), "gguf")


def _check_tensor_data(tensors: tuple[GgufTensor, ...], start: int, size: int) -> None:
    """Refuse a tensor whose data runs past *size*, or a quantised tensor
    whose row is no whole number of blocks; a type ``gguf`` does not know
    is not sized.

    Raises:
        ValueError: One such tensor.
    """
    # pylint: disable-next=import-outside-toplevel
    from gguf.constants import GGML_QUANT_SIZES, GGMLQuantizationType

    for tensor in tensors:
        try:
            block, type_size = GGML_QUANT_SIZES[GGMLQuantizationType(tensor.ggml_type)]
        except (ValueError, KeyError) as exc:
            reraise_internal(exc)
            continue
        if block > 1 and tensor.shape and tensor.shape[0] % block:
            raise ValueError(
                f"tensor {tensor.name!r} row of {tensor.shape[0]} is no whole "
                f"number of {block}-element blocks"
            )
        room = size - start - tensor.offset
        if room < 0 or not tensor_fits(
            tensor.shape, ((room + 1) * block - 1) // type_size
        ):
            raise ValueError(f"tensor {tensor.name!r} data runs past the end")


def tensor_fits(shape: tuple[int, ...], most: int) -> bool:
    """Whether a tensor of *shape* has at most *most* elements, the product
    stopped once past it (a declared dimension is any 64-bit number)."""
    if 0 in shape:
        return True
    elements = 1
    for dim in shape:
        elements *= dim
        if elements > most:
            return False
    return elements <= most  # a scalar, ``()``: one element


def _read(data: bytes | mmap.mmap, keep: dict[str, int]) -> GgufHeader:
    try:
        header = read_gguf_header(data, GGUF_LIMITS, keep)
    except DeclaredBeyondFile as exc:
        if exc.what == "tensors":
            raise ModelLimitExceeded(LIMIT_GGUF_TENSORS % exc.count) from exc
        if exc.what == "pairs":
            raise ModelLimitExceeded(LIMIT_GGUF_PAIRS % exc.count) from exc
        raise ModelLimitExceeded(LIMIT_GGUF_ARRAY % exc.count) from exc
    except UnknownVersion as exc:
        if _reader_accepts(exc.version):
            raise ModelLimitExceeded(LIMIT_GGUF_VERSION % exc.version) from exc
        raise ValueError(exc.reason) from exc
    except FormatError as exc:
        raise ValueError(exc.reason) from exc
    if header.tensors is not None and header.data_offset is not None:
        _check_tensor_data(header.tensors, header.data_offset, len(data))
    return header


def load_gguf_header(path: Path, keep: dict[str, int]) -> GgufHeader:
    """The header of the GGUF file at *path*, read in part when a bound
    stops the walk (:attr:`GgufHeader.stop`).

    Args:
        path: The file.
        keep: For each key whose string elements the caller needs, how
            many to parse.

    Raises:
        ModelLimitExceeded: A count beyond the file, or a version the
            ``gguf`` package reads and the header reader does not.
        ValueError: Not a GGUF file, or a malformed one.
        OSError: The file cannot be read.
    """
    with path.open("rb") as fh:
        if not os.fstat(fh.fileno()).st_size:
            return _read(b"", keep)
        with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return _read(data, keep)
