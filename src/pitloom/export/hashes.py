# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read the SHA-256 digest off an SPDX 3 element.

See also: :mod:`pitloom.export.spdx3_json` (``sha256_hash``, its builder counterpart).
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

__all__ = ["sha256_of"]


def sha256_of(obj: object) -> str | None:
    """Return the lowercase SHA-256 hex digest from *obj*'s ``verifiedUsing``.

    The first ``sha256`` ``Hash`` with a non-empty value wins; ``None`` when
    there is none. Lowercased so the same bytes compare equal however a
    producer spelled the digest.
    """
    for h in getattr(obj, "verifiedUsing", None) or []:
        if getattr(h, "algorithm", None) == spdx3.HashAlgorithm.sha256:
            value = getattr(h, "hashValue", None)
            if value:
                return str(value).lower()
    return None
