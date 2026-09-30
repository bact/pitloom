# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Run a command, retrying only when it failed because of the network.

For CI steps whose tool downloads remote data on every run (``spdx3-validate``
and ``loom validate-wheel`` fetch the SPDX schema, ontology and context from
spdx.org). A failure is network-caused when the tool's output ends in a
network exception or CLI ``ERROR:`` line, as classified by
``tests/_network_classify.py`` (shared with the pytest helpers so the two
cannot drift), or when an attempt exceeds ``--timeout``. Any other failure is
final and is never retried.

Exit status: 0 the command passed; 1 it failed for a non-network reason
(its own exit status is printed); 75 (``EX_TEMPFAIL``) every attempt failed
because of the network, so the command's verdict is unknown. A network
failure never becomes a pass.

The command's output is replayed on stdout between ``::stop-commands::``
markers, so a line starting with ``::`` cannot run as a workflow command.
Everything is written as bytes (the command's own, and UTF-8 for this
script's lines): a non-UTF-8 stdout encoding, such as cp1252 on a Windows
runner, cannot fail the replay.

Usage: ``python scripts/retry_network.py [--attempts N] [--delay S]
[--timeout S] -- COMMAND [ARG ...]``
"""

from __future__ import annotations

import argparse
import secrets
import subprocess  # nosec B404
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# pylint: disable-next=wrong-import-position
from tests._network_classify import network_cause_in_text  # noqa: E402

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_NETWORK = 75


def _run_once(command: Sequence[str], timeout: float) -> tuple[int | None, bytes]:
    """Run *command*; return its exit status (``None`` on timeout) and output."""
    try:
        res = subprocess.run(  # nosec B603
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return None, exc.output or b""
    return res.returncode, res.stdout


def _write(data: bytes) -> None:
    """Write *data* to stdout as is, bypassing its text encoding."""
    sys.stdout.flush()
    sys.stdout.buffer.write(data if data.endswith(b"\n") else data + b"\n")
    sys.stdout.buffer.flush()


def _say(text: str) -> None:
    """Write one line of this script's own, UTF-8 encoded."""
    _write(f"retry_network: {text}".encode())


def _replay(output: bytes, verdict: str | None = None) -> None:
    """Write *output* and *verdict* with workflow commands disabled."""
    token = secrets.token_hex(16)
    _write(f"::stop-commands::{token}".encode())
    _write(output)
    if verdict is not None:
        _say(verdict)
    _write(f"::{token}::".encode())


def run_with_retry(
    command: Sequence[str], attempts: int, delay: float, timeout: float
) -> int:
    """Run *command* up to *attempts* times; see the module docstring."""
    for attempt in range(1, attempts + 1):
        status, output = _run_once(command, timeout)
        if status == 0:
            _replay(output)
            return EXIT_PASSED
        if status is None:
            cause: str | None = f"no result within {timeout:g} s"
        else:
            cause = network_cause_in_text(output.decode("utf-8", errors="replace"))
        verdict = (
            f"attempt {attempt}/{attempts}: exit status {status}, not a network failure"
            if cause is None
            else f"attempt {attempt}/{attempts}: network failure: {cause}"
        )
        _replay(output, verdict)
        if cause is None:
            return EXIT_FAILED
        if attempt < attempts:
            wait = delay * 3 ** (attempt - 1)
            _say(f"retrying in {wait:g} s")
            time.sleep(wait)
    _say(f"all {attempts} attempts failed because of the network")
    return EXIT_NETWORK


def _positive(kind: Callable[[str], float]) -> Callable[[str], float]:
    def parse(raw: str) -> float:
        value = kind(raw)
        if value <= 0:
            raise argparse.ArgumentTypeError(f"must be positive: {raw}")
        return value

    return parse


def main(argv: Sequence[str] | None = None) -> int:
    """Parse *argv* and run the command."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--attempts", type=_positive(int), default=3)
    parser.add_argument(
        "--delay", type=float, default=10.0, help="first back-off, tripled each time"
    )
    parser.add_argument(
        "--timeout", type=_positive(float), default=300.0, help="per attempt"
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given")
    if args.delay < 0:
        parser.error("--delay must not be negative")
    return run_with_retry(command, args.attempts, args.delay, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
