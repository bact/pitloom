---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-23
Last-Modified: 2026-11-23
---

# Message catalogue PR 17a: build record

See also: [message-catalogue-pr17-plan.md](message-catalogue-pr17-plan.md)
(the plan, the questions and the rulings) and
[message-catalogue-pr17-plan-steps.md](message-catalogue-pr17-plan-steps.md).

Scope: sites 2, 6, 10, 11, 12, 15, 16, 19, 20, 21, 22, 26, 27, 34, 42, 43
and 44, plus H1 and H2. The uncoded ratchet goes from 44 to 27.

## Probes

### P1: the two safety nets (Q6)

- **Dataset card net (`_loom_dataset_meta._optional_card`): KEPT.**
  Fuzzing about 60 card frontmatters (deep nesting, a `10**5000` version,
  every YAML type for `license`, aliases, an alias bomb, recursion) and
  file-system shapes did not reach it: the card reader warns for each
  problem itself. A NUL or surrogate name reaches it only when
  `_optional_card` is called directly (`read_sources` guards with
  `os.path.isdir` first). A **removed current directory does reach it**:
  `cwd_relative_label` calls `os.getcwd()`, which raises
  `FileNotFoundError`. The net is now `file-unreadable` with the new
  `DIR_READ_LINE` (`DIR=<dir>: could not read for the dataset card;
  <failure>`), and `CARD_SKIPPED_WARNING` is gone.
  Review round 1: the label is now computed in its own `try` (bare name on
  an `OSError`), so a removed current directory no longer skips an
  absolute dataset directory's card; the coded net stays for what else
  escapes the reader. Caveat: through the full `loom` API the same run
  still fails later with an uncoded `FileNotFoundError` traceback at
  `_loom_dataset.py` (`cwd_relative_label`, unguarded there).
- **Enricher net (`enrich.run_enrichers`): DROPPED.** No input reached it.
  An enricher's exception now propagates: the run fails with the CLI's
  coded `ERROR:` line (exit 1), instead of a `WARNING: Enricher ...
  failed, skipping` line.

### P2: an unknown provenance schema in the configuration (H2)

- HEAD: `ERROR: loom generate: Unknown provenance schema 'bogus'; known:
  pitloom/1`, uncoded, raised halfway through the SBOM.
- Now: `ERROR: loom generate: FILE=<dir>/pyproject.toml:
  [tool.pitloom.provenance] schema: must be one of pitloom/1, got a string
  'bogus' [config-invalid]`, when the configuration is read.

### P4: `loom env` when pipdeptree fails (H1)

- HEAD: `Failed to run pipdeptree (exit status 1): ...` and `Unexpected
  pipdeptree output: expected a JSON list`, uncoded.
- Now: `pipdeptree exited with code 1; last output: <line>
  [environment-unreadable]`, `could not run pipdeptree; <strerror>`,
  `pipdeptree output is not JSON; <failure>` and `pipdeptree output is not
  its --json list: <problem>` (closed table). pipdeptree's text is the last
  non-blank line, masked, cut and escaped. The missing-module case still
  shows the interpreter path, because pipdeptree's own output does.

## What was built

- New entry `environment-unreadable` (`messages/_environment.py`, helpers
  in `_environment_say.py`; topic dependencies) and `CodedRuntimeError`.
- `option-invalid` gains the namespace lines (`namespace_invalid()`);
  `EXPECTED` gains `one-of-schema` and `sbom-content`. The namespace
  problem texts moved to the leaf `core/namespace_problems.py` (re-exported
  by `core.iri`), so `core.iri` imports the catalogue at module level
  without a cycle.
- `file-unreadable` gains `DIR_READ_LINE`. The per-wheel handlers
  (`verify-wheel`, `validate-wheel`, `embed-wheel`) say an uncoded
  `OSError` via `report_wheel_failure()`: `file-unreadable` for the wheel
  by its file name, or `input-not-found` when the system says it is gone
  (an errno-less `FileNotFoundError` included). An `OSError` with no
  description of its own is said by its class name, never its text
  (`system_failure()`, also used by `file_unreadable_error()`).
- Review round 1: an embed's writes are coded where they are made
  (`_embed_wheel._coded_write`): the new wheel (temporary file, replace)
  and the `-o` copy (`write_sbom_copy`, used by `embed_wheel_sbom()` and
  `loom wheel --embed`) are `file-unwritable` (`WRITE_ERROR_LINE`, `for
  the SBOM`) naming that file, raised as the new `CodedOSError`. So
  `report_wheel_failure()` sees only reads. The hook does not embed through
  these (it hands Hatchling the SBOM via `build_data`).
