---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-25
Last-Modified: 2026-11-25
---

# Message catalogue sweep B ("strict"): plan and rulings

See also: [message-catalogue-sweep-plan.md](message-catalogue-sweep-plan.md)
(sweep A, built), [message-catalogue-sweep-b-evidence.md](message-catalogue-sweep-b-evidence.md)
(measured state, proof table), [message-catalogue-finish-plan.md](message-catalogue-finish-plan.md).

Status 2026-11-25: planned by Opus (read-only), reviewed by Fable (read-only);
the maintainer ruled "go with the recommendations", split B into B1 and B2, and
asked that every sweep A leftover be fixed or carried. Reference tree: main
3be02626 (after #536). Counts are in the evidence page.

## Rulings (all taken as recommended)

- **R1** Prune `DETAIL_EXC` to the 21 names that need proof; rename
  `_usage_ast._OverCap` to `_UsageOverCap`. (`_over_cap` is a helper that
  returns `ParameterCountRejected`, not a dead name: dropping it is
  count-neutral, measured 630 -> 630.)
- **R2** D5 is strict from INFO upward, with the kinds `summary`, `detail`,
  `relay`.
- **R3** D5 is on by default; per-test `uncoded_output` markers, a stale
  allowance fails.
- **R4** `line_kind` and `RELAY_PREFIXES` live in `pitloom.messages`; relay
  modules keep their own constant; a drift test checks the two agree.
- **R5** An `UNSHOWN_MESSAGE` `ERROR:` line stays uncoded, allowed by marker.
- **R6** Update the hand-written prose (`docs/messages.md:19`, both skills'
  `references/messages.md:20`): a line without a code is a summary, a `-v`
  `KEY=VALUE` detail, another tool's words after its name, an unexpected
  error's own text, the unshown-message line, or an untagged usage or traceback
  line (Fable 9).
- **R7** Two PRs: **B1** (D4, test-only) and **B2** (D5, D6, per-wheel fix).
  If B2 must obey the 30-file cap, split it: B2a (kinds, classifier, inventory
  rule, D6; strict off) and B2b (strict on, markers, per-wheel fix, docs).

## Amendments from the Fable review

1. **Reader relay (B2).** `extract/_reader_relay.py:93` re-says a captured
   reader record (e.g. `fickling: `) with `extra=None`: copy `pitloom_kind`
   through, and let `line_kind` accept `RELAY_FRAME` before a relay prefix.
   Add `_reader_relay.py` and its test to the Opus M fence.
2. **D4 has three kinds, not two.** `detail` (the exception text reaches a
   coded line), `carrier` (a coded line is said from the payload, e.g. a
   `Cap`; the text is neither required nor forbidden) and `signal` (control
   flow, text never shown). Drop the "text appears nowhere" assertion. Carriers:
   `_OverCap`, `HeaderBlockOverCap`, `ModelOverCap`, `NotAModel`,
   `LockFileRefusedError(cap=)`, and (built in B1) `_Unlistable`: its
   `dir-unlistable` line names the directory and the OS error's `strerror`,
   never `str(_Unlistable)`. `_DuplicateKeyError` is `detail`, not `signal`.
3. **D4 proves sites, not only names.** Add a meta-test: every `raise X` in
   `src/` for a table name sits in a (file, function) the table lists, one
   case per catching path. Several names are mixed per site
   (`InvalidRequirement`, `InvalidMarker`, `LockFileRefusedError`).
4. **Packaging classes.** A spy on `__init__` cannot tell Pitloom's raise from
   packaging's: trigger Pitloom's own refusal (nesting, overlong number) and
   assert the reason text. The `_TOO_DEEP` raises (`pep508.py:169,188`) need a
   monkeypatch to reach.
5. **Allowances.** Marks go on `pytest.param` (a marker on a parametrised test
   fails for parameters that emit nothing); read `own_markers` only
   (`get_closest_marker` also sees a module `pytestmark`); run the B2 suite on
   the 3.14 leg and with `test-all-os` before push.
6. **Rulings still needed inside B2 (maintainer or Opus, recorded in the PR):**
   uncoded argparse wording on a Python whose usage text has no catalogue line
   (`usage_code()` returns `None` by design): declare a kind, not an alarm;
   `InternalError` has no code, so the per-wheel fix prints an uncoded `ERROR:`
   in its test, allowed by marker; a coded line over 65,536 characters
   (`trusted_message` returns `None`) gets its own `overlong` kind.
7. **State the INFO gap.** `Logger.handle` runs after `isEnabledFor`, so INFO
   records never reach the hook while the `pitloom` logger is unconfigured.
   That is a silent gap; D6 `-v` runs cover the rest.
8. **No `pytester`** (not enabled). The stale-allowance logic is a pure
   `check(lines, allowances)` function tested directly, plus at most one
   `runpytest_subprocess` smoke test. Put the strict logic in a new module
   (`tests/_message_drift.py` is 429 lines).
9. **Relay prefix list.** Drift test that the prose names each prefix, or
   generate the list into the message reference.
10. **PR #537 conflict is small.** #537 edits `logging_config.py` lines 26 and
    412-470; B2 edits about 51 and 207-225. Do not touch the import line.

## Sweep A leftovers: routing

| Leftover | Goes to |
| --- | --- |
| Per-wheel `except (ValueError, OSError)` swallowing `InternalError` (`cli/commands/utils.py:282`, `cli/commands/verify_wheel.py:119`) | B2 |
| R0911 in `scripts/message_inventory/_relay.py:relay_kind` | B2 |
| `test_usage_parse` hang (a `sys.settrace` that raises leaves `work` unrun; production hang, not only a flake) | Own tiny PR `usage-parse-settrace-hang`, before B's Gate A |
| GGUF dataset provenance names the temp copy (`extract/scanner.py:207-219`, `_restore_source_name`); changes SBOM output | Own PR `gguf-dataset-provenance-source`, before 0.25.0 |
| loom SDK fragment write not `file-unwritable` (`_loom_active_run.py:460`) | Sweep C |
| `os.path.abspath(script_path)` with the cwd gone (`_loom_active_run.py:153`) | Sweep C (same file as the line above) |
| Floor-docs test reads only the first `licenseid>=` | Sweep C |
| Inventory does not follow tuple unpacking or returned values | Consistency rescan |
| Mutation survivors (`_loom_dataset_meta` merge helpers, `_sbom_io` stdout/replace) | Mutation-backfill PR after the rescan |

## Size and fences

B1 about 550 lines, 6 files; B2 about 750 lines, about 40 files (26 are
one-line markers). B1 and B2 are file-disjoint (`_scope.py` versus
`_relay.py`).

- **B1 fence:** `scripts/message_inventory/_scope.py`,
  `src/pitloom/extract/_usage_ast.py` (rename), `tests/messages/test_detail_classes*.py`,
  `tests/scripts/message_inventory/test_scope_detail.py`.
- **B2, Opus M (first, sequential):** `src/pitloom/logging_config.py`,
  `messages/_summary.py`, `messages/_line_kind.py` (new), `messages/_relays.py`,
  `messages/__init__.py`, `cli/kv_output.py`, `extract/_licenseid_relay.py`,
  `extract/_reader_relay.py`, `core/_models_wheel_setuptools_relay.py`,
  `extract/ai_model/pytorch.py`, `scripts/message_inventory/_relay.py`, their
  tests, `tests/messages/test_line_kind.py`.
- **B2, then in parallel:** Opus S (strict check: a new test module,
  `tests/conftest.py`, `pyproject.toml` markers only, `tests/_loom_child.py`);
  Sonnet D6 (`scripts/manual_cli_checks/_harness.py`, `_matrix_run.py`,
  `tests/scripts/test_manual_cli_checks.py`); Sonnet W (per-wheel fix in
  `cli/commands/utils.py`, `verify_wheel.py` and their tests). Then Sonnet
  markers for the 24 other files, then docs.

Gates and risks: see the evidence page, sections "Gates" and "Risks".
