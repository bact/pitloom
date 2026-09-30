# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Config-cascade resolution helpers shared by the CLI command handlers.

Resolves effective settings (creation metadata, ``pretty``/
``describe_relationship``, output paths, project paths) from the
CLI-flag > ``[tool.pitloom]`` > default precedence cascade. Split out
of :mod:`pitloom.cli.options` once that file crossed the ~400-500 line
soft limit -- that module keeps the ``add_*_argument()``/``warn_*()``
flag-definition helpers; this one owns the "what value actually wins"
logic that runs after argparse has already produced *args*.

See also: :mod:`pitloom.cli.options`, re-exported from there for every
existing call site (``from pitloom.cli.options import ...``) so this
split needed no import-site changes.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitloom._toml_io import load_toml_file
from pitloom.cli.constants import (
    _PROJECT_CONFIG_FILES,
    _PROJECT_PYPROJECT_SOURCE,
    _PROJECT_SETUP_CFG_SOURCE,
    _PROJECT_SETUP_PY_SOURCE,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import load_config_file
from pitloom.core.creation import (
    CreationMetadata,
    Creator,
    Tool,
)
from pitloom.core.project import ProjectMetadata, is_sdist_archive
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.extract.project import (
    resolve_project_with_lockfile,
    sdist_config_source,
)


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


def _resolve_project_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    """Resolve and validate project directory or sdist archive path."""
    project_dir = args.project_dir.resolve()
    if not project_dir.exists():
        print(f"ERROR: project directory not found: {project_dir}", file=sys.stderr)
        return None, None

    if project_dir.is_file():
        return project_dir, project_dir

    for candidate in _PROJECT_CONFIG_FILES:
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
    config_source: str,
) -> _ResolvedValue:
    """Resolve a creation field with precedence CLI > config > default."""
    if cli_value is not None:
        return _ResolvedValue(value=cli_value, source="command-line")
    if config_value is not None:
        return _ResolvedValue(value=config_value, source=config_source)
    return _ResolvedValue(value=default_value, source="default")


def _resolve_creators(
    args: argparse.Namespace,
    config_creators: list[Creator],
    config_source: str,
) -> _ResolvedCreators:
    """Resolve the creator list with precedence CLI > config > default."""
    cli_creators: list[Creator] | None = args.creators
    if cli_creators:
        return _ResolvedCreators(value=cli_creators, source="command-line")
    if config_creators:
        return _ResolvedCreators(value=config_creators, source=config_source)
    return _ResolvedCreators(value=[], source="default")


