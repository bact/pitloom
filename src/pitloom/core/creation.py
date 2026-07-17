# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM creation metadata for Pitloom-generated documents."""

from __future__ import annotations

from dataclasses import dataclass, field

#: Valid ``Creator.type`` values -- the SPDX 3 Agent subclass a creator maps
#: onto is selected by one of these names.  ``"agent"`` is the generic base
#: class, for a creator that is deliberately unspecified.  This is the
#: canonical set; :mod:`pitloom.assemble.spdx3.creation_info` builds its
#: name -> Agent-class map from these same names (``core`` must not import
#: from ``assemble``, so the mapping itself has to live there).
VALID_CREATOR_TYPES: frozenset[str] = frozenset(
    {"person", "organization", "software-agent", "agent"}
)


@dataclass
class Creator:
    """A single named creator, mapping onto an SPDX 3 Agent.

    Attributes:
        name: Display name of the person or organisation that initiated
            the SBOM generation.
        type: Agent subclass: ``"person"`` (default), ``"organization"``,
            ``"software-agent"``, or the generic ``"agent"``.  All four are
            valid ``createdBy`` types per the SPDX 3 spec.  Validated (and
            normalised to lower-case, stripped) in ``__post_init__``.
        email: E-mail address of the creator.  Recorded as an ``email``
            external identifier on the creator Agent.

    Raises:
        ValueError: If ``name`` is empty or whitespace-only, or if ``type``
            (after normalisation) is not one of :data:`VALID_CREATOR_TYPES`.
    """

    name: str
    type: str = "person"
    email: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError(f"Creator name must be non-empty, got {self.name!r}.")
        normalized = (self.type or "person").strip().lower()
        if normalized not in VALID_CREATOR_TYPES:
            valid = ", ".join(sorted(VALID_CREATOR_TYPES))
            raise ValueError(
                f"Invalid creator type {self.type!r}; must be one of: {valid}."
            )
        self.type = normalized


@dataclass
class Tool:
    """A single creation tool, mapping onto an SPDX 3 Tool.

    Attributes:
        name: Name of the tool.  A tool literally named ``"Pitloom"`` gets
            a version summary appended automatically.

    Raises:
        ValueError: If ``name`` is empty or whitespace-only.
    """

    name: str

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError(f"Tool name must be non-empty, got {self.name!r}.")


@dataclass
class CreationMetadata:
    """Metadata describing who and what generated an SBOM.

    Pitloom's own model for creation provenance -- distinct from, but
    mapping onto, SPDX 3 ``CreationInfo``: each *creator* becomes an Agent
    in ``createdBy`` (``Person``, ``Organization``, ``SoftwareAgent``, or
    the generic ``Agent`` -- see ``Creator.type``), and each *tool* becomes
    a ``Tool`` in ``createdUsing``.  When no creator is named, the
    assembler records the automated ``SoftwareAgent`` ``"Pitloom"`` in
    ``createdBy`` -- Pitloom acting on its own -- rather than inventing a
    ``Person``.

    Attributes:
        creators: Named creators, in order.  When empty (default), no named
            creator is asserted and the assembler emits the
            ``SoftwareAgent`` ``"Pitloom"`` in ``createdBy`` instead.  When
            multiple creators are supplied, each becomes its own Agent; the
            SPDX 3 ``suppliedBy`` of the main package (single-valued) is set
            to the *first* named creator.
        tools: Creation tools, in order.  ``None`` (default) means the
            default single ``Tool`` ``"Pitloom"``.  An empty list suppresses
            ``createdUsing`` entirely (matches ``--no-creation-tool``).  A
            non-empty list emits one ``Tool`` per entry.
        creation_datetime: ISO 8601 string for the creation timestamp.
            Full ISO forms are accepted (e.g. offsets and fractional
            seconds). Pitloom preserves input precision internally and
            normalises to SPDX 3 DateTime (``YYYY-MM-DDThh:mm:ssZ``)
            only at export time.
            When ``None`` the assembler uses the current UTC time.
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

    creators: list[Creator] = field(default_factory=list)
    tools: list[Tool] | None = None
    creation_datetime: str | None = None
    creation_comment: str | None = None
    build_datetime: str | None = None


__all__ = ["VALID_CREATOR_TYPES", "CreationMetadata", "Creator", "Tool"]
