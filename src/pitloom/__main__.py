# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom SBOM generator."""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitloom.__about__ import __version__
from pitloom.assemble import generate_sbom
from pitloom.core.creation import CreationMetadata

_SPDX3_JSON_EXT = ".spdx3.json"


@dataclass(frozen=True)
class _ResolvedValue:
    """A resolved option value paired with its source label."""

    value: str | None
    source: str


@dataclass(frozen=True)
class _ResolvedCreationMetadata:
    """Resolved creation metadata values and their source labels."""

    creator_name: _ResolvedValue
    creator_email: _ResolvedValue
    creation_datetime: _ResolvedValue
    creation_tool: _ResolvedValue
    creation_comment: _ResolvedValue

    def to_creation_metadata(self) -> CreationMetadata:
        """Convert resolved values to :class:`CreationMetadata`."""
        return CreationMetadata(
            creator_name=self.creator_name.value or "Pitloom",
            creator_email=self.creator_email.value or "",
            creation_datetime=self.creation_datetime.value,
            creation_tool=self.creation_tool.value,
            creation_comment=self.creation_comment.value,
        )


def _build_parser() -> argparse.ArgumentParser:
    """Create and configure the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Pitloom - Generate SPDX 3 SBOM for Python projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"Pitloom {__version__}",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose output including Pitloom version, paths, "
        "and effective options.",
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Path to the project directory (containing pyproject.toml)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Output file path. "
            "Default: <name>-<version>.spdx3.json derived from pyproject.toml, "
            "or the basename from [tool.pitloom] sbom-basename if set."
        ),
    )
    parser.add_argument(
        "--creator-name",
        dest="creation_creator_name",
        type=str,
        help="Name of the SBOM creator (default: Pitloom)",
    )
    parser.add_argument(
        "--creator-email",
        dest="creation_creator_email",
        type=str,
        help="Email of the SBOM creator",
    )
    parser.add_argument(
        "--creation-datetime",
        type=str,
        help=(
            "Creation timestamp as ISO 8601. "
            "Normalised to SPDX 3 DateTime at export "
            "(UTC, no fractional seconds)."
        ),
    )
    parser.add_argument(
        "--creation-tool",
        type=str,
        help="Name of the tool that created the SBOM (default: Pitloom)",
    )
    parser.add_argument(
        "--no-creation-tool",
        action="store_true",
        help="Omit the creation tool from the SBOM. "
        "Overrides --creation-tool and pyproject.toml.",
    )
    parser.add_argument(
        "--creation-comment",
        type=str,
        help="Comment to include in the SBOM creation information",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=None,
        help=(
            "Pretty-print the SBOM output with 2-space indentation. "
            "Overrides 'pretty' in [tool.pitloom] in pyproject.toml. "
            "Default is compact output (machine-optimized)."
        ),
    )
    parser.add_argument(
        "-d",
        "--describe-relationship",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Add descriptive text to relationships to ease human reading. "
            "Overrides 'describe-relationship' in pyproject.toml. "
            "Default is False (machine-optimized format, no extra text in SBOM)."
        ),
    )
    return parser


def _resolve_project_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    """Resolve and validate project directory and pyproject path."""
    project_dir = args.project_dir.resolve()
    if not project_dir.exists():
        print(f"Error: Project directory not found: {project_dir}", file=sys.stderr)
        return None, None

    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        print(
            f"Error: pyproject.toml not found in {project_dir}",
            file=sys.stderr,
        )
        return None, None

    return project_dir, pyproject_path


def _resolve_creation_field(
    cli_value: str | None,
    config_value: str | None,
    default_value: str | None,
) -> _ResolvedValue:
    """Resolve a creation field with precedence CLI > pyproject > default."""
    if cli_value is not None:
        return _ResolvedValue(value=cli_value, source="command-line")
    if config_value is not None:
        return _ResolvedValue(value=config_value, source="pyproject.toml")
    return _ResolvedValue(value=default_value, source="default")


def _resolve_creation_tool(
    args: argparse.Namespace,
    config_value: str | None,
    default_value: str | None,
) -> _ResolvedValue:
    """Resolve the creation tool, supporting explicit omission via CLI."""
    if args.no_creation_tool:
        return _ResolvedValue(value=None, source="command-line")
    return _resolve_creation_field(args.creation_tool, config_value, default_value)


def _resolve_creation_metadata(
    args: argparse.Namespace,
    pitloom_config: Any,
) -> _ResolvedCreationMetadata:
    """Resolve creation metadata in CreationMetadata field order."""
    default_creation = CreationMetadata()
    return _ResolvedCreationMetadata(
        creator_name=_resolve_creation_field(
            args.creation_creator_name,
            pitloom_config.creation_creator_name,
            default_creation.creator_name,
        ),
        creator_email=_resolve_creation_field(
            args.creation_creator_email,
            pitloom_config.creation_creator_email,
            default_creation.creator_email,
        ),
        creation_datetime=_resolve_creation_field(
            args.creation_datetime,
            pitloom_config.creation_creation_datetime,
            default_creation.creation_datetime,
        ),
        creation_tool=_resolve_creation_tool(
            args,
            pitloom_config.creation_creation_tool,
            default_creation.creation_tool,
        ),
        creation_comment=_resolve_creation_field(
            args.creation_comment,
            pitloom_config.creation_comment,
            default_creation.creation_comment,
        ),
    )


def _load_pitloom_tool_section(pyproject_path: Path) -> dict[str, Any]:
    """Load ``[tool.pitloom]`` as raw TOML for source reporting."""
    # pylint: disable=import-outside-toplevel
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    try:
        raw_toml = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        tool_section = raw_toml.get("tool")
        if not isinstance(tool_section, dict):
            return {}

        pitloom_tool = tool_section.get("pitloom")
        if not isinstance(pitloom_tool, dict):
            return {}

        return {str(key): value for key, value in pitloom_tool.items()}
    except Exception:  # pylint: disable=broad-exception-caught
        return {}


def _resolve_output_source(args: argparse.Namespace, pitloom_config: Any) -> str:
    """Return source label for output path choice."""
    if args.output is not None:
        return "command-line"
    if pitloom_config.sbom_basename:
        return "pyproject.toml"
    return "default"


def _resolve_pretty(
    args: argparse.Namespace,
    pitloom_config: Any,
    pitloom_tool: dict[str, Any],
) -> tuple[bool, str]:
    """Resolve effective pretty option and its source label."""
    value = pitloom_config.pretty if args.pretty is None else args.pretty
    if args.pretty is not None:
        return value, "command-line"
    if "pretty" in pitloom_tool:
        return value, "pyproject.toml"
    return value, "default"


def _resolve_describe_relationship(
    args: argparse.Namespace,
    pitloom_config: Any,
    pitloom_tool: dict[str, Any],
) -> tuple[bool, str]:
    """Resolve effective describe-relationship option and source label."""
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
        return value, "pyproject.toml"
    return value, "default"


def _quote_optional(value: str | None) -> str:
    """Render optional string values with single quotes for verbose output."""
    return f"'{value}'"


def _build_creation_option_rows(
    creation: _ResolvedCreationMetadata,
    eff_pretty: bool,
    pretty_src: str,
    eff_desc: bool,
    desc_src: str,
) -> list[tuple[str, str, str]]:
    """Build ordered rows for creation-related verbose options."""
    return [
        ("pretty", str(eff_pretty), pretty_src),
        ("describe_relationship", str(eff_desc), desc_src),
        (
            "creator_name",
            _quote_optional(creation.creator_name.value),
            creation.creator_name.source,
        ),
        (
            "creator_email",
            _quote_optional(creation.creator_email.value),
            creation.creator_email.source,
        ),
        (
            "creation_datetime",
            _quote_optional(creation.creation_datetime.value),
            creation.creation_datetime.source,
        ),
        (
            "creation_tool",
            _quote_optional(creation.creation_tool.value),
            creation.creation_tool.source,
        ),
        (
            "creation_comment",
            _quote_optional(creation.creation_comment.value),
            creation.creation_comment.source,
        ),
    ]


def _print_aligned_rows(rows: list[tuple[str, str, str]]) -> None:
    """Print rows in three aligned columns: label, value, and source."""
    label_width = max(len(label) for label, _, _ in rows)
    value_width = max(len(value) for _, value, _ in rows)
    for label, value, source in rows:
        print(f"{label:<{label_width}} : {value:<{value_width}} [{source}]")


def _print_verbose(
    args: argparse.Namespace,
    project_dir: Path,
    output_path: Path,
    pitloom_config: Any,
    pyproject_path: Path,
    creation: _ResolvedCreationMetadata,
) -> None:
    """Print verbose summary of effective CLI options and their sources."""
    pitloom_tool = _load_pitloom_tool_section(pyproject_path)
    out_src = _resolve_output_source(args, pitloom_config)
    eff_pretty, pretty_src = _resolve_pretty(args, pitloom_config, pitloom_tool)
    eff_desc, desc_src = _resolve_describe_relationship(
        args,
        pitloom_config,
        pitloom_tool,
    )

    top_rows: list[tuple[str, str, str]] = [
        ("Project directory", str(project_dir), "command-line"),
        ("Output path", str(output_path), out_src),
    ]
    option_rows = _build_creation_option_rows(
        creation,
        eff_pretty,
        pretty_src,
        eff_desc,
        desc_src,
    )
    aligned_rows = top_rows + [
        (f"  {label}", value, source) for label, value, source in option_rows
    ]

    label_width = max(len(label) for label, _, _ in aligned_rows)
    value_width = max(len(value) for _, value, _ in aligned_rows)

    def _print_row(label: str, value: str, source: str) -> None:
        print(f"{label:<{label_width}} : {value:<{value_width}} [{source}]")

    print(f"Pitloom version: {__version__}")
    for row in top_rows:
        _print_row(*row)
    print("Effective options:")
    for row in aligned_rows[2:]:
        _print_row(*row)


def _resolve_output_path(explicit: Path | None, project_dir: Path) -> Path:
    """Return the SBOM output path to use.

    Priority:
    1. Explicit ``-o`` / ``--output`` argument.
    2. ``[tool.pitloom] sbom-basename`` from ``pyproject.toml``
       → ``<basename>.spdx3.json``.
    3. ``<name>-<version>.spdx3.json`` derived from project metadata.
    4. Fallback: ``sbom.spdx3.json``.
    """
    if explicit is not None:
        return explicit

    try:
        # pylint: disable=import-outside-toplevel
        from pitloom.extract.pyproject import read_pyproject

        metadata, pitloom_config = read_pyproject(project_dir / "pyproject.toml")

        if pitloom_config.sbom_basename:
            return Path(f"{pitloom_config.sbom_basename}{_SPDX3_JSON_EXT}")

        parts = [metadata.name] if metadata.name else ["sbom"]
        if metadata.version:
            parts.append(metadata.version)
        return Path("-".join(parts) + _SPDX3_JSON_EXT)

    except Exception:  # pylint: disable=broad-exception-caught
        return Path(f"sbom{_SPDX3_JSON_EXT}")


def main() -> int:
    """Main entry point for the Pitloom CLI.

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    parser = _build_parser()
    args = parser.parse_args()

    try:
        project_dir, pyproject_path = _resolve_project_paths(args)
        if project_dir is None or pyproject_path is None:
            return 1

        # pylint: disable=import-outside-toplevel
        from pitloom.extract.pyproject import read_pyproject

        _, pitloom_config = read_pyproject(pyproject_path)
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = pitloom_config.pretty if args.pretty is None else args.pretty
        effective_describe_relationship = (
            pitloom_config.describe_relationship
            if args.describe_relationship is None
            else args.describe_relationship
        )

        output_path = _resolve_output_path(args.output, project_dir)

        if args.verbose:
            _print_verbose(
                args,
                project_dir,
                output_path,
                pitloom_config,
                pyproject_path,
                creation,
            )

        generate_sbom(
            project_dir,
            output_path=output_path,
            creation_info=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe_relationship,
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error generating SBOM: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
