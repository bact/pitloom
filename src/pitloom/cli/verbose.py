# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pitloom.cli.kv_output import log_kv, log_verbose
from pitloom.cli.options import (
    _load_pitloom_tool_section,
    _quote_optional,
    _resolve_describe_relationship,
    _resolve_output_source,
    _resolve_pretty,
    _ResolvedCreationMetadata,
)
from pitloom.cli.options_resolve import config_file_display, config_source_label


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


def log_verbose_options(
    args: argparse.Namespace,
    project_dir: Path,
    output_path: Path,
    pitloom_config: Any,
    config_path: Path | None,
    creation: _ResolvedCreationMetadata,
) -> None:
    """``-v`` for a project: ``PITLOOM_VERSION``, then one
    ``INFO: OPTION=<name> SOURCE=<source> VALUE=<value>`` line per effective
    option. ``VALUE`` goes last: it is the one that may hold a space."""
    pitloom_tool = _load_pitloom_tool_section(config_path)
    config_source = config_source_label(config_path)
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

    rows: list[tuple[str, str, str]] = [
        ("project_directory", str(project_dir), "command-line"),
        ("config_file", config_file_display(config_path), "command-line"),
        ("output_path", str(output_path), out_src),
        *_build_creation_option_rows(
            creation, eff_pretty, pretty_src, eff_desc, desc_src
        ),
    ]
    log_verbose()
    for name, value, source in rows:
        log_kv(OPTION=name, SOURCE=source, VALUE=value)
