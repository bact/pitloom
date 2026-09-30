# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared raw-bytes JSON-file read.

See also: :mod:`pitloom._toml_io` (the TOML counterpart, same
"propagate exceptions, exception-handling policy stays with the caller"
shape), :mod:`pitloom.extract.lock._common` (``load_lock_json()``, for
lock files -- adds caching and a dict-shape check), and
:mod:`pitloom.extract._license_detect`
(``_read_license_from_codemeta_json()``, for ``codemeta.json``).
``pitloom.cli.commands.fragment`` needs the same raw-bytes-plus-parse
shape for SBOM fragment reads (a SHA-256 check alongside the JSON parse)
but does not call this helper -- it must preserve the raw bytes even when
the JSON parse itself fails, which this helper's "propagate on any
failure" contract doesn't allow for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["load_json_bytes"]


def load_json_bytes(path: Path) -> tuple[bytes, Any]:
    """Read *path*'s raw bytes and parse them as JSON.

    Returns ``(raw_bytes, parsed)``. Propagates ``OSError`` (including
    ``FileNotFoundError``), ``UnicodeDecodeError``, and
    ``json.JSONDecodeError`` to the caller -- callers decide how to log
    and what fallback to return for each, and may still need
    *raw_bytes* even when only the parse result matters (e.g. for a
    hash check alongside the JSON read).
    """
    raw = path.read_bytes()
    # json.loads(bytes), not raw.decode("utf-8") + json.loads(str): the
    # former auto-detects and strips a leading UTF-8 BOM, the latter
    # raises "Unexpected UTF-8 BOM" -- a BOM-prefixed but otherwise valid
    # file would otherwise fail here for no real reason.
    return raw, json.loads(raw)
