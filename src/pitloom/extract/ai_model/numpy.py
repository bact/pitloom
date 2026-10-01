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
from pathlib import Path
from typing import IO, Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.extract.ai_model.archive_member import open_model_binary
from pitloom.extract.ai_model.limits import MAX_MODEL_ENTRIES, ModelLimitExceeded
from pitloom.extract.ai_model.reader_requirements import require_library
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

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
        raise ModelLimitExceeded(
            f".npy header of {length} bytes, over {_MAX_NPY_HEADER_BYTES}"
        )
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
        raise ValueError(f"Not a valid .npy file: {model_path}")
    return header[6], header[7]


def _read_npy_metadata(
    model_path: Path, source: str
) -> tuple[str, dict[str, str], list[dict[str, Any]], dict[str, str]]:
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
    # inputs is always a single-element literal, so provenance["inputs"] is
    # always set below -- unlike _read_npz_metadata's genuinely conditional
    # equivalent, which is built via a loop and can be empty.
    inputs = [{"shape": list(arr.shape), "dtype": str(arr.dtype)}]
    provenance["inputs"] = f"{source} | Field: .npy header (shape, dtype)"
    # np.memmap has no close() of its own -- drop the only reference now
    # that shape/dtype are copied out, so the mapped file handle is
    # released deterministically here rather than implicitly whenever the
    # interpreter next collects this function's frame.
    del arr

    return format_version, properties, inputs, provenance


def _shim_read_array_header(
    fp: Any, version: tuple[int, int]
) -> tuple[tuple[int, ...], bool, Any]:
    """Shim for reading numpy array headers across numpy 1.x and 2.x."""
    # pylint: disable=import-outside-toplevel
    import numpy.lib.format as fmt

    if hasattr(fmt, "_read_array_header"):
        return fmt._read_array_header(fp, version)  # type: ignore
    if version == (1, 0):
        return fmt.read_array_header_1_0(fp)  # type: ignore
    if version == (2, 0):
        return fmt.read_array_header_2_0(fp)  # type: ignore

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
    header = fp.read(header_length).decode("utf-8")
    d = ast.literal_eval(header)
    return (
        d["shape"],
        d["fortran_order"],
        fmt.descr_to_dtype(d["descr"]),  # type: ignore[no-untyped-call]
    )


def _read_npz_metadata(
    model_path: Path, source: str
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Helper to read .npz format metadata."""
    # pylint: disable=import-outside-toplevel
    import numpy as np

    # pylint: disable=import-outside-toplevel
    from numpy.lib.format import read_magic

    inputs: list[dict[str, Any]] = []
    provenance: dict[str, str] = {}
    # np.load reads the handle that was checked and leaves it open.
    with (
        open_model_binary(model_path) as fh,
        np.load(fh, allow_pickle=False) as npzfile,
    ):
        for archive_name in npzfile.zip.namelist():
            if len(inputs) > MAX_MODEL_ENTRIES:
                # One past the cap, so the scanner's cap_entries sees the
                # list was longer, cuts it to the cap and warns.
                break
            if not archive_name.endswith(".npy"):
                continue
            array_name = archive_name[:-4]
            with npzfile.zip.open(archive_name) as f:
                version = read_magic(f)  # type: ignore[no-untyped-call]
                header = _bounded_header(f, version[0])
                shape, _, dtype = _shim_read_array_header(header, version)
                inputs.append(
                    {
                        "name": array_name,
                        "shape": list(shape),
                        "dtype": str(dtype),
                    }
                )
    if inputs:
        provenance["inputs"] = f"{source} | Field: array names, shapes, dtypes"

    return inputs, provenance


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
    is never loaded.  For ``.npz`` archives each constituent array's shape
    and dtype are listed as :attr:`~AiModelMetadata.inputs` entries; per-array
    NPY version is not surfaced for ``.npz`` files.

    Neither format embeds a model name, description, or training
    configuration, so :attr:`~AiModelMetadata.name`,
    :attr:`~AiModelMetadata.description`, and
    :attr:`~AiModelMetadata.version` are always ``None``.

    Args:
        model_path: Path to a ``.npy`` or ``.npz`` file.

    Returns:
        AiModelMetadata with shape/dtype information in
        :attr:`~AiModelMetadata.inputs`.

    Raises:
        ImportError: If ``numpy`` is not installed.
        ValueError: If the file cannot be read as a valid NumPy file.
    """
    require_library(AiModelFormat.NUMPY)

    source = f"Source: {sanitize_provenance_text(model_path.name)}"
    format_version: str | None = None
    properties: dict[str, str] = {}
    inputs: list[dict[str, Any]] = []
    provenance: dict[str, str] = {}

    kind = _detect_numpy_kind(model_path)
    try:
        if kind == "npy":
            format_version, properties, inputs, provenance = _read_npy_metadata(
                model_path, source
            )
        elif kind == "npz":
            inputs, provenance = _read_npz_metadata(model_path, source)
    except ModelLimitExceeded:
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.debug(
            "Failed to read NumPy file %s: %s",
            loggable(str(model_path)),
            loggable(str(exc)),
        )
        raise ValueError(f"Failed to read NumPy file {model_path}: {exc}") from exc

    provenance["type_of_model"] = f"{source} | Field: format type"

    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.NUMPY,
            format_version=format_version,
            framework="numpy",
        ),
        type_of_model="numpy array",
        inputs=inputs,
        properties=properties,
        provenance=provenance,
    )
