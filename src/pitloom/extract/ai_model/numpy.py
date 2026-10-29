# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""NumPy array file metadata extractor.

References:
    - https://numpy.org/neps/nep-0001-npy-format.html
    - https://numpy.org/doc/stable/reference/generated/numpy.lib.format.html
"""

# pylint: disable=protected-access

from __future__ import annotations

import io
import logging
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any, cast

from pitloom.core.ai_metadata import (
    MAX_MODEL_ENTRIES,
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    source_metadata,
)
from pitloom.core.provenance import sanitize_provenance_text
from pitloom.core.quote_source import quote_source
from pitloom.extract.ai_model.archive_member import open_model_binary
from pitloom.extract.ai_model.limits import ModelLimitExceeded, ModelOverCap
from pitloom.extract.ai_model.reader_requirements import require_library
from pitloom.logging_config import Cap, loggable

log = logging.getLogger(__name__)

#: What numpy's header readers return: shape, Fortran order, dtype.
_ArrayHeader = tuple[tuple[int, ...], bool, Any]

# Maps NPY format major version -> header encoding.
#   Version 1.x: 2-byte LE uint16 header-length field, latin1 encoding.
#   Version 2.x: 4-byte LE uint32 header-length field, latin1 encoding.
#   Version 3.x: 4-byte LE uint32 header-length field, UTF-8 encoding.
# Unknown future versions default to utf-8 (the newer, stricter encoding).
_NPY_HEADER_ENCODING: dict[int, str] = {1: "latin1", 2: "latin1", 3: "utf-8"}

# Largest header numpy itself accepts (its ``max_header_size`` default).
# numpy reads the declared number of header bytes before it checks that, so
# a 4 GiB declaration in a few compressed bytes is checked here first.
_MAX_NPY_HEADER_BYTES = 10000


def _bounded_header(fp: IO[bytes], major: int) -> IO[bytes]:
    """The header-length field and header of the array at *fp* (just past
    the magic and version), as a stream numpy can parse.

    Raises:
        ModelLimitExceeded: The declared header is over
            :data:`_MAX_NPY_HEADER_BYTES`; nothing of it was read.
        ValueError: The length field is cut short.
    """
    width = 2 if major == 1 else 4
    prefix = fp.read(width)
    if len(prefix) < width:
        raise ValueError("truncated .npy header")
    length = int.from_bytes(prefix, "little")
    if length > _MAX_NPY_HEADER_BYTES:
        raise ModelOverCap(Cap(_MAX_NPY_HEADER_BYTES, "byte", ".npy-header"))
    return io.BytesIO(prefix + fp.read(length))


def _read_npy_version(model_path: Path) -> tuple[int, int]:
    """Read the NPY format version from bytes 6-7 of a ``.npy`` file.

    The ``.npy`` binary layout always starts with the 6-byte magic prefix
    ``b'\\x93NUMPY'`` followed immediately by one unsigned byte for the major
    version and one for the minor version.

    Args:
        model_path: Path to a ``.npy`` file.

    Returns:
        Tuple of ``(major, minor)`` version numbers (e.g. ``(1, 0)``).

    Raises:
        ValueError: If the file is shorter than 8 bytes or the magic prefix
            is absent.
    """
    with model_path.open("rb") as fh:
        header = fh.read(8)
    if len(header) < 8 or header[:6] != b"\x93NUMPY":
        raise ValueError(f"Not a valid .npy file: {quote_source(model_path)}")
    return header[6], header[7]


def _read_npy_metadata(
    model_path: Path, source: str
) -> tuple[str, dict[str, str], dict[str, str]]:
    """Helper to read .npy format metadata."""
    # pylint: disable=import-outside-toplevel
    import numpy as np

    major, minor = _read_npy_version(model_path)
    with model_path.open("rb") as fh:
        fh.seek(8)
        _bounded_header(fh, major)
    format_version = f"{major}.{minor}"
    encoding = _NPY_HEADER_ENCODING.get(major, "utf-8")
    properties = {"header_encoding": encoding}
    provenance = {
        "format_version": f"{source} | Field: .npy format header version (bytes 6-7)",
        "properties.header_encoding": (
            f"{source} | Field: .npy header encoding (from format version)"
        ),
    }
    # mmap_mode='r' reads shape/dtype from header without loading full tensor
    arr = np.load(str(model_path), mmap_mode="r", allow_pickle=False)
    # The array's shape and dtype are file properties, not model inputs.
    properties["array_shape"] = "x".join(map(str, arr.shape)) or "scalar"
    properties["array_dtype"] = str(arr.dtype)
    for key in ("array_shape", "array_dtype"):
        provenance[f"properties.{key}"] = f"{source} | Field: .npy header"
    # np.memmap has no close() of its own -- drop the only reference now
    # that shape/dtype are copied out, so the mapped file handle is
    # released deterministically here rather than implicitly whenever the
    # interpreter next collects this function's frame.
    del arr

    return format_version, properties, provenance


def _shim_read_array_header(fp: Any, version: tuple[int, int]) -> _ArrayHeader:
    """Shim for reading numpy array headers across numpy 1.x and 2.x."""
    # pylint: disable=import-outside-toplevel
    import numpy.lib.format as numpy_format

    # Untyped before numpy 2.5 and typed after: an ``Any`` view needs no
    # ``type: ignore`` that one of the two would call unused.
    fmt: Any = numpy_format
    if hasattr(fmt, "_read_array_header"):
        return cast(_ArrayHeader, fmt._read_array_header(fp, version))
    if version == (1, 0):
        return cast(_ArrayHeader, fmt.read_array_header_1_0(fp))
    if version == (2, 0):
        return cast(_ArrayHeader, fmt.read_array_header_2_0(fp))

    # Fallback for version (3, 0) on numpy >= 2.0 where _read_array_header is removed
    # and read_array_header_3_0 is not exposed.
    # (3, 0) uses 4-byte uint for length and utf-8.
    # Format specification:
    # https://numpy.org/doc/stable/reference/generated/numpy.lib.format.html
    # pylint: disable=import-outside-toplevel
    import ast

    # pylint: disable=import-outside-toplevel
    import struct

    hlength_str = fp.read(4)
    header_length = struct.unpack("<I", hlength_str)[0]
    text = fp.read(header_length).decode("utf-8")
    d = ast.literal_eval(text)
    return (d["shape"], d["fortran_order"], fmt.descr_to_dtype(d["descr"]))


def _read_npz_metadata(
    model_path: Path, source: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Helper to read .npz format metadata."""
    # pylint: disable=import-outside-toplevel
    import numpy as np

    # pylint: disable=import-outside-toplevel
    from numpy.lib.format import read_magic as numpy_read_magic

    read_magic: Callable[..., Any] = numpy_read_magic  # untyped before numpy 2.5

    # np.load reads the handle that was checked and leaves it open.
    with (
        open_model_binary(model_path) as fh,
        np.load(fh, allow_pickle=False) as npzfile,
    ):
        members = [n for n in npzfile.zip.namelist() if n.endswith(".npy")]
        # Headers are checked for the first members only, as the entry cap
        # bounded the work before.
        for archive_name in members[: MAX_MODEL_ENTRIES + 1]:
            with npzfile.zip.open(archive_name) as f:
                version = read_magic(f)
                header = _bounded_header(f, version[0])
                _shim_read_array_header(header, version)  # a bad header raises
    # The arrays are not model inputs: only their number is recorded.
    properties = {"array_count": str(len(members))}
    provenance = {"properties.array_count": f"{source} | Field: .npz archive members"}

    return properties, provenance


