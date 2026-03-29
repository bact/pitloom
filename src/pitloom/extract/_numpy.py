# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""NumPy array file metadata extractor.

References:
    - https://numpy.org/neps/nep-0001-npy-format.html
    - https://numpy.org/doc/stable/reference/generated/numpy.lib.format.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata

# Maps NPY format major version → header encoding.
#   Version 1.x: 2-byte LE uint16 header-length field, latin1 encoding.
#   Version 2.x: 4-byte LE uint32 header-length field, latin1 encoding.
#   Version 3.x: 4-byte LE uint32 header-length field, UTF-8 encoding.
# Unknown future versions default to utf-8 (the newer, stricter encoding).
_NPY_HEADER_ENCODING: dict[int, str] = {1: "latin1", 2: "latin1", 3: "utf-8"}


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


def read_numpy(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a NumPy array file (``.npy`` or ``.npz``).

    Requires the ``numpy`` package (``pip install numpy``).

    For ``.npy`` files the format version is read directly from the file
    header bytes 6-7 and stored in ``properties``:

    - **Version 1.x** — 2-byte header-length field, latin1-encoded header.
    - **Version 2.x** — 4-byte header-length field, latin1-encoded header.
    - **Version 3.x** — 4-byte header-length field, UTF-8-encoded header.

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
    try:
        import numpy as np  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "The 'numpy' package is required to extract NumPy model metadata. "
            "Install it with: pip install numpy"
        ) from exc

    source = f"Source: {model_path.name}"
    framework = "numpy"
    format_version: str | None = None
    properties: dict[str, str] = {}
    inputs: list[dict[str, Any]] = []
    provenance: dict[str, str] = {}

    suffix = model_path.suffix.lower()

    try:
        if suffix == ".npy":
            major, minor = _read_npy_version(model_path)
            fmt_version = f"{major}.{minor}"
            format_version = fmt_version
            encoding = _NPY_HEADER_ENCODING.get(major, "utf-8")
            properties["header_encoding"] = encoding
            provenance["format_version"] = (
                f"{source} | Field: .npy format header version (bytes 6-7)"
            )
            provenance["properties"] = (
                f"{source} | Field: .npy format header version (bytes 6-7)"
            )
            # mmap_mode='r' reads shape/dtype from header without loading
            # the full tensor data into memory.
            arr = np.load(str(model_path), mmap_mode="r", allow_pickle=False)
            inputs = [{"shape": list(arr.shape), "dtype": str(arr.dtype)}]
            if inputs:
                provenance["inputs"] = f"{source} | Field: .npy header (shape, dtype)"
        elif suffix == ".npz":
            with np.load(str(model_path), allow_pickle=False) as npzfile:
                for array_name in npzfile.files:
                    arr = npzfile[array_name]
                    inputs.append(
                        {
                            "name": array_name,
                            "shape": list(arr.shape),
                            "dtype": str(arr.dtype),
                        }
                    )
            if inputs:
                provenance["inputs"] = f"{source} | Fields: array names, shapes, dtypes"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(f"Failed to read NumPy file {model_path}: {exc}") from exc

    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.NUMPY,
            format_version=format_version,
            framework=framework,
        ),
        type_of_model="numpy array",
        inputs=inputs,
        properties=properties,
        provenance=provenance,
    )
