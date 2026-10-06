# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Run the manual CLI integration checks unattended.

Real ``loom`` processes, fixture projects in a fresh temp dir (never the
repo tree), stdlib only, Linux/macOS/Windows. Three kinds of check:

- ``1``-``17``, ``B1``-``B7``: the numbered checks of
  ``working-docs/implementation/manual-cli-checks.md`` (check 6, skills
  drift, needs judgement and stays manual);
- ``M/<command>/<group>/<variant>``: the CLI matrix -- every subcommand
  x its options x the environment variables that change it, declared in
  ``_matrix_plan.py``; ``M/completeness`` fails on any subcommand or
  option the plan does not classify;
- ``S1``-``S8``: commands run in order, where one's side effect is the
  next one's input.

Usage::

    python scripts/manual_cli_checks                  # every offline check
    python scripts/manual_cli_checks --network        # also network checks
    python scripts/manual_cli_checks --only 'M/project/*' --only S2
    python scripts/manual_cli_checks --list           # every check id
    python scripts/manual_cli_checks -j 8 --report matrix.md

It checks the ``pitloom`` importable by the interpreter running it
(``sys.executable -m pitloom``) and prints which one first: use the
checkout's environment (e.g. ``.venv/bin/python``). Wheel-based checks
need ``build`` and ``hatchling`` (``pitloom[build]``); B2, B3 and B5
need POSIX signals and skip on Windows. A deviation already tracked in
the roadmap is reported as ``KNOWN`` (see ``_known.py``), not ``FAIL``.
Exit status: 1 if any check failed, else 0.

See also: ``tests/scripts/test_manual_cli_checks.py`` (keeps this
runner working), ``scripts/compare_allow_build.py`` (check 10).
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import signal
import subprocess  # nosec B404
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import _checks_build  # noqa: F401  # pylint: disable=unused-import
import _checks_config  # noqa: F401  # pylint: disable=unused-import
import _checks_core  # noqa: F401  # pylint: disable=unused-import
import _checks_model  # noqa: F401  # pylint: disable=unused-import
import _checks_setuptools  # noqa: F401  # pylint: disable=unused-import
import _checks_wheel  # noqa: F401  # pylint: disable=unused-import
import _fixtures
import _matrix
import _sequences  # noqa: F401  # pylint: disable=unused-import
from _harness import CHECKS, Check, CheckSkipped, Context, child_env
from _known import known_issue

import pitloom

_PRINT_LOCK = threading.Lock()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="manual_cli_checks",
        description=(__doc__ or "").split("\n\n", maxsplit=1)[0],
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="check id or glob, e.g. 7, B*, 'M/project/*' "
        "(repeatable; comma-separated also works)",
    )
    parser.add_argument(
        "--network", action="store_true", help="also run checks that need the network"
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=os.cpu_count() or 2,
        help="checks run in parallel (default: CPU count)",
    )
    parser.add_argument(
        "--report", type=Path, help="write every result as a Markdown table here"
    )
    parser.add_argument(
        "--keep", action="store_true", help="keep the scratch dir for inspection"
    )
    parser.add_argument("--list", action="store_true", help="list checks and exit")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print a failing check's full message",
    )
    return parser.parse_args(argv)


def _selected(patterns: list[str]) -> list[Check]:
    wanted = [p.strip() for item in patterns for p in item.split(",") if p.strip()]
    if not wanted:
        return list(CHECKS)
    unmatched = [
        p for p in wanted if not any(fnmatch.fnmatchcase(c.check_id, p) for c in CHECKS)
    ]
    if unmatched:
        raise SystemExit(f"no check matches: {', '.join(unmatched)}")
    return [
        c for c in CHECKS if any(fnmatch.fnmatchcase(c.check_id, p) for p in wanted)
    ]


