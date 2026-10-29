# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

""":class:`Cap`, a limit Pitloom puts on an input, as the one over-cap
warning names it.

See also: :mod:`pitloom.messages._over_cap_warning` (the one helper every
cap warns through).
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Cap:
    """A limit Pitloom puts on an input, as
    :func:`~pitloom.messages.warn_over_cap` names it:
    ``<subject>=<where>: larger than the <limit>-<unit> <purpose> cap``."""

    #: The most the input may hold, in *unit*.
    limit: int
    #: What *limit* counts, singular (``"byte"``, ``"entry"``).
    unit: str
    #: What the cap is for (``"license-detection"``).
    purpose: str
    #: The key naming the input, ``"FILE"`` or ``"FIELD"``, after the keys
    #: of :meth:`after` (``"FORMAT=gguf FILE"``).
    subject: str = "FILE"

    @property
    def reason(self) -> str:
        """What an input over this cap is, the same in a ``WARNING:`` and
        in an error's text."""
        return f"larger than the {self.limit}-{self.unit} {self.purpose} cap"

    def after(self, keys: str) -> Cap:
        """This cap, its input named after *keys* (``"FORMAT=gguf"``,
        trusted text): the keys a subsystem puts first."""
        return replace(self, subject=f"{keys} {self.subject}")
