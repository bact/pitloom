# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Entry points of the ``loom``/``pitloom`` command line and ``python -m pitloom``."""

from __future__ import annotations

import sys
import typing
from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType

from pitloom.cli.parser import _build_parser, command_frame, command_path
from pitloom.logging_config import (
    apply_debug_override,
    configure_logging,
    debug_enabled,
    error_frame,
    print_error,
    print_traceback,
    set_error_frame,
)

# 128 + SIGINT, the status a shell reports for a command ended by Ctrl-C.
_EXIT_INTERRUPTED = 130


def main() -> int:
    """Main entry point for the Pitloom CLI, for in-process callers.

    Every ``ERROR:`` line starts with the frame of its command (``loom
    generate: ``; ``loom: `` before the command is known), so Ctrl-C is one
    ``ERROR: loom generate: interrupted`` line and exit status 130; the
    traceback follows only with ``--debug``/``PITLOOM_DEBUG``. By the time
    the ``KeyboardInterrupt`` gets here, a ``--allow-build`` build tree
    has been killed and its temporary directories removed (the
    :class:`~pitloom.core.build_signals.TerminationGuard` owner's exit).
    """
    try:
        with _framed_session():
            return _run()
    except KeyboardInterrupt:
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
        with _framed_session():
            return _run()
    except KeyboardInterrupt:
        sys.excepthook = _ignore_exception
        raise


@contextmanager
def _framed_session() -> Iterator[None]:
    """Run the command line with its error frame open (``loom: `` until the
    subcommand is known), and report a Ctrl-C inside it, so the line carries
    the frame of the command that was running; the ``KeyboardInterrupt``
    goes on to the caller."""
    with error_frame(command_frame("")):
        try:
            yield
        except KeyboardInterrupt:
            _report_interrupt()
            raise


def _report_interrupt() -> None:
    """Print the one ``ERROR:`` line for Ctrl-C, and under debug the
    traceback of the ``KeyboardInterrupt`` being handled."""
    print_error("interrupted")
    if debug_enabled():
        print_traceback()


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
    set_error_frame(command_frame(command_path(args)))

    if hasattr(args, "func"):
        return typing.cast(int, args.func(args))
    return 1


if __name__ == "__main__":
    sys.exit(console_main())
