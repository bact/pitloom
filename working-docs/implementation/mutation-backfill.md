---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Mutation backfill (2026-11-26): recorded survivors and credential masking

See also: [recurring-bug-patterns-test-harness.md](recurring-bug-patterns-test-harness.md)
("Mutation testing has two silent ways to lie"),
[testing-and-review-policy.md](testing-and-review-policy.md) (Gate B),
[known-bugs.md](../design/known-bugs.md) (the bugs this pass found).

A tests-only pass that closes the backlog of mutation survivors the
catalogue PRs parked for a "mutation-backfill PR", re-measured on `main`
4f927257, plus a first pass on the credential masking modules that no PR
had mutated. `src/` is unchanged.

## Scope (decided with a second opinion)

The inventory found 15 recorded open survivors and 3 "no pass yet" notes,
and about 60 non-message modules plus 31 `messages/` modules changed since
`v0.24.0` with no recorded pass. Options: (A) recorded survivors only,
(B) those plus a bounded set of the riskiest unpassed modules, (C) all.
Chosen: **B**, Opus concurring. The bounded set is credential masking and
finding, where a missed branch leaks a secret: `core/url_masking/_hits`,
`_urls`, `_detect`, `_tokens` and `export/_spdx3_credentials/_find`,
`_fields`, `_check`. The cap was 40-50 killed survivors, split by package. The
masking package alone reached it, so `_spdx3_credentials` moves to a second
backfill PR (see [Backlog](#backlog)). `messages/` belongs to the
consistency rescan and was left out. The licence modules were left out
because a parallel change is rewriting them.

## Method

- Scratch copies of `main` (`git archive`), eight of them, one per worker.
  Nothing was mutated in the worktree.
- An AST mutator: comparison, boolean-operator and arithmetic swaps, negated
  conditions, `return None`, constants (`True`/`False`, `n+1`), dropped call
  statements and `raise`, `break`/`continue` swaps, `+=`/`-=`, unwrapped
  `sorted`/`reversed`, and `min`/`max`. Hand-written mutants were added for
  the recorded ones the operators do not make (`repr(min(changed))`,
  `is True` to `is not False`).
- **Test selection by coverage context.** One full-suite run with
  `--cov-context=test` maps each line to the tests that run it. A mutant
  runs only those tests, with `-x`. A line covered by more than 200 tests
  is narrowed to the test files whose path names the topic. A line run
  only at import (a default argument, a module constant, a dataclass flag)
  falls back to the module's own tests. If that run times out, the
  function's body coverage is used instead (the callers that can see a
  default).
- `PYTHONDONTWRITEBYTECODE=1`, and `__pycache__` is cleared after each
  mutant. A killed runner left mutants in the copies twice; the copies
  were restored from `git show` both times.
- **Kill check.** A copy of the worktree's `src/` and `tests/` gets the
  exact mutant. The new test must pass there without it and fail with it.
  Every test below passed this check.
- **Limits.** Regex text is not mutated: patterns in `_boundary.py` and
  `_tokens.py` were reviewed in #526 and #544. An `error4` (`_tokens.py`,
  8 mutants) is a mutant that breaks the module's import, so every test
  sees it.

## Recorded survivors

| Id | Recorded in | Module | Verdict | Test |
| - | - | - | - | - |
| S1 | allow-build-followups.md | `core/build_signals.py` cleanup order | Gap, killed | `test_build_signals_arming.py::test_cleanups_run_newest_first_when_the_block_ends_by_an_exception` |
| S2 | same | nested `hold` | Gap, killed | `test_a_signal_in_a_nested_hold_waits_for_the_outer_hold`, `test_a_signal_in_a_hold_ends_the_process_at_the_hold_exit` |
| S3 | same | `_wait_until` deadline slack | Gap, killed | `test_models_wheel_build_subprocess_wait.py` |
| S4 | same | `parse_build_timeout` empty match | Gap, killed | `test_parse_build_timeout_error_shows_the_value_cut_at_40[empty]` |
| S5 | known-bugs/messages-and-provenance.md | `export/spdx3_json.py` `repr(min(changed))` | Gap; the "equivalent for ASCII" note was wrong (equivalent only for a name that holds the surrogate and is otherwise ASCII) | `test_spdx3_json_graph.py::test_the_lone_surrogate_warning_names_the_element_as_a_file_field` |
| S6 | license-pr276-followups.md | licence gap terms | Not measured (licence modules fenced) | Backlog |
| S7 | roadmap.md | hook `scan-model-usage` tri-state | Already killed on `main` at all five call sites | None needed |
| S8 | sweep plans | `_loom_dataset_meta` merge helpers | 4 gaps killed, 2 equivalent | see below |
| S9 | same | `_sbom_io` stdout/replace | 2 gaps killed, 3 equivalent | see below |
| S10 | log-masking-before-collapse.md | `_boundary.py` cost-gate lookbehind | Speed-only, left on purpose (regex text, not mutated here) | None |
| S11 | model-usage-ast-scan-lessons.md | `_usage_ast._propagate_reach` worklist | Gap, killed. The two mutants still survived; a bounded test (`run_bounded`, 5 s) fails instead of hanging | `test_usage_ast_cost.py::test_constants_built_from_each_other_end` |
| S12 | message-catalogue-review-rounds.md | `config_cascade` `id-registry = ""` | Design call, not a test gap | None |
| S13 | same | `requirements.py` `except InvalidRequirement` | Reachable, not dead: packaging 25.0-26.2 (a known bug now) | `test_requirements.py::test_an_extra_entry_that_does_not_parse_again_is_skipped` |
| S14 | recurring-bug-patterns-test-harness.md | `action.yml`, `scripts/action/` | Left on purpose (CI-only `if:`) | None |
| S15 | process-lessons.md | #276 licence typing | Fenced (licence) | Backlog |
| N1 | name-keyed-lookups-and-direct-references.md | `pep508.is_direct_reference` | Measured: all 5 killed | None needed |
| N2 | refactors-proved-by-output-equality.md | a Poetry test assertion | An observation about a test, not a module | None |
| N3 | process-lessons.md | the 0.21.1 diff | Superseded by later passes on the same code | None |

