# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``wheel`` subcommand: an Analyzed SBOM from a built wheel."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble import (
    embed_sbom_in_wheel,
    generate_wheel_sbom,
    generate_wheel_sbom_with_metadata,
)
from pitloom.cli.commands._embed_wheel_batch import report_embed_result
from pitloom.cli.commands._remote_pypi import refuse_embed_of_pypi_url, run_pypi
from pitloom.cli.commands.utils import (
    _print_sbom_output_path,
    cli_error_handler,
    input_file_or_say,
    refuse_non_wheel,
)
from pitloom.cli.kv_output import log_verbose
from pitloom.cli.options import (
    add_allow_signed_wheel_argument,
    add_offline_argument,
)
from pitloom.cli.options_config import (
    add_archive_project_dir_argument,
    explicit_config_and_options,
)
from pitloom.core.inert_options import (
    EMBED_STANDALONE,
    EMBEDDED_SBOM_PARAMS,
    INERT,
    WHEEL,
    forward_options,
    settle_inert,
)
from pitloom.core.no_effect import warn_no_effect
from pitloom.core.url_masking import sanitize_url
from pitloom.embed import embed_filename, refuse_unembeddable_wheel
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.extract.remote.pypi import WHEEL as WHEEL_FILE
from pitloom.extract.remote.pypi_url import is_pypi_url
from pitloom.extract.wheel import wheel_identity


def _run_pypi_wheel(args: argparse.Namespace, url: str) -> int:
    """``loom wheel`` on a PyPI URL: ``--embed`` is refused (the wheel is a
    temporary file), else the release's wheel is downloaded and read."""
    if getattr(args, "embed", False):
        return refuse_embed_of_pypi_url(url)
    if args.allow_signed_wheel:
        warn_no_effect(
            sanitize_url(url.strip()),
            ("--allow-signed-wheel",),
            "without --embed",
        )
    return run_pypi(args, url, WHEEL_FILE)


@cli_error_handler
def _run_wheel_command(args: argparse.Namespace) -> int:
    """Generate an Analyzed SBOM from a built wheel.

    ``--embed`` here is deliberately narrower than the ``embed-wheel``
    command (see :func:`_run_embed_wheel_command`): always the wheel's own
    Analyzed SBOM, one wheel, no project-directory scanning. Both paths
    converge on :func:`~pitloom.embed.embed_sbom_in_wheel` for the actual
    archive mutation (RECORD update, stale-entry cleanup, atomic
    rewrite), so a fix there benefits both without needing to be
    duplicated -- only SBOM *content* generation differs by design.
    """
    target: str = args.target
    if is_pypi_url(target):
        return _run_pypi_wheel(args, target)
    if refuse_non_wheel(Path(target)):
        return 1
    # Absolute, not resolved: the file name is judged as given.
    wheel_path: Path = Path(target).absolute()
    # A regular file only: a directory named .whl is not a wheel.
    if not input_file_or_say(wheel_path, "wheel file", shown=Path(target)):
        return 1

    pitloom_config, options = explicit_config_and_options(args)

    embed = getattr(args, "embed", False)
    if args.allow_signed_wheel and not embed:
        warn_no_effect(
            wheel_path.name,
            ("--allow-signed-wheel",),
            "without --embed",
        )
    if embed:
        # The same SBOM, and the same warnings, as embed-wheel without a
        # project: canonical, no relationship descriptions, no registry
        # harvest. -o writes a copy of it.
        inert = INERT[EMBED_STANDALONE]
        settle_inert(EMBED_STANDALONE, target, {name: options[name] for name in inert})
        options.update(dict.fromkeys(inert))
        options.update(dict.fromkeys(EMBEDDED_SBOM_PARAMS, False))
    # With --embed, only write a standalone copy if the user explicitly
    # asked for one via -o; embedding into the wheel is the primary
    # output and shouldn't also litter cwd with a same-named file.
    output_path = (
        args.output
        if embed
        else args.output or (Path.cwd() / f"{wheel_path.name}{SPDX3_JSONLD_EXTENSION}")
    )

    if args.verbose:
        # OUTPUT_PATH only for a copy written: --embed without -o writes none.
        given = options["project_dir"]
        project_dir = {} if given is None else {"PROJECT_DIR": given}
        output = {} if output_path is None else {"OUTPUT_PATH": output_path}
        log_verbose(WHEEL_FILE=wheel_path, **output, **project_dir)

    if embed:
        # As embed-wheel: refuse before generating (that may run a build).
        refuse_unembeddable_wheel(wheel_path, args.allow_signed_wheel)
    # With --embed, the -o copy is written once the embed has succeeded: a
    # wheel the embed refuses leaves nothing behind.
    sbom_json, wheel_metadata = generate_wheel_sbom_with_metadata(
        wheel_path,
        output_path=None if embed else output_path,
        pitloom_config=pitloom_config,
        # Subject as given, so the warning reads as `loom generate`'s does.
        **forward_options(WHEEL, target, generate_wheel_sbom, options),
    )

    if embed:
        _, arcname, removed, floored = embed_sbom_in_wheel(
            wheel_path,
            sbom_json,
            sbom_filename=embed_filename(
                pitloom_config.sbom_basename if pitloom_config else None
            ),
            # Already read (and warned about) by the generation above.
            identity=wheel_identity(wheel_metadata),
            allow_signed_wheel=args.allow_signed_wheel,
        )
        write_sbom_output(sbom_json, output_path)
        report_embed_result(arcname, wheel_path.name, removed, floored, output_path)

    if output_path is not None:
        _print_sbom_output_path(output_path)

    return 0


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``wheel`` subcommand."""
    # Built wheel: loom wheel <WHEEL_FILE>
    wheel_parser = subparsers.add_parser(
        "wheel",
        parents=[parent_parser],
        help="Generate an Analyzed SBOM from a built wheel (.whl) or a PyPI URL.",
    )
    wheel_parser.add_argument(
        "target",
        type=str,
        help="Path to the built .whl file, or the https URL of a PyPI project "
        "or release page (https://pypi.org/project/NAME/[VERSION/]): the "
        "release's wheel that best matches this Python and platform is "
        "downloaded, its SHA-256 checked against the one PyPI declares, and "
        "read as a local wheel is (its own [tool.pitloom] is not read; "
        "--config applies). Not combinable with --embed.",
    )
    wheel_parser.add_argument(
        "--embed",
        action="store_true",
        help="Embed the generated SBOM directly into the wheel archive (PEP 770).",
    )
    add_allow_signed_wheel_argument(wheel_parser)
    add_archive_project_dir_argument(wheel_parser)
    add_offline_argument(
        wheel_parser,
        " -- skip PyPI lookup, no error (local metadata already covers what it "
        "can). A PyPI URL: error, nothing is fetched.",
    )
    wheel_parser.set_defaults(func=_run_wheel_command)
