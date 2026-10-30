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

from pitloom.messages import _file_unreadable, _lfs_pointer, _model_stub, _over_cap
from pitloom.messages._types import Message


def _by_code(entries: Iterable[Message]) -> Mapping[str, Message]:
    """*entries* keyed by code, read-only.

    Raises:
        ValueError: Two entries share a code, or two of one family name
            different conditions (a variant never changes the condition).
    """
    found: dict[str, Message] = {}
    conditions: dict[str, str] = {}
    for entry in entries:
        if entry.code in found:
            raise ValueError(f"message code {entry.code!r} is catalogued twice")
        held = conditions.setdefault(entry.family, entry.condition)
        if held != entry.condition:
            raise ValueError(
                f"{entry.code}: condition {entry.condition!r}, its family's is {held!r}"
            )
        found[entry.code] = entry
    return MappingProxyType(found)


#: Every catalogued message, by code.
MESSAGES: Final = _by_code(
    (
        *_lfs_pointer.ENTRIES,
        *_over_cap.ENTRIES,
        *_model_stub.ENTRIES,
        *_file_unreadable.ENTRIES,
    )
)
