# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Per-batch state for ``embed-wheel``: resolving ``--project-dir``, settling
the options every wheel in the batch shares, and embedding one wheel.

See also: ``pitloom.cli.commands.embed_wheel``, which owns the subcommand
entry point and builds :class:`EmbedBatchContext` once per invocation
before looping over the wheel files with :func:`try_embed_one_wheel`.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path
from typing import Any

from pitloom.assemble import ConfigOverrides, embed_wheel_sbom
from pitloom.cli.commands.utils import report_error_line
from pitloom.cli.kv_output import print_kv
from pitloom.cli.options_config import (
    creation_flags_given,
    load_explicit_config,
    run_options,
    warn_verbose_no_effect,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.inert_options import (
    EMBED_PROJECT,
    EMBED_SBOM,
    EMBED_STANDALONE,
    INERT,
    settle_inert,
)
from pitloom.embed import RECORD_SIGNATURES, EmbedFileCache
from pitloom.extract.project import read_project
from pitloom.id_registry import IdRegistry, registry_base_dir, resolve_registry
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)


def report_embed_result(
    arcname: str,
    wheel_name: str,
    removed: tuple[str, ...],
    timestamp_floored: bool = False,
) -> None:
    """Print the embed's ``WHEEL=<wheel name> SBOM=<arcname>`` data line,
    plus one ``INFO:`` line per notable side effect.

    Shared by ``wheel --embed`` and ``embed-wheel`` so both report results
    identically -- see ``pitloom.cli.commands.wheel._run_wheel_command``/
    :func:`try_embed_one_wheel`. Lives here (not in
    ``pitloom.cli.commands.embed_wheel``) so :func:`try_embed_one_wheel`
    can call it directly instead of taking it as a callback parameter --
    a plain function-to-function call, not an ``Any``-typed indirection.
    """
    print_kv(WHEEL=wheel_name, SBOM=arcname)
    for stale_arcname in removed:
        if stale_arcname.endswith(RECORD_SIGNATURES):
            log.info(
                "removed %s from %s: it signed the RECORD the embed rewrote; "
                "re-sign the wheel",
                loggable(stale_arcname),
                loggable(wheel_name),
            )
            continue
        log.info(
            "removed stale SBOM %s from %s",
            loggable(stale_arcname),
            loggable(wheel_name),
        )
    if timestamp_floored:
        log.info(
            "%s's embedded SBOM entry timestamp was before 1980 and was "
            "floored to 1980-01-01 (ZIP format limitation); the SBOM's own "
            "'created' field keeps the true value",
            wheel_name,
        )


def resolve_project_dir_and_config(
    project_dir: Path | None, *, read_config: bool = True
) -> tuple[Path | None, PitloomConfig | None] | None:
    """Resolve ``--project-dir`` into ``(project_dir, its PitloomConfig)``,
    or ``(None, None)`` when it was not given.

    Without ``--project-dir`` there is no project: the current directory is
    never assumed to be the wheel's project, since it may be an unrelated
    one. Returns ``None`` (already printed an ``ERROR:``) if the given
    directory doesn't exist or has no ``pyproject.toml``/``setup.cfg``.

    Only ``[tool.pitloom]`` config is used here; ``read_project()``'s
    lock/pin cascade is skipped (``include_locked_dependencies=False``)
    -- ``embed-wheel`` is build-stage, and a source-stage lock file's
    resolved dependencies must never leak into a wheel-embedded SBOM. Its
    in-tree installed-metadata resolution is skipped too
    (``include_installed_metadata=False``) for the same build-stage
    rationale, and purely to skip that I/O since this caller discards the
    metadata anyway.

    Without *read_config* (a ``--config`` replaces it) the
    project's own config is not read at all, as
    :func:`~pitloom.embed.embed_wheel_sbom` does not read it when given a
    config, so an unrelated fault in it cannot fail the embed.
    """
    if project_dir is None:
        return None, None

    proj_path = Path(project_dir).resolve()
    if not proj_path.exists():
        print(f"ERROR: project directory not found: {proj_path}", file=sys.stderr)
        return None
    if not read_config:
        return proj_path, None
    try:
        _, pitloom_config, _ = read_project(
            proj_path,
            include_locked_dependencies=False,
            include_installed_metadata=False,
        )
    except FileNotFoundError as exc:
        # read_project()'s own message already names the specific reason
        # (no config file at all, vs. a config file present but resolving
        # to no usable metadata) -- relay it instead of a fixed guess.
        report_error_line(exc)
        return None
    return proj_path, pitloom_config