def _pitloom_location() -> str:
    """The ``pitloom`` a check's ``loom`` imports: probed, as every check
    runs, with :func:`child_env` and a working directory other than ours.

    Exits unless it is the one this runner imported: the matrix plan
    derives expectations (e.g. which options warn) from our own copy, so
    checks against another copy would fail or pass for the wrong reason.
    """
    proc = subprocess.run(  # nosec B603
        [
            sys.executable,
            "-c",
            "import pitloom; print(pitloom.__version__, pitloom.__file__)",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=child_env(),
        cwd=tempfile.gettempdir(),
    )
    if proc.returncode != 0:
        raise SystemExit(f"pitloom is not importable by {sys.executable}")
    location = proc.stdout.strip()
    theirs = Path(location.split(" ", 1)[-1]).resolve()
    ours = Path(pitloom.__file__).resolve()
    if theirs != ours:
        raise SystemExit(
            f"checks would run pitloom from {theirs}, not this runner's {ours}"
            " -- check PYTHONPATH"
        )
    return location


def _run_one(item: Check, root: Path, args: argparse.Namespace) -> tuple[str, str]:
    ctx = Context(
        root / item.check_id.replace("/", os.sep),
        network=args.network,
        verbose=args.verbose,
    )
    ctx.work.mkdir(parents=True)
    start = time.monotonic()
    try:
        if item.network and not args.network:
            raise CheckSkipped("needs --network")
        item.func(ctx)
        status, detail = "PASS", ""
    except CheckSkipped as exc:
        status, detail = "SKIP", str(exc)
    # Any exception fails this one check, never the whole run.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
        tracked = known_issue(item.check_id, detail)
        if tracked:
            status, detail = "KNOWN", f"{tracked} -- {detail}"
    detail = "\n".join([detail, *ctx.notes]).strip()
    with _PRINT_LOCK:
        print(
            f"{status:<5} {item.check_id}  {item.title} "
            f"({time.monotonic() - start:.1f}s)",
            flush=True,
        )
        if detail and (status in ("SKIP", "KNOWN") or args.verbose or status == "FAIL"):
            lines = detail.splitlines()
            shown = lines if args.verbose else lines[:2]
            for line in shown:
                print(f"      {line}", flush=True)
    return status, detail


def _write_report(path: Path, rows: list[tuple[Check, str, str]]) -> None:
    lines = ["| Check | What | Result | Detail |", "| --- | --- | --- | --- |"]
    for item, status, detail in rows:
        cell = detail.replace("|", "\\|").replace("\n", "<br>")[:500]
        lines.append(f"| `{item.check_id}` | {item.title} | {status} | {cell} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the selected checks; 1 if any failed."""
    args = _parse_args(argv)
    _matrix.register(CHECKS)
    if args.list:
        for item in CHECKS:
            print(
                f"{item.check_id}  {item.title}{' [network]' if item.network else ''}"
            )
        return 0
    selected = _selected(args.only)
    # A Python-level handler (not SIG_IGN, as in a background shell job)
    # lets child `loom` processes start with Ctrl-C enabled.
    if signal.getsignal(signal.SIGINT) == signal.SIG_IGN:
        signal.signal(signal.SIGINT, signal.default_int_handler)
    print(f"pitloom {_pitloom_location()}\npython {sys.executable}", flush=True)
    # Resolved: on macOS the temp dir is behind a /var -> /private/var link.
    root = Path(tempfile.mkdtemp(prefix="pitloom-mcc-")).resolve()
    print(f"scratch {root}", flush=True)
    _fixtures.install(_fixtures.Fixtures(root / "_fixtures"))
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(pool.map(lambda c: _run_one(c, root, args), selected))
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)
    rows = [
        (item, status, detail)
        for item, (status, detail) in zip(selected, results, strict=True)
    ]
    if args.report:
        _write_report(args.report, rows)
    counts = {
        s: sum(1 for _, st, _ in rows if st == s)
        for s in ("PASS", "FAIL", "KNOWN", "SKIP")
    }
    print(", ".join(f"{n} {s.lower()}" for s, n in counts.items()))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