- The usage hint is two module-level `Summary` entries (`USAGE_HINTS`);
  the text is unchanged.
- `core.provenance.require_provenance_choices()` checks format, schema and
  detail, in that order, for `ProvenanceConfig` and
  `PitloomConfig.provenance`. The writer-side checks are now
  `InternalError`.
- Inventory rules, each with positive and negative fixtures:
  - R-a (`_scope.is_os_error_rebuilt`, an AST check since review round
    1): an `OSError` rebuilt from `errno.E*` or `<x>.errno`, exactly
    `os.strerror(...)` or `<x>.strerror`, and at most a bare name or
    `str(<name>)` as path, is detail. The `template is None` condition was
    dropped: a template is set only when `dynamic_expr` is not.
  - R-b (`_relay` `exception-param`): a function whose only statement is
    `print_error(str(p), code=code_of(p))`, *p* a parameter annotated with
    an exception class (`Exception`, `BaseException`, `...Error`, a `|`
    union of them) and no default; a bare `p` as text stays counted.
  - R-c (`_relay` prefixed): `one_line(<param>, <LIMIT>)` with a module int
    constant.
- H1: `_shape_error` removed from `DETAIL_EXC`; the
  `Unknown provenance schema` internal pattern removed.

## Review round 2

- An embed's I/O error is said by its direction: `refuse_unreadable`
  (`core/wheel_dist_info.py`, also behind `RefusingReader.read`) turns an
  uncoded `OSError` of a member read into `file-unreadable` for the wheel,
  still an `OSError` (`recoded` as `CodedOSError`; `input-not-found` for a
  missing errno), so `_coded_write` passes it through and says only the
  writes as `file-unwritable`. This also codes a read error for
  `verify-wheel`, `validate-wheel` and every `METADATA` reader.
- `write_sbom_copy` writes `-o -` through the shared stdout writer, not
  wrapped: a closed pipe is never `FILE=-`.
- `embed_wheel_sbom()` documents `CodedOSError`.
- The dataset card's DIR line drops main's `| Field(s) affected
  (skipped): ...` suffix: the rule for card lines (H8 in
  `implementation/message-catalogue-families.md`, item 4; Q13 of
  `message-catalogue-pr14-rulings.md` for the Hub lines) is that the
  entry's `did` says what is lost; `file-unreadable`'s `did` says a model
  or dataset card, the DIR line too, sets none of the fields it states.
  The summary no longer names the removed current directory as its cause
  (round 1 fixed that path).

## Behaviour changes for the CHANGELOG

- Q4 (API): `ProvenanceConfig(format=..., schema=..., detail=...,
  preserve_source_metadata=...)` and `PitloomConfig.provenance` raise a
  coded `ValueError` (`option-invalid`) when built, not when provenance is
  first written (`preserve_source_metadata` was silently `auto`). An unknown
  configuration schema is `config-invalid` (with `FILE=`).
- An enricher's exception propagates (the net is dropped).
- `embed_sbom_in_wheel()` and `embed_wheel_sbom()`: a refused write is a
  `CodedOSError` (an `OSError`, no longer a `PermissionError` or
  `FileNotFoundError` subclass), `file-unwritable`.
- `loom env` errors are coded `RuntimeError`s (`environment-unreadable`)
  with new texts.
- The namespace error text is reordered: the condition first, the value
  last (`namespace must not contain '#': <value>`, `namespace is empty`).
- The empty-SBOM (`sbom_content`) and `Creator.type` refusals use the
  shared `invalid_value` text (`must be ..., got ...`).
- The fickling relay reads `WARNING: fickling: <text>` (it was
  `WARNING: fickling reported on stderr: <text>`).
- `project_metadata` without `pitloom_config` is `option-no-effect`.

## Caveats and out-of-scope findings

- Q9: fixed in review round 1 (writes coded at their site). The other
  generators' `-o` writes (`write_sbom_output`) remain an uncoded
  `OSError` on every surface; out of scope here.
- `cwd_relative_label` in `_loom_dataset.py` is unguarded against a
  removed current directory (see P1).
- H3 (swallowed network failures) is unchanged.
- A `Creator.type` set to a non-string after construction raises
  `AttributeError` in `creation_info`, not the coded refusal.
- pipdeptree's own output can show the interpreter path (see P4).

## Reference page sizes

The largest pages are `message-codes-files.md` (29,649 bytes, 444 lines;
skill copies 29,613, after review round 1), `message-codes-targets.md` (27,547) and
`message-codes-values.md` (23,482). All pages are under 30,000 bytes and
800 lines.
