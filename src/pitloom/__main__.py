# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitloom.__about__ import __version__
from pitloom.assemble import (
    generate_ai_model_sbom,
    generate_huggingface_sbom,
    generate_sbom,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import (
    VALID_CREATOR_TYPES,
    CreationMetadata,
    Creator,
    Tool,
)
from pitloom.core.project import ProjectMetadata
from pitloom.extract._huggingface import is_huggingface_source, parse_hf_model_id
from pitloom.extract.project import read_project

_SPDX3_JSON_EXT = ".spdx3.json"
_PROJECT_PYPROJECT_SOURCE = "pyproject.toml"
_PROJECT_SETUP_CFG_SOURCE = "setup.cfg"
_PROJECT_SETUP_PY_SOURCE = "setup.py"


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
    """Resolved tool list paired with its source label.

    ``value`` mirrors :attr:`CreationMetadata.tools`: ``None`` means the
    default single ``Tool`` ``"Pitloom"``; ``[]`` suppresses ``createdUsing``.
    """

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
        """Convert resolved values to :class:`CreationMetadata`.

        ``creators`` may be empty (no named creator) -- the assembler then
        emits the default ``SoftwareAgent`` ``"Pitloom"``.
        """
        return CreationMetadata(
            creators=self.creators.value,
            tools=self.tools.value,
            creation_datetime=self.creation_datetime.value,
            creation_comment=self.creation_comment.value,
        )


class _CreatorNameAction(argparse.Action):
    """``--creator-name`` starts a new :class:`Creator`, appended in order."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        creators: list[Creator] = getattr(namespace, self.dest) or []
        creators.append(Creator(name=values))
        setattr(namespace, self.dest, creators)


class _CreatorTypeAction(argparse.Action):
    """``--creator-type`` sets the type of the most recently named creator."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        creators: list[Creator] | None = getattr(namespace, self.dest)
        if not creators:
            parser.error(f"{option_string} must come after a --creator-name")
        # Reconstruct rather than mutate in-place so this routes through
        # Creator.__post_init__ normalisation/validation (defense in depth,
        # in case `choices=` on this argument is ever loosened).
        creators[-1] = Creator(
            name=creators[-1].name, type=values, email=creators[-1].email
        )


class _CreatorEmailAction(argparse.Action):
    """``--creator-email`` sets the email of the most recently named creator."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        creators: list[Creator] | None = getattr(namespace, self.dest)
        if not creators:
            parser.error(f"{option_string} must come after a --creator-name")
        # Reconstruct rather than mutate in-place, see _CreatorTypeAction.
        creators[-1] = Creator(
            name=creators[-1].name, type=creators[-1].type, email=values
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
        nargs="?",
        default=None,
        help=(
            "Path to the project directory "
            "(containing pyproject.toml, setup.cfg, or setup.py). "
            "Required unless -m/--aimodel is used."
        ),
    )
    parser.add_argument(
        "-m",
        "--aimodel",
        dest="aimodel",
        type=str,
        default=None,
        metavar="MODEL_FILE_OR_HF_URL",
        help=(
            "Path to a local AI model file, or a Hugging Face URL / model ID. "
            "Generate a standalone SBOM for the model as an AIPackage, "
            "without requiring a project directory. "
            "Local formats: GGUF, ONNX, Safetensors, PyTorch, "
            "Keras, HDF5, NumPy, fastText. "
            "Hugging Face: full URL "
            "(e.g. https://huggingface.co/mistralai/Mistral-7B-v0.1) "
            "or bare model ID (e.g. Qwen/Qwen3-235B-A22B)."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Output file path. "
            "Default: <name>-<version>.spdx3.json derived from project metadata, "
            "or the basename from [tool.pitloom] sbom-basename if set."
        ),
    )
    parser.add_argument(
        "--creator-name",
        dest="creators",
        action=_CreatorNameAction,
        default=None,
        metavar="NAME",
        help=(
            "Name of an SBOM creator (see --creator-type/--creator-email to "
            "set that creator's type/email). Repeatable: each occurrence "
            "starts a new creator, in order. When omitted, the "
            "SoftwareAgent 'Pitloom' is recorded as the automated creator."
        ),
    )
    parser.add_argument(
        "--creator-email",
        dest="creators",
        action=_CreatorEmailAction,
        default=None,
        metavar="EMAIL",
        help="Email of the most recently named --creator-name.",
    )
    parser.add_argument(
        "--creator-type",
        dest="creators",
        action=_CreatorTypeAction,
        default=None,
        choices=sorted(VALID_CREATOR_TYPES),
        metavar="TYPE",
        help=(
            "Agent subclass for the most recently named --creator-name: "
            "person (default), organization, software-agent, or agent."
        ),
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
        dest="creation_tools",
        action="append",
        type=str,
        metavar="NAME",
        help="Name of a tool that created the SBOM (default: Pitloom). "
        "Repeatable to record more than one tool.",
    )
    parser.add_argument(
        "--no-creation-tool",
        action="store_true",
        help="Omit the creation tool(s) from the SBOM. "
        "Overrides --creation-tool and pyproject.toml.",
    )
    parser.add_argument(
        "--creation-comment",
        type=str,
        help="Comment to include in the SBOM creation metadata",
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
    """Resolve and validate project directory and primary config file path.

    The second element of the tuple is the path of whichever configuration
    file was found first in priority order:
    ``pyproject.toml`` > ``setup.cfg`` > ``setup.py``.
    It is ``None`` only when the project directory itself does not exist.
    """
    project_dir = args.project_dir.resolve()
    if not project_dir.exists():
        print(f"Error: Project directory not found: {project_dir}", file=sys.stderr)
        return None, None

    for candidate in ("pyproject.toml", "setup.cfg", "setup.py"):
        config_path = project_dir / candidate
        if config_path.exists():
            return project_dir, config_path

    print(
        f"Error: No project configuration found in {project_dir}. "
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
    """Resolve the creator list with precedence CLI > pyproject > default.

    A whole-list replacement: if the CLI supplies any ``--creator-name``,
    it replaces the config's creators entirely rather than merging.
    """
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
    """Resolve the tool list, supporting explicit omission via CLI.

    A whole-list replacement, same as :func:`_resolve_creators`.
    """
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
    pitloom_config: Any,
) -> _ResolvedCreationMetadata:
    """Resolve creation metadata in CreationMetadata field order."""
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


def _load_pitloom_tool_section(config_path: Path | None) -> dict[str, Any]:
    """Load ``[tool.pitloom]`` keys for verbose source reporting.

    For ``pyproject.toml`` reads ``[tool.pitloom]`` as raw TOML.
    For other files returns an empty dict (verbose source labels default
    to ``"default"``).
    """
    if config_path is None or config_path.name != "pyproject.toml":
        return {}

    # pylint: disable=import-outside-toplevel
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    try:
        raw_toml = tomllib.loads(config_path.read_text(encoding="utf-8"))
        tool_section = raw_toml.get("tool")
        if not isinstance(tool_section, dict):
            return {}

        pitloom_tool = tool_section.get("pitloom")
        if not isinstance(pitloom_tool, dict):
            return {}

        return {str(key): value for key, value in pitloom_tool.items()}
    except Exception:  # pylint: disable=broad-exception-caught
        return {}


def _resolve_output_source(
    args: argparse.Namespace, pitloom_config: Any, config_path: Path | None
) -> str:
    """Return source label for output path choice."""
    if args.output is not None:
        return "command-line"
    if pitloom_config.sbom_basename:
        return config_path.name if config_path else _PROJECT_PYPROJECT_SOURCE
    return "default"


def _resolve_pretty(
    args: argparse.Namespace,
    pitloom_config: Any,
    pitloom_tool: dict[str, Any],
    config_source: str = _PROJECT_PYPROJECT_SOURCE,
) -> tuple[bool, str]:
    """Resolve effective pretty option and its source label."""
    value = pitloom_config.pretty if args.pretty is None else args.pretty
    if args.pretty is not None:
        return value, "command-line"
    if "pretty" in pitloom_tool:
        return value, config_source
    return value, "default"


def _resolve_describe_relationship(
    args: argparse.Namespace,
    pitloom_config: Any,
    pitloom_tool: dict[str, Any],
    config_source: str = _PROJECT_PYPROJECT_SOURCE,
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
        return value, config_source
    return value, "default"


def _quote_optional(value: str | None) -> str:
    """Render optional values, leaving ``None`` unquoted for readability."""
    if value is None:
        return "None"
    return f"'{value}'"


def _build_creation_option_rows(
    creation: _ResolvedCreationMetadata,
    eff_pretty: bool,
    pretty_src: str,
    eff_desc: bool,
    desc_src: str,
) -> list[tuple[str, str, str]]:
    """Build ordered rows for creation-related verbose options.

    Each creator and each tool is listed individually with its source, since
    both are now lists rather than single values.
    """
    rows: list[tuple[str, str, str]] = [
        ("pretty", str(eff_pretty), pretty_src),
        ("describe_relationship", str(eff_desc), desc_src),
    ]

    if creation.creators.value:
        for index, creator in enumerate(creation.creators.value, start=1):
            rows.append(
                (
                    f"creator[{index}]",
                    f"name={creator.name!r} type={creator.type!r} "
                    f"email={_quote_optional(creator.email)}",
                    creation.creators.source,
                )
            )
    else:
        rows.append(
            ("creators", "[] (SoftwareAgent 'Pitloom')", creation.creators.source)
        )

    tools_value = creation.tools.value
    if tools_value is None:
        rows.append(("tools", "None (default: 'Pitloom')", creation.tools.source))
    elif not tools_value:
        rows.append(("tools", "[] (createdUsing omitted)", creation.tools.source))
    else:
        for index, tool in enumerate(tools_value, start=1):
            rows.append(
                (f"tool[{index}]", f"name={tool.name!r}", creation.tools.source)
            )

    rows.append(
        (
            "creation_datetime",
            _quote_optional(creation.creation_datetime.value),
            creation.creation_datetime.source,
        )
    )
    rows.append(
        (
            "creation_comment",
            _quote_optional(creation.creation_comment.value),
            creation.creation_comment.source,
        )
    )
    return rows


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
    config_path: Path | None,
    creation: _ResolvedCreationMetadata,
) -> None:
    """Print verbose summary of effective CLI options and their sources."""
    pitloom_tool = _load_pitloom_tool_section(config_path)
    config_source = config_path.name if config_path else "project config"
    out_src = _resolve_output_source(args, pitloom_config, config_path)
    eff_pretty, pretty_src = _resolve_pretty(
        args, pitloom_config, pitloom_tool, config_source
    )
    eff_desc, desc_src = _resolve_describe_relationship(
        args,
        pitloom_config,
        pitloom_tool,
        config_source,
    )

    top_rows: list[tuple[str, str, str]] = [
        ("Project directory", str(project_dir), "command-line"),
        ("Config file", str(config_path) if config_path else "(none)", "command-line"),
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
    for row in aligned_rows[len(top_rows) :]:
        _print_row(*row)


def _resolve_output_path(
    explicit: Path | None, metadata: ProjectMetadata, pitloom_config: Any
) -> Path:
    """Return the SBOM output path to use.

    Priority:
    1. Explicit ``-o`` / ``--output`` argument.
    2. ``[tool.pitloom] sbom-basename`` from the project config
       -> ``<basename>.spdx3.json``.
    3. ``<name>-<version>.spdx3.json`` derived from project metadata.
    4. Fallback: ``sbom.spdx3.json``.
    """
    if explicit is not None:
        return explicit

    if pitloom_config.sbom_basename:
        return Path(f"{pitloom_config.sbom_basename}{_SPDX3_JSON_EXT}")

    parts = [metadata.name] if metadata.name else ["sbom"]
    if metadata.version:
        parts.append(metadata.version)
    return Path("-".join(parts) + _SPDX3_JSON_EXT)


def _resolve_model_output_path(explicit: Path | None, model_path: Path) -> Path:
    """Return the SBOM output path for a standalone model SBOM.

    Uses the explicit ``-o`` path when given; otherwise writes
    ``<stem>.spdx3.json`` to the current working directory.
    """
    if explicit is not None:
        return explicit
    return Path.cwd() / (model_path.stem + _SPDX3_JSON_EXT)


def _resolve_hf_output_path(explicit: Path | None, model_id: str) -> Path:
    """Return the SBOM output path for a Hugging Face model SBOM.

    Uses the explicit ``-o`` path when given; otherwise derives
    ``<model-name>.spdx3.json`` from the model ID and writes it to the
    current working directory.
    """
    if explicit is not None:
        return explicit
    # model_id is "owner/name" - use the name part as the stem
    stem = model_id.split("/")[-1]
    return Path.cwd() / (stem + _SPDX3_JSON_EXT)


def main() -> int:
    """Main entry point for the Pitloom CLI.

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    parser = _build_parser()
    args = parser.parse_args()

    if args.aimodel is not None:
        return _run_model_mode(args)

    if args.project_dir is None:
        print(
            "Error: project_dir is required unless -m/--aimodel is used.",
            file=sys.stderr,
        )
        return 1

    return _run_project_mode(args)


def _run_model_mode(args: argparse.Namespace) -> int:
    """Generate a standalone SBOM - dispatches to HF or local-file mode."""
    source: str = args.aimodel
    if is_huggingface_source(source):
        return _run_hf_model_mode(args, source)
    return _run_local_model_mode(args, source)


def _run_local_model_mode(args: argparse.Namespace, source: str) -> int:
    """Generate a standalone SBOM for a single local AI model file."""
    try:
        model_path: Path = Path(source).resolve()
        if not model_path.exists():
            print(f"Error: Model file not found: {model_path}", file=sys.stderr)
            return 1

        pitloom_config = PitloomConfig()
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = args.pretty if args.pretty is not None else False
        effective_describe = (
            bool(args.describe_relationship)
            if args.describe_relationship is not None
            else False
        )

        output_path = _resolve_model_output_path(args.output, model_path)

        if args.verbose:
            print(f"Pitloom version: {__version__}")
            print(f"Model file      : {model_path}")
            print(f"Output path     : {output_path}")

        generate_ai_model_sbom(
            model_path,
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe,
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error generating model SBOM: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


def _run_hf_model_mode(args: argparse.Namespace, source: str) -> int:
    """Generate a standalone SBOM from a Hugging Face model repository."""
    try:
        model_id = parse_hf_model_id(source)
        if model_id is None:
            print(
                f"Error: Not a valid Hugging Face URL or model ID: {source!r}",
                file=sys.stderr,
            )
            return 1

        pitloom_config = PitloomConfig()
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = args.pretty if args.pretty is not None else False
        effective_describe = (
            bool(args.describe_relationship)
            if args.describe_relationship is not None
            else False
        )

        output_path = _resolve_hf_output_path(args.output, model_id)

        if args.verbose:
            print(f"Pitloom version    : {__version__}")
            print(f"Hugging Face model : {model_id}")
            print(f"Output path        : {output_path}")

        generate_huggingface_sbom(
            model_id,
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe,
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error generating Hugging Face model SBOM: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


def _run_project_mode(args: argparse.Namespace) -> int:
    """Generate a full project SBOM from a project directory."""
    try:
        project_dir, _ = _resolve_project_paths(args)
        if project_dir is None:
            return 1

        project_metadata, pitloom_config, config_path = read_project(project_dir)
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = pitloom_config.pretty if args.pretty is None else args.pretty
        effective_describe_relationship = (
            pitloom_config.describe_relationship
            if args.describe_relationship is None
            else args.describe_relationship
        )

        output_path = _resolve_output_path(
            args.output, project_metadata, pitloom_config
        )

        if args.verbose:
            _print_verbose(
                args,
                project_dir,
                output_path,
                pitloom_config,
                config_path,
                creation,
            )

        generate_sbom(
            project_dir,
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe_relationship,
            project_metadata=project_metadata,
            pitloom_config=pitloom_config,
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error generating SBOM: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
