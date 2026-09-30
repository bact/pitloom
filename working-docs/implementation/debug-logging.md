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

`__main__.main()` catches `KeyboardInterrupt`: one `ERROR: interrupted`
line, exit status 130 (128 + SIGINT, what a shell reports for Ctrl-C).
Returned, not re-raised as a `SIG_DFL` SIGINT: keeps `main()` testable
in-process. Trade-off: a parent that checks for death by SIGINT (a bash
loop, `subprocess` returncode `-2`) sees exit status 130 instead.

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
