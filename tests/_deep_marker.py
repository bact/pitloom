# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Markers nesting deep, for the marker-nesting cap's tests.

See also: tests/core/test_pep508.py and tests/test_deep_marker_surfaces.py
(the users).
"""

from __future__ import annotations

#: The crafted requirement once crashing every route: ``packaging`` raised
#: ``RecursionError`` parsing it.
DEEP_REQUIREMENT = "a; " + "(" * 900 + 'python_version > "3"' + ")" * 900


def nested_marker(depth: int) -> str:
    """A marker really nesting *depth* levels: no parenthesis is redundant,
    so ``str(Marker(...))`` keeps them all."""
    marker = 'os_name == "a"'
    for _ in range(depth):
        marker = f'({marker} or os_name == "b") and os_name == "c"'
    return marker
