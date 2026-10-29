# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every catalogued message, by code.

See also: :mod:`pitloom.messages` (the public names).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages import _lfs_pointer
from pitloom.messages._types import Message


def _by_code(entries: Iterable[Message]) -> Mapping[str, Message]:
    """*entries* keyed by code, read-only.

    Raises:
        ValueError: Two entries share a code.
    """
    found: dict[str, Message] = {}
    for entry in entries:
        if entry.code in found:
            raise ValueError(f"message code {entry.code!r} is catalogued twice")
        found[entry.code] = entry
    return MappingProxyType(found)


#: Every catalogued message, by code.
MESSAGES: Final = _by_code(_lfs_pointer.ENTRIES)
