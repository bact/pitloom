# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitloom.cli.constants import _PROJECT_PYPROJECT_SOURCE, _SPDX3_JSON_EXT
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import (
    CreationMetadata,
    Creator,
    Tool,
)
from pitloom.core.project import ProjectMetadata
from pitloom.extract._toml_io import load_toml_file
from pitloom.extract.project import read_project


@dataclass(frozen=True)
class _ResolvedValue:
    """A resolved option value paired with its source label."""

    value: str | None
    source: str


@dataclass(frozen=True)
class _ResolvedCreators:
    """Resolved creator list paired with its source label."""

    value: list[Creator]
    source: str


@dataclass(frozen=True)
class _ResolvedTools:
    """Resolved tool list paired with its source label."""

    value: list[Tool] | None
    source: str


@dataclass(frozen=True)
class _ResolvedCreationMetadata:
    """Resolved creation metadata values and their source labels."""

    creators: _ResolvedCreators
    tools: _ResolvedTools
    creation_datetime: _ResolvedValue
    creation_comment: _ResolvedValue

    def to_creation_metadata(self) -> CreationMetadata:
        """Convert resolved values to :class:`CreationMetadata`."""
        return CreationMetadata(
            creators=self.creators.value,
            tools=self.tools.value,
            creation_datetime=self.creation_datetime.value,
            creation_comment=self.creation_comment.value,
        )


def add_offline_argument(parser: argparse.ArgumentParser, effect: str) -> None:
    """Add the shared ``--offline``/``--no-offline`` flag.

    The mechanics (``BooleanOptionalAction``, ``default=None`` so the CLI
    can defer to ``[tool.pitloom] offline`` when omitted) and the closing
    "Defers to..." sentence are identical for every command that offers
    this flag; only what "forbid network access" actually does differs by
    command/target. *effect* is spliced in verbatim right after "Forbid
    network access" (include its own leading punctuation and trailing
    period, e.g. ``" -- skip PyPI lookup, no error (...)."``) so each
    caller keeps its own accurate, command-specific wording instead of one
    generic sentence that would misdescribe some commands' actual behaviour.
    """
    parser.add_argument(
        "--offline",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            f"Forbid network access{effect} Defers to [tool.pitloom] "
            "offline (off by default) when omitted."
        ),
    )


