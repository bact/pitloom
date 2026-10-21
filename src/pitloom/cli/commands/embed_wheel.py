# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``embed-wheel`` subcommand: embed an SBOM into built wheels (PEP 770).

See also: ``pitloom.cli.commands._embed_wheel_batch``, which holds the
per-batch resolution helpers (``--project-dir``, settled options, the
resolved registry, ``EmbedBatchContext``/``try_embed_one_wheel``, and
``report_embed_result``) this module's ``_run_embed_wheel_command``
builds and loops over.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

from pitloom._wheel_sbom_location import (
    EmbeddedSbomLocation,
    read_wheel_name_version_from_path,
)
from pitloom.cli.commands._embed_wheel_batch import (
    EmbedBatchContext,
    batch_options,
    resolve_batch_id_registry,
    resolve_project_dir_and_config,
    try_embed_one_wheel,
)
from pitloom.cli.commands.utils import (
    _collect_wheel_paths,
    _locate_and_detect,
    _print_sbom_output_path,
    cli_error_handler,
)
from pitloom.cli.commands.validate_wheel import _validate_location
from pitloom.cli.commands.verify_wheel import _check_location, _check_name_version
from pitloom.cli.options import (
    add_allow_build_argument,
    add_allow_signed_wheel_argument,
    add_build_timeout_argument,
    add_no_build_isolation_argument,
    add_offline_argument,
    build_options_from_args,
)
from pitloom.cli.options_config import overrides_from_options
from pitloom.core.build_options import EXTERNAL_SBOM_REASON, NO_PROJECT_DIR_REASON
from pitloom.embed import EmbedFileCache

log = logging.getLogger(__name__)


def _run_post_embed_checks(
    args: argparse.Namespace, embedded_wheel_path: Path, arcname: str
) -> bool:
    """Run ``--verify``/``--validate`` against the wheel just written; return
    whether they passed (``True`` when neither was given).

    The SBOM is located and its format detected once, from the wheel on
    disk (:func:`~pitloom.cli.commands.utils._locate_and_detect`), then
    passed to both checks, so they judge what landed in the wheel, not the
    string that was generated. ``--verify``'s name/version check reads
    ``METADATA`` separately and only warns (:func:`_warn_on_name_version_mismatch`).
    """
    if not args.verify and not args.validate:
        return True

    embedded_filename = arcname.rsplit("/", 1)[-1]
    located = _locate_and_detect(embedded_wheel_path, embedded_filename)
    if located is None:
        return False
    location, sbom_format = located

    # `is not False`: _validate_location returns None when no validator is
    # registered (a skip, not a failure).
    verify_ok = not args.verify or (
        _check_location(embedded_wheel_path, location, sbom_format) is not False
    )
    if args.verify:
        _warn_on_name_version_mismatch(embedded_wheel_path, location, sbom_format)
    validate_ok = not args.validate or (
        _validate_location(embedded_wheel_path, location, sbom_format) is not False
    )
    return verify_ok and validate_ok


def _warn_on_name_version_mismatch(
    embedded_wheel_path: Path,
    location: EmbeddedSbomLocation,
    sbom_format: str | None,
) -> None:
    """``--verify``'s name/version check on the embedded wheel; it logs a
    ``WARNING:`` on a mismatch and never fails the command (only
    ``verify-wheel --fail-on-mismatch`` does)."""
    wheel_name, wheel_version = read_wheel_name_version_from_path(embedded_wheel_path)
    _check_name_version(
        embedded_wheel_path,
        wheel_name,
        wheel_version,
        location,
        sbom_format,
        fail_on_mismatch=False,
    )


