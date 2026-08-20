# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for NumPy header parsing, format versions, and array shim edge cases.

See also:
- :mod:`tests.extract.test_numpy` for core NumPy .npy/.npz integration tests.
"""

from __future__ import annotations

import io
import struct
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract._numpy import _shim_read_array_header, read_numpy


def test_shim_read_array_header_fallbacks() -> None:
    """_shim_read_array_header executes fallbacks when _read_array_header is absent."""
    import numpy.lib.format as fmt  # pylint: disable=import-outside-toplevel

    orig_fn = getattr(fmt, "_read_array_header", None)
    if orig_fn is not None:
        delattr(fmt, "_read_array_header")

    try:
        # 1. Version (1, 0)
        mock_1_0 = MagicMock(return_value=((2, 2), False, "float32"))
        with patch.object(fmt, "read_array_header_1_0", mock_1_0):
            res1 = _shim_read_array_header(io.BytesIO(b""), (1, 0))
            assert res1[0] == (2, 2)

        # 2. Version (2, 0)
        mock_2_0 = MagicMock(return_value=((4, 4), True, "int32"))
        with patch.object(fmt, "read_array_header_2_0", mock_2_0):
            res2 = _shim_read_array_header(io.BytesIO(b""), (2, 0))
            assert res2[0] == (4, 4)

        # 3. Version (3, 0) custom header parsing
        header_dict_str = (
            "{'descr': '<f4', 'fortran_order': False, 'shape': (10, 20), }"
        )
        header_bytes = header_dict_str.encode("utf-8")
        header_len = len(header_bytes)
        payload = struct.pack("<I", header_len) + header_bytes
        shape, fortran_order, dtype = _shim_read_array_header(
            io.BytesIO(payload), (3, 0)
        )
        assert shape == (10, 20)
        assert fortran_order is False
        assert str(dtype) == "float32"
    finally:
        if orig_fn is not None:
            fmt._read_array_header = orig_fn  # type: ignore[attr-defined]


def test_read_numpy_npz_skips_non_npy_archive_members() -> None:
    """read_numpy with .npz skips archive members not ending with .npy."""
    with tempfile.NamedTemporaryFile(suffix=".npz", delete=False) as f:
        npz_path = Path(f.name)

    try:
        with zipfile.ZipFile(npz_path, "w") as zf:
            zf.writestr("README.txt", "This is a metadata text file.")
            # Put a valid minimal npy array inside
            import numpy as np  # pylint: disable=import-outside-toplevel

            arr_bytes = io.BytesIO()
            np.save(arr_bytes, np.zeros((2, 2)))
            zf.writestr("weights.npy", arr_bytes.getvalue())

        meta = read_numpy(npz_path)
        assert meta.format_info.model_format == AiModelFormat.NUMPY
        # Only the weights array is extracted as input
        assert len(meta.inputs or []) == 1
        assert meta.inputs[0]["name"] == "weights"
    finally:
        npz_path.unlink(missing_ok=True)


def test_read_numpy_unrecognized_suffix_returns_empty_format_version() -> None:
    """read_numpy on a path without .npy/.npz extension handles metadata gracefully."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        bin_path = Path(f.name)

    try:
        meta = read_numpy(bin_path)
        assert meta.format_info.model_format == AiModelFormat.NUMPY
        assert meta.format_info.format_version is None
    finally:
        bin_path.unlink(missing_ok=True)
