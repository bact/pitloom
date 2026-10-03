# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator.

Shared ``add_*_argument()`` flag-definition helpers and their
``warn_*()`` companions. Config-cascade *resolution* logic (turning
parsed ``args`` plus ``[tool.pitloom]`` into effective settings) lives
in :mod:`pitloom.cli.options_resolve`, split out once this file crossed
the ~400-500 line soft limit -- re-exported below so every existing
``from pitloom.cli.options import ...`` call site needed no changes.
"""

from __future__ import annotations

import argparse

# Re-exports (mypy's explicit-reexport check under strict=true needs
# either "import X as X" or __all__ membership for a name to count as
# part of this module's own public surface; __all__ below satisfies
# both mypy and pyflakes -- "as X" self-aliasing satisfies mypy but
# pyflakes still flags it as an unused import) -- see the module
# docstring.
from pitloom.cli.options_resolve import (
    _load_pitloom_tool_section,
    _quote_optional,
    _resolve_creation_metadata,
    _resolve_describe_relationship,
    _resolve_hf_output_path,
    _resolve_model_output_path,
    _resolve_output_path,
    _resolve_output_source,
    _resolve_pretty,
    _resolve_project_generation_settings,
    _resolve_project_paths,
    _ResolvedCreationMetadata,
    _ResolvedCreators,
    _ResolvedTools,
    _ResolvedValue,
)
from pitloom.core._models_wheel_types import parse_build_timeout
from pitloom.core.build_options import BuildOptions

__all__ = [
    "_load_pitloom_tool_section",
    "_quote_optional",
    "_resolve_creation_metadata",
    "_resolve_describe_relationship",
    "_resolve_hf_output_path",
    "_resolve_model_output_path",
    "_resolve_output_path",
    "_resolve_output_source",
    "_resolve_pretty",
    "_resolve_project_generation_settings",
    "_resolve_project_paths",
    "_ResolvedCreationMetadata",
    "_ResolvedCreators",
    "_ResolvedTools",
    "_ResolvedValue",
    "add_offline_argument",
    "add_use_lockfile_argument",
    "add_allow_build_argument",
    "add_no_build_isolation_argument",
    "add_build_timeout_argument",
    "build_options_from_args",
    "add_debug_argument",
]


def add_offline_argument(parser: argparse.ArgumentParser, effect: str) -> None:
    """Add the shared ``--offline``/``--no-offline`` flag.

    The mechanics (``BooleanOptionalAction``, ``default=None`` so the CLI
    can defer to ``[tool.pitloom] offline`` when omitted) and the closing
    "Defers to..." sentence are identical for every command that offers
    this flag; only what "forbid network access" actually does differs by
    command/target. *effect* is spliced in verbatim right after "Forbid
    network access" (include its own leading punctuation and trailing
    period, e.g. ``" -- skip PyPI lookup, no error (...)."``) so each
    caller keeps its own accurate, command-specific wording instead of one
    generic sentence that would misdescribe some commands' actual behaviour.
    """
    parser.add_argument(
        "--offline",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            f"Forbid network access{effect} Defers to [tool.pitloom] "
            "offline (off by default) when omitted."
        ),
    )


def add_use_lockfile_argument(parser: argparse.ArgumentParser, effect: str) -> None:
    """Add the shared ``--use-lockfile``/``--no-use-lockfile`` flag.

    Unlike ``--offline``/``--enrich`` this is an *opt-out* flag: the lock/pin
    file cascade is on by default. ``default=None`` here still means
    "unset", deferring to ``[tool.pitloom] use-lockfile`` (itself on by
    default) when omitted.
    """
    parser.add_argument(
        "--use-lockfile",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            f"Resolve exact versions from a lock/pin file cascade{effect} "
            "Defers to [tool.pitloom] use-lockfile (on by default) when "
            "omitted."
        ),
    )


def add_allow_build_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--allow-build`` flag.

    Unlike ``--offline``/``--use-lockfile`` above, this is a plain
    ``store_true`` flag with a literal ``False`` default, not a
    ``BooleanOptionalAction`` deferring to ``[tool.pitloom]`` when unset --
    deliberately: the config file being read lives in the (untrusted)
    project being scanned, and it must never be able to silently opt
    itself into third-party code execution. This always defaults to off
    and must be passed explicitly on every invocation that wants it.
    """
    parser.add_argument(
        "--allow-build",
        action="store_true",
        default=False,
        help=(
            "SECURITY: allow Pitloom to invoke a project's own PEP 517 "
            "build backend (subprocess; may install build-requires from "
            "the network) to discover a wheel's real file list -- either "
            "for a backend with no static-config discovery module of its "
            "own (currently: uv_build), or as a fallback when a "
            "supported backend's own static discovery fails on this "
            "project. Executes third-party build-time code. Off by "
            "default -- without it, an unhandled or failed backend falls "
            "back to the Hatchling-based heuristic with a WARNING:, "
            "unchanged. Deliberately has no [tool.pitloom] equivalent, "
            "unlike --offline/--content-type above: a target project's "
            "own pyproject.toml must never be able to silently enable "
            "code execution for whoever scans it."
        ),
    )


