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
        creation_datetime: ISO 8601 string for the creation timestamp.
            Full ISO forms are accepted (e.g. offsets and fractional
            seconds). Pitloom preserves input precision internally and
            normalises to SPDX 3 DateTime (``YYYY-MM-DDThh:mm:ssZ``)
            only at export time.
            When ``None`` the assembler uses the current UTC time.
        creation_tool: Name of the tool that produced the SBOM.
            Defaults to ``"Pitloom"``.  When ``None``, no tool element is
            emitted and ``createdUsing`` is omitted from ``CreationInfo``.
        creation_comment: Optional comment to include on the SPDX
            ``CreationInfo`` element.
        build_datetime: ISO 8601 string for when the artifact was built
            (e.g. the moment the Hatchling hook fires).  When set, the
            assembler records it as ``builtTime`` on the main
            ``software_Package`` element.  When ``None`` (default),
            ``builtTime`` is omitted from the SBOM.
    """

    creator_name: str = "Pitloom"
    creator_email: str = ""
    creation_datetime: str | None = None
    creation_tool: str | None = "Pitloom"
    creation_comment: str | None = None
    build_datetime: str | None = None


__all__ = ["CreationMetadata"]
