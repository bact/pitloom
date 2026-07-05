# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: CC0-1.0

"""Version source for the dynamic-version test fixture.

Deliberately computed rather than a literal string, so that a naive
text-only extraction of the assignment below cannot reproduce the real
value. Only Hatchling -- which imports this module and evaluates the
configured expression -- resolves the correct value.
"""

__version__ = "1.0." + str(2 + 3)