def add_allow_signed_wheel_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--allow-signed-wheel`` flag (``embed-wheel`` and
    ``wheel --embed``).

    A plain ``store_true`` with a literal ``False`` default, like
    ``--allow-build`` and ``--allow-mismatch``: removing a signature is a
    per-run decision, so no ``[tool.pitloom]`` key can make it ambient.
    """
    parser.add_argument(
        "--allow-signed-wheel",
        action="store_true",
        default=False,
        help=(
            "SECURITY: embed into a wheel that carries a RECORD signature "
            "(RECORD.jws, RECORD.p7s). The embed rewrites RECORD, so the "
            "signature would no longer verify: it is removed, and the wheel "
            "must be re-signed afterwards. Without this flag such a wheel "
            "is refused and left untouched. Deliberately has no "
            "[tool.pitloom] equivalent."
        ),
    )


def add_no_build_isolation_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--no-build-isolation`` flag. No effect without
    ``--allow-build`` (the library warns if passed without it)."""
    parser.add_argument(
        "--no-build-isolation",
        action="store_true",
        default=False,
        help=(
            "With --allow-build, skip creating an isolated build "
            "environment and use the current Python environment's "
            "already-installed build backend instead (faster, no "
            "network) -- mirrors 'python -m build --no-isolation'. No "
            "effect without --allow-build (logs a WARNING: if passed "
            "alone)."
        ),
    )


def _build_timeout_arg(text: str) -> int:
    """``type=`` callable for ``--build-timeout``: parse *text* via the
    single shared duration parser
    (:func:`~pitloom.core._models_wheel_types.parse_build_timeout`) and
    convert its ``ValueError``/``TypeError`` into
    ``argparse.ArgumentTypeError`` so argparse reports it the normal way
    (``argument --build-timeout: ...``, exit code 2) instead of a raw
    traceback."""
    try:
        return parse_build_timeout(text)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def add_build_timeout_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--build-timeout`` flag.

    ``default=None`` (like ``--offline``/``--use-lockfile`` above) means
    "not given" -- needed to tell an explicit value apart from Pitloom's
    own default when warning about a stray flag without ``--allow-build``.
    """
    parser.add_argument(
        "--build-timeout",
        type=_build_timeout_arg,
        default=None,
        metavar="DURATION",
        help=(
            "With --allow-build, stop the build after DURATION -- "
            "seconds (e.g. 900) or h/m/s units (e.g. 90m, 1h30m); "
            "default 20m, max 7 days -- and fall back to static file "
            "discovery with a WARNING:. No effect without --allow-build."
        ),
    )


def build_options_from_args(args: argparse.Namespace) -> BuildOptions:
    """Bundle ``--allow-build``/``--no-build-isolation``/``--build-timeout``
    into one :class:`~pitloom.core.build_options.BuildOptions`, unsettled:
    the caller settles it for its target before reading any metadata."""
    return BuildOptions(
        allow=args.allow_build,
        no_isolation=args.no_build_isolation,
        timeout=args.build_timeout,
    )


def add_debug_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--debug``/``--no-debug`` flag.

    Same ``BooleanOptionalAction``/``default=None`` mechanics as
    :func:`add_offline_argument` -- ``None`` (the flag omitted) means
    "no explicit choice", letting :func:`pitloom.logging_config.apply_debug_override`
    leave an ambient ``PITLOOM_DEBUG`` as it found it, rather than the CLI
    silently forcing debug output off.
    """
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Surface DEBUG:-level diagnostics on stderr (developer detail, "
            "e.g. why an extraction step was skipped). Same effect as "
            "setting PITLOOM_DEBUG=1; --no-debug overrides an ambient "
            "PITLOOM_DEBUG back off for this invocation. Covers entry "
            "points that don't parse this flag (the Hatchling build hook, "
            "the library API) either way."
        ),
    )
