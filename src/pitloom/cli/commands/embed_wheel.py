# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path
from typing import Any

from pitloom._wheel_sbom_location import (
    EmbeddedSbomLocation,
    _find_dist_info_prefix,
    _open_wheel_zip,
    read_wheel_name_version,
)
from pitloom.assemble import ConfigOverrides, embed_wheel_sbom
from pitloom.cli.commands.utils import (
    _collect_wheel_paths,
    _locate_and_detect,
    _print_sbom_output_path,
    cli_error_handler,
    resolve_effective_provenance,
)
from pitloom.cli.commands.validate_wheel import _validate_location
from pitloom.cli.commands.verify_wheel import _check_location, _check_name_version
from pitloom.cli.options import _resolve_creation_metadata, add_offline_argument
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.extract.project import read_project

log = logging.getLogger(__name__)


def _report_embed_result(
    arcname: str,
    wheel_name: str,
    removed: tuple[str, ...],
    timestamp_floored: bool = False,
) -> None:
    """Print the embed confirmation, plus one line per notable side effect.

    Shared by ``wheel --embed`` and ``embed-wheel`` so both report results
    identically -- see :func:`_run_wheel_command`/:func:`_run_embed_wheel_command`.
    """
    print(f"pitloom: embedded {arcname} into {wheel_name}")
    for stale_arcname in removed:
        log.info("removed stale SBOM %s from %s", stale_arcname, wheel_name)
    if timestamp_floored:
        log.info(
            "%s's embedded SBOM entry timestamp was before 1980 and was "
            "floored to 1980-01-01 (ZIP format limitation); the SBOM's own "
            "'created' field keeps the true value",
            wheel_name,
        )


def _run_post_embed_checks(
    args: argparse.Namespace, embedded_wheel_path: Path, arcname: str
) -> bool:
    """Run --verify/--validate against the wheel embed_wheel_sbom() just
    modified. Same checks verify-wheel/validate-wheel use standalone,
    chained here like `wheel --embed` chains into the same embed function.

    Deliberately re-reads *embedded_wheel_path* from disk rather than
    checking the pre-write `sbom_json` string generation produced: the
    whole point of `--verify`/`--validate` is confirming what actually
    landed in the wheel, not what Pitloom intended to write -- an
    in-memory shortcut would silently narrow that guarantee for exactly
    the command whose job is to catch that kind of drift.

    Locates the SBOM from disk and detects its format exactly ONCE (via
    `_locate_and_detect`, shared with `_check_one_wheel`/`_validate_one_wheel`)
    and passes both to `_check_location`/`_validate_location` when the
    relevant flags are given, rather than each check re-locating/
    re-detecting independently -- one genuine disk read for the SBOM
    entry itself, not duplicated. `--verify`'s name/version half
    (`_warn_on_name_version_mismatch` below) is a SEPARATE disk read of
    its own -- it needs `.dist-info/METADATA`, not the SBOM entry, so it
    isn't covered by the SBOM-specific dedup above; not worth threading a
    third return value through `_locate_and_detect` to avoid one small
    extra read on what's normally a small archive.

    `--verify`'s name/version half is always non-fatal here (`WARNING:`
    only, no `--fail-on-mismatch` equivalent on `embed-wheel` itself) --
    for a `--sbom`-supplied embed, `embed_wheel_sbom()` already refused
    (or was told `allow_mismatch=True`) *before* this ever runs, so a
    mismatch surviving to here is either an intentionally-forced one or a
    generated SBOM, neither of which `embed-wheel` should fail on by
    itself; run standalone `verify-wheel --fail-on-mismatch` for that.
    """
    if not args.verify and not args.validate:
        return True

    embedded_filename = arcname.rsplit("/", 1)[-1]
    located = _locate_and_detect(embedded_wheel_path, embedded_filename)
    if located is None:
        return False
    location, sbom_format = located

    # `is not False` (not plain truthiness), even though _check_location
    # only ever returns bool: _validate_location returns None for "no
    # validator registered" (a skip, not a failure), and matching idioms
    # here keeps the checks symmetric so a future one copy-pasted from
    # either line stays correct by default.
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
    """Run `_check_name_version` as part of `--verify`, always non-fatal
    here (no `--fail-on-mismatch` equivalent on `embed-wheel` itself --
    use standalone `verify-wheel --fail-on-mismatch` for that). For a
    `--sbom`-supplied embed, `embed_wheel_sbom()` already refused (or was
    told `allow_mismatch=True`) *before* this ever ran, so a mismatch
    surviving to here is either an intentionally-forced one or a
    generated SBOM -- `embed-wheel` shouldn't fail its own exit code on
    either.
    """
    with _open_wheel_zip(embedded_wheel_path) as zf:
        dist_info = _find_dist_info_prefix(zf, embedded_wheel_path)
        wheel_name, wheel_version = read_wheel_name_version(zf, dist_info)
    _check_name_version(
        embedded_wheel_path,
        wheel_name,
        wheel_version,
        location,
        sbom_format,
        fail_on_mismatch=False,
    )


