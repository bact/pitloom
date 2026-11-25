---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-24
Last-Modified: 2026-11-25
---

# Message catalogue sweep: plan

See also: [message-catalogue-finish-plan.md](../design/message-catalogue-finish-plan.md),
[message-catalogue-pr17c-build.md](../design/message-catalogue-pr17c-build.md).

Status 2026-11-24: ruled by the maintainer: three PRs (sweep-a, sweep-b,
sweep-c), the LicenseID 0.9.2 pin first in sweep-a (one commit with the pin).
sweep-a MERGED 2026-11-25 as #536 (see "Build notes: sweep-a" at the end).
Planned by Opus against main after #534 (ratchet 0). Counts below were
measured then. Sweep B (D4-D6): see
[message-catalogue-sweep-b-plan.md](message-catalogue-sweep-b-plan.md), which
also routes the "Left for later" items below (fixed in #539, #540, #542, or
carried to sweep C). Sweep C (section 3, item 3) is not built yet.

## Sweep PR plan (read-only; reference tree = main after #534; LicenseID 0.9.2)

I checked the counts below by running the tools. `message_inventory --check` passes with 0 uncoded sites.

### 0. Current state
- **INTERNAL_PAT** hides 27 raise sites (the plan said 28). Two of its alternatives match nothing: `max_bytes must be a positive` and `GGUF array field without`.
- **LIBRARY_EXC** is just `{_no_active_run}`, with 7 sites in `loom.py`. LIBRARY_SITES has 1 site. No raise starts with `loom: `, so **D3 is already met**.
- **DETAIL_EXC** has 28 names covering 130 raise sites. Three names match no raise: `ArgumentError`, `ArgumentTypeError` (the bare names) and `_over_cap`. Separately, 121 raises are counted as detail because they are in the reader package, and 2 more under rule R-a.
- **PASSTHROUGH_PAT** covers 14 sites (`%s`, plus `%s%s` at `plugins/hatch.py:224`). The plan said 5.
- **Runtime probe.** I hooked `Logger.handle` across 16,800 in-process tests. Apart from summaries, `log_kv` and the two relays (`setuptools stderr: `, `licenseid: `), only two sites log an uncoded INFO-or-higher record:
  - `assemble/_model_generator.py:227` (31 hits)
  - `extract/scanner.py:265` (1 hit)
  - So making D5 strict by default is realistic.
- **D7 scan.** 338 backticked `LEVEL:` quotes across 139 doc and skill files. 84 of them hold no family marker, so nothing checks them.
- **Dead drift markers.** 10 markers in `tests/messages/test_drift_quotes.py` match none of their own family's templates: input-not-found x5 (`<input>/directory/archive/path/PATH not found: `), interrupted x2, `not valid JSON for `, `cannot be used when`, `must be a local file, not a URL`.

### 1. Sweep items

