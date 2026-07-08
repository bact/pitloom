# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared SPDX 3 ``CreationInfo`` construction.

Single source of truth for the creator ``Agent`` (``createdBy``), the
``Tool`` (``createdUsing``), the ``created`` timestamp, and the ``comment``.
Used by both the document assembler (CLI / Hatchling build hook) and the
``pitloom.loom`` fragment SDK so all paths model creation the same way.
"""

from __future__ import annotations

from datetime import datetime, timezone

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__about__ import __version__
from pitloom.core.creation import CreationMetadata
from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import require_spdx_id


def parse_iso_datetime(value: str) -> datetime:
    """Parse a full ISO 8601 datetime string.

    Accepts offset forms (including trailing ``Z``) and optional fractional
    seconds. Naive values are interpreted as UTC.
    """
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO 8601 datetime: {value}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def to_spdx3_datetime(value: datetime) -> datetime:
    """Convert datetime to SPDX 3 DateTime constraints (UTC, whole seconds)."""
    return value.astimezone(timezone.utc).replace(microsecond=0)


def spdx3_utc_now() -> datetime:
    """Return current UTC time truncated to whole seconds for SPDX DateTime."""
    return to_spdx3_datetime(datetime.now(timezone.utc))


#: Valid ``creator_type`` values -> the SPDX 3 Agent subclass to construct.
#: All four are valid ``createdBy`` types per the spec; "agent" is the
#: generic base class, for a creator that is deliberately unspecified.
CREATOR_TYPES: dict[str, type[spdx3.Agent]] = {
    "person": spdx3.Person,
    "organization": spdx3.Organization,
    "software-agent": spdx3.SoftwareAgent,
    "agent": spdx3.Agent,
}


def _tool_summary(creation_tool: str) -> str | None:
    """Pitloom's version, but only when *creation_tool* is still the default
    ``"Pitloom"`` name -- a user-supplied tool name may not refer to Pitloom
    itself, so no version is asserted in that case.
    """
    if creation_tool == CreationMetadata().creation_tool:
        return f"Pitloom {__version__}"
    return None


def build_creator_agent(
    creation_metadata: CreationMetadata,
    doc_name: str,
    doc_uuid: str,
    spdx_ci: spdx3.CreationInfo,
) -> spdx3.Agent:
    """Build the ``createdBy`` Agent.

    A named creator becomes whichever Agent subclass ``creator_type``
    selects -- ``Person`` (default), ``Organization``, ``SoftwareAgent``, or
    the generic ``Agent`` -- see :data:`CREATOR_TYPES`. With no named
    creator, the automated ``SoftwareAgent`` ``"Pitloom"`` stands in --
    Pitloom running on its own -- which satisfies ``createdBy``'s required
    Agent without asserting a human did the work.

    Raises:
        ValueError: If ``creator_type`` is set but not one of
            :data:`CREATOR_TYPES`.
    """
    if not creation_metadata.creator_name:
        return spdx3.SoftwareAgent(
            spdxId=generate_spdx_id(
                "SoftwareAgent", doc_name=doc_name, doc_uuid=doc_uuid
            ),
            name="Pitloom",
            creationInfo=spdx_ci,
        )

    creator_type = (creation_metadata.creator_type or "person").strip().lower()
    agent_cls = CREATOR_TYPES.get(creator_type)
    if agent_cls is None:
        valid = ", ".join(sorted(CREATOR_TYPES))
        raise ValueError(
            f"Invalid creator_type {creation_metadata.creator_type!r}; "
            f"must be one of: {valid}."
        )
    agent = agent_cls(
        spdxId=generate_spdx_id(
            agent_cls.__name__, doc_name=doc_name, doc_uuid=doc_uuid
        ),
        name=creation_metadata.creator_name,
        creationInfo=spdx_ci,
    )
    if creation_metadata.creator_email:
        agent.externalIdentifier = [
            spdx3.ExternalIdentifier(
                externalIdentifierType=spdx3.ExternalIdentifierType.email,
                identifier=creation_metadata.creator_email,
            )
        ]
    return agent


def build_tool(
    creation_metadata: CreationMetadata,
    doc_name: str,
    doc_uuid: str,
    spdx_ci: spdx3.CreationInfo,
) -> spdx3.Tool | None:
    """Build the ``createdUsing`` Tool, or ``None`` when suppressed.

    ``Tool.summary`` carries Pitloom's version, but only for the default
    ``"Pitloom"`` tool name (see :func:`_tool_summary`).
    """
    if not creation_metadata.creation_tool:
        return None
    tool = spdx3.Tool(
        spdxId=generate_spdx_id("Tool", doc_name=doc_name, doc_uuid=doc_uuid),
        name=creation_metadata.creation_tool,
        creationInfo=spdx_ci,
    )
    summary = _tool_summary(creation_metadata.creation_tool)
    if summary:
        tool.summary = summary
    return tool


def build_creation_info(
    creation_metadata: CreationMetadata,
    doc_name: str,
    doc_uuid: str,
    *,
    default_comment: str | None = None,
) -> tuple[spdx3.CreationInfo, spdx3.Agent, spdx3.Tool | None]:
    """Assemble a ``CreationInfo`` plus its creator Agent and Tool.

    ``created`` comes from ``creation_metadata.creation_datetime`` (normalised
    to SPDX DateTime) or the current UTC time.  ``comment`` uses
    ``creation_metadata.creation_comment`` if set, else *default_comment*.
    The creator Agent goes in ``createdBy`` and the Tool (when present) in
    ``createdUsing``.
    """
    created = (
        to_spdx3_datetime(parse_iso_datetime(creation_metadata.creation_datetime))
        if creation_metadata.creation_datetime
        else spdx3_utc_now()
    )
    spdx_ci = spdx3.CreationInfo(specVersion="3.0.1", created=created)

    comment = (
        creation_metadata.creation_comment
        if creation_metadata.creation_comment is not None
        else default_comment
    )
    if comment:
        spdx_ci.comment = comment

    creator = build_creator_agent(creation_metadata, doc_name, doc_uuid, spdx_ci)
    tool = build_tool(creation_metadata, doc_name, doc_uuid, spdx_ci)

    spdx_ci.createdBy = [require_spdx_id(creator)]
    if tool is not None:
        spdx_ci.createdUsing = [require_spdx_id(tool)]
    return spdx_ci, creator, tool


__all__ = [
    "parse_iso_datetime",
    "to_spdx3_datetime",
    "spdx3_utc_now",
    "build_creator_agent",
    "build_tool",
    "build_creation_info",
]
