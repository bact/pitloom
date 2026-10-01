# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one map from parsed CLI arguments to library parameters.

Every SBOM subcommand hands its shared options to the library through
:func:`run_options` (as keyword arguments) or :func:`overrides_from_options`
(as a :class:`~pitloom.core.config_cascade.ConfigOverrides`), so a new
shared flag is added in one place and cannot reach one command and miss
another. An omitted flag stays ``None``: the library's cascade decides
what it resolves to, never the CLI.

``--config FILE`` is loaded here too (:func:`load_explicit_config`). It is
the only way a command whose target has no project of its own (``wheel``,
``env``, ``model``, ``enrich``, ``embed-wheel`` without ``--project-dir``)
gets a ``[tool.pitloom]`` config; on a project target it replaces the
project's own.

See also: :mod:`pitloom.cli.options_resolve` (project-target resolution and
``--verbose`` source reporting) and :mod:`pitloom.core.inert_options` (what
happens to an option the target cannot use).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pitloom.cli.options_resolve import (
    _resolve_creation_metadata,
    load_explicit_config,
)
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides
from pitloom.core.no_effect import INERT_LOG_PREFIX, warn_no_effect

#: Shared flags whose ``argparse`` dest is also the library parameter name.
#: ``offline`` and ``use_lockfile`` are per-command (absent on some), so
#: every one is read with a ``None`` default.
_SAME_NAME_OPTIONS = (
    "pretty",
    "describe_relationship",
    "enrich",
    "extract_file_header",
    "scan_model_usage",
    "trust_wheel_model",
    "content_type",
    "content_type_method",
    "max_source_metadata_bytes",
    "offline",
    "id_registry",
    "update_id_registry",
    "use_lockfile",
)

#: The creator/creation flags' dests: any one given means "creation
#: metadata was given" for the inert-option check.
_CREATION_DESTS = (
    "creators",
    "creation_tools",
    "creation_datetime",
    "creation_comment",
)


def creation_flags_given(args: argparse.Namespace) -> bool:
    """Whether any creator/creation flag was given on the command line."""
    return bool(getattr(args, "no_creation_tool", False)) or any(
        getattr(args, dest, None) is not None for dest in _CREATION_DESTS
    )


def run_options(args: argparse.Namespace, config: PitloomConfig) -> dict[str, Any]:
    """Library keyword arguments for the shared flags, keyed by parameter
    name.

    ``creation_metadata`` is resolved against *config* (flag > config >
    default), since it is a single object rather than one value per flag.
    Every other value is the raw flag, ``None`` when omitted, except that a
    relative ``--id-registry`` is made absolute against the current
    directory, as a path on the command line is -- the library resolves a
    relative one against the project directory.
    """
    options: dict[str, Any] = {
        name: getattr(args, name, None) for name in _SAME_NAME_OPTIONS
    }
    if options["id_registry"] is not None:
        options["id_registry"] = Path(options["id_registry"]).absolute()
    options["creation_metadata"] = _resolve_creation_metadata(
        args, config
    ).to_creation_metadata()
    return options


def explicit_config_and_options(
    args: argparse.Namespace,
) -> tuple[PitloomConfig | None, dict[str, Any]]:
    """``--config`` (``None`` when not given) and :func:`run_options`
    resolved against it -- the pair every command without a project of its
    own starts from, since only an explicitly named config applies there.
    """
    explicit = load_explicit_config(args)
    return explicit, run_options(args, explicit or PitloomConfig())


def overrides_from_options(
    options: dict[str, Any], build_options: BuildOptions = BuildOptions()
) -> ConfigOverrides:
    """The :class:`ConfigOverrides` for *options* (from :func:`run_options`);
    ``id_registry`` and ``creation_metadata`` are separate arguments of the
    embed API and are not part of it."""
    return ConfigOverrides(
        enrich=options["enrich"],
        extract_file_header=options["extract_file_header"],
        scan_model_usage=options["scan_model_usage"],
        trust_wheel_model=options["trust_wheel_model"],
        content_type=options["content_type"],
        content_type_method=options["content_type_method"],
        offline=options["offline"],
        pretty=options["pretty"],
        describe_relationship=options["describe_relationship"],
        update_id_registry=options["update_id_registry"],
        max_source_metadata_bytes=options["max_source_metadata_bytes"],
        build_options=build_options,
    )


def warn_verbose_no_effect(
    args: argparse.Namespace, subject: object, reason: str
) -> None:
    """Warn, in the shared no-effect wording, when ``-v`` was given to a
    command path that prints no verbose details. ``-v`` is CLI-only, so it
    is not an :data:`~pitloom.core.inert_options.INERT` parameter."""
    if getattr(args, "verbose", False):
        warn_no_effect(INERT_LOG_PREFIX, subject, ("-v/--verbose",), reason)


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--config FILE`` option."""
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Read [tool.pitloom] settings from FILE (a pyproject.toml-style "
            "TOML file). The only config a wheel, environment or model "
            "file gets -- none is read from the current directory. For a "
            "project target it replaces the project's own [tool.pitloom]. "
            "A relative id-registry in FILE resolves against FILE's directory."
        ),
    )


__all__ = [
    "add_config_argument",
    "creation_flags_given",
    "explicit_config_and_options",
    "load_explicit_config",
    "overrides_from_options",
    "run_options",
    "warn_verbose_no_effect",
]