def settle_batch_options(
    args: argparse.Namespace,
    project_dir: Path | None,
    options: dict[str, Any],
) -> None:
    """Warn once for the whole batch about every option this embed cannot
    use, and clear every option it cannot use in place -- given or not --
    so no per-wheel call warns again. Creation metadata counts as given
    only when a creator/creation flag was, since *options* always carries
    a resolved value."""
    if args.sbom is not None:
        kind, subject = EMBED_SBOM, args.sbom
    elif project_dir is not None:
        kind, subject = EMBED_PROJECT, project_dir
    else:
        kind, subject = EMBED_STANDALONE, "embed-wheel"
    warn_verbose_no_effect(args, subject, "for embed-wheel (it prints no details)")
    given = dict(options)
    if not creation_flags_given(args):
        given["creation_metadata"] = None
    settle_inert(kind, subject, given)
    for name in INERT[kind]:
        options[name] = None


def batch_options(
    args: argparse.Namespace,
    project_dir: Path | None,
    project_config: PitloomConfig | None,
) -> tuple[dict[str, Any], PitloomConfig | None]:
    """The batch's settled options and the config its wheels embed with.

    ``--config`` replaces the project's own ``[tool.pitloom]``, and is the
    only config a wheel embedded without a project gets. An ``--sbom`` is
    embedded as is: it uses neither, so a given ``--config`` or
    ``--project-dir`` is not read (not even checked to exist), only warned
    about by the batch settle."""
    if args.sbom is not None:
        options = run_options(args, PitloomConfig())
        # Given, not read: the batch settle warns about both.
        options["pitloom_config"] = args.config
        options["project_dir"] = args.project_dir
        settle_batch_options(args, project_dir, options)
        return options, None
    explicit_config = load_explicit_config(args)
    options = run_options(args, explicit_config or project_config or PitloomConfig())
    options["pitloom_config"] = explicit_config
    settle_batch_options(args, project_dir, options)
    return options, explicit_config or project_config


def resolve_batch_id_registry(
    args: argparse.Namespace,
    options: dict[str, Any],
    pitloom_config: PitloomConfig | None,
    project_dir: Path | None,
) -> IdRegistry | None:
    """Resolve the registry once for the whole embed-wheel batch (not
    once per wheel): :func:`~pitloom.embed.embed_wheel_sbom` accepts an
    already-loaded ``IdRegistry`` and passes it straight through its own
    ``resolve_registry()`` call, which returns it unchanged (see
    ``resolve_registry()``'s isinstance check) instead of reloading the
    file per wheel. Skipped entirely for an ``--sbom`` batch
    (``INERT[EMBED_SBOM]``): that path embeds the given SBOM as is and
    never resolves a registry."""
    if args.sbom is not None:
        return None
    return resolve_registry(
        options["id_registry"],
        pitloom_config.id_registry if pitloom_config is not None else None,
        registry_base_dir(project_dir) if project_dir is not None else Path.cwd(),
    )


@dataclasses.dataclass(frozen=True)
class EmbedBatchContext:
    """The per-run values every wheel in a batch embeds with -- resolved
    once in ``_run_embed_wheel_command``, not per-wheel, and bundled here
    so :func:`try_embed_one_wheel` stays under the arg-count limit.

    ``file_cache`` is a mutable :class:`~pitloom.embed.EmbedFileCache`,
    not a value like the other fields: it memoizes ``project_dir``'s
    file-discovery result across every wheel in the batch (see its own
    docstring). ``_run_embed_wheel_command`` holds its ``with`` block
    around the whole batch, not per wheel.
    """

    project_dir: Path | None
    pitloom_config: PitloomConfig | None
    creation_metadata: CreationMetadata | None
    id_registry: IdRegistry | None
    overrides: ConfigOverrides
    file_cache: EmbedFileCache


def try_embed_one_wheel(
    wheel_path: Path,
    output_path: Path | None,
    batch: EmbedBatchContext,
    args: argparse.Namespace,
) -> tuple[Path, str] | None:
    """Embed into *wheel_path*, report the result via
    :func:`report_embed_result`, and return ``(embedded_wheel_path,
    arcname)`` -- or ``None`` on a per-wheel failure that's already been
    reported as an ``ERROR:``.

    ValueError/OSError here mean *this* wheel failed (bad archive, bad
    ``--sbom-basename``, or a ``--sbom`` name/version mismatch that
    wasn't ``--allow-mismatch``'d) -- the same per-wheel-failure contract
    `find_embedded_sbom()`/`open_wheel_zip()` already document. Caught
    here (not left to the outer `cli_error_handler`) so one bad wheel in
    a multi-wheel batch doesn't abort the others, matching how a failing
    `--verify`/`--validate` on one wheel already doesn't stop the loop
    in ``_run_embed_wheel_command``.
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
            id_registry=batch.id_registry,
            overrides=batch.overrides,
            allow_mismatch=args.allow_mismatch,
            allow_signed_wheel=args.allow_signed_wheel,
            file_cache=batch.file_cache,
        )
    except (ValueError, OSError) as exc:
        report_error_line(exc)
        return None
    report_embed_result(arcname, wheel_path.name, removed, floored)
    return embedded_wheel_path, arcname
