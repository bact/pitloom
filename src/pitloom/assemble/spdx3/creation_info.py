# SPDX-FileContributor: Arthit Suriyawongkul
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
from pitloom.core.creation import VALID_CREATOR_TYPES, CreationMetadata, Tool
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
#: Keys must match :data:`pitloom.core.creation.VALID_CREATOR_TYPES` exactly
#: -- that constant is the canonical source of valid creator-type names
#: (validated eagerly in ``Creator.__post_init__``); this dict just adds the
#: SPDX 3 Agent subclass for each, which ``core`` cannot know about since
#: ``core`` must not import from ``assemble``.
CREATOR_TYPES: dict[str, type[spdx3.Agent]] = {
    "person": spdx3.Person,
    "organization": spdx3.Organization,
    "software-agent": spdx3.SoftwareAgent,
    "agent": spdx3.Agent,
}
if set(CREATOR_TYPES) != VALID_CREATOR_TYPES:
    raise RuntimeError(
        "CREATOR_TYPES keys must match pitloom.core.creation.VALID_CREATOR_TYPES"
    )


def _tool_summary(tool_name: str | None) -> str | None:
    """Pitloom's version, but only when *tool_name* is literally ``"Pitloom"``
    -- a user-supplied tool name may not refer to Pitloom itself, so no
    version is asserted in that case.
    """
    if not tool_name:
        return None
    if tool_name == "Pitloom":
        return f"Pitloom {__version__}"
    return None


def build_creator_agents(
    creation_metadata: CreationMetadata,
    doc_name: str,
    doc_uuid: str,
    spdx_ci: spdx3.CreationInfo,
) -> list[spdx3.Agent]:
    """Build the ``createdBy`` Agents, one per named creator.

    Each named creator becomes whichever Agent subclass its ``type``
    selects -- ``Person`` (default), ``Organization``, ``SoftwareAgent``, or
    the generic ``Agent`` -- see :data:`CREATOR_TYPES`. With no named
    creators, the automated ``SoftwareAgent`` ``"Pitloom"`` stands in --
    Pitloom running on its own -- which satisfies ``createdBy``'s required
    Agent without asserting a human did the work.

    Raises:
        ValueError: If a creator's ``type`` is set but not one of
            :data:`CREATOR_TYPES`.
    """
    if not creation_metadata.creators:
        return [
            spdx3.SoftwareAgent(
                spdxId=generate_spdx_id(
                    "SoftwareAgent", doc_name=doc_name, doc_uuid=doc_uuid
                ),
                name="Pitloom",
                creationInfo=spdx_ci,
            )
        ]

    agents: list[spdx3.Agent] = []
    for creator in creation_metadata.creators:
        creator_type = (creator.type or "person").strip().lower()
        agent_cls = CREATOR_TYPES.get(creator_type)
        if agent_cls is None:
            valid = ", ".join(sorted(CREATOR_TYPES))
            raise ValueError(
                f"Invalid creator type {creator.type!r}; must be one of: {valid}."
            )
        agent = agent_cls(
            spdxId=generate_spdx_id(
                agent_cls.__name__, doc_name=doc_name, doc_uuid=doc_uuid
            ),
            name=creator.name,
            creationInfo=spdx_ci,
        )
        if creator.email:
            agent.externalIdentifier = [
                spdx3.ExternalIdentifier(
                    externalIdentifierType=spdx3.ExternalIdentifierType.email,
                    identifier=creator.email,
                )
            ]
        agents.append(agent)
    return agents


def build_tools(
    creation_metadata: CreationMetadata,
    doc_name: str,
    doc_uuid: str,
    spdx_ci: spdx3.CreationInfo,
) -> list[spdx3.Tool]:
    """Build the ``createdUsing`` Tools.

    ``tools is None`` yields the default single ``Tool`` ``"Pitloom"``;
    ``tools == []`` suppresses ``createdUsing`` entirely; otherwise one
    ``Tool`` per :class:`~pitloom.core.creation.Tool`.  ``Tool.summary``
    carries Pitloom's version, but only for a tool literally named
    ``"Pitloom"`` (see :func:`_tool_summary`).
    """
    source_tools = (
        [Tool(name="Pitloom")]
        if creation_metadata.tools is None
        else creation_metadata.tools
    )
    tools: list[spdx3.Tool] = []
    for source_tool in source_tools:
        tool = spdx3.Tool(
            spdxId=generate_spdx_id("Tool", doc_name=doc_name, doc_uuid=doc_uuid),
            name=source_tool.name,
            creationInfo=spdx_ci,
        )
        summary = _tool_summary(tool.name)
        if summary:
            tool.summary = summary
        tools.append(tool)
    return tools


def build_creation_info(
    creation_metadata: CreationMetadata,
    doc_name: str,
    doc_uuid: str,
    *,
    default_comment: str | None = None,
) -> tuple[spdx3.CreationInfo, list[spdx3.Agent], list[spdx3.Tool]]:
    """Assemble a ``CreationInfo`` plus its creator Agents and Tools.

    ``created`` comes from ``creation_metadata.creation_datetime`` (normalised
    to SPDX DateTime) or the current UTC time.  ``comment`` uses
    ``creation_metadata.creation_comment`` if set, else *default_comment*.
    The creator Agents go in ``createdBy`` and the Tools (when present) in
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

    agents = build_creator_agents(creation_metadata, doc_name, doc_uuid, spdx_ci)
    tools = build_tools(creation_metadata, doc_name, doc_uuid, spdx_ci)

    spdx_ci.createdBy = [require_spdx_id(agent) for agent in agents]
    if tools:
        spdx_ci.createdUsing = [require_spdx_id(tool) for tool in tools]
    return spdx_ci, agents, tools


def build_enrichment_creation_info(
    tool_name: str,
    main_creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> tuple[spdx3.CreationInfo, spdx3.Tool]:
    """Build a second ``CreationInfo`` for elements an enrichment run
    created (N3).

    ``createdBy`` is deliberately the *same* Agent(s) already used by
    ``main_creation_info`` -- reused directly, not re-minted via
    :func:`build_creator_agents` -- so enrichment doesn't invent a
    fictitious second "Pitloom" identity alongside the one the rest of
    the document already uses. ``createdUsing`` is a fresh ``Tool`` named
    after the enricher (e.g. ``"pitloom.enrich.readme"``), and ``created``
    is the enrichment run's own timestamp (now), distinct from the main
    document's creation time.

    SPDX 3.0.1 has no native ``Tool.version`` (added in 3.1-dev); version
    info goes in ``Tool.summary`` instead, same workaround
    :func:`_tool_summary` uses for the main "Pitloom" tool -- set directly
    here rather than widening that helper's tool-name-scoped contract.
    """
    ci = spdx3.CreationInfo(specVersion="3.0.1", created=spdx3_utc_now())
    tool = spdx3.Tool(
        spdxId=generate_spdx_id("Tool", doc_name=doc_name, doc_uuid=doc_uuid),
        name=tool_name,
        creationInfo=ci,
        summary=f"Pitloom {__version__}",
    )
    ci.createdBy = main_creation_info.createdBy
    ci.createdUsing = [require_spdx_id(tool)]
    return ci, tool


__all__ = [
    "parse_iso_datetime",
    "to_spdx3_datetime",
    "spdx3_utc_now",
    "build_creator_agents",
    "build_tools",
    "build_creation_info",
    "build_enrichment_creation_info",
]