def add_debug_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--debug``/``--no-debug`` flag.

    Same ``BooleanOptionalAction``/``default=None`` mechanics as
    :func:`add_offline_argument` -- ``None`` (the flag omitted) means
    "no explicit choice", letting :func:`pitloom.logging_config.apply_debug_override`
    leave an ambient ``PITLOOM_DEBUG`` as it found it, rather than the CLI
    silently forcing debug output off.
    """
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Surface DEBUG:-level diagnostics on stderr (developer detail, "
            "e.g. why an extraction step was skipped). Same effect as "
            "setting PITLOOM_DEBUG=1; --no-debug overrides an ambient "
            "PITLOOM_DEBUG back off for this invocation. Covers entry "
            "points that don't parse this flag (the Hatchling build hook, "
            "the library API) either way."
        ),
    )


def _resolve_project_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    """Resolve and validate project directory or sdist archive path."""
    project_dir = args.project_dir.resolve()
    if not project_dir.exists():
        print(f"ERROR: project directory not found: {project_dir}", file=sys.stderr)
        return None, None

    if project_dir.is_file():
        return project_dir, project_dir

    for candidate in ("pyproject.toml", "setup.cfg", "setup.py"):
        config_path = project_dir / candidate
        if config_path.exists():
            return project_dir, config_path

    print(
        f"ERROR: no project configuration found in {project_dir}. "
        "Expected pyproject.toml, setup.cfg, or setup.py.",
        file=sys.stderr,
    )
    return None, None


def _resolve_creation_field(
    cli_value: str | None,
    config_value: str | None,
    default_value: str | None,
) -> _ResolvedValue:
    """Resolve a creation field with precedence CLI > pyproject > default."""
    if cli_value is not None:
        return _ResolvedValue(value=cli_value, source="command-line")
    if config_value is not None:
        return _ResolvedValue(value=config_value, source=_PROJECT_PYPROJECT_SOURCE)
    return _ResolvedValue(value=default_value, source="default")


def _resolve_creators(
    args: argparse.Namespace,
    config_creators: list[Creator],
) -> _ResolvedCreators:
    """Resolve the creator list with precedence CLI > pyproject > default."""
    cli_creators: list[Creator] | None = args.creators
    if cli_creators:
        return _ResolvedCreators(value=cli_creators, source="command-line")
    if config_creators:
        return _ResolvedCreators(
            value=config_creators, source=_PROJECT_PYPROJECT_SOURCE
        )
    return _ResolvedCreators(value=[], source="default")


def _resolve_tools(
    args: argparse.Namespace,
    config_tools: list[Tool] | None,
) -> _ResolvedTools:
    """Resolve the tool list."""
    if args.no_creation_tool:
        return _ResolvedTools(value=[], source="command-line")
    cli_tools: list[str] | None = args.creation_tools
    if cli_tools:
        return _ResolvedTools(
            value=[Tool(name=name) for name in cli_tools],
            source="command-line",
        )
    if config_tools is not None:
        return _ResolvedTools(value=config_tools, source=_PROJECT_PYPROJECT_SOURCE)
    return _ResolvedTools(value=None, source="default")


def _resolve_creation_metadata(
    args: argparse.Namespace,
    pitloom_config: PitloomConfig,
) -> _ResolvedCreationMetadata:
    """Resolve creation metadata."""
    default_creation = CreationMetadata()
    return _ResolvedCreationMetadata(
        creators=_resolve_creators(args, pitloom_config.creators),
        tools=_resolve_tools(args, pitloom_config.tools),
        creation_datetime=_resolve_creation_field(
            args.creation_datetime,
            pitloom_config.creation_datetime,
            default_creation.creation_datetime,
        ),
        creation_comment=_resolve_creation_field(
            args.creation_comment,
            pitloom_config.creation_comment,
            "Generated via Pitloom CLI",
        ),
    )


def _resolve_common_options(
    args: argparse.Namespace,
    target_dir: Path | None = None,
    load_project: bool = True,
) -> tuple[PitloomConfig, CreationMetadata, bool, bool]:
    """Resolve common settings using project config when available."""
    if load_project:
        lookup_dir = target_dir if target_dir is not None else Path.cwd()
        if lookup_dir.is_file():
            lookup_dir = lookup_dir.parent

        try:
            _, pitloom_config, _ = read_project(lookup_dir)
        except FileNotFoundError:
            pitloom_config = PitloomConfig()
    else:
        pitloom_config = PitloomConfig()

    creation = _resolve_creation_metadata(args, pitloom_config)
    effective_pretty = (
        pitloom_config.pretty
        if getattr(args, "pretty", None) is None
        else getattr(args, "pretty", False)
    )
    effective_describe_relationship = bool(
        pitloom_config.describe_relationship
        if getattr(args, "describe_relationship", None) is None
        else getattr(args, "describe_relationship", False)
    )
    return (
        pitloom_config,
        creation.to_creation_metadata(),
        effective_pretty,
        effective_describe_relationship,
    )


def _load_pitloom_tool_section(config_path: Path | None) -> dict[str, Any]:
    """Load ``[tool.pitloom]`` keys for verbose source reporting."""
    if config_path is None or config_path.name != "pyproject.toml":
        return {}

    try:
        raw_toml = load_toml_file(config_path)
        tool_section = raw_toml.get("tool")
        if not isinstance(tool_section, dict):
            return {}
        pitloom_tool = tool_section.get("pitloom")
        if not isinstance(pitloom_tool, dict):
            return {}
        return {str(key): value for key, value in pitloom_tool.items()}
    # pylint: disable=broad-exception-caught
    except Exception:
        return {}


def _resolve_output_source(
    args: argparse.Namespace, pitloom_config: PitloomConfig, config_path: Path | None
) -> str:
    if args.output is not None:
        return "command-line"
    if pitloom_config.sbom_basename:
        return config_path.name if config_path else _PROJECT_PYPROJECT_SOURCE
    return "default"


def _resolve_pretty(
    args: argparse.Namespace,
    pitloom_config: PitloomConfig,
    pitloom_tool: dict[str, Any],
    config_source: str = "pyproject.toml",
) -> tuple[bool, str]:
    value = pitloom_config.pretty if args.pretty is None else args.pretty
    if args.pretty is not None:
        return value, "command-line"
    if "pretty" in pitloom_tool:
        return value, config_source
    return value, "default"


def _resolve_describe_relationship(
    args: argparse.Namespace,
    pitloom_config: PitloomConfig,
    pitloom_tool: dict[str, Any],
    config_source: str = "pyproject.toml",
) -> tuple[bool, str]:
    value = bool(
        pitloom_config.describe_relationship
        if args.describe_relationship is None
        else args.describe_relationship
    )
    if args.describe_relationship is not None:
        return value, "command-line"
    if (
        "describe_relationship" in pitloom_tool
        or "describe-relationship" in pitloom_tool
    ):
        return value, config_source
    return value, "default"


def _quote_optional(value: str | None) -> str:
    if value is None:
        return "None"
    return f"'{value}'"


def _resolve_output_path(
    explicit: Path | None, metadata: ProjectMetadata, pitloom_config: PitloomConfig
) -> Path:
    if explicit is not None:
        return explicit
    if pitloom_config.sbom_basename:
        return Path(f"{pitloom_config.sbom_basename}{_SPDX3_JSON_EXT}")
    parts = [metadata.name] if metadata.name else ["sbom"]
    if metadata.version:
        parts.append(metadata.version)
    return Path("-".join(parts) + _SPDX3_JSON_EXT)


def _resolve_model_output_path(explicit: Path | None, model_path: Path) -> Path:
    if explicit is not None:
        return explicit
    return Path.cwd() / (model_path.name + _SPDX3_JSON_EXT)


def _resolve_hf_output_path(explicit: Path | None, model_id: str) -> Path:
    if explicit is not None:
        return explicit
    stem = model_id.split("/")[-1]
    return Path.cwd() / (stem + _SPDX3_JSON_EXT)
