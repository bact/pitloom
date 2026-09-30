---
Created: 2026-09-17
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `--debug` flag and DEBUG:-level output ([PR #201](https://github.com/bact/pitloom/pull/201))

See also: [roadmap.md](../design/roadmap.md) (Near-term -- "Diagnostics /
logging"), the "CLI output" section of the top-level `CLAUDE.md`.

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

## Surface `DEBUG:`-level output on request

Shipped both triggers rather than choosing one:

- A new top-level `--debug` flag, parsed before the subcommand (like
  `-V`). `cli/verbose.py`'s existing `--verbose` was left alone since it
  does something unrelated.
- The `PITLOOM_DEBUG` environment variable, which also covers entry
  points that don't parse CLI flags themselves (the Hatchling build
  hook, every public library-API generator).

`configure_logging(debug=...)` resolves `None` (every existing
no-argument call site) against the env var; an explicit `True`/`False`
(the CLI's `--debug`) wins outright. See `pitloom.logging_config`.

## Promote silent-data-loss `DEBUG:` messages to `WARNING:`

18 messages across the HF Hub, PyTorch/PT2, fastText, README
enrichment, and sdist extractors, plus `pitloom.loom`'s
caller-provenance detection, now surface by default (not just under
`--debug`) when a failure drops or degrades an SBOM/AIBOM field.

Each names the affected field(s) via one shared, grep-able helper,
`field_loss_suffix()` (`pitloom.logging_config`), instead of
hand-duplicated suffix text per call site.

## Ctrl-C at the CLI entry point

Ctrl-C prints one `ERROR: interrupted` line. The process must still end
*by SIGINT*, not with a plain exit status 130: bash stops a loop or
script only when its child died of SIGINT; after a normal exit it
assumes the child handled Ctrl-C and runs the next command.

- `console_main()` (the `loom`/`pitloom` console scripts and `python -m
  pitloom`) re-raises the `KeyboardInterrupt` with `sys.excepthook` set
  to print nothing. Python (3.8+) then finalizes and ends by SIGINT, or
  exits 130 where the signal does not end it (PID 1),
  `STATUS_CONTROL_C_EXIT` on Windows. Rejected: calling
  `signal.raise_signal(SIGINT)` from `console_main()` itself, which
  skips atexit handlers and stream flushing.
- `main()` (in-process callers, the tests) returns 130 instead.

- **Traceback under debug, not `-v`.** The traceback is a developer
  diagnostic (where a seemingly stuck run was), so it follows
  `--debug`/`PITLOOM_DEBUG` via `logging_config.debug_enabled()`.
  `cli_error_handler` gates its traceback on `-v`, which is a
  per-subcommand flag (not parsed on every command) and means "option
  details"; `--debug` is global.
- **Composes with `TerminationGuard`.** The guard leaves SIGINT to
  Python; the `KeyboardInterrupt` unwinds through the build wait loop
  (kills the tree) and the guard owner's exit (runs the cleanups,
  restores handlers) before reaching `main()`.
- **Library API unchanged**: only `main()` catches it; a library caller
  still gets the `KeyboardInterrupt`.