## Re-measured survivors (recorded-survivor modules, 393 mutants)

Of 393 mutants, 342 were killed by existing tests at first, and 3 more
(import-time defaults) once their function body's tests ran. The 48
survivors' verdicts, triaged by an Opus agent and checked:

| Module | Mutant | Verdict | Test |
| - | - | - | - |
| `_loom_dataset_meta` | `reraise_internal` dropped in the card read | Gap | `test_a_card_reader_bug_is_not_skipped_as_unreadable` |
| | `value != ""` dropped; `stated = True` | Gap | `test_merge_takes_what_a_source_states` |
| | `meta.creator or ""` to `meta.creator` (writes an Agent "None") | Gap | `test_write_metadata_strips_a_creator_and_skips_a_blank_one[absent]` |
| | `frozen=False` on `DatasetDoc`; `preprocessing_declared` default | Equivalent: never hashed or assigned; the sole caller passes the flag | None |
| `_sbom_io` | `sys.stdout.flush()` and `buffer.flush()` dropped | Gap | `test_stdout_bytes_follow_earlier_text_and_reach_the_stream` |
| | temp-name `token_hex(8)` to 9; `O_BINARY` default 0 to 1; `is not None` in `is_stdout` | Equivalent (length only matters at the name limit, a bug below; `O_WRONLY` is 1 on POSIX; `str(None)` is never `-`) | None |
| `build_signals` | `_arm` owner/armed guard (3); `continue` to `break`; `log.debug` dropped; `_terminated` reset | Gap | `test_build_signals_arming.py` (three existing tests moved there from `test_build_signals.py` and extended, so no near-duplicate) |
| | `_pending_in_hold` initial values (2); stale `_installed.pop()` | Equivalent (read only after `_handle` sets it; `_restore` checks the handler identity) | None |
| `_models_wheel_types` | the 40-character cut (3); six-digit component `>` to `>=` | Gap | `test_parse_build_timeout_error_shows_the_value_cut_at_40`, two `accepts` cases |
| | `zip(..., strict=True)` | Equivalent (always 3 items) | None |
| `requirements` | `continue` to `break` (2); the warning dropped | Gap | one `quiet` case extended; the new reparse test |
| `pep508` | `)` lowering depth by 2; `return False` to `None` (2); the `marker=`/`quiet=` defaults (5) | Gap | `sibling-then-deeper` case; `test_cap_checks_return_a_bool`; `test_a_cap_check_by_default_reads_a_requirement_and_warns` |
| | `_shown` `>` to `>=` | Equivalent (only reached for text over a cap, longer than 60) | None |
| `_hatch_document` | `_cleanup()` dropped | Equivalent (the hatchling route's cleanup is a no-op) | None |
| `_dep_groups` | `frozen=False` (2) | Equivalent (never hashed or assigned) | None |

## Credential masking (432 mutants)

`_hits.py`: 135 killed by existing tests. `_urls.py`: 66. `_detect.py`: 17.
`_tokens.py`: 16, including the 8 import breaks. Of the 39 `_hits`/`_urls`
survivors and timeouts, an Opus agent tested each one with a differential
probe (2,703 test literals, a crafted set and 46,711 grammar-fuzzed
strings):

- **23 gaps, killed** by cases folded into existing parametrizes in
  `tests/core/url_masking/`, plus three new tests:
  - quoted and enclosed values, start and end characters
    (`test_one_enclosing_pair_is_not_part_of_the_value`);
  - a nested secret after a non-secret parameter, inside a weak value, at
    a fragment's first character;
  - the 16-mark and 8-step bounds;
  - the PURL subpath scp and the weak qualifier;
  - `ssh://git@?token=T` with `account=True` (U30/U37, the riskiest: the
    mutant accepted the token);
  - an id's values not decoded twice
    (`test_an_id_is_read_at_each_depth_its_values_not_again`).
- **4** were killed by existing tests; their "timeout" was a slow run.
- **13 equivalent**, each with a reason in the triage note (for example
  `mark` is never 0, a `_Memo` lookup at `len - 1`, a default only `_detect`
  passes explicitly).
- **1 left**: U27, the `0x21` urllib-leading bound. It is a known bug
  (below), not pinned.

Of the 5 `_detect`/`_tokens` survivors, 3 are gaps, now killed: the
`find`/`holds` defaults (`test_the_defaults_read_an_account_name_and_no_id`)
and the token window `length - 1` (the `glpat-digit-past-20` case). 2 are
equivalent: the `Finding.weak` default, which its one constructor always
passes, and the character-class order of the `sorted` set.

Pinning rulings (Opus second opinion): U39 (a nested secret ends at `;`,
as the masker writes it) is pinned. So is U4 (a decoded URL's own values
are not decoded again), under the same documented "too-deep" ruling as
the existing `too-deep` case. U27 is not pinned: pinning "no finding"
would freeze a possible leak.

## Bugs found

| Bug | Where recorded |
| - | - |
| packaging 25.0-26.2 drops a valid extras entry whose marker value holds `"`, with a false "not a PEP 508" warning (reproduced with 26.0) | [extraction-and-fragments.md](../design/known-bugs/extraction-and-fragments.md) |
| A registry file name of 234-255 characters cannot be saved (`ENAMETOOLONG`, reproduced) | [id-registry-and-identity.md](../design/known-bugs/id-registry-and-identity.md) |
| `!https://u:S3CRET@h/x` in a URL field: no `credentials-unsafe` line, not refused, while the maskers mask it (reproduced end to end) | [messages-and-provenance.md](../design/known-bugs/messages-and-provenance.md) |
| `test_a_long_unread_value_is_cut_in_the_warning` fails with a long `TMPDIR` (523 characters) | [process-tooling-and-release-checks.md](../design/known-bugs/process-tooling-and-release-checks.md) |

## Lessons

- A recorded survivor goes stale. S7 and N1 were already killed on `main`,
  S5's "equivalent" claim was wrong, and S13's "dead code" was a
  version-dependent bug. Re-measure before writing a test.
- "A test that hangs CI is worse than the mutant" is a false choice when a
  bounded runner exists (S11).
- Coverage-context test selection made each mutant a seconds-long run.
  Lines every test runs (logging, masking) still need narrowing by topic.
- A default argument is invisible to line coverage: the `def` line runs at
  import. Select the tests that run the body.

## Backlog

**Second backfill PR (`export/_spdx3_credentials`).** Run 3 left 32
survivors and 14 timeouts there, not triaged: `_find.py` 27 survivors and
3 timeouts, `_check.py` 5 and 1, `_fields.py` 10 timeouts (import-time
table entries). The raw list was left in the side-session notes of
this work; re-measure first, `main` moves.

**Modules changed since `v0.24.0` with no recorded pass**, ranked by
changed lines, from the inventory of this session (excluding `messages/`,
licence modules and those passed here):

- No pass at all: `cli/_parser_credentials.py` (142), `_embed_generate.py`
  (115), `extract/remote/huggingface.py` (113), `extract/_usage_parse.py`
  (113), `core/given_path.py` (107), `core/given_file.py` (82),
  `cli/parser.py` (62), `cli/commands/merge.py` (52),
  `assemble/_generators_wheel.py` (51), `core/no_effect.py` (45),
  `cli/commands/generate.py` (44), `cli/commands/project.py` (43),
  `assemble/_generators_git.py` (42), `__main__.py` (41),
  `cli/options_resolve.py` (35), `cli/commands/model.py` (35),
  `core/_models_wheel_guard.py` (33), and a tail under 30 lines.
- Planned, never recorded (a natural PR of their own, identity and
  serialisation): `id_registry/_format.py` (235), `_types.py` (185),
  `import_keys.py` (143), `cli/_id_entity.py` (131), `id_registry/_session.py`
  (77), `_persist.py` (70), `_sbom_read.py` (62), `_generate.py` (62),
  `extract/remote/huggingface_fetch.py` (132), `_hub_api.py` (107),
  `_loom_model.py` (102), `extract/ai_model/pytorch.py` (92).
- `messages/` (31 modules, about 3,570 lines, mostly definitions): after the
  rescan. Small branching logic in `_authors_say`, `_fields_authors`,
  `_options_say`, `_summary`, `_registry_save_say`, `_environment_say`,
  `_text_malformed_warning`.

**Not mutation gaps:** S6/S15 (licence, after the licence change lands),
S10 (speed-only regex), S12 (design call), S14 (Action, CI only).

**Docs:** the `known-bugs.md` index counts were stale before this pass for
the AI-model, remote-sources and surfaces parts. Only the rows this pass
touched were recounted. Left for the docs sweep.
