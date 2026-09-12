# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Deterministic SHA-256 selection among an artifact's multiple hash
candidates.

Shared by :mod:`pitloom.assemble.spdx3.deps_pypi` (a PyPI JSON API
release's several ``urls[]`` entries) and every per-format lock-hash
extractor (:mod:`pitloom.extract._pylock_hashes`,
:mod:`pitloom.extract._uv_lock_hashes`,
:mod:`pitloom.extract._poetry_lock_hashes`,
:mod:`pitloom.extract._pdm_lock_hashes`,
:mod:`pitloom.extract._pipfile_lock_hashes`) so a package's selected
``verifiedUsing`` hash follows one tie-break rule regardless of which
source supplied it.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ["select_sha256_hash"]

_SHA256_HEX_LEN = 64
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _is_valid_sha256(digest: str) -> bool:
    return len(digest) == _SHA256_HEX_LEN and all(c in _HEX_DIGITS for c in digest)


def select_sha256_hash(candidates: Iterable[tuple[str | None, str]]) -> str | None:
    """Deterministically select one lowercase hex SHA-256 digest among
    *candidates*, each a ``(filename, digest)`` pair.

    *filename* is ``None`` when the source format doesn't associate one
    with its hash (e.g. ``Pipfile.lock``'s bare ``hashes`` list); a
    malformed (wrong-length or non-hex) *digest* is treated as absent,
    not an error -- a bad hash string in a lock file is a data-quality
    problem in that file, not something this selection step should raise
    on.

    A wheel artifact (filename ending ``.whl``) is preferred over any
    other artifact (typically an sdist); ties within a category are
    broken by sorting filenames, and a candidate with no filename at all
    is only used when no filenamed candidate exists, broken by sorting
    the raw digest strings themselves. This is a *stable, deterministic*
    tie-break, not a claim that the chosen artifact is somehow more
    correct than the others -- relying on whatever order a JSON/TOML
    source happens to list candidates in would make the choice depend on
    an ordering this repo has no contract with, violating the "SBOMs
    must be bit-for-bit identical" requirement.
    """
    valid = [
        (name, digest.lower())
        for name, digest in candidates
        if _is_valid_sha256(digest)
    ]
    if not valid:
        return None

    wheels = [c for c in valid if c[0] is not None and c[0].endswith(".whl")]
    if wheels:
        return min(wheels, key=lambda c: (c[0] or "", c[1]))[1]

    named = [c for c in valid if c[0] is not None]
    if named:
        return min(named, key=lambda c: (c[0] or "", c[1]))[1]

    return min(digest for _name, digest in valid)
