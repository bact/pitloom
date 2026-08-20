# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for pitloom.assemble.spdx3.creation_info.

Complements the full-pipeline graph assertions in test_generator.py etc.
with tests that call these functions directly and assert on their return
values, so a regression here fails in this file instead of surfacing as
a generic "wrong graph shape" failure somewhere else.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

import pitloom.assemble.spdx3.creation_info as creation_info_module
import pitloom.core.creation as creation_module
from pitloom.assemble.spdx3.creation_info import (
    _tool_summary,
    build_creation_info,
    build_creator_agents,
    build_tools,
    parse_iso_datetime,
    to_spdx3_datetime,
)
from pitloom.core.creation import CreationMetadata, Creator, Tool

_DOC_NAME = "testproject"
_DOC_UUID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# parse_iso_datetime / to_spdx3_datetime
# ---------------------------------------------------------------------------


def test_parse_iso_datetime_with_offset() -> None:
    parsed = parse_iso_datetime("2026-01-15T10:30:00+02:00")
    offset = parsed.utcoffset()
    assert parsed.hour == 10
    assert offset is not None
    assert offset.total_seconds() == 7200
    assert to_spdx3_datetime(parsed) == datetime(
        2026, 1, 15, 8, 30, tzinfo=timezone.utc
    )


def test_parse_iso_datetime_trailing_z() -> None:
    parsed = parse_iso_datetime("2026-01-15T10:30:00Z")
    assert parsed == datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)


def test_parse_iso_datetime_naive_assumed_utc() -> None:
    parsed = parse_iso_datetime("2026-01-15T10:30:00")
    assert parsed.tzinfo == timezone.utc


def test_parse_iso_datetime_invalid_raises() -> None:
    with pytest.raises(ValueError, match="Invalid ISO 8601 datetime"):
        parse_iso_datetime("not-a-date")


def test_to_spdx3_datetime_truncates_microseconds() -> None:
    value = datetime(2026, 1, 15, 10, 30, 0, 123456, tzinfo=timezone.utc)
    assert to_spdx3_datetime(value).microsecond == 0


# ---------------------------------------------------------------------------
# _tool_summary
# ---------------------------------------------------------------------------


def test_tool_summary_none_name() -> None:
    assert _tool_summary(None) is None


def test_tool_summary_empty_name() -> None:
    assert _tool_summary("") is None


def test_tool_summary_non_pitloom_name() -> None:
    assert _tool_summary("SomeOtherTool") is None


def test_tool_summary_pitloom_name_includes_version() -> None:
    summary = _tool_summary("Pitloom")
    assert summary is not None
    assert summary.startswith("Pitloom ")


# ---------------------------------------------------------------------------
# build_creator_agents
# ---------------------------------------------------------------------------


def test_build_creator_agents_no_creators_yields_pitloom_software_agent() -> None:
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(), _DOC_NAME, _DOC_UUID
    )
    agents = build_creator_agents(CreationMetadata(), _DOC_NAME, _DOC_UUID, spdx_ci)
    assert len(agents) == 1
    assert agents[0].name == "Pitloom"


def test_build_creator_agents_with_email() -> None:
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(), _DOC_NAME, _DOC_UUID
    )
    metadata = CreationMetadata(
        creators=[Creator(name="Jane Doe", type="person", email="jane@example.com")]
    )
    agents = build_creator_agents(metadata, _DOC_NAME, _DOC_UUID, spdx_ci)
    assert len(agents) == 1
    assert agents[0].name == "Jane Doe"
    identifier = agents[0].externalIdentifier[0]
    assert isinstance(identifier, spdx3.ExternalIdentifier)
    assert identifier.identifier == "jane@example.com"


def test_build_creator_agents_invalid_type_raises() -> None:
    # Creator.__post_init__ already validates `type` eagerly against the
    # same VALID_CREATOR_TYPES set, so a normal construction can never
    # reach build_creator_agents's own check -- mutate `type` after
    # construction (Creator isn't frozen) to exercise that second,
    # defensive layer directly, same as a future VALID_CREATOR_TYPES/
    # CREATOR_TYPES drift would.
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(), _DOC_NAME, _DOC_UUID
    )
    creator = Creator(name="Bad", type="person")
    creator.type = "not-a-real-type"
    metadata = CreationMetadata(creators=[creator])
    with pytest.raises(ValueError, match="Invalid creator type"):
        build_creator_agents(metadata, _DOC_NAME, _DOC_UUID, spdx_ci)


