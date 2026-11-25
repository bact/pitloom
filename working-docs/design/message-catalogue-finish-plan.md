---
Created: 2026-11-23
Last-Modified: 2026-11-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Finishing the message catalogue: definition of done, order of work, rescan

See also: [message-catalogue-pr17-plan.md](message-catalogue-pr17-plan.md)
(17a, 17b, 17c), [message-catalogue-migration-plan.md](message-catalogue-migration-plan.md),
[message-catalogue-and-skills.md](message-catalogue-and-skills.md).

Status (2026-11-23): plan by Opus (read-only) against the 17a tree and main
b0e43ccf. User instruction: finish the catalogue, then upgrade LicenseID to
0.9.1, then rescan every location for consistency and fix what is missing.
(V) verified by running or reading; (I) inferred.

Progress (2026-11-25): 17a-17c merged (ratchet 0); sweep A merged (#536,
D2, D3, LicenseID pinned at 0.9.2 instead of 0.9.1); sweep B: B1 merged (#541,
D4), B2 is #542 (D5 on by default, D6). Side PRs merged: #537 (Hub request id
dropped from `failure=`), #538 (link-loop guard), #539 (usage-scan parse
hang), #540 (GGUF dataset provenance names the wheel member). Next: sweep C
(D7 and the carried items), then the `TOKEN_RE` PR, the 0.25.0 cut, the
rescan. Plans:
[message-catalogue-sweep-plan.md](../implementation/message-catalogue-sweep-plan.md),
[message-catalogue-sweep-b-plan.md](../implementation/message-catalogue-sweep-b-plan.md)
(its "Carried to sweep C or the rescan" list).

## 1. Measured state (V)

