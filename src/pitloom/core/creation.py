# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM creation metadata for Pitloom-generated documents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CreationMetadata:
    """Metadata describing who and what generated an SBOM.

    Attributes:
        creator_name: Display name of the person or organisation that
            initiated the SBOM generation.  Defaults to ``"Pitloom"``.
        creator_email: E-mail address of the creator.  Optional; omitted
            from the output when empty.
        creation_datetime: ISO 8601 string (e.g.
            ``"2026-03-25T12:00:00+00:00"``) for the creation timestamp.
            When ``None`` the assembler uses the current UTC time.
        creation_tool: Name of the tool that produced the SBOM.
            Defaults to ``"Pitloom"``.
        build_datetime: ISO 8601 string for when the artifact was built
            (e.g. the moment the Hatchling hook fires).  When set, the
            assembler records it as ``builtTime`` on the main
            ``software_Package`` element.  When ``None`` (default),
            ``builtTime`` is omitted from the SBOM.
    """

    creator_name: str = "Pitloom"
    creator_email: str = ""
    creation_datetime: str | None = None
    creation_tool: str = "Pitloom"
    build_datetime: str | None = None


__all__ = ["CreationMetadata"]