| Item | Sites (checked) | Change | Size / risk | User-visible? |
|---|---|---|---|---|
| **pypi-url-unusable duplicate** (minimum release) | `_model_generator.py:227`: `log.warning("%s", error)` then raise. Library only; the CLI refuses at `cli/commands/model.py:127`. Probe output: an uncoded `WARNING: URL=...: a PyPI page is not a model...` and then the raise. | Drop the log. This matches the Git route (`git.py:231`) and #503 ("no longer printed twice"). | S / low | Yes: the duplicate WARNING goes. Same text and code on the error; no catalogue change. |
| **scanner relay drops its code** | `scanner.py:265`: `relay_extra` returns `None` once the prefix or path replacement breaks the line. | Find the case with the D5 hook. Never relay a coded record uncoded: say it unframed with its code, else raise InternalError. Fold in 17c section 5's temp-copy name in `SOURCE=` (`SOURCE='1.gguf'`): same relay family, and the key freezes at 0.25.0. | M / medium | Yes (`SOURCE=` value). |
| **Hook catch-all** | `hatch.py:224` `log.error("%s%s", HOOK_FRAME, one_line(exc), extra=code_extra_of(exc))`, exempted only through PASSTHROUGH `%s%s`. | Make it a declared relay of the R-b shape, as `cli_error_handler` is, and remove `%s%s` from PASSTHROUGH_PAT. Hatchling's own `addr_spec` ValueError stays uncoded (third party, raised before Pitloom reads). | S / low | No. |
| **D2: INTERNAL_PAT emptied** | 27 sites. Not mechanical: see the four groups after this table. | Delete `INTERNAL_PAT` and add a test that it is gone. | M / medium | No, apart from exception classes. |
| **D3** | Already met. | Add a fixture test: a new `LIBRARY_EXC` name, or a `^loom: ` raise, fails the ratchet. | XS | No |
| **PASSTHROUGH audit** | 14 `%s` sites (`cli/id.py:232,386`, `_lock_io.py:127,141`, `_ambiguous.py:295`, `_harvest/__init__.py:294`, `_persist.py:208`, three `messages/*_say.py`, ...). | Each one must forward a code (`forwards_code`) or become a declared relay. Shrink the pattern. | S-M | No |
| **D4: detail classes proved** | 25 live classes. | Drop the 3 dead names. Add one parametrised case per class: trigger it through a surface and assert the wrapping line passes `trusted_message` with the class's text inside. Add a meta-test that `DETAIL_EXC` equals the set of proved classes. | L (tests) / low | No |
| **D5: strict records** | `tests/_message_drift.record_problem`, `conftest.py:200`. | Mark the four allowed uncoded kinds with a `pitloom_kind` record attribute (set in `say_summary`, `log_kv`, the relay helpers and the hook relay). Fail any other uncoded INFO+ `pitloom.*` record. Turn it on by default (the probe shows it is feasible). | M / medium (thread records, subprocess blind spot) | No |
| **D6: manual matrix** | `_harness.py:231 expect_tagged`, `_matrix_run.py:177 universal`. | Every tagged line must be trusted, a summary or a declared relay. Share one `line_kind()` classifier between the harness and D5. | S / medium (needs the full matrix run) | No |
| **D7 plus dead markers** | 84 unchecked quotes, 10 dead markers. | Triage the 84: licenseid relays, `Options:` `-v` lines, summaries, the generic `ERROR: loom <command>: ...`, external tools. Possibly stale: `WARNING: popularity.csv: missing`, `INFO: fragment list: ...`, `INFO: Merge: 'name' on ...`. Add a reverse-scan test with a shrink-only allowlist, and a test that every marker is a substring of one of its family's templates. | M / low | Docs and skills only |
| **Uncoded `-o` writes** (17a caveat) | `_sbom_io.write_sbom_output` (9 callers) raises a bare `OSError`. The embed path already codes it through `_coded_write`. | Move `_coded_write` into `write_sbom_output`; `write_sbom_copy` becomes redundant. | S / low | Yes: the ERROR gains the `file-unwritable` text and code (existing line). |
| **`cwd_relative_label`** | `_loom_caller.py:87`: `getcwd`/`abspath` raise when the current directory was removed. 5 callers. | Return the bare name on `OSError`. Remove the local `try` in `_loom_dataset_meta`. | XS | No |
| **Creator.type** | `creation_info.py:154`: `.strip()` on a non-string gives `AttributeError` (still there). | Add an `isinstance` guard, then use the existing `invalid_value` line. | XS | No |
| **`error_frame` docstring** | `logging_config.py:189-190` says the hook "runs where no frame is open", but `hatch.py:217` opens one. | Fix the docstring. | XS | No |
| **R1 forward-only** | The 6 outliers listed in `implementation/message-catalogue-review-rounds.md`. | Record the ruling in `message-catalogue-and-skills.md`. Add a level/actor/effect table test that names those 6. | S | No |
| **Per-line `since`** | `Line` has no `since` field. | Add `Line.since`, show it in the generator, and add a snapshot of the v0.24.0 catalogue. | M | Yes: reference pages regenerated |
| **text-malformed `ELEMENT=`** | `export/spdx3_json.py:143` passes an element id as `file=min(changed)`. | New line and field. Depends on per-line `since`. | S-M | Yes: catalogue, reference, `since` |
| **git-userinfo quoting** | `_git_credentials.py:144` uses `quote_source(sanitize_url(...))`; its siblings use `url_text`. | Make it match the siblings. Update the quotes in `docs/git-urls.md:329` and `skills/sbom-generate/references/git-url.md:55`. | S / medium (credential text) | Yes |
| **download-timeout singular** (17c section 5) | "1 seconds". | Singular form in the template. | XS | Yes: reference |

