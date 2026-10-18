# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read the SHA-256 and SHA-512 digests off an SPDX 3 element.

See also: :mod:`pitloom.export.spdx3_json` (``sha256_hash``,
``sha512_hash`` and ``file_hashes``, its builder counterparts).
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.file_hash import HexDigests

__all__ = ["file_digests_of", "sha256_of"]


def _hash_of(obj: object, algorithm: str) -> str | None:
    """The first non-empty *algorithm* ``Hash`` value of *obj*'s
    ``verifiedUsing``, lowercased; ``None`` when there is none."""
    for h in getattr(obj, "verifiedUsing", None) or []:
        if getattr(h, "algorithm", None) == algorithm:
            value = getattr(h, "hashValue", None)
            if value:
                return str(value).lower()
    return None


def sha256_of(obj: object) -> str | None:
    """Return the lowercase SHA-256 hex digest from *obj*'s ``verifiedUsing``.

    The first ``sha256`` ``Hash`` with a non-empty value wins; ``None`` when
    there is none. Lowercased so the same bytes compare equal however a
    producer spelled the digest.
    """
    return _hash_of(obj, spdx3.HashAlgorithm.sha256)


def file_digests_of(obj: object) -> HexDigests | None:
    """*obj*'s SHA-256 and SHA-512 (``None`` when it states none), read as
    :func:`sha256_of` reads the first; ``None`` without a SHA-256."""
    sha256 = sha256_of(obj)
    if sha256 is None:
        return None
    return HexDigests(sha256, _hash_of(obj, spdx3.HashAlgorithm.sha512))
