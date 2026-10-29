# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Git LFS pointer bytes for tests, with a real ``oid`` and ``size``.

See also: ``tests/fixtures/lfs-pointers/`` (real pointers from the Hub).
"""

from __future__ import annotations

import hashlib

#: The spec URL git-lfs writes today.
LFS_SPEC_URL = "https://git-lfs.github.com/spec/v1"


def lfs_pointer_bytes(
    content: bytes = b"x",
    *,
    eol: str = "\n",
    url: str = LFS_SPEC_URL,
    trailing_newline: bool = True,
) -> bytes:
    """The pointer git-lfs would write for *content* (its SHA-256 and
    length), with lines ending in *eol*, under the spec *url*."""
    lines = [
        f"version {url}",
        f"oid sha256:{hashlib.sha256(content).hexdigest()}",
        f"size {len(content)}",
    ]
    return (eol.join(lines) + (eol if trailing_newline else "")).encode("ascii")
