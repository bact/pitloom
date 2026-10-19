# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``verifiedUsing`` a file Pitloom read must carry, computed here with
:mod:`hashlib` alone (independently of :mod:`pitloom.core.file_hash`).

See also: tests/core/test_file_hash.py (the reader) and
tests/assemble/test_file_hashes.py (where each surface emits it).
"""

from __future__ import annotations

import hashlib
from typing import Any


def file_hashes_json(data: bytes) -> list[dict[str, str]]:
    """The serialised ``verifiedUsing`` of a file holding *data*: its
    SHA-256, then its SHA-512."""
    return [
        {"type": "Hash", "algorithm": "sha256", "hashValue": _hex("sha256", data)},
        {"type": "Hash", "algorithm": "sha512", "hashValue": _hex("sha512", data)},
    ]


def algorithms(element: dict[str, Any]) -> list[str]:
    """The ``algorithm`` of each of *element*'s ``verifiedUsing``, in order."""
    return [str(h["algorithm"]) for h in element.get("verifiedUsing", [])]


def _hex(algorithm: str, data: bytes) -> str:
    return hashlib.new(algorithm, data).hexdigest()
