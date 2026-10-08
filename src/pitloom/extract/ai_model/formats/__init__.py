# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Metadata-only readers for AI model file formats.

Reads the few header bytes that hold a model's metadata and nothing else,
under explicit :class:`Limits`. Standard library only, with no import from
the rest of Pitloom (a test enforces it), so the package can be lifted out
as it is. Inputs are bytes or binary file objects; outputs are plain
values; failures are :class:`FormatError` subclasses. No logging, no global
state.

Modules:

- :mod:`.crfsuite`: the header and label strings of a CRFsuite model.
- :mod:`.pickle_walk`: the opcodes of a pickle, without converting its
  decimal numbers.

See also: :mod:`pitloom.extract.ai_model._pickle_bounds` and
:mod:`pitloom.extract.ai_model.crfsuite` (Pitloom's adapters).
"""

from __future__ import annotations

from ._errors import FormatError, LimitExceeded, Malformed, UnsupportedVersion
from ._limits import Limits

__all__ = [
    "FormatError",
    "LimitExceeded",
    "Limits",
    "Malformed",
    "UnsupportedVersion",
]