**D2 in detail (27 sites):**
- **Become `InternalError` (about 17):** `_embed_build_sbom.py:109,236,243,322`, `_models_wheel_lock.py:80`, `build_signals.py:242`, `creation_info.py:104`, `deps_license.py:79`, `core/models.py:114`, `export/spdx3_json.py:88,294`, `inert_options.py:430`, `_registry.py:434`, `_session.py:359`, `_types.py:110`, `plugins/_hatch_base.py:54`.
- **Actually user-reachable detail, not internal:** `_sbom_format.py:319` (NaN in an SBOM becomes the failure text of `json-malformed`) and `_fragments_equal.py:37,62`. Give each a named exception class and add it to DETAIL_EXC.
- **Wrong Python type from a library caller (go to LIBRARY_SITES):** `_models_wheel_types.py:312`, `build_options.py:118`, `scalar_text.py:140`, `_registry.py:96,216`, `id_registry/_types.py:176`.
- **Become `option-invalid`:** `_config_types.py:77` (`content_type_method`; check whether the config file validates it earlier). `_registry.py:619` ("No path given") needs a ruling.

Checked and dropped: the `report_wheel_failure` write misreport was fixed by 17a review rounds 1 and 2.

### 2. Follow-ups

**In the sweep:**
- uncoded `-o` writes
- the wheel-scan temp-copy name in `SOURCE=`
- `cwd_relative_label`
- `_publish_input_ids`: `_loom_active_run.py:411` returns early when there are no inputs, so an output naming an input is silently unlinked. Drop the `input_datasets` condition so the existing `reference-not-found` WARNING fires. XS.

**Separate PRs:**
- **The `TOKEN_RE` PR, already in the minimum release set:** the masking items. That is `Cookie:`/`X-Api-Key:` values, scp passwords with non-ASCII or a raw `@`, tokens glued to ANSI colour codes, and `loggable()` escaping before masking (about 40 call sites now, not 50; the leak class is the same). These are credential leaks, not catalogue items.
- **Path cutting:** the shared `path=`/`FILE=` writers do not cut a 1 MB value. Cutting is a policy decision (where to cut, how to keep the name findable) and touches every file line.
- **Docs split:** `AGENTS.md` is 33,893 B and `working-docs/design/roadmap.md` is 36,519 B, both over the 30 KB limit.
- **`stated_count` placeholders:** a behaviour change to dataset evidence; goes with the rescan.

**Stay deferred:** H3 (swallowed network failures; needs a noise design), the Action's shell annotations (21 `::error/::warning/::notice` lines now, not 15; on the roadmap), Hatchling's `addr_spec`, the bidi dataset name with no source, and the `fetch_json` redirect policy.

### 3. Split and size limit
Hard limit per sub-PR: 900 changed lines of src and tests (generated pages excluded), 30 files, one CHANGELOG block. Order:
1. **sweep-a "pin and gaps":** LicenseID pin (step 0), pypi duplicate, scanner relay plus `SOURCE=`, hook relay, `-o` writes, cwd label, Creator.type, `_publish_input_ids`, docstring, D2, D3 test, PASSTHROUGH audit. This covers every minimum-release item that belongs to the sweep.
2. **sweep-b "strict":** D4, D5 on by default, D6.
3. **sweep-c "quotes and wording"** (before the 0.25.0 cut, since renames after release are costly): D7, dead markers, git-userinfo, timeout singular, per-line `since`, `ELEMENT=`, R1.

