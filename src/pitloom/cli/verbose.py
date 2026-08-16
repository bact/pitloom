# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pitloom.__about__ import __version__
from pitloom.cli.options import (
    _load_pitloom_tool_section,
    _quote_optional,
    _resolve_describe_relationship,
    _resolve_output_source,
    _resolve_pretty,
    _ResolvedCreationMetadata,
)

_SPDX3_JSON_EXT = ".spdx3.json"
_PROJECT_PYPROJECT_SOURCE = "pyproject.toml"
_PROJECT_SETUP_CFG_SOURCE = "setup.cfg"
_PROJECT_SETUP_PY_SOURCE = "setup.py"


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
