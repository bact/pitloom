# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM creation metadata for Pitloom-generated documents."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pitloom.core.internal_error import reraise_internal
from pitloom.messages import CodedValueError
from pitloom.messages.config import (
    EPOCH_NOT_INTEGER_LINE,
    EPOCH_OUT_OF_RANGE_LINE,
    SOURCE_DATE_EPOCH_INVALID,
    Parameter,
    invalid_value,
)

#: Valid ``Creator.type`` values -- the SPDX 3 Agent subclass a creator maps
#: onto is selected by one of these names.  ``"agent"`` is the generic base
#: class, for a creator that is deliberately unspecified.  This is the
#: canonical set; :mod:`pitloom.assemble.spdx3.creation_info` builds its
#: name -> Agent-class map from these same names (``core`` must not import
#: from ``assemble``, so the mapping itself has to live there).
VALID_CREATOR_TYPES: frozenset[str] = frozenset(
    {"person", "organization", "software-agent", "agent"}
)


def normalised_creator_type(value: str | None) -> str:
    """*value* as ``Creator.type`` keeps it: stripped, lower-case, and
    ``person`` for none or empty."""
    return (value or "person").strip().lower()


def creator_type_problem(value: object) -> str | None:
    """Why *value* is no creator type: the ``expected`` id (see
    :data:`~pitloom.messages.config.EXPECTED`) ``"string"`` (not a string)
    or ``"creator-type"`` (not one of :data:`VALID_CREATOR_TYPES` once
    normalised, as :class:`Creator` does), else ``None``. ``None`` is
    ``person``, as for :class:`Creator`. The one check of the config reader
    and of ``Creator.__post_init__``."""
    if value is not None and not isinstance(value, str):
        return "string"
    return (
        None
        if normalised_creator_type(value) in VALID_CREATOR_TYPES
        else ("creator-type")
    )


def iso_datetime_or_none(value: str) -> datetime | None:
    """*value*, a full ISO 8601 datetime, as a timezone-aware
    :class:`~datetime.datetime`, or ``None`` when it is none.

    Accepts offset forms (a trailing ``Z`` included, which
    :meth:`~datetime.datetime.fromisoformat` takes from Python 3.11 only)
    and optional fractional seconds. A naive value is read as UTC. The one
    parse of a datetime string: stdlib only, so the config reader and the
    assembler share it.
    """
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        reraise_internal(exc)
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    try:
        parsed.astimezone(timezone.utc)
    except OverflowError:
        return None  # out of range once read as UTC, e.g. year 1 at +05:00
    return parsed


@dataclass
class Creator:
    """A single named creator, mapping onto an SPDX 3 Agent.

    Attributes:
        name: Display name of the person or organisation that initiated
            the SBOM generation.  Stripped in ``__post_init__``: the
            creator Agent carries the name an author is matched on.
        type: Agent subclass: ``"person"`` (default), ``"organization"``,
            ``"software-agent"``, or the generic ``"agent"``.  All four are
            valid ``createdBy`` types per the SPDX 3 spec.  Validated (and
            normalised to lower-case, stripped) in ``__post_init__``.
        email: E-mail address of the creator.  Recorded as an ``email``
            external identifier on the creator Agent.  Stripped in
            ``__post_init__``; an empty or whitespace-only address is no
            address (``None``).

    Raises:
        ValueError: If ``name`` is empty or whitespace-only (no name), or if
            ``type`` (after normalisation) is not one of
            :data:`VALID_CREATOR_TYPES`.
    """

    name: str
    type: str = "person"
    email: str | None = None

    def __post_init__(self) -> None:
        name = self.name.strip() if isinstance(self.name, str) else ""
        if not name:
            raise invalid_value(Parameter("Creator.name"), "non-empty", got=self.name)
        self.name = name
        self.email = (self.email or "").strip() or None
        problem = creator_type_problem(self.type)
        if problem is not None:
            raise invalid_value(Parameter("Creator.type"), problem, got=self.type)
        self.type = normalised_creator_type(self.type)


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
        if not isinstance(self.name, str) or not self.name.strip():
            raise invalid_value(Parameter("Tool.name"), "non-empty", got=self.name)


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
            to the *first* named creator that is not a ``"software-agent"``
            (a program that made the SBOM did not supply the package).
        tools: Creation tools, in order.  ``None`` (default) means the
            default single ``Tool`` ``"Pitloom"``.  An empty list suppresses
            ``createdUsing`` entirely (matches ``--no-creation-tool``).  A
            non-empty list emits one ``Tool`` per entry.
        creation_datetime: ISO 8601 string for the creation timestamp.
            Full ISO forms are accepted (e.g. offsets and fractional
            seconds). Pitloom preserves input precision internally and
            normalises to SPDX 3 DateTime (``YYYY-MM-DDThh:mm:ssZ``)
            only at export time.
            When ``None``, the assembler falls back to ``SOURCE_DATE_EPOCH``
            (reproducible-builds.org) if set, else the current UTC time --
            see :func:`resolve_source_date_epoch`.
        creation_comment: Optional comment to include on the SPDX
            ``CreationInfo`` element.  Callers (CLI, Hatchling build hook,
            loom SDK) set this to a description of the invocation channel,
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


def resolve_source_date_epoch() -> datetime | None:
    """Read ``SOURCE_DATE_EPOCH`` as a UTC datetime, per reproducible-builds.org.

    <https://reproducible-builds.org/specs/source-date-epoch/>: a single
    environment variable the whole build toolchain honours for every
    embedded timestamp, so an operator opts a build into reproducibility
    once rather than configuring each tool individually. Shared by every
    Pitloom timestamp that should respect it (SBOM ``created``, the
    Hatchling build hook's ``builtTime``, embedded wheel ZIP entries) so
    the parsing/validation rule -- and what counts as invalid -- stays in
    one place.

    Returns:
        The resolved UTC datetime, or ``None`` when unset or empty --
        callers fall back to their own default.

    Raises:
        ValueError: It is set and not an integer number of seconds, or out
            of range for a date: the specification says a build should fail
            on a malformed value, as Hatchling does. Every SBOM entry point
            reads it, whether or not a creation date is pinned, so each
            reports the one exception, once.
    """
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if not raw:
        return None
    try:
        seconds = int(raw)
    except ValueError as exc:
        reraise_internal(exc)
        raise CodedValueError(
            SOURCE_DATE_EPOCH_INVALID, line=EPOCH_NOT_INTEGER_LINE, value=raw
        ) from None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (ValueError, OverflowError, OSError) as exc:
        reraise_internal(exc)
        raise CodedValueError(
            SOURCE_DATE_EPOCH_INVALID, line=EPOCH_OUT_OF_RANGE_LINE, value=raw
        ) from None


__all__ = [
    "VALID_CREATOR_TYPES",
    "CreationMetadata",
    "Creator",
    "Tool",
    "creator_type_problem",
    "iso_datetime_or_none",
    "normalised_creator_type",
    "resolve_source_date_epoch",
]