def _resolve_project_dir_and_config(
    project_dir: Path | None,
) -> tuple[Path | None, PitloomConfig] | None:
    """Resolve *project_dir* (from ``--project-dir``, or cwd if unset)
    into ``(project_dir, PitloomConfig)``.

    Returns ``None`` (already printed an ``ERROR:``) if an *explicit*
    ``--project-dir`` doesn't exist or has no ``pyproject.toml``/
    ``setup.cfg`` -- that's a user mistake worth failing on. Falling back
    to cwd with no project file there is not an error (a standalone-wheel
    embed with no project directory is a legitimate use), so that case
    silently returns the default config with `project_dir=None`.
    """
    if project_dir is None:
        try:
            _, pitloom_config, _ = read_project(Path.cwd())
            return Path.cwd(), pitloom_config
        except FileNotFoundError:
            return None, PitloomConfig()

    proj_path = Path(project_dir).resolve()
    if not proj_path.exists():
        print(f"ERROR: project directory not found: {proj_path}", file=sys.stderr)
        return None
    try:
        _, pitloom_config, _ = read_project(proj_path)
    except FileNotFoundError:
        print(
            "ERROR: No pyproject.toml or setup.cfg found "
            f"in project directory: {proj_path}",
            file=sys.stderr,
        )
        return None
    return proj_path, pitloom_config


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

    resolved = _resolve_project_dir_and_config(args.project_dir)
    if resolved is None:
        return 1
    project_dir, pitloom_config = resolved

    creation = _resolve_creation_metadata(args, pitloom_config)
    overrides = ConfigOverrides(
        enrich=args.enrich,
        extract_file_header=args.extract_file_header,
        content_type=args.content_type,
        content_type_method=args.content_type_method,
        provenance=resolve_effective_provenance(pitloom_config, args),
        offline=args.offline,
    )
    batch = _EmbedBatchContext(
        project_dir=project_dir,
        pitloom_config=pitloom_config,
        creation_metadata=creation.to_creation_metadata(),
        overrides=overrides,
    )

    all_ok = True
    for wheel_path in unique_wheels:
        output_path = args.output if len(unique_wheels) == 1 else None
        embedded = _try_embed_one_wheel(wheel_path, output_path, batch, args)
        if embedded is None:
            all_ok = False
            continue
        embedded_wheel_path, arcname = embedded
        if output_path is not None:
            _print_sbom_output_path(output_path)
        if not _run_post_embed_checks(args, embedded_wheel_path, arcname):
            all_ok = False
    return 0 if all_ok else 1


@dataclasses.dataclass(frozen=True)
class _EmbedBatchContext:
    """The per-run values every wheel in a batch embeds with -- resolved
    once in :func:`_run_embed_wheel_command`, not per-wheel, and bundled
    here so :func:`_try_embed_one_wheel` stays under the arg-count limit."""

    project_dir: Path | None
    pitloom_config: PitloomConfig
    creation_metadata: CreationMetadata
    overrides: ConfigOverrides


def _try_embed_one_wheel(
    wheel_path: Path,
    output_path: Path | None,
    batch: _EmbedBatchContext,
    args: argparse.Namespace,
) -> tuple[Path, str] | None:
    """Embed into *wheel_path*, report the result, and return
    ``(embedded_wheel_path, arcname)`` -- or ``None`` on a per-wheel
    failure that's already been reported as an ``ERROR:``.

    ValueError/OSError here mean *this* wheel failed (bad archive, bad
    ``--sbom-basename``, or a ``--sbom`` name/version mismatch that
    wasn't ``--allow-mismatch``'d) -- the same per-wheel-failure contract
    `find_embedded_sbom()`/`_open_wheel_zip()` already document. Caught
    here (not left to the outer `cli_error_handler`) so one bad wheel in
    a multi-wheel batch doesn't abort the others, matching how a failing
    `--verify`/`--validate` on one wheel already doesn't stop the loop
    in :func:`_run_embed_wheel_command`.
    """
    try:
        embedded_wheel_path, arcname, _, removed, floored = embed_wheel_sbom(
            wheel_path,
            project_dir=batch.project_dir,
            pitloom_config=batch.pitloom_config,
            sbom_path=args.sbom,
            output_path=output_path,
            sbom_basename=args.sbom_basename,
            creation_metadata=batch.creation_metadata,
            registry=args.registry,
            overrides=batch.overrides,
            allow_mismatch=args.allow_mismatch,
        )
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None
    _report_embed_result(arcname, wheel_path.name, removed, floored)
    return embedded_wheel_path, arcname


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
            "metadata, AI models, and file headers from (defaults to cwd)."
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
    embed_parser.set_defaults(func=_run_embed_wheel_command)
