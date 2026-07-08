# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM creation metadata for Pitloom-generated documents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CreationMetadata:
    """Metadata describing who and what generated an SBOM.

    This maps to SPDX 3 ``CreationInfo``: the *creator* becomes an Agent in
    ``createdBy`` (a human ``Person`` or an ``Organization``), and the *tool*
    becomes a ``Tool`` in ``createdUsing``.  When no creator is named, the
    assembler records the automated ``SoftwareAgent`` ``"Pitloom"`` in
    ``createdBy`` -- Pitloom acting on its own -- rather than inventing a
    ``Person``.

    Attributes:
        creator_name: Display name of the person or organisation that
            initiated the SBOM generation.  When ``None`` (default), no named
            creator is asserted and the assembler emits the ``SoftwareAgent``
            ``"Pitloom"`` in ``createdBy`` instead.
        creator_email: E-mail address of the creator.  Recorded as an
            ``email`` external identifier on the creator Agent.  Ignored when
            ``creator_name`` is ``None``.
        creator_type: Agent subclass for a named creator: ``"person"``
            (default), ``"organization"``, ``"software-agent"``, or the
            generic ``"agent"``.  All four are valid ``createdBy`` types per
            the SPDX 3 spec.  Ignored when ``creator_name`` is ``None``.
        creation_datetime: ISO 8601 string for the creation timestamp.
            Full ISO forms are accepted (e.g. offsets and fractional
            seconds). Pitloom preserves input precision internally and
            normalises to SPDX 3 DateTime (``YYYY-MM-DDThh:mm:ssZ``)
            only at export time.
            When ``None`` the assembler uses the current UTC time.
        creation_tool: Name of the tool that produced the SBOM, emitted as a
            ``Tool`` in ``createdUsing``.  Defaults to ``"Pitloom"``.  When
            ``None``, no tool element is emitted and ``createdUsing`` is
            omitted from ``CreationInfo``.
        creation_comment: Optional comment to include on the SPDX
            ``CreationInfo`` element.  Callers (CLI, Hatchling build hook)
            set this to a static description of the invocation channel,
            e.g. ``"Generated via Pitloom CLI"``.
        build_datetime: ISO 8601 string for when the artifact was built
            (e.g. the moment the Hatchling hook fires).  When set, the
            assembler records it as ``builtTime`` on the main
            ``software_Package`` element.  When ``None`` (default),
            ``builtTime`` is omitted from the SBOM.
    """

    creator_name: str | None = None
    creator_email: str | None = None
    creator_type: str = "person"
    creation_datetime: str | None = None
    creation_tool: str | None = "Pitloom"
    creation_comment: str | None = None
    build_datetime: str | None = None


__all__ = ["CreationMetadata"]
