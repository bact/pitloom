# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The error of a broken internal contract.

See also: :mod:`pitloom.messages` (the catalogue of messages a user sees)
and ``scripts/message_inventory/`` (which leaves these raises out of the
message ratchet, by their class); ``tests/core/test_internal_error_reraised.py``
(every broad handler in ``src/`` calls :func:`reraise_internal` first).
"""

from __future__ import annotations

__all__ = ["InternalError", "reraise_internal"]


class InternalError(ValueError):
    """A caller passed what no input of a user can produce (an evidence
    level that does not exist, an unknown provenance segment key): a
    programming error, whose text is for a developer and is never
    catalogued. A :class:`ValueError`, so a caller that catches one still
    does."""


def reraise_internal(exc: BaseException) -> None:
    """Raise *exc* again when it is an :class:`InternalError`; else return.

    The first statement of every handler that catches ``ValueError``,
    ``Exception``, ``BaseException`` or anything, so a bug in Pitloom is
    never reported as a user's bad input, a skipped field or a debug line.

    Raises:
        InternalError: *exc* is one.
    """
    if isinstance(exc, InternalError):
        raise exc