@cli_error_handler("wheel SBOM embedding failed")
def _run_embed_wheel_command(args: argparse.Namespace) -> int:
    """Embed an SPDX 3 SBOM into one or more built wheels (PEP 770).

    The richer counterpart to ``wheel --embed`` (see :func:`_run_wheel_command`):
    supports multiple wheels, a project directory (Build-type SBOM), a
    pre-generated ``--sbom`` file, and a custom ``--sbom-basename``. Both
    commands converge on :func:`~pitloom.embed.embed_sbom_in_wheel` for
    the actual archive mutation.
    """
    unique_wheels = _collect_wheel_paths(args.wheel_files)
    if not unique_wheels:
        return 1

    if len(unique_wheels) > 1 and args.output is not None:
        print(
            "ERROR: --output cannot be used when embedding multiple wheels",
            file=sys.stderr,
        )
        return 1

    # Settle the build flags up front, so an ineffective flag's warning
    # comes before any metadata warning; the batch's EmbedFileCache then
    # has nothing left to warn about.
    build_options = build_options_from_args(args)
    if args.sbom is not None:
        build_options = build_options.settle_not_applicable(
            args.sbom, EXTERNAL_SBOM_REASON
        )
    elif args.project_dir is not None:
        # A missing --project-dir settles nothing: it fails below with an
        # ERROR alone, as `loom project` does.
        build_options = build_options.settle_target(Path(args.project_dir))
    else:
        # Same subject and reason as the options settled below.
        build_options = build_options.settle_not_applicable(
            "embed-wheel", NO_PROJECT_DIR_REASON
        )
        if os.path.isfile("pyproject.toml"):
            # For a user expecting the project here to be rescanned.
            log.info(
                "embed-wheel: no --project-dir given; the SBOM is built from "
                "the wheel alone (the project in the current directory is "
                "not used)"
            )

    # An --sbom is embedded as is: --project-dir is not even checked (the
    # batch settle warns that it has no effect).
    resolved = (
        (None, None)
        if args.sbom is not None
        else resolve_project_dir_and_config(
            args.project_dir, read_config=args.config is None
        )
    )
    if resolved is None:
        return 1
    project_dir, project_config = resolved
    options, pitloom_config = batch_options(args, project_dir, project_config)
    overrides = overrides_from_options(options, build_options)
    all_ok = True
    # One file cache for the whole batch, cleaned up once on leaving the
    # block, on every exit path: it resolves project_dir's file list (and
    # runs any --allow-build real build) at most once, shared across every
    # wheel -- see EmbedFileCache's own docstring.
    with EmbedFileCache() as file_cache:
        batch = EmbedBatchContext(
            project_dir=project_dir,
            pitloom_config=pitloom_config,
            creation_metadata=options["creation_metadata"],
            id_registry=resolve_batch_id_registry(
                args, options, pitloom_config, project_dir
            ),
            overrides=overrides,
            file_cache=file_cache,
        )
        for wheel_path in unique_wheels:
            output_path = args.output if len(unique_wheels) == 1 else None
            embedded = try_embed_one_wheel(wheel_path, output_path, batch, args)
            if embedded is None:
                all_ok = False
                continue
            embedded_wheel_path, arcname = embedded
            if output_path is not None:
                _print_sbom_output_path(output_path)
            if not _run_post_embed_checks(args, embedded_wheel_path, arcname):
                all_ok = False
    return 0 if all_ok else 1


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``embed-wheel`` subcommand."""
    # Note: Using 4-space indent
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
            "metadata, AI models, and file headers from. Without it, the "
            "SBOM is built from the wheel alone; the current directory is "
            "never used."
        ),
    )
    embed_parser.add_argument(
        "--sbom",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Pre-generated SBOM JSON file to embed directly instead of "
            "generating one. Its declared subject name/version is "
            "cross-checked against the wheel's own METADATA before "
            "anything is written; a mismatch aborts the embed unless "
            "--allow-mismatch is given."
        ),
    )
    embed_parser.add_argument(
        "--sbom-basename",
        type=str,
        default=None,
        metavar="NAME",
        help="Custom basename for the embedded SBOM inside .dist-info/sboms/.",
    )
    add_allow_signed_wheel_argument(embed_parser)
    embed_parser.add_argument(
        "--allow-mismatch",
        action="store_true",
        help=(
            "With --sbom, embed anyway (WARNING only) when its declared "
            "name/version doesn't match the wheel's METADATA, instead of "
            "aborting before writing. Has no effect without --sbom."
        ),
    )
    embed_parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "After embedding, also run 'verify-wheel' against the result "
            "(PEP 770 location, recommended extension, and name/version "
            "cross-check)."
        ),
    )
    embed_parser.add_argument(
        "--validate",
        action="store_true",
        help=(
            "After embedding, also run 'validate-wheel' against the result "
            "(schema/SHACL content validation)."
        ),
    )
    add_offline_argument(embed_parser, " during SBOM generation.")
    add_allow_build_argument(embed_parser)
    add_no_build_isolation_argument(embed_parser)
    add_build_timeout_argument(embed_parser)
    embed_parser.set_defaults(func=_run_embed_wheel_command)
