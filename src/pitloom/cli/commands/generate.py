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

from pitloom.assemble import (
    generate,
    generate_project_sbom,
    target_resolves_to_project,
)
from pitloom.cli.commands.utils import (
    _print_sbom_output_path,
    cli_error_handler,
    resolve_effective_provenance,
)
from pitloom.cli.options import (
    _resolve_common_options,
    _resolve_project_generation_settings,
    add_allow_build_argument,
    add_build_timeout_argument,
    add_no_build_isolation_argument,
    add_offline_argument,
    add_use_lockfile_argument,
    build_options_from_args,
)
from pitloom.core.build_options import (
    NON_PROJECT_TARGET_REASON,
    SDIST_TARGET_REASON,
)


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

    target_path = Path(args.target) if args.target else None
    if (
        target_path is not None
        and target_path.is_dir()
        and target_resolves_to_project(args.target)
    ):
        # A real project directory: is_dir() above already confirms it's
        # not an sdist archive, so settle a stray --no-build-isolation/
        # --build-timeout (and warn about it) right now, before the
        # metadata/lock-file read below -- same reasoning as 'loom
        # project' (see cli/commands/project.py).
        build_options = build_options_from_args(args, target_path)

        # Resolve it once via the same shared helper 'loom project' uses,
        # then pre-supply the result to generate_project_sbom() -- a
        # single real read, instead of a config-only peek here followed
        # by generate()'s own read.
        (
            project_metadata,
            pitloom_config,
            _config_path,
            creation,
            effective_pretty,
            effective_describe_relationship,
        ) = _resolve_project_generation_settings(args, target_path)
        generate_project_sbom(
            target_path,
            output_path=args.output,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe_relationship,
            project_metadata=project_metadata,
            pitloom_config=pitloom_config,
            registry=args.registry,
            update_registry=args.update_registry,
            provenance=resolve_effective_provenance(pitloom_config, args),
            enrich=args.enrich,
            offline=args.offline,
            extract_file_header=args.extract_file_header,
            content_type=args.content_type,
            content_type_method=args.content_type_method,
            build_options=build_options,
        )
        _print_sbom_output_path(args.output)
        return 0

    # Every other target (env / wheel / model file / HF URL / sdist
    # archive): generate()'s own read never re-parses the same file this
    # peek reads (an sdist archive's real read parses its internal
    # metadata via read_sdist(), not this peek's sibling pyproject.toml),
    # so quieting the peek would silently drop its only WARNING: instead
    # of deferring it to a re-emission that never happens.
    build_options = build_options_from_args(args)
    if args.target is not None and not target_resolves_to_project(args.target):
        # env / wheel / model file / HF target: settle with the same reason
        # generate() uses, before _resolve_common_options()'s peek below, so
        # the build-flag WARNING precedes any metadata WARNING the peek logs.
        build_options = build_options.settle_not_applicable(
            str(args.target).strip(), NON_PROJECT_TARGET_REASON
        )
    elif target_path is not None and target_path.is_file():
        # sdist archive: settle with its own target-specific reason right
        # now, before _resolve_common_options()'s peek below -- so the
        # build-flag WARNING precedes any metadata WARNING that peek can
        # produce. generate_project_sbom()'s own settle_not_applicable()
        # call for the same target (reached via generate() below) then
        # finds nothing left to warn about.
        build_options = build_options.settle_not_applicable(
            target_path, SDIST_TARGET_REASON
        )

    pitloom_config, creation_metadata, pretty, describe_relationship = (
        _resolve_common_options(args, target_dir=target_path)
    )
    generate(
        args.target,
        offline=args.offline,
        use_lockfile=args.use_lockfile,
        output_path=args.output,
        creation_metadata=creation_metadata,
        pretty=pretty,
        describe_relationship=describe_relationship,
        registry=args.registry,
        update_registry=args.update_registry,
        provenance=resolve_effective_provenance(pitloom_config, args),
        enrich=args.enrich,
        extract_file_header=args.extract_file_header,
        content_type=args.content_type,
        content_type_method=args.content_type_method,
        build_options=build_options,
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