def _resolve_tools(
    args: argparse.Namespace,
    config_tools: list[Tool] | None,
    config_source: str,
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
        return _ResolvedTools(value=config_tools, source=config_source)
    return _ResolvedTools(value=None, source="default")


def _resolve_creation_metadata(
    args: argparse.Namespace,
    pitloom_config: PitloomConfig,
    config_source: str = _PROJECT_PYPROJECT_SOURCE,
) -> _ResolvedCreationMetadata:
    """Resolve creation metadata; *config_source* labels a value taken
    from *pitloom_config* for ``--verbose``."""
    default_creation = CreationMetadata()
    return _ResolvedCreationMetadata(
        creators=_resolve_creators(args, pitloom_config.creators, config_source),
        tools=_resolve_tools(args, pitloom_config.tools, config_source),
        creation_datetime=_resolve_creation_field(
            args.creation_datetime,
            pitloom_config.creation_datetime,
            default_creation.creation_datetime,
            config_source,
        ),
        creation_comment=_resolve_creation_field(
            args.creation_comment,
            pitloom_config.creation_comment,
            "Generated via Pitloom CLI",
            config_source,
        ),
    )


def load_explicit_config(args: argparse.Namespace) -> PitloomConfig | None:
    """Load ``--config FILE``, or ``None`` when it was not given.

    Raises:
        FileNotFoundError, ValueError, OSError: the named file is missing,
            invalid or unreadable -- fatal, since the user asked for it
            (see :func:`~pitloom.core.config_cascade.load_config_file`).
    """
    path: Path | None = getattr(args, "config", None)
    if path is None:
        return None
    return load_config_file(path)


def _resolve_bool_cascade(cli_value: bool | None, config_value: bool | None) -> bool:
    """The one CLI-flag > ``[tool.pitloom]`` > default precedence rule
    for a boolean option, factored out so every caller that needs it
    (the plain value-only cascade below, and the ``--verbose``
    source-reporting resolvers further down) shares the exact same
    expression -- see AGENTS.md's "pattern hand-copied across 3+ call
    sites drifts" rule: a change to the precedence rule applied to only
    some callers would make ``--verbose`` silently report the wrong
    source for the value the SBOM actually used. Returns ``bool``, not
    ``bool | None`` (``config_value`` can itself be ``None`` for an
    unset ``describe_relationship``) -- callers should never have to
    remember their own ``bool(...)`` wrap to get a strict boolean.
    """
    return bool(config_value if cli_value is None else cli_value)


def _resolve_project_generation_settings(
    args: argparse.Namespace, project_dir: Path
) -> tuple[ProjectMetadata, PitloomConfig, Path | None, _ResolvedCreationMetadata]:
    """Resolve *project_dir*'s metadata, the config that applies to it and
    its creation metadata in one call -- the sequence every
    project-target SBOM command needs (``loom project`` and ``loom
    generate`` on a project directory or sdist), kept in one place.

    ``--config FILE`` replaces the project's own ``[tool.pitloom]``, and the
    returned config path is then that file, so ``--verbose`` names the
    config that actually applied. Its ``use-lockfile`` decides the lock-file
    cascade when ``--use-lockfile`` is not given.
    """
    explicit = load_explicit_config(args)
    project_metadata, pitloom_config, config_path = resolve_project_with_lockfile(
        project_dir, args.use_lockfile, explicit
    )
    if explicit is not None:
        config_path = args.config
    creation = _resolve_creation_metadata(
        args, pitloom_config, config_source_label(config_path)
    )
    return project_metadata, pitloom_config, config_path, creation


def config_file_display(config_path: Path | None) -> str:
    """The ``--verbose`` "Config file" value: the path, or for an sdist
    archive member ``<archive path>:<member>`` (the member is not a file)."""
    if config_path is None:
        return "(none)"
    if is_sdist_archive(config_path.parent):
        return f"{config_path.parent}:{config_path.name}"
    return str(config_path)


def config_source_label(config_path: Path | None) -> str:
    """The ``--verbose`` label for a value taken from the config at
    *config_path* -- the project's own, a ``--config`` file, or a member of
    an sdist archive (``<archive>/<member>``, labelled ``x.tar.gz:member``)."""
    if config_path is None:
        return _PROJECT_PYPROJECT_SOURCE
    if is_sdist_archive(config_path.parent):
        return f"{config_path.parent.name}:{config_path.name}"
    return config_path.name


def _load_pitloom_tool_section(config_path: Path | None) -> dict[str, Any]:
    """Load ``[tool.pitloom]`` keys for verbose source reporting, from a
    project's ``pyproject.toml``, a ``--config`` file of any name, or an sdist
    archive's own ``pyproject.toml`` member."""
    if (
        config_path is None
        or config_path.name in (_PROJECT_SETUP_CFG_SOURCE, _PROJECT_SETUP_PY_SOURCE)
        or is_sdist_archive(config_path)
    ):
        return {}
    if is_sdist_archive(config_path.parent):
        return dict(sdist_config_source(config_path.parent)[1])

    try:
        raw_toml = load_toml_file(config_path)
        tool_section = raw_toml.get("tool")
        if not isinstance(tool_section, dict):
            return {}
        pitloom_tool = tool_section.get("pitloom")
        if not isinstance(pitloom_tool, dict):
            return {}
        return {str(key): value for key, value in pitloom_tool.items()}
    # pylint: disable-next=broad-exception-caught
    except Exception:
        return {}


def _resolve_output_source(
    args: argparse.Namespace, pitloom_config: PitloomConfig, config_path: Path | None
) -> str:
    if args.output is not None:
        return "command-line"
    if pitloom_config.sbom_basename:
        return config_source_label(config_path)
    return "default"


def _resolve_pretty(
    args: argparse.Namespace,
    pitloom_config: PitloomConfig,
    pitloom_tool: dict[str, Any],
    config_source: str = "pyproject.toml",
) -> tuple[bool, str]:
    value = _resolve_bool_cascade(args.pretty, pitloom_config.pretty)
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
    value = _resolve_bool_cascade(
        args.describe_relationship, pitloom_config.describe_relationship
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
        return Path(f"{pitloom_config.sbom_basename}{SPDX3_JSONLD_EXTENSION}")
    parts = [metadata.name] if metadata.name else ["sbom"]
    if metadata.version:
        parts.append(metadata.version)
    return Path("-".join(parts) + SPDX3_JSONLD_EXTENSION)


def _resolve_model_output_path(explicit: Path | None, model_path: Path) -> Path:
    if explicit is not None:
        return explicit
    return Path.cwd() / (model_path.name + SPDX3_JSONLD_EXTENSION)


def _resolve_hf_output_path(explicit: Path | None, model_id: str) -> Path:
    if explicit is not None:
        return explicit
    stem = model_id.split("/")[-1]
    return Path.cwd() / (stem + SPDX3_JSONLD_EXTENSION)
