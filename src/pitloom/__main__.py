# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from pitloom.__about__ import __version__
from pitloom.assemble import (
    embed_sbom_in_wheel,
    embed_wheel_sbom,
    enrich_model,
    generate,
    generate_env_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
    merge_fragments,
)
from pitloom.core.config import VALID_CONTENT_TYPE_METHODS, PitloomConfig
from pitloom.core.creation import (
    VALID_CREATOR_TYPES,
    CreationMetadata,
    Creator,
    Tool,
)
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract._huggingface import is_huggingface_source, parse_hf_model_id
from pitloom.extract.project import read_project
from pitloom.ids import DEFAULT_REGISTRY_FILENAME, IdRegistry

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
        if creators is None or len(creators) == 0:
            parser.error(f"{option_string} must come after a --creator-name")
            return  # type: ignore[unreachable]
        creators[-1] = Creator(
            name=creators[-1].name,
            type=values,
            email=creators[-1].email,
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
        if creators is None or len(creators) == 0:
            parser.error(f"{option_string} must come after a --creator-name")
            return  # type: ignore[unreachable]
        creators[-1] = Creator(
            name=creators[-1].name,
            type=creators[-1].type,
            email=values,
        )


def _build_parent_parser() -> argparse.ArgumentParser:
    """Build shared parent parser with common options."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="FILE",
        help="Write JSON-LD SBOM to FILE.",
    )
    parent.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Indent JSON output with 2 spaces.",
    )
    parent.add_argument(
        "--describe-relationship",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include human-readable text on SPDX relationships.",
    )
    parent.add_argument(
        "--enrich",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Run local README/model-card enrichment for discovered AI "
            "models. Defers to [tool.pitloom] enrich (off by default) "
            "when omitted."
        ),
    )
    parent.add_argument(
        "--extract-file-header",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Scan each source file's leading comment header for SPDX-File* "
            "tags (FileCopyrightText, FileContributor, FileType) and a "
            "per-file SPDX-License-Identifier. Defers to "
            "[tool.pitloom] extract-file-header (on by default) when "
            "omitted."
        ),
    )
    parent.add_argument(
        "--content-type",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Detect each file's real content type via magika/mimetypes, "
            "independent of --extract-file-header. Defers to "
            "[tool.pitloom.content-type] enabled (off by default -- real "
            "per-file cost) when omitted."
        ),
    )
    parent.add_argument(
        "--content-type-method",
        choices=VALID_CONTENT_TYPE_METHODS,
        default=None,
        help=(
            "Which detector resolves --content-type's contentType values: "
            "'auto' (try magika, fall back to a filename-extension guess), "
            "'magika' (same, but error immediately if the magika package "
            "isn't installed), or 'extension' (skip magika entirely, "
            "stdlib-only). Defers to [tool.pitloom.content-type] method "
            "('auto' by default) when omitted."
        ),
    )
    parent.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose execution and option details.",
    )
    parent.add_argument(
        "--registry",
        type=Path,
        default=None,
        metavar="FILE",
        help="Loom ID registry JSON file path.",
    )

    creator_group = parent.add_argument_group("Creator metadata")
    creator_group.add_argument(
        "--creator-name",
        action=_CreatorNameAction,
        dest="creators",
        default=None,
        metavar="NAME",
        help="Name of creator.",
    )
    creator_group.add_argument(
        "--creator-type",
        action=_CreatorTypeAction,
        dest="creators",
        default=None,
        choices=VALID_CREATOR_TYPES,
        metavar="TYPE",
        help=f"Type of creator ({', '.join(VALID_CREATOR_TYPES)}).",
    )
    creator_group.add_argument(
        "--creator-email",
        action=_CreatorEmailAction,
        dest="creators",
        default=None,
        metavar="EMAIL",
        help="Email of creator.",
    )
    creator_group.add_argument(
        "--creation-tool",
        action="append",
        dest="creation_tools",
        default=None,
        metavar="NAME",
        help="Tool name used to create SBOM.",
    )
    creator_group.add_argument(
        "--no-creation-tool",
        action="store_true",
        help="Omit createdUsing tool list.",
    )
    creator_group.add_argument(
        "--creation-datetime",
        default=None,
        metavar="ISO8601",
        help="Creation timestamp in UTC ISO 8601 format.",
    )
    creator_group.add_argument(
        "--creation-comment",
        default=None,
        metavar="TEXT",
        help="Comment string for CreationInfo.",
    )
    return parent


def _build_parser() -> argparse.ArgumentParser:
    """Build the main CLI ArgumentParser."""
    parent_parser = _build_parent_parser()

    parser = argparse.ArgumentParser(
        prog="loom",
        description="Pitloom - Generate SPDX 3 SBOMs for Python projects and AI models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"Pitloom {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Smart Entrypoint: loom generate [TARGET]
    gen_parser = subparsers.add_parser(
        "generate",
        parents=[parent_parser],
        help="Generate an SBOM with automatic target detection.",
    )
    gen_parser.add_argument(
        "target",
        type=str,
        nargs="?",
        default=".",
        help="Target path, sdist archive, .whl, model file, HF URL, or 'env'.",
    )
    gen_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access; effect depends on the resolved target -- "
            "HF URL/ID: error, no fetch attempted (no local fallback exists). "
            "project dir / .whl: skip PyPI lookup, no error (local metadata "
            "already covers what it can). "
            "local model file: no-op (no network path exists)."
        ),
    )

    # 2. Project Source & Sdist: loom project [PATH]
    proj_parser = subparsers.add_parser(
        "project",
        parents=[parent_parser],
        help="Generate a Source SBOM from a project directory or sdist archive.",
    )
    proj_parser.add_argument(
        "project_dir",
        type=Path,
        nargs="?",
        default=Path.cwd(),
        help="Path to project directory or sdist archive (.tar.gz, .zip).",
    )
    proj_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access -- skip PyPI lookup, no error "
            "(local metadata already covers what it can)."
        ),
    )

    # 3. Built Wheel: loom wheel <WHEEL_FILE>
    wheel_parser = subparsers.add_parser(
        "wheel",
        parents=[parent_parser],
        help="Generate an Analyzed SBOM from a built wheel (.whl).",
    )
    wheel_parser.add_argument(
        "target",
        type=str,
        help="Path to the built .whl file.",
    )
    wheel_parser.add_argument(
        "--embed",
        action="store_true",
        help="Embed the generated SBOM directly into the wheel archive (PEP 770).",
    )
    wheel_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access -- skip PyPI lookup, no error "
            "(local metadata already covers what it can)."
        ),
    )

    # 3b. Embed into Wheel: loom embed-wheel <WHEEL_FILES...>
    embed_parser = subparsers.add_parser(
        "embed-wheel",
        parents=[parent_parser],
        help="Embed an SPDX 3 SBOM into one or more built wheels (PEP 770).",
    )
    embed_parser.add_argument(
        "wheel_files",
        type=str,
        nargs="+",
        help="Path(s) or glob pattern(s) of built .whl file(s) to embed the SBOM into.",
    )
    embed_parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Project directory containing pyproject.toml to extract project "
            "metadata, AI models, and file headers from (defaults to cwd)."
        ),
    )
    embed_parser.add_argument(
        "--sbom",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Pre-generated SBOM JSON file to embed directly instead of generating one."
        ),
    )
    embed_parser.add_argument(
        "--sbom-basename",
        type=str,
        default=None,
        metavar="NAME",
        help="Custom basename for the embedded SBOM inside .dist-info/sboms/.",
    )
    embed_parser.add_argument(
        "--offline",
        action="store_true",
        help="Forbid network access during SBOM generation.",
    )

    # 4. AI Model Asset: loom model <SOURCE> [--offline]
    model_parser = subparsers.add_parser(
        "model",
        parents=[parent_parser],
        help="Generate an AI Model SBOM (AIBOM) from a local file or HF repo.",
    )
    model_parser.add_argument(
        "target",
        type=str,
        help="Path to local AI model file or Hugging Face URL / model ID.",
    )
    model_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access; effect depends on the resolved target -- "
            "HF URL/ID: error, no fetch attempted (no local fallback exists). "
            "local model file: no-op (no network path exists)."
        ),
    )

    # 4b. Enrichment only: loom enrich <SOURCE>
    enrich_parser = subparsers.add_parser(
        "enrich",
        parents=[parent_parser],
        help=(
            "Run enrichment only for a local AI model file; write a "
            "standalone fragment for merging into a base SBOM."
        ),
    )
    enrich_parser.add_argument(
        "target",
        type=str,
        help="Path to a local AI model file.",
    )
    enrich_parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Project root the model belongs to, when the fragment will "
            "merge into a 'loom project'/'loom generate <dir>'-generated "
            "base document rather than a 'loom model'-generated one. "
            "Required for a correct merge in that case -- project-level "
            "and single-model documents assign the model's ai_AIPackage "
            "a different id."
        ),
    )

    # 5. Deployed Environment: loom env
    env_parser = subparsers.add_parser(
        "env",
        parents=[parent_parser],
        help="Generate a Deployed SBOM for the active installed environment.",
    )
    env_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access -- skip PyPI lookup, no error "
            "(local metadata already covers what it can)."
        ),
    )

    # 6. Fragment Merger: loom merge <FRAGMENTS_DIR>
    merge_parser = subparsers.add_parser(
        "merge",
        help="Merge dynamic execution SBOM fragments into a combined SBOM.",
    )
    merge_parser.add_argument(
        "fragments_dir",
        type=Path,
        help="Directory containing .spdx3.json fragments.",
    )
    merge_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.cwd() / f"merged{_SPDX3_JSON_EXT}",
        help="Output JSON-LD path.",
    )
    merge_parser.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Indent JSON output with 2 spaces.",
    )

    # 7. Registry Management: loom ids
    _add_ids_subparser(subparsers)

    return parser


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
    pitloom_config: Any,
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


def _resolve_generate_mode_settings(
    args: argparse.Namespace,
) -> tuple[CreationMetadata, bool | None, bool | None]:
    """Resolve settings for ``loom generate`` using project config when available."""
    pitloom_config = PitloomConfig()
    target_value = str(args.target).strip()
    if target_value:
        target_path = Path(target_value)
        if target_path.exists():
            try:
                _, pitloom_config, _ = read_project(target_path)
            except FileNotFoundError:
                pitloom_config = PitloomConfig()

    creation = _resolve_creation_metadata(args, pitloom_config)
    effective_pretty = pitloom_config.pretty if args.pretty is None else args.pretty
    effective_describe_relationship = (
        pitloom_config.describe_relationship
        if args.describe_relationship is None
        else args.describe_relationship
    )
    return (
        creation.to_creation_metadata(),
        effective_pretty,
        effective_describe_relationship,
    )


def _load_pitloom_tool_section(config_path: Path | None) -> dict[str, Any]:
    """Load ``[tool.pitloom]`` keys for verbose source reporting."""
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


def _build_creation_option_rows(
    creation: _ResolvedCreationMetadata,
    eff_pretty: bool,
    pretty_src: str,
    eff_desc: bool,
    desc_src: str,
) -> list[tuple[str, str, str]]:
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


def _print_verbose(
    args: argparse.Namespace,
    project_dir: Path,
    output_path: Path,
    pitloom_config: Any,
    config_path: Path | None,
    creation: _ResolvedCreationMetadata,
) -> None:
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


def _configure_logging() -> None:
    """Prefix internal ``log.warning(...)`` output with ``WARNING: ``.

    Without this, Python's last-resort handler prints library warnings
    (``pitloom.ids``, ``pitloom.loom``, etc.) to stderr with no prefix at
    all, breaking the CLI's shared grep-able ``LEVEL: <description>``
    convention (see ``ERROR:``, used by this module's own ``print()``
    calls). Reconfigures on every call rather than guarding with a
    "configured once" flag, so repeated ``main()`` calls in the same
    process (e.g. across tests) don't stack duplicate handlers.
    Propagation to the root logger is left untouched, so ``pytest``'s
    ``caplog`` fixture still captures these records.
    """
    logger = logging.getLogger("pitloom")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)


def main() -> int:
    """Main entry point for the Pitloom CLI."""
    _configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    handlers = {
        "ids": _run_ids_cli,
        "generate": _run_generate_mode,
        "project": _run_project_mode,
        "wheel": _run_wheel_mode,
        "embed-wheel": _run_embed_wheel_mode,
        "model": _run_model_mode,
        "enrich": _run_enrich_mode,
        "env": _run_env_mode,
        "merge": _run_merge_mode,
    }
    handler = handlers.get(args.command)
    if handler is not None:
        return handler(args)
    return 1


def _run_generate_mode(args: argparse.Namespace) -> int:
    """Smart generate mode."""
    try:
        creation_metadata, pretty, describe_relationship = (
            _resolve_generate_mode_settings(args)
        )
        output_path = args.output
        generate(
            args.target,
            offline=args.offline or None,
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=args.registry,
            enrich=args.enrich,
            extract_file_header=args.extract_file_header,
            content_type=args.content_type,
            content_type_method=args.content_type_method,
        )
        return 0
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: SBOM generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def _run_project_mode(args: argparse.Namespace) -> int:
    """Generate a Source SBOM from a project directory or sdist archive."""
    try:
        project_dir, config_path = _resolve_project_paths(args)
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

        generate_project_sbom(
            project_dir,
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe_relationship,
            project_metadata=project_metadata,
            pitloom_config=pitloom_config,
            registry=args.registry,
            enrich=args.enrich,
            offline=args.offline or None,
            extract_file_header=args.extract_file_header,
            content_type=args.content_type,
            content_type_method=args.content_type_method,
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: SBOM generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def _run_wheel_mode(args: argparse.Namespace) -> int:
    """Generate an Analyzed SBOM from a built wheel."""
    target: str = args.target
    try:
        wheel_path: Path = Path(target).resolve()
        if not wheel_path.exists():
            print(f"ERROR: wheel file not found: {wheel_path}", file=sys.stderr)
            return 1

        pitloom_config = PitloomConfig()
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = args.pretty if args.pretty is not None else False
        effective_describe = (
            bool(args.describe_relationship)
            if args.describe_relationship is not None
            else False
        )

        output_path = args.output or (
            Path.cwd() / f"{wheel_path.name}{_SPDX3_JSON_EXT}"
        )

        if args.verbose:
            print(f"Pitloom version : {__version__}")
            print(f"Wheel file      : {wheel_path}")
            print(f"Output path     : {output_path}")

        sbom_json = generate_wheel_sbom(
            wheel_path,
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe,
            registry=args.registry,
            offline=args.offline or None,
        )

        if getattr(args, "embed", False):
            _, arcname = embed_sbom_in_wheel(wheel_path, sbom_json)
            print(f"pitloom: embedded {arcname} into {wheel_path.name}")

        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: wheel SBOM generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def _collect_wheel_paths(patterns: list[str]) -> list[Path]:
    """Resolve and expand wheel file paths and glob patterns.

    Every pattern is validated before returning, so all invalid literal
    paths get reported -- not just the first one encountered. Returns an
    empty list if any pattern is invalid.
    """
    wheel_paths: list[Path] = []
    had_error = False
    for pattern in patterns:
        if any(c in pattern for c in ("*", "?", "[")):
            matched = [
                p
                for p in Path.cwd().glob(pattern)
                if p.is_file() and p.name.endswith(".whl")
            ]
            if not matched:
                p_obj = Path(pattern)
                parent = p_obj.parent if p_obj.parent != Path(".") else Path.cwd()
                matched = [
                    p
                    for p in parent.glob(p_obj.name)
                    if p.is_file() and p.name.endswith(".whl")
                ]
            wheel_paths.extend(matched)
        else:
            p = Path(pattern).resolve()
            if not p.exists():
                print(f"ERROR: wheel file not found: {p}", file=sys.stderr)
                had_error = True
                continue
            if not p.name.endswith(".whl"):
                print(f"ERROR: not a .whl file: {p}", file=sys.stderr)
                had_error = True
                continue
            wheel_paths.append(p)
    if had_error:
        return []
    return list(dict.fromkeys(wheel_paths))


def _run_embed_wheel_mode(args: argparse.Namespace) -> int:
    """Embed an SPDX 3 SBOM into one or more built wheels (PEP 770)."""
    try:
        unique_wheels = _collect_wheel_paths(args.wheel_files)
        if not unique_wheels:
            if not any(
                any(c in pat for c in ("*", "?", "[")) for pat in args.wheel_files
            ):
                return 1
            print(
                f"ERROR: no wheel files matched: {' '.join(args.wheel_files)}",
                file=sys.stderr,
            )
            return 1

        project_dir = args.project_dir
        pitloom_config = PitloomConfig()
        if project_dir is not None:
            proj_path = Path(project_dir).resolve()
            if not proj_path.exists():
                print(
                    f"ERROR: project directory not found: {proj_path}",
                    file=sys.stderr,
                )
                return 1
            try:
                _, pitloom_config, _ = read_project(proj_path)
            except FileNotFoundError:
                pass
        else:
            for cand in ("pyproject.toml", "setup.cfg", "setup.py"):
                if (Path.cwd() / cand).exists():
                    try:
                        _, pitloom_config, _ = read_project(Path.cwd())
                    except FileNotFoundError:
                        pass
                    break

        creation = _resolve_creation_metadata(args, pitloom_config)

        for wheel_path in unique_wheels:
            output_path = args.output if len(unique_wheels) == 1 else None
            _, arcname, _ = embed_wheel_sbom(
                wheel_path,
                project_dir=project_dir,
                sbom_path=args.sbom,
                output_path=output_path,
                sbom_basename=args.sbom_basename,
                creation_metadata=creation.to_creation_metadata(),
                registry=args.registry,
                enrich=args.enrich,
                extract_file_header=args.extract_file_header,
                content_type=args.content_type,
                content_type_method=args.content_type_method,
                offline=args.offline or None,
            )
            print(f"pitloom: embedded {arcname} into {wheel_path.name}")
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: wheel SBOM embedding failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def _run_model_mode(args: argparse.Namespace) -> int:
    """Generate an AI Model SBOM from a local file or HF repository."""
    target: str = args.target
    try:
        model_target: Path | str
        if is_huggingface_source(target):
            model_id = parse_hf_model_id(target)
            if model_id is None:
                print(
                    f"ERROR: not a valid Hugging Face URL or model ID: {target!r}",
                    file=sys.stderr,
                )
                return 1
            output_path = _resolve_hf_output_path(args.output, model_id)
            if args.verbose:
                print(f"Pitloom version    : {__version__}")
                print(f"Hugging Face model : {model_id}")
                print(f"Output path        : {output_path}")
            model_target = model_id
        else:
            model_path: Path = Path(target).resolve()
            if not model_path.exists():
                print(f"ERROR: model file not found: {model_path}", file=sys.stderr)
                return 1
            output_path = _resolve_model_output_path(args.output, model_path)
            if args.verbose:
                print(f"Pitloom version: {__version__}")
                print(f"Model file      : {model_path}")
                print(f"Output path     : {output_path}")
            model_target = model_path

        pitloom_config = PitloomConfig()
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = args.pretty if args.pretty is not None else False
        effective_describe = (
            bool(args.describe_relationship)
            if args.describe_relationship is not None
            else False
        )

        generate_model_sbom(
            model_target,
            offline=args.offline or None,
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe,
            registry=args.registry,
            enrich=args.enrich,
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: model SBOM generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def _run_enrich_mode(args: argparse.Namespace) -> int:
    """Run enrichment only for a local AI model file; write a fragment."""
    target: str = args.target
    try:
        model_path: Path = Path(target).resolve()
        if not model_path.exists():
            print(f"ERROR: model file not found: {model_path}", file=sys.stderr)
            return 1

        pitloom_config = PitloomConfig()
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = args.pretty if args.pretty is not None else False

        output_path = args.output or (
            Path.cwd() / f"{model_path.name}.enrich{_SPDX3_JSON_EXT}"
        )

        if args.verbose:
            print(f"Pitloom version: {__version__}")
            print(f"Model file      : {model_path}")
            print(f"Output path     : {output_path}")
            if args.project_dir:
                print(f"Project dir     : {args.project_dir}")

        enrich_model(
            model_path,
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            enrich=args.enrich,
            project_target=args.project_dir,
            registry=args.registry,
        )
        print(f"Enrichment fragment written to: {output_path}")
        print(
            "Register it under [tool.pitloom.fragment] and re-run "
            "'loom project'/'loom generate' to merge it into a base SBOM."
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: enrichment fragment generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def _run_env_mode(args: argparse.Namespace) -> int:
    """Generate a Deployed SBOM for the active installed environment."""
    try:
        pitloom_config = PitloomConfig()
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = args.pretty if args.pretty is not None else False
        effective_describe = (
            bool(args.describe_relationship)
            if args.describe_relationship is not None
            else False
        )

        output_path = args.output or (
            Path.cwd() / f"deployed-environment{_SPDX3_JSON_EXT}"
        )

        if args.verbose:
            print(f"Pitloom version : {__version__}")
            print(f"Output path     : {output_path}")

        generate_env_sbom(
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe,
            registry=args.registry,
            offline=args.offline or None,
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: deployed SBOM generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def _run_merge_mode(args: argparse.Namespace) -> int:
    """Merge dynamic execution fragments into a combined SBOM."""
    try:
        fragments_dir: Path = args.fragments_dir.resolve()
        if not fragments_dir.exists():
            print(
                f"ERROR: fragments directory not found: {fragments_dir}",
                file=sys.stderr,
            )
            return 1

        fragment_files = [
            f.relative_to(fragments_dir).as_posix()
            for f in sorted(fragments_dir.glob("*.json"))
            if f.is_file()
        ]
        if not fragment_files:
            print(
                f"ERROR: no JSON fragment files found in {fragments_dir}",
                file=sys.stderr,
            )
            return 1

        exporter = Spdx3JsonExporter()
        merge_fragments(fragments_dir, fragment_files, exporter)

        sbom_json = exporter.to_json(pretty=bool(args.pretty))
        output_path: Path = args.output
        if str(output_path) == "-":
            sys.stdout.write(sbom_json)
            if not sbom_json.endswith("\n"):
                sys.stdout.write("\n")
        else:
            output_path.write_text(sbom_json, encoding="utf-8")
            print(
                f"pitloom: merged {len(fragment_files)} fragment(s) into {output_path}"
            )
        return 0
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: fragment merge failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# `pitloom ids` -- Loom ID registry management
# ---------------------------------------------------------------------------

_DEFAULT_IDS_GENERATE_DIR_NAMES: tuple[str, ...] = ("src", "data", "models")


def _load_or_create_registry(
    registry_path: Path, project_dir_name: str
) -> IdRegistry | None:
    """Load existing registry from registry_path or return a new one."""
    if registry_path.exists():
        try:
            return IdRegistry.load(registry_path)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(
                f"ERROR: failed to load registry from {registry_path}: {exc}",
                file=sys.stderr,
            )
            return None

    namespace = f"https://spdx.org/spdxdocs/{project_dir_name}-{uuid4()}"
    return IdRegistry(namespace=namespace)


def _default_ids_generate_paths(project_dir: Path) -> list[Path]:
    """Return default candidate paths for `pitloom ids generate`."""
    return [
        project_dir / name
        for name in _DEFAULT_IDS_GENERATE_DIR_NAMES
        if (project_dir / name).exists()
    ]


def _add_ids_subparser(subparsers: Any) -> None:
    """Add the ``ids`` subcommand to the main parser."""
    ids_parser = subparsers.add_parser(
        "ids",
        help="Manage the Loom ID registry.",
        description=(
            "Manage the Loom ID registry, a stable file/entity -> SPDX ID "
            "registry consulted by 'pitloom.loom', the Hatchling build hook, "
            "and the CLI."
        ),
    )
    ids_subparsers = ids_parser.add_subparsers(dest="ids_command", required=True)

    gen_parser = ids_subparsers.add_parser(
        "generate",
        help="Index files (and detected AI models) under PATHs into the registry.",
    )
    gen_parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=None,
        help="Files or directories to index.",
    )
    gen_parser.add_argument(
        "-o",
        "--registry",
        type=Path,
        default=None,
        metavar="FILE",
        help="Registry file to update.",
    )
    gen_parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Project directory root.",
    )
    gen_parser.add_argument(
        "-e",
        "--entity",
        action="append",
        default=None,
        metavar="NAME[:TYPE]",
        help="Explicit entity name to register.",
    )

    imp_parser = ids_subparsers.add_parser(
        "import",
        help="Import entries from an external SBOM file.",
    )
    imp_parser.add_argument(
        "sbom",
        type=Path,
        help="Source SBOM JSON file to import.",
    )
    imp_parser.add_argument(
        "-o",
        "--registry",
        type=Path,
        default=None,
        metavar="FILE",
        help="Registry file to update.",
    )


def _run_ids_generate(args: argparse.Namespace) -> int:
    """Run `pitloom ids generate`."""
    project_dir: Path = (args.project_dir or Path.cwd()).resolve()
    registry_path = (
        (project_dir / args.registry).resolve()
        if args.registry
        else (project_dir / DEFAULT_REGISTRY_FILENAME)
    )

    registry = _load_or_create_registry(registry_path, project_dir.name)
    if registry is None:
        return 1

    paths: list[Path] = args.paths or _default_ids_generate_paths(project_dir)
    if not paths:
        print(
            f"ERROR: no source/data directories found under {project_dir}; "
            "pass explicit PATH argument(s).",
            file=sys.stderr,
        )
        return 1

    registry.generate(paths, project_dir)
    for entity_spec in args.entity or []:
        name, _, type_name = entity_spec.partition(":")
        registry.register_entity(name, type_name or "ai_AIPackage")
    registry.save(registry_path)
    print(
        f"pitloom ids: wrote {len(registry.files)} file(s) and "
        f"{len(registry.entities)} entit(y/ies) to {registry_path}"
    )
    return 0


def _run_ids_import(args: argparse.Namespace) -> int:
    """Run `pitloom ids import`."""
    sbom_path: Path = args.sbom.resolve()
    if not sbom_path.exists():
        print(f"ERROR: SBOM file not found: {sbom_path}", file=sys.stderr)
        return 1

    registry_path = (
        args.registry.resolve()
        if args.registry
        else Path.cwd() / DEFAULT_REGISTRY_FILENAME
    )
    registry = _load_or_create_registry(registry_path, sbom_path.stem)
    if registry is None:
        return 1

    try:
        registry.import_sbom(sbom_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"ERROR: failed to import SBOM {sbom_path}: {exc}", file=sys.stderr)
        return 1

    registry.save(registry_path)
    print(
        f"pitloom ids: imported into {registry_path} "
        f"({len(registry.files)} file(s), {len(registry.entities)} entit(y/ies))"
    )
    return 0


def _run_ids_cli(args: argparse.Namespace) -> int:
    """Dispatch `pitloom ids <command> ...` arguments."""
    if args.ids_command == "generate":
        return _run_ids_generate(args)
    if args.ids_command == "import":
        return _run_ids_import(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
