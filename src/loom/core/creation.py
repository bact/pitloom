# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM creation metadata for Loom-generated documents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CreationInfo:
    """Loom-level inputs describing who and what generated an SBOM.

    This is **not** a representation of ``spdx3.CreationInfo`` from the SPDX
    spec.  It is a plain Loom data object that the assembler translates into
    the appropriate SPDX 3.0 elements (``Person``, ``Tool``,
    ``spdx3.CreationInfo``, …).  The fields are chosen for ergonomics at the
    Loom API boundary, not for SPDX compliance.

    Attributes:
        creator_name: Display name of the person or organisation that
            initiated the SBOM generation.  Defaults to ``"Loom"``.
        creator_email: E-mail address of the creator.  Optional; omitted
            from the output when empty.
        creation_datetime: ISO 8601 string (e.g.
            ``"2026-03-25T12:00:00+00:00"``) for the creation timestamp.
            When ``None`` the assembler uses the current UTC time.
        creation_tool: Name of the tool that produced the SBOM.
            Defaults to ``"Loom"``.  Recorded as a ``spdx3.Tool`` element
            in the output document.
    """

    creator_name: str = "Loom"
    creator_email: str = ""
    creation_datetime: str | None = None
    creation_tool: str = "Loom"


__all__ = ["CreationInfo"]