### 4. Rulings to confirm (my recommendation first in each)
1. Split into sweep-a, sweep-b, sweep-c with the 900-line cap (alternative: one PR).
2. pypi duplicate: drop the log (alternative: log at ERROR with its code).
3. D2 RuntimeError sites become `InternalError`, which is a `ValueError`; update any `raises(RuntimeError)` in tests.
4. D5 marks records with a `pitloom_kind` attribute rather than test-side path matching, and is on by default in sweep-b.
5. The "with LicenseID 0.8.4" wording in the three `SKILL.md` requirement lines stays until the 0.25.0 cut: it describes the released pitloom 0.24.1 floor.
6. The `0.9.0` provenance examples (`licenseid==0.9.0`) and the outdated-database example (`build v3 ... current v4`) move to `0.9.2` and `build v4 ... current v5`.
7. Per-line `since` and `ELEMENT=` go in sweep-c (alternative: defer both to the rescan).

### 5. LicenseID 0.9.2 pin
**Move these (requirement or example):**
- `pyproject.toml:73`, plus a `# 0.9.2:` comment line in the block at lines 64-72
- `AGENTS.md:122`
- the Unreleased bullet at `CHANGELOG.md:102` (#502): change the floor, add the new link and the rebuild note
- `docs/github-action.md:36`
- `docs/metadata-provenance-licences.md:58,112`
- `docs/metadata-provenance.md:60`
- `skills/sbom-generate/SKILL.md:84`
- `skills/sbom-generate/references/examples.md:104`
- `skills/sbom-generate/references/known-limitations.md:354`
- `src/pitloom/extract/_license_resolve.py:99` (docstring)
- outdated-database example: `docs/messages.md:61-62`, `docs/metadata-provenance-licences.md:168-169`, `known-limitations.md:392-393`, `src/pitloom/extract/_licenseid_relay.py:11`

**Leave alone:**
- released CHANGELOG sections and `CHANGELOG-archive.md`
- the skills' 0.24.1 lines (ruling 5)
- synthetic versions in tests (0.3.0, 0.4, 9.9, v2/v3)
- the history comment at `action-selftest-install.yml:12-13`
- `README.md:50`, `CONTRIBUTING.md:103-109`, `test.yml:106` and `action-selftest.yml:64` run `licenseid update --source packaged` with no version, so they need no change. There is no `uv.lock`.

**What changes with 0.9.2** (from LicenseID's own CHANGELOG at tag v0.9.2, which includes 0.9.1):
- Database build 5. A database built by 0.9.0 or 0.9.1 warns as outdated through the relay, so users must rebuild with `licenseid update --source packaged`.
- `detect` fixes: MIT with a title and copyright line, Apache-2.0 without its appendix (it gave Pixar), LGPL-3.0.
- `resolve`: `MIT or later..` now gives no answer (it was `MIT+`, exact). From 0.9.1: `MIT or later.` is a separator and not exact.
- New `SAME_TEXT` and `REASON` fields, which Pitloom ignores.
- The provenance `Tool: licenseid==` value follows the installed version.

**The 4 skips:** No `skipif` on a LicenseID version exists anywhere in the tests. The only LicenseID skips are "database not built" (`tests/assemble/conftest.py:374`, `tests/extract/test_licenseid_relay.py:218,233`). I listed every skip reason on 0.9.2 (91 skips) and none mentions LicenseID or its database. So no skip is stale, and I cannot say which 4 tests started running without a 0.9.0 baseline. To find them: run `pytest -rs` in a 0.9.0 environment and diff the SKIPPED lines against 0.9.2.

### 6. Steps, agents and file fences
1. Haiku: the pin. Fence: the move list in section 5.
2. Opus A: D2, D3, PASSTHROUGH. Fence: `scripts/message_inventory/`, `tests/test_message_ratchet.py`, the 27 raise-site files.
3. Opus B: the pypi, scanner, hook and `-o` items. Fence: `_model_generator.py`, `scanner.py`, `hatch.py`, `_sbom_io.py`, `_embed_wheel.py`.
4. Sonnet: cwd label, Creator.type, `_publish_input_ids`, docstring. Fence: `_loom_caller.py`, `_loom_dataset_meta.py`, `creation_info.py`, `_loom_active_run.py`, `logging_config.py` (docstring only).
5. Gate A, then fresh Opus review, then commit sweep-a.
6. sweep-b: Opus designs the `line_kind` classifier and D5. Sonnet writes the D4 cases.
7. sweep-c: Sonnet triages D7. Opus does git-userinfo, `ELEMENT=` and `since`.

### 7. Tests (each must fail on the base tree with `-o pythonpath=`)
- **pypi:** `caplog` shows no record before the raise.
- **Scanner relay:** a relayed coded record keeps its code, and `SOURCE=` names `demo/m.gguf`.
- **Hook:** the inventory site is a relay, and `PASSTHROUGH_PAT` no longer matches `%s%s`.
- **`-o`:** a read-only directory gives `[file-unwritable]` on CLI, library and hook (mark `platform`).
- **cwd:** `rmdir` the current directory, then `cwd_relative_label` gives the bare name (POSIX only, `platform`).
- **Creator.type:** `c.type = 5` gives `option-invalid`.
- **`_publish_input_ids`:** no inputs plus a named input gives the WARNING.
- **D2-D7:** the meta-tests above.
- **Pin:** `test_licenseid_contract` already checks the version dynamically. Add a docs-floor test: every `licenseid>=` spelling equals the floor in `pyproject.toml`.

### 8. Gates
- **Gate A:** `ruff format`, `ruff check --fix`, `pylint examples/ src/ tests/ tests/*/`, `mypy`, `pyright`, `pyrefly check`, `bandit -r`, `flake8`.
- Also `python -m scripts.message_inventory --check` and `python scripts/generate_message_reference.py --check`.
- Full suite: `pytest -n 4 --cov=src/pitloom --cov-branch` on changed files.
- Manual checks: `scripts/manual_cli_checks --only 2,5,12,14,16,17,19,20,21,'M/generate/output/*'`.
- **Gate B for sweep-b:** the full manual matrix `-j 8` (D6) and the `test-all-os` label.

### 9. Risks, highest first
1. D5 strict mode fails on thread or worker records, or on CLI subprocess runs the in-process hook cannot see.
2. D2 misfiles a user-reachable raise as internal: the NaN and duplicate-key cases already show the list is not mechanical.
3. The `SOURCE=` and git-userinfo changes alter text a skill quotes.
4. Database build 5 makes CI or a user's machine warn about an outdated database until it is rebuilt.
5. CHANGELOG conflicts between the sub-PRs.
6. The `files` and `targets` reference pages are close to 30 KB.

### 10. Branch and CHANGELOG
Branch and worktree: `catalogue-sweep-a` (then `-b`, `-c`).

CHANGELOG bullets (Changed):
- `Requires licenseid>=0.9.2,<0.10`; rebuild the database (`licenseid update --source packaged`) after upgrading ([#502], [#NNN])
- `generate_model_sbom()` on a PyPI URL raises `pypi-url-unusable` without an uncoded WARNING first; an `-o` write the system refuses is `file-unwritable` ([#NNN])
- A model scanned from a wheel names its own path in `SOURCE=`, and a relayed reader line keeps its code; the hook's error line is a declared relay ([#NNN])

### Critical files for implementation
- /Users/arthit/projects/pitloom/.claude/worktrees/catalogue-datasets/scripts/message_inventory/_scope.py
- /Users/arthit/projects/pitloom/.claude/worktrees/catalogue-datasets/tests/_message_drift.py (with tests/conftest.py)
- /Users/arthit/projects/pitloom/.claude/worktrees/catalogue-datasets/src/pitloom/extract/scanner.py
- /Users/arthit/projects/pitloom/.claude/worktrees/catalogue-datasets/src/pitloom/_sbom_io.py
- /Users/arthit/projects/pitloom/.claude/worktrees/catalogue-datasets/tests/messages/test_drift_quotes.py

## Build notes: sweep-a

Built 2026-11-24, merged 2026-11-25 as #536. Opus A (D2, D3, passthrough,
`Creator.type`), Opus B (pypi, scanner, hook, `-o`), Sonnet (cwd label,
`_publish_input_ids`, floor test); two fresh Opus review rounds; two Opus fix
rounds; mutation of the inventory rules (12 mutants, all killed).

**Rulings.**

- `_registry.py:619` ("No path given", `IdRegistry.save`) and `_registry.py:434`
  (`_mint_id`, empty type name) go to `LIBRARY_SITES`: only a library call
  reaches them. `LIBRARY_SITES` entries are keyed on (file, function,
  exception class, template), so a new raise in a listed function stays
  counted.
- `plugins/_hatch_base.py` arity error stays `InternalError`: a Hatchling
  release this build hook has not been updated for is a compatibility bug fixed
  by a release, not a user's input.
- `_config_types.py:77` (`content_type_method`) is `option-invalid`
  (`one-of-method`): library parameters are not validated earlier.
- `_sbom_format._NonJsonConstant` and `_fragments_equal._NotComparableJson` are
  named detail classes (`DETAIL_EXC`); the first reaches `json-malformed`.
- `PASSTHROUGH_PAT` is `^%s$` and exempts a site only when it forwards a code;
  `extra=<name>` is followed through assignments of the same function.
  "Any assignment binds a code" was kept over "every assignment" (no site
  differs on the tree).
- A relayed coded record is said framed, else unframed with its code, else as
  read (escaped) with its code plus a `--debug` line; `InternalError` only when
  even that is not a catalogued line.
- The hook's failure line is printed by `print_error` with `HOOK_FRAME` (as the
  CLI handler does), not logged: a declared `exception-param` relay.

**Left for later.**

- A wheel-scanned GGUF dataset's provenance in the SBOM still names the
  temporary copy ([message-catalogue-pr17c-build.md](../design/message-catalogue-pr17c-build.md) section 5).
- `_generators_git.py` and `_generators_pypi.py` forward `output_path` to the
  generators; their Raises sections do not mention `CodedOSError` yet.
- `scripts/message_inventory/_relay.py:356` pylint R0911 (CI lints only
  `examples/ src/ tests/`).
- The inventory does not follow tuple unpacking or a returned value when it
  looks for a forwarded code.
- The docs-floor test reads the first `licenseid>=` match in `pyproject.toml`
  and does not scan `src/` docstrings.
- The loom SDK's fragment write (`_loom_active_run.py` `finalize()`) is not
  `file-unwritable`: a refused write raises a bare `PermissionError`. It needs
  its own wording (the text says "for the SBOM", a fragment is not one).
- Per-wheel `except (ValueError, OSError)` in `cli/commands/utils.py`
  (`_locate_embedded_sbom_or_report`) and `verify_wheel.py` still swallow an
  `InternalError` into an uncoded per-wheel `ERROR:`; not reachable today.
- `_loom_active_run.py:153` `os.path.abspath(script_path)` raises when the
  current directory is gone.
- `test_usage_parse.py::test_no_other_thread_runs_while_the_parse_stack_size_is_set`
  flakes under `--cov` with `-n 4` (a hang at 99%, or coverage's `RuntimeError:
  Cannot install a trace function while another trace function is being
  installed` from the 1 microsecond switch-interval watcher). Not in this PR's
  diff; passes alone and without coverage.
- Mutation pass on the PR (about 300 mutants): the survivors in code this PR
  changed have tests (new files under `tests/`); survivors in older code
  (`_loom_dataset_meta` merge helpers, `_sbom_io` stdout/replace helpers) were
  left. `test_reader_log_interrupt.py` now undoes every captured logger: it had
  left a dispatcher on the second one and leaked into later scanner tests.