- Inventory: in scope and uncoded 15 after 17b (17c's 15); 27 after 17a. The ratchet check passes.
- Sites the exemption lists keep out of the ratchet (`scripts/message_inventory/_scope.py`):
  `INTERNAL_PAT` hides 28 raises; `LIBRARY_EXC` (was `LIBRARY_PAT` 11;
  17b keeps only `_no_active_run`); `DETAIL_EXC` 28 classes
  (151 sites, 7 never named in an `except`); `PASSTHROUGH_PAT` 5 `%s` sites.
  The 17a review found two real uncoded lines hidden by these lists.
- Runtime probe: a root-logger plugin over 26,992 tests found 62 distinct
  sites logging INFO or higher with no code. 27 are the ratchet sites, about
  20 are `Summary` templates, 4 are by-design relays (`licenseid: `,
  `setuptools stderr: `, `fickling: `, `log_kv`). Real gaps: `_model_generator.py:228`
  (bare `pypi-url-unusable` before the raise), `scanner.py:265` (a relay that
  drops its code), `plugins/hatch.py:224` (an uncoded exception on the
  hook's ERROR line).
- Static: no `warnings.warn`, `sys.exit("...")` or click; stderr writes only in
  `logging_config.py`. The Action has 15 hand-written annotation lines, none
  coded (`action.yml`, `scripts/action/*.sh`).
- `docs/message-codes-files.md` is 29,649 B of 30,000: the `files` page
  needs a split before 17b/17c add to it.
- Released codes (v0.24.0): all 59 kept, none renamed; 14 gained lines.

## 2. Definition of done

| # | Criterion | Proof |
| - | - | - |
| D1 | Ratchet 0 | `tests/test_message_ratchet.py` |
| D2 | `INTERNAL_PAT` empty: each site `InternalError` or coded `option-invalid` | `_scope.py` plus a test |
| D3 | `LIBRARY_PAT` keeps only `_no_active_run`; `^loom: ` raises take `loom SDK: ` | ratchet fixtures |
| D4 | Every `DETAIL_EXC` class proved to surface inside a coded line | one parametrised test per class |
| D5 | An INFO+ `pitloom.*` record with no code fails a test unless marked `Summary`, declared relay or `log_kv` | `tests/_message_drift.record_problem`; opt-in first, default at the end |
| D6 | Every tagged line of the manual matrix is trusted, a marked summary or a marked relay | `_harness.py:233`, `_matrix_run.py:183` |
| D7 | Skills and docs quote only catalogued text (reverse scan of backticked `WARNING:`/`ERROR:` lines) | `test_drift_quotes.py` |
| D8 | Pages and skill copies in step, under 30,000 B and 800 lines | existing checks |

Out of scope, to record in `message-catalogue-and-skills.md`: the `--debug`
traceback and `Logging error` line; argparse usage text (coded via
`_LoomParser.error`); third-party last-resort lines (D6 reports them as
untagged); tool relays' own words; Summaries; library `TypeError`s for a wrong
Python type; the Action's 15 shell annotations (a roadmap item).

## 3. Order of work

1. **17a** (built, in review fixes): gates, merge main in (user), `test-all-os`.
2. **17b** (MERGED #527; authors, loom SDK, `sbom-basename`; 27 to
   15), from main after 17a merges. See
   [message-catalogue-pr17b-build.md](message-catalogue-pr17b-build.md). Step 0: split the `files` topic page. Also move the
   `_loom_dataset_meta.py:135,167` `loom: ` raises to `loom SDK: `.
3. **17c** (built, PR #534; datasets, display text, metadata budget; 15 to
   0; ratchet baseline empty). See
   [message-catalogue-pr17c-build.md](message-catalogue-pr17c-build.md).
4. **Sweep PRs** (D2-D7; split into sweeps A, B and C, see Progress above):
   exemption audit; bare `pypi-url-unusable`;
   `scanner.py:265`; `hatch.py:224`; `cwd_relative_label` traceback; the
   `report_wheel_failure` write misreport and `Creator.type`
   `AttributeError` if 17a left them; dead drift markers; `error_frame`
   docstring; R1 forward-only; per-line `since`; `text-malformed` `ELEMENT=`;
   `git-userinfo` quoting.
5. **`TOKEN_RE` PR** (separate, small, before 0.25.0): a token after an
   escaped control character, plus `Bearer` masking. A credential leak, not a
   catalogue item.
6. **LicenseID 0.9.1** (can be built in parallel; disjoint files; merge after
   the catalogue): `pyproject.toml:73` to `>=0.9.1,<0.10`; docs and skills
   lines naming the version (`docs/github-action.md:36`,
   `docs/metadata-provenance-licences.md:58,112`, `docs/metadata-provenance.md:60`,
   `skills/sbom-generate/SKILL.md:71,84`, `references/known-limitations.md:345`,
   `references/examples.md:104`; the stale "0.8.4" in the sbom-enrich and
   sbom-validate skills); a CHANGELOG line. 0.9.1 changes `resolve()` (`MIT or
   later.` moves from `stated_qualifier` to `separator`) and some `detect()`
   cases; no schema change. A 26,992-test run against 0.9.1 showed no
   behaviour regression. T14 (per-operand licence provenance) and option G's
   code stage stay deferred (they wait on the taxonomy and `--provenance`).
   Ruling (user, 2026-11-23): the upgrade is the pin only.
7. **0.25.0 cut** (user): raise the skills' floor, `plugin.json`,
   `__about__.py`; the paper re-run follows.
8. **Rescan** (section 4), fixes in follow-up PRs; wording renames before the
   cut or they become renames after release.

Deferred: H3 (swallowed network failures: adds new lines, needs a noise
design); the 14a follow-ups other than `Bearer`; code-shape and file-size
items; Hub behaviour items.

## 4. Consistency rescan

Permanent tests (new): D4 and D5; a closed subject-key vocabulary; level
against effect and actor (derive the table from today's entries, fail on new
outliers; R1 forward-only); British spelling and term lint over templates and
advice; a small glossary (file, path, directory, archive, member, wheel); `since`
against a checked-in snapshot of the last tag's catalogue.

One-off audits (results into a working doc): near-duplicate templates
across families (similarity 0.85 or more: merge candidates); the
cross-surface parity matrix (CLI, library, hook, Action, loom SDK per code);
prefix and frame spelling; stale working docs; the reverse quote scan (D7).

Expected backlog (I): 30 to 50 items, about two sweep PRs; wording or code
renames in their own PR, apart from the tooling.

## 5. Risks and cuts

Risks: the `files` page cap; `targets` at 27.5 KB; sources near 500 lines
(`provenance.py`, `_ai_package.py`, `_loom_active_run.py`); Windows and 3.10
legs for the errno and `os.access` paths; strict mode flaking on thread
records; a LicenseID 0.9.2 changing a `resolve()` category before the paper
re-run; CHANGELOG conflicts on every PR (keep each PR's bullets in one block).

To ship 0.25.0 sooner, cut in this order: D5 stays opt-in; defer the Action
coding and merge candidates (do or freeze renames of unreleased codes); defer
H3, 14a, code shape; do the D2-D4 audit for `INTERNAL_PAT` and `LIBRARY_PAT`
only. Minimum release: 17a, 17b, 17c (ratchet 0), the `pypi-url-unusable`
duplicate fix, the `TOKEN_RE` PR, the 0.9.1 bump and the floor sweep. Do not
ship at ratchet 15: 17c's dataset readers print attacker text uncoded.
