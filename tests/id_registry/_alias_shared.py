# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A registry table that fails any whole-table walk, to prove a lookup
stays one dictionary access per candidate.

See also: test_keys_alias.py, test_session_alias.py (its users).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pitloom.id_registry import RegistryEntry

_Key = tuple[str, str]

SCANNED = "the registry table was scanned"


class NoScanTable(dict[_Key, RegistryEntry]):
    """``IdRegistry.elements`` that raises on iteration and on every
    whole-table view; ``get`` and ``in`` still work. Never annotated
    ``NoReturn``: linters infer the shared table's type from this
    assignment, and would call code after any walk unreachable."""

    def __iter__(self) -> Iterator[_Key]:
        raise AssertionError(SCANNED)

    def items(self) -> Any:
        raise AssertionError(SCANNED)

    def values(self) -> Any:
        raise AssertionError(SCANNED)

    def keys(self) -> Any:
        raise AssertionError(SCANNED)
