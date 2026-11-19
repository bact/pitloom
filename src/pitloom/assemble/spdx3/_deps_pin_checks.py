# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whether a locked version agrees with a dependency's declared constraint.

See also: :mod:`pitloom.assemble.spdx3.deps_installed`
(``_resolve_version`` and ``build_dependency_version_conflict``, the
callers).
"""

from __future__ import annotations

from packaging.requirements import Requirement

from pitloom.core.pep440 import specifier_contains
from pitloom.extract.lock.common import is_same_version


def is_exact_pin_conflict(
    req: Requirement | None, pinned: str, locked_version: str
) -> bool:
    """Return True if locked_version conflicts with declared exact pin."""
    if req is not None and req.specifier:
        contained = specifier_contains(req.specifier, locked_version)
        if contained is not None:
            return not contained
    return not is_same_version(locked_version, pinned)


def satisfies_constraint(req: Requirement | None, locked_version: str) -> bool | None:
    """Return whether locked_version satisfies req.specifier, or ``None``
    when that can't be determined at all (dep was unparseable, so its
    declared constraint -- if any -- is unknown, not merely absent)."""
    if req is None:
        return None
    if not req.specifier:
        return True
    return specifier_contains(req.specifier, locked_version) is True
