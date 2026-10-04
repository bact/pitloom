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

from pitloom.assemble import generate, target_resolves_to_project
from pitloom.cli.commands.project import generate_project_from_args
from pitloom.cli.commands.utils import (
    _print_sbom_output_path,
    cli_error_handler,
    refuse_non_wheel,
)
from pitloom.cli.options import (
    add_allow_build_argument,
    add_build_timeout_argument,
    add_no_build_isolation_argument,
    add_offline_argument,
    add_use_lockfile_argument,
    build_options_from_args,
)
from pitloom.cli.options_config import (
    explicit_config_and_options,
    warn_verbose_no_effect,
)
from pitloom.core.build_options import NON_PROJECT_TARGET_REASON
from pitloom.core.wheel_dist_info import looks_like_wheel_path


@cli_error_handler("SBOM generation failed")
def _run_generate_command(args: argparse.Namespace) -> int:
    """Smart generate mode.

    ``-o``/``--output`` is required here (unlike ``project``/``wheel``/
    ``model``/``env``/``enrich``, which each know their target type and
    so have an obvious default filename): ``generate`` dispatches across
    project/wheel/model/env targets, each with a different natural
    default name, so guessing one would be arbitrary. Failing fast is
    more transparent than picking a name the user didn't ask for.
    """
    if args.output is None:
        print(
            "ERROR: -o/--output is required for 'loom generate' "
            "(the target-detection dispatch has no single natural default "
            "filename -- pass -o FILE, or use 'loom project'/'loom wheel'/"
            "'loom model'/'loom env' directly for that target type's own "
            "default).",
            file=sys.stderr,
        )
        return 1

    if looks_like_wheel_path(args.target) and refuse_non_wheel(
        Path(args.target).resolve()
    ):
        return 1

    if target_resolves_to_project(args.target):
        # A project directory or sdist archive: exactly what `loom project`
        # does, so the two cannot drift. Settle first, as `loom project`
        # does, so the build-flag WARNING: precedes any metadata WARNING:.
        target_path = Path(args.target).resolve()
        build_options = build_options_from_args(args).settle_target(target_path)
        generate_project_from_args(args, target_path, build_options)
        _print_sbom_output_path(args.output)
        return 0

    # env / wheel / model file / HF: no project of its own, so only an
    # explicitly named config applies, and generate() settles every option
    # the target cannot use.
    target = str(args.target).strip()
    build_options = build_options_from_args(args).settle_not_applicable(
        target, NON_PROJECT_TARGET_REASON
    )
    warn_verbose_no_effect(
        args,
        target,
        "for this target under 'generate' (the target's own command, e.g. "
        "'loom wheel -v', prints them)",
    )
    pitloom_config, options = explicit_config_and_options(args)
    generate(
        args.target,
        output_path=args.output,
        build_options=build_options,
        pitloom_config=pitloom_config,
        **options,
    )
    _print_sbom_output_path(args.output)
    return 0


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``generate`` subcommand."""
    # Note: Using 4-space indent
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
    add_offline_argument(
        gen_parser,
        "; effect depends on the resolved target -- "
        "HF URL/ID: error, no fetch attempted (no local fallback exists). "
        "project dir / .whl: skip PyPI lookup, no error (local metadata "
        "already covers what it can). "
        "local model file: no-op (no network path exists).",
    )
    add_use_lockfile_argument(
        gen_parser,
        "; effect depends on the resolved target -- "
        "project dir: fall back to direct dependencies + environment "
        "introspection only. "
        "sdist archive / wheel / model file / HF URL / env: no-op (no "
        "lock-file concept applies).",
    )
    add_allow_build_argument(gen_parser)
    add_no_build_isolation_argument(gen_parser)
    add_build_timeout_argument(gen_parser)
    gen_parser.set_defaults(func=_run_generate_command)
