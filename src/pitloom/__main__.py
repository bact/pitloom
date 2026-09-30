# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import sys
import traceback
import typing
from types import TracebackType

from pitloom.cli.parser import _build_parser
from pitloom.logging_config import (
    apply_debug_override,
    configure_logging,
    debug_enabled,
)

# 128 + SIGINT, the status a shell reports for a command ended by Ctrl-C.
_EXIT_INTERRUPTED = 130


def main() -> int:
    """Main entry point for the Pitloom CLI, for in-process callers.

    Ctrl-C is one ``ERROR: interrupted`` line and exit status 130; the
    traceback follows only with ``--debug``/``PITLOOM_DEBUG``. By the time
    the ``KeyboardInterrupt`` gets here, a ``--allow-build`` build tree
    has been killed and its temporary directories removed (the
    :class:`~pitloom.core.build_signals.TerminationGuard` owner's exit).
    """
    try:
        return _run()
    except KeyboardInterrupt:
        _report_interrupt()
        return _EXIT_INTERRUPTED


def console_main() -> int:
    """The ``loom``/``pitloom`` console scripts and ``python -m pitloom``.

    As :func:`main`, but Ctrl-C ends the process by SIGINT, not a plain
    exit status 130: the ``KeyboardInterrupt`` is re-raised with the
    traceback printout off, and Python exits by SIGINT once finalized
    (130 where it cannot, e.g. as PID 1; ``STATUS_CONTROL_C_EXIT`` on
    Windows). A shell sees a Ctrl-C and stops a loop or script running
    ``loom``, rather than going on to the next command.
    """
    try:
        return _run()
    except KeyboardInterrupt:
        _report_interrupt()
        sys.excepthook = _ignore_exception
        raise


def _report_interrupt() -> None:
    """Print the one ``ERROR:`` line for Ctrl-C, and under debug the
    traceback of the ``KeyboardInterrupt`` being handled."""
    print("ERROR: interrupted", file=sys.stderr)
    if debug_enabled():
        traceback.print_exc()


def _ignore_exception(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
) -> None:
    """``sys.excepthook`` printing nothing: the exception was reported."""
    del exc_type, exc, tb


def _run() -> int:
    """Parse the arguments and run the subcommand; its exit status."""
    parser = _build_parser()
    args = parser.parse_args()
    # Parsed before configuring so --debug/--no-debug (parsed here,
    # unlike PITLOOM_DEBUG) can take effect. Routed through PITLOOM_DEBUG
    # itself (see apply_debug_override()'s docstring) rather than passed
    # as configure_logging(debug=...) here, so every subcommand's own
    # bare configure_logging() call agrees with this one instead of
    # silently reverting to INFO. getattr() rather than args.debug: a
    # Namespace missing "func" (see
    # test_main_returns_1_when_parsed_args_have_no_func) may lack every
    # other attribute too.
    apply_debug_override(getattr(args, "debug", None))
    configure_logging()

    if hasattr(args, "func"):
        return typing.cast(int, args.func(args))
    return 1


if __name__ == "__main__":
    sys.exit(console_main())
