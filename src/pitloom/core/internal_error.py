# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The error of a broken internal contract.

See also: :mod:`pitloom.messages` (the catalogue of messages a user sees)
and ``scripts/message_inventory/`` (which leaves these raises out of the
message ratchet, by their class).
"""

from __future__ import annotations

__all__ = ["InternalError"]


class InternalError(ValueError):
    """A caller passed what no input of a user can produce (an evidence
    level that does not exist, an unknown provenance segment key): a
    programming error, whose text is for a developer and is never
    catalogued. A :class:`ValueError`, so a caller that catches one still
    does."""