def _detect_numpy_kind(model_path: Path) -> str | None:
    """Detect whether file is a .npy file, .npz archive, or unrecognized."""
    try:
        with model_path.open("rb") as fh:
            magic = fh.read(8)
            if len(magic) >= 6 and magic[:6] == b"\x93NUMPY":
                return "npy"
    except OSError:
        pass

    try:
        if zipfile.is_zipfile(model_path):
            return "npz"
    except (OSError, zipfile.BadZipFile):
        pass

    suffix = model_path.suffix.lower()
    if suffix == ".npz":
        return "npz"
    if suffix == ".npy":
        return "npy"
    return None


def read_numpy(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a NumPy array file (``.npy`` or ``.npz``).

    Requires the ``numpy`` package (``pip install numpy``).

    For ``.npy`` files the format version is read directly from the file
    header bytes 6-7 and stored in ``properties``:

    - **Version 1.x** -- 2-byte header-length field, latin1-encoded header.
    - **Version 2.x** -- 4-byte header-length field, latin1-encoded header.
    - **Version 3.x** -- 4-byte header-length field, UTF-8-encoded header.

    Shape and dtype are extracted via memory-mapping so the full tensor data
    is never loaded.  An ``.npy`` file's shape and dtype are file
    ``properties`` (``array_shape``, ``array_dtype``); an ``.npz`` archive's
    array count is ``array_count``.  Arrays are weights or data, not model
    inputs, so :attr:`~AiModelMetadata.inputs` stays empty.  Per-array NPY
    version is not surfaced for ``.npz`` files.

    Neither format embeds a model name, description, or training
    configuration, so :attr:`~AiModelMetadata.name`,
    :attr:`~AiModelMetadata.description`, and
    :attr:`~AiModelMetadata.version` are always ``None``.

    Args:
        model_path: Path to a ``.npy`` or ``.npz`` file.

    Returns:
        AiModelMetadata with the array information in ``properties``.

    Raises:
        ImportError: If ``numpy`` is not installed.
        ValueError: If the file cannot be read as a valid NumPy file.
        pitloom.extract.ai_model.limits.ModelLimitExceeded: A header is over
            its bound.
    """
    require_library(AiModelFormat.NUMPY)

    source = f"Source: {sanitize_provenance_text(model_path.name)}"
    format_version: str | None = None
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    kind = _detect_numpy_kind(model_path)
    try:
        if kind == "npy":
            format_version, properties, provenance = _read_npy_metadata(
                model_path, source
            )
        elif kind == "npz":
            properties, provenance = _read_npz_metadata(model_path, source)
    except ModelLimitExceeded:
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.debug(
            "Failed to read NumPy file %s: %s",
            loggable(str(model_path)),
            loggable(str(exc)),
        )
        raise ValueError(
            f"Failed to read NumPy file {quote_source(model_path)}: {exc}"
        ) from exc

    provenance["type_of_model"] = f"{source} | Field: format type"
    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.NUMPY,
            format_version=format_version,
            framework="numpy",
        ),
        type_of_model="numpy array",
        properties=properties,
        **source_metadata(properties),
        provenance=provenance,
    )
