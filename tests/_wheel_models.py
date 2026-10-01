# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel carrying AI model files under exact raw member names, for the
wheel model scan tests.

See also: tests/_raw_archive.py (the raw-name writer),
tests/extract/scanner/test_scanner_wheel.py and
tests/assemble/test_scan_model_usage_wheel.py (the users).
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from tests._raw_archive import write_raw_zip


def safetensors_bytes(extra: int = 0, metadata: dict[str, str] | None = None) -> bytes:
    """A valid one-tensor Safetensors file of ``1 + extra`` float32 values,
    with the free-form ``__metadata__`` table *metadata* when given."""
    size = 4 * (1 + extra)
    table: dict[str, object] = {
        "t": {"dtype": "F32", "shape": [1 + extra], "data_offsets": [0, size]}
    }
    if metadata is not None:
        table["__metadata__"] = metadata
    header = json.dumps(table).encode()
    return struct.pack("<Q", len(header)) + header + b"\0" * size


def write_model_wheel(
    directory: Path,
    members: dict[str, bytes],
    name: str = "demo",
    version: str = "1.0.0",
) -> Path:
    """A wheel of *members* (raw arcname -> bytes) plus its ``.dist-info``."""
    directory.mkdir(parents=True, exist_ok=True)
    dist_info = f"{name}-{version}.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()
    return write_raw_zip(
        directory / f"{name}-{version}-py3-none-any.whl",
        {
            **members,
            f"{dist_info}/METADATA": metadata,
            f"{dist_info}/RECORD": b"",
        },
    )
