# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a format reader raises.

See also: :mod:`pitloom.extract.ai_model.formats._limits`.
"""

from __future__ import annotations


class FormatError(Exception):
    """A model file was not read.

    Attributes:
        reason: What went wrong, as one short phrase (no path).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LimitExceeded(FormatError):
    """The file declares or holds more than a :class:`Limits` bound allows."""


class Malformed(FormatError):
    """The file is not well-formed in its format (truncated, unknown code,
    inconsistent lengths)."""


class UnsupportedVersion(FormatError):
    """The file is in a version of its format the reader does not know."""
