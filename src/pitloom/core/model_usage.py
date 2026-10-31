# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How a Python file uses an AI model file: the access the usage scan found.

The access is what the code does with the model's path, read from the syntax
tree. It is not an intention: opening a file for writing says nothing about
whether that happens in training or in development, so every usage is recorded
with the same lifecycle scope.

See also: :mod:`pitloom.extract._usage_ast` (the scan that finds it),
:mod:`pitloom.extract._usage_table` (the calls it recognises) and
:func:`pitloom.assemble.spdx3.ai._add_ai_model_file_relationships` (where the
text becomes the relationship's comment).
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass

from pitloom.core.internal_error import InternalError

__all__ = ["ModelUsage", "UsageAccess", "combine_access", "merge_usages"]


class UsageAccess(enum.Enum):
    """What a file does with a model file; the value is the relationship's
    comment, a fixed vocabulary a consumer can match."""

    READ = "read access"
    WRITE = "write access"
    READ_WRITE = "read and write access"
    UNKNOWN = "unknown access"


@dataclass(frozen=True)
class ModelUsage:
    """One Python file's use of one model file.

    Attributes:
        distribution_path: The distribution path of the ``.py`` file.
        access: What it does with the model file.
    """

    distribution_path: str
    access: UsageAccess = UsageAccess.UNKNOWN


def combine_access(accesses: Iterable[UsageAccess]) -> UsageAccess:
    """One file's accesses to one model as a single access.

    A read and a write are a read and a write. ``unknown`` only stands when
    nothing is classified: a file that is known to read a model does not also
    "unknown-access" it.

    Raises:
        pitloom.core.internal_error.InternalError: *accesses* is empty.
    """
    found = set(accesses)
    if not found:
        raise InternalError("no access to combine")
    if (
        UsageAccess.READ_WRITE in found
        or {
            UsageAccess.READ,
            UsageAccess.WRITE,
        }
        <= found
    ):
        return UsageAccess.READ_WRITE
    found.discard(UsageAccess.UNKNOWN)
    return next(iter(found), UsageAccess.UNKNOWN)


def merge_usages(usages: Iterable[ModelUsage]) -> list[ModelUsage]:
    """*usages* with one entry per file, its accesses combined
    (:func:`combine_access`), sorted by distribution path (plain string
    order, as the scanner sorts its sources)."""
    by_path: dict[str, list[UsageAccess]] = {}
    for usage in usages:
        by_path.setdefault(usage.distribution_path, []).append(usage.access)
    return [
        ModelUsage(path, combine_access(accesses))
        for path, accesses in sorted(by_path.items())
    ]
