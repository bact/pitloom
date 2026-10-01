# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pitloom.__about__ import __version__
from pitloom.assemble import (
    enrich_model,
)
from pitloom.cli.commands.utils import cli_error_handler, existing_model_path
from pitloom.cli.options import add_use_lockfile_argument
from pitloom.cli.options_config import explicit_config_and_options
from pitloom.core.inert_options import ENRICH, forward_options
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION


@cli_error_handler("enrichment fragment generation failed")
def _run_enrich_command(args: argparse.Namespace) -> int:
    """Run enrichment only for a local AI model file; write a fragment."""
    target: str = args.target
    # The path as given goes to the generator, so its log lines name the
    # file as the user wrote it.
    given_path = Path(target)
    model_path: Path = given_path.resolve()
    opened_path = existing_model_path(given_path)
    if opened_path is None:
        print(f"ERROR: model file not found: {model_path}", file=sys.stderr)
        return 1

    # Only an explicitly named config applies: a pyproject.toml near the
    # model or in the current directory may belong to an unrelated project.
    pitloom_config, options = explicit_config_and_options(args)

    output_path = args.output or (
        Path.cwd() / f"{model_path.name}.enrich{SPDX3_JSONLD_EXTENSION}"
    )

    if args.verbose:
        print(f"Pitloom version: {__version__}")
        print(f"Model file      : {model_path}")
        print(f"Output path     : {output_path}")
        if args.project_dir:
            print(f"Project dir     : {args.project_dir}")

    enrich_model(
        opened_path,
        output_path=output_path,
        project_target=args.project_dir,
        pitloom_config=pitloom_config,
        # enrich_model settles use_lockfile itself (it depends on the
        # project target); forward_options warns only for the rest.
        **forward_options(ENRICH, str(opened_path), enrich_model, options),
    )
    print(f"Enrichment fragment written to: {output_path}")
    print(
        "Register it under [tool.pitloom.fragment] and re-run "
        "'loom project'/'loom generate' to merge it into a base SBOM."
    )
    return 0


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``enrich`` subcommand."""
    # Note: Using 4-space indent
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
    add_use_lockfile_argument(
        enrich_parser,
        " when computing the base document's identity for --project-dir "
        "matching -- must match whatever setting produced that base SBOM, "
        "or omit to auto-match its [tool.pitloom] config",
    )
    enrich_parser.set_defaults(func=_run_enrich_command)