# ---------------------------------------------------------------------------
# build_tools
# ---------------------------------------------------------------------------


def test_build_tools_default_is_pitloom() -> None:
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(), _DOC_NAME, _DOC_UUID
    )
    tools = build_tools(CreationMetadata(), _DOC_NAME, _DOC_UUID, spdx_ci)
    assert len(tools) == 1
    assert tools[0].name == "Pitloom"
    assert tools[0].summary is not None
    assert tools[0].externalIdentifier


def test_build_tools_empty_list_suppresses_created_using() -> None:
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(), _DOC_NAME, _DOC_UUID
    )
    tools = build_tools(CreationMetadata(tools=[]), _DOC_NAME, _DOC_UUID, spdx_ci)
    assert not tools


def test_build_tools_custom_tool_no_pitloom_summary() -> None:
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(), _DOC_NAME, _DOC_UUID
    )
    tools = build_tools(
        CreationMetadata(tools=[Tool(name="SomeBuildTool")]),
        _DOC_NAME,
        _DOC_UUID,
        spdx_ci,
    )
    assert len(tools) == 1
    assert tools[0].name == "SomeBuildTool"
    assert tools[0].summary is None


# ---------------------------------------------------------------------------
# build_creation_info
# ---------------------------------------------------------------------------


def test_build_creation_info_uses_default_comment_when_none_given() -> None:
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(), _DOC_NAME, _DOC_UUID, default_comment="default text"
    )
    assert spdx_ci.comment == "default text"


def test_build_creation_info_explicit_comment_overrides_default() -> None:
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(creation_comment="explicit"),
        _DOC_NAME,
        _DOC_UUID,
        default_comment="default text",
    )
    assert spdx_ci.comment == "explicit"


def test_build_creation_info_explicit_datetime_used() -> None:
    metadata = CreationMetadata(creation_datetime="2026-03-01T00:00:00Z")
    spdx_ci, _agents, _tools = build_creation_info(metadata, _DOC_NAME, _DOC_UUID)
    assert spdx_ci.created == datetime(2026, 3, 1, tzinfo=timezone.utc)


def test_build_creation_info_source_date_epoch_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SOURCE_DATE_EPOCH (reproducible-builds.org) sets `created` when unpinned."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(), _DOC_NAME, _DOC_UUID
    )
    assert spdx_ci.created == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_build_creation_info_explicit_datetime_overrides_source_date_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pinned creation_datetime wins over SOURCE_DATE_EPOCH, matching the
    Hatchling build hook's build_datetime priority -- an explicit, deliberate
    per-SBOM pin is more specific than the ambient, workspace-wide
    SOURCE_DATE_EPOCH signal, so it wins.
    """
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    metadata = CreationMetadata(creation_datetime="2026-03-01T00:00:00Z")
    spdx_ci, _agents, _tools = build_creation_info(metadata, _DOC_NAME, _DOC_UUID)
    assert spdx_ci.created == datetime(2026, 3, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Module-level CREATOR_TYPES / VALID_CREATOR_TYPES invariant
# ---------------------------------------------------------------------------


def test_creator_types_mismatch_raises_runtime_error_on_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The module-level sanity check guarding CREATOR_TYPES against
    pitloom.core.creation.VALID_CREATOR_TYPES drifting apart must raise
    RuntimeError if the two ever disagree -- simulated here by patching
    VALID_CREATOR_TYPES and re-executing the module's top level via
    importlib.reload()."""
    original_valid = creation_module.VALID_CREATOR_TYPES
    monkeypatch.setattr(
        creation_module, "VALID_CREATOR_TYPES", frozenset({"bogus-type"})
    )
    try:
        with pytest.raises(RuntimeError, match="CREATOR_TYPES keys must match"):
            importlib.reload(creation_info_module)
    finally:
        # Restore the real VALID_CREATOR_TYPES and re-reload so the module
        # is left in a normal, working state for any tests that run after
        # this one (monkeypatch's own teardown runs after this function
        # returns, too late to protect a reload happening here).
        monkeypatch.setattr(creation_module, "VALID_CREATOR_TYPES", original_valid)
        importlib.reload(creation_info_module)
