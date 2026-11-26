---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-25
Last-Modified: 2026-11-26
---

# Message catalogue sweep B: evidence, design and proof table

See also: [message-catalogue-sweep-b-plan.md](message-catalogue-sweep-b-plan.md)
(rulings, amendments, routing, fences). Where this page and the plan page
disagree, the plan page wins (Fable review, 2026-11-25). (V) = verified by
reading or running; (G) = guess. Status: built as B1 (#541, merged) and B2
(#542); line numbers below are those of the reference tree.

## Measured state Verified current state

### Runtime probes (V)
**Uncoded records and stderr lines across the pytest suite.**
- Setup: macOS, Python 3.10 venv, serial, sharded 9 ways, `-m "not network"`, about 25,000 tests.
- What I hooked: `Logger.handle` (INFO and above, `pitloom*` loggers, no `pitloom_code`), and `print` inside `pitloom.logging_config` (every `print_error` line).
- **Production code: no uncoded record outside four by-design kinds.**
  - Summaries: `messages/_summary.py:77`.
  - `log_kv`: `cli/kv_output.py:97`.
  - Three prefixed relays: `fickling: ` (`extract/ai_model/pytorch.py:216`), `setuptools stderr: ` (`core/_models_wheel_setuptools_relay.py:64`), `licenseid: ` (`logging_config.py:400` via `log_once`).
  - `extract/_reader_relay.py:93`, only when tests feed it uncoded reader records.
- **Uncoded `print_error` lines come from three sources only.**
  - The validator relay (`spdx3-validate: `, by design).
  - Tests that inject uncoded exceptions: `_Stop`, "stopped by the test", fake `RemoteSourceError`, "boom", "Simulated failure".
  - Unit tests of `print_error` itself.
- **Tests that would trip a strict check: 38 test functions in 26 files.**
  - Some use their own non-`pitloom.test_` loggers (the `test_reader_log*` files, `test_scanner_reader_logs.py`, `test_pypi_fetch.py:349`, `test_url_masking_checkout.py:207`, `test_cli_id_entity_key.py:146`, `test_credential_sinks_cut.py:80`, `test_hook_lines.py:344`).
  - The rest inject uncoded exceptions: `test_cli_error_lines.py`, `test_hatch_hook_*`, `test_fetch_policy_surfaces.py`, `test_frames.py`, `test_messages_emit.py`, `test_logging_config.py`, `test_cli_git_url_download_cap.py`, `test_cli_project_git_url.py`, `test_cli_model_git_url.py`, `test_cli_id.py`, `test_embed_wheel_batch_*.py`, `test_enrich_readme.py`, `test_config_hook.py`, `test_credential_deep_query_surfaces.py`.
  - The rest also includes `UNSHOWN_MESSAGE` (`log_masking.py:23`): when a line cannot be masked, `ERROR: ... (a log message that could not be shown)` is printed uncoded.
- **Two probe failures, neither related to messages.**
  - A SIGINT timing test in `tests/messages` (slow_backend) failed under 9-way load.
  - One `relpath("")` crash was my probe's own bug.

**Manual matrix with a prototype `line_kind` (`-j 8`, offline).**
- Result: 620 pass, 0 fail, 29 known, 30 skip; 1,350 `loom` runs.
- Tagged lines by kind: coded 658, summary 479, detail (`-v` `KEY=VALUE`) 42, relay 0, uncoded 0. There were 140 DEBUG lines.
- The 2,408 untagged lines come from runs not checked by `universal()`: argparse usage text, a child script's traceback, sdist build chatter.
- **So D6 strict passes on today's tree.**

### D4 (V)
- `DETAIL_EXC` is at `scripts/message_inventory/_scope.py:47-79`. It holds 30 names covering 133 raise sites.
- Dead names (no raise): `ArgumentError`, `ArgumentTypeError` (bare) and `_over_cap`.
- Six names are raised only inside `READER_PACKAGE`, which `_raise_reach` already treats as detail, so listing them changes no count:
  - `Malformed` (45 sites), `ConfigShapeError` (8), `LimitExceeded` (3), `UnsupportedVersion` (4), `ModelLimitExceeded` (11), `_UnsupportedAttribute` (1).
- 21 names need proof:
  - `_NonJsonConstant`, `_NotComparableJson`, `FragmentReadError`
  - `argparse.ArgumentTypeError` (11 sites), `argparse.ArgumentError` (2)
  - `on_duplicate`, `_Unlistable`, `MarkerShapeError` (9), `ReadBudgetExceeded`, `ParameterCountRejected`
  - `InvalidSpecifier`, `InvalidRequirement`, `InvalidMarker`, `_OverCap` (3)
  - `HeaderBlockOverCap` (3), `LockFileRefusedError` (3), `_MarkersTypeError`, `NotAModel`
  - `MemberReadError` (2), `ModelOverCap` (2 outside readers), `_DuplicateKeyError`
- Two hazards in how the list is keyed:
  - It is keyed on the bare name. `_OverCap` is defined twice: `core/requirements.py:298` and `extract/_usage_ast.py:84`. The second raises with no text, so it is not counted.
  - `on_duplicate` is not a class. It is a callable parameter (`core/archive_member_names.py:148`), and its only caller passes `refuse_duplicate_name` (`core/wheel_dist_info.py:204`).
- Five classes are never named in an `except`; they are caught through their base class: `MemberReadError` (OSError), `LockFileRefusedError`, `_MarkersTypeError`, `_NonJsonConstant`, `_NotComparableJson`.
- No test exists that proves a class reaches a coded line.
- **Where the sweep plan is stale:** it says "25 live classes, 3 dead". Today there are 27 live (sweep-a added `_NonJsonConstant` and `_NotComparableJson`) and still 3 dead. It also misses the six reader-only names and the two hazards above.

### D5 (V)
- `tests/conftest.py:200-221` (`_catalogued_records_are_valid`) checks only records that already carry a code, via `tests/_message_drift.py:191 record_problem`. An uncoded record returns `None` straight away.
- Nothing watches `print_error` lines (`logging_config.py:207`, a direct `print(..., file=sys.stderr)`).
- `pitloom_kind` does not exist anywhere.
- **Where the sweep plan is stale:**
  - "Two sites log uncoded" was fixed by sweep-a.
  - "The four allowed kinds include the hook relay" is no longer true: the hook line is now `print_error` with `code_of(exc)` (`plugins/hatch.py:113-122`), not a record.
  - What remains: three record kinds (summary, detail, relay) plus one stderr relay (the validator).
- Finish-plan D5 says INFO and above. The brief says WARNING and above. Ruling R2 below.

### D6 (V)
- `scripts/manual_cli_checks/_harness.py:231 expect_tagged` and `_matrix_run.py:177 universal` check only that each line has a tag.
- Call sites: `universal` is called at 8 sites; `expect_tagged` at 6 sites in 3 check modules.
- pytest runs a matrix slice in CI (`tests/scripts/test_manual_cli_checks.py:55`).
- **Stale references:** the finish plan's line numbers (`:233`, `:183`) are out of date; the sweep plan's (`:231`, `:177`) are right.
- `tests/_loom_child.py` (`run_loom` plus `coded_lines`) is a shared subprocess seam, used by 9 files.

## Design

### D4: proof table (recommended)
- Remove the 3 dead names and the 6 reader-only names from `DETAIL_EXC`, leaving 21. Check with `--check` that no count moves; the reader rule is already proven by `test_a_model_readers_raise_reaches_a_user_only_through_the_scan`.
- Rename `_usage_ast._OverCap` to `_UsageOverCap`.
- New table test: one case per name. Each case is (name, class object or factory, trigger through a real surface, expected code, kind).
  - The trigger spies the class's `__init__` (monkeypatched on the class) to prove the class was raised.
  - Then it asserts that the surface produced a coded result: a `trusted_message` line, a coded record, or a coded exception (`code_of`).
  - **kind `detail`:** the escaped first 40 characters of `str(instance)` appear inside that coded line.
  - **kind `signal`:** the class is control flow whose text never reaches the user. The test asserts it does not appear anywhere. (G) Likely `signal` cases: `_OverCap`, `_Unlistable`, `_DuplicateKeyError` and possibly `NotAModel`; Opus decides per class.
  - `on_duplicate` is a factory case: a duplicate-member wheel through `verify-wheel` gives an exception with `code_of(...) is not None`.
- Meta-tests:
  - The table's names equal `DETAIL_EXC`.
  - Every non-argparse, non-factory name has exactly one `ClassDef` in `src/` (AST scan), which catches a future name clash.
- Rejected:
  - Keying `DETAIL_EXC` on (file, class) in the inventory: `exc_origin` holds only the imported name, so this needs import resolution. Medium effort, and the one-definition meta-test gives the same protection.
  - Proving all 27 names: the 6 reader-only names add about 6 cases for no change in the ratchet.

### D5: kind attribute plus shared classifier, strict by default (recommended)
- **`KIND_ATTR = "pitloom_kind"`** in `logging_config.py`, next to `CODE_ATTR`. Values: `summary`, `detail`, `relay`.
- **Who sets the kind:**
  - `say_summary` passes `extra={KIND_ATTR: "summary"}`.
  - `log_kv` passes `"detail"`.
  - The three prefixed relays pass `extra=RELAY_EXTRA`, a read-only mapping exported from `pitloom.messages`.
- **Inventory change (required):** the `prefixed` rule (`_relay.py` `_is_prefixed`) refuses any keyword today. Allow exactly `extra=RELAY_EXTRA`, imported from `pitloom.messages` and bound once, mirroring the `_MASKERS` rule. Fix the R0911 in `relay_kind` in the same edit.
- **`line_kind(line) -> str`**, new in `src/pitloom/messages/_line_kind.py` and exported. Order:
  1. Strip a trailing `\r`.
  2. `debug` for `DEBUG: `.
  3. `untagged` for no tag.
  4. `coded` when `trusted_message` matches.
  5. `summary` for an INFO line matching a `SUMMARIES` template (compiled once, cached).
  6. `detail` for `INFO: KEY=VALUE`.
  7. `relay` for a declared prefix after at most one frame.
  8. Otherwise `uncoded`.
- **Relay prefixes:** add `RELAY_PREFIXES` in `messages/_relays.py`. `VALIDATOR_PREFIX` already lives in messages (`_sbom_input.py:93`). The three relay modules keep their own constant, because the inventory's shape rule needs a module-level string.
  - A drift test asserts each module constant is in `RELAY_PREFIXES`.
  - The strict check's cross-test (a record marked `relay` must classify as `relay`) catches a new relay at run time.
- **New `record_problem` rules:**
  - Problem when a record has both a code and a kind.
  - Problem when an uncoded record at INFO or above on logger `pitloom` or `pitloom.*` (exact: `name == "pitloom" or name.startswith("pitloom.")`, not `startswith("pitloom")`) has no kind.
  - Problem when a kind disagrees with `line_kind` of the rendered line.
  - DEBUG, `pitloom.test_*` and third-party loggers stay out of scope.
- **Stderr leg:** `print_error` writes through a module-level `_write_error_line(line)`. The autouse fixture wraps that function: it is looked up as a module global, so patching it reaches every caller. It fails a line whose `line_kind` is `uncoded`.
  - The validator relay classifies as `relay`.
  - `UNSHOWN_MESSAGE` lines are uncoded; Ruling R5.
- **Allowances:** a registered marker `@pytest.mark.uncoded_output(*regexes)`, per test and never module-wide. Only lines matching a regex are allowed. **An allowance that matches nothing fails the test (stale allowance).** It goes on the 38 tests found. Tests with their own `pitloom.x` logger names take the marker rather than a rename (the `reader_log` tests need real hierarchy names, G).
- **Subprocess seam:** `tests/_loom_child.run_loom` asserts there is no `uncoded` line unless the caller passes `allow=`.
- **Interaction with the ratchet:** the static ratchet stays as it is (baseline 0). D5 is the runtime complement, catching what static analysis cannot see: dropped codes, uncoded exceptions reaching `cli_error_handler`, or a relay to which `relay_extra` gives no code.
- **Rejected:**
  - Text-only classification of records: an uncoded `log.info` whose text happens to match a summary would pass.
  - Matching paths in the tests (the plan's alternative): misses intent and drifts.
  - A `say_relay()` catalogue helper: weakens the "text is a parameter through `one_line`" shape guarantee.
  - Capturing `sys.stderr` in the fixture: clashes with `capsys`, and the handler-outlives-capture bug class.

### D6 (recommended)
- `universal()` and `expect_tagged()` call `pitloom.messages.line_kind` on each line and fail on `uncoded`.
- `untagged` stays a failure where it is today, and stays out of scope in checks that do not call them: argparse usage text and third-party last-resort lines.
- `expect_tagged(..., allow=...)` takes regexes, as the marker does. No check needs one today.

### Left for later: where each item goes
| Item | Where | Why |
| --- | --- | --- |
| Per-wheel `except (ValueError, OSError)` swallowing `InternalError` (`cli/commands/utils.py:282`, `cli/commands/verify_wheel.py:119`) | **B (strict)** | Exactly the class of uncoded ERROR line D5 targets; XS. Re-raise `InternalError` first, as `tests/cli/test_embed_wheel_batch_internal_error.py` shows embed already does. |
| R0911 in `_relay.py` | **B (strict)** | Same function edited for `RELAY_EXTRA`. |
| loom SDK fragment write not `file-unwritable` (`_loom_active_run.py:460`) | **C** | New wording ("fragment"), a catalogue line, per-line `since`. |
| `os.path.abspath(script_path)` when the cwd is gone (`_loom_active_run.py:153`) | **C** | Same file and agent as the line above; not catalogue strictness. |
| Floor-docs test reads only the first `licenseid>=` | **C** | (V) `pyproject.toml` has one match and `src/` none, so it is a docs-coverage tweak. |
| GGUF dataset provenance naming the temp copy | **Own small PR before 0.25.0** (or C) | Changes SBOM output; B should stay SBOM-neutral so its "SBOM diff vs main is empty" check is strong. |
| Inventory not following tuple unpacking or returned values | **Rescan** | (V per sweep-a) no site differs today; D5 covers the paths tests exercise. |
| Mutation survivors (`_loom_dataset_meta` merge helpers, `_sbom_io` stdout/replace) | **Separate mutation-backfill PR** after the rescan (done: [mutation-backfill.md](mutation-backfill.md)) | Unrelated to B. |

### Rulings to confirm (my recommendation first in each)
1. **R1.** Prune `DETAIL_EXC` to the 21 proven names and rename `_usage_ast._OverCap`. Alternative: prove all 27.
2. **R2.** D5 is strict from INFO upward, with the three kinds. Alternative: WARNING upward, which needs no summary or detail kinds but leaves INFO lines unchecked.
3. **R3.** D5 is on by default in this sweep, with per-test `uncoded_output` markers whose stale allowance fails. Alternative: opt in first.
4. **R4.** `line_kind` and `RELAY_PREFIXES` live in `pitloom.messages`. Relay modules keep their constant; a drift test checks the two agree.
5. **R5.** An `UNSHOWN_MESSAGE` `ERROR:` line stays uncoded, allowed by its marker. Alternative: give it the caught exception's code when it has one.
6. **R6.** Update the hand-written prose in this sweep: `docs/messages.md:19` and `skills/{sbom-generate,sbom-enrich}/references/messages.md:20`, both above the generated block, currently "A line without a code is not catalogued yet". New text: a line without a code is a summary, a `-v` `KEY=VALUE` detail, or another tool's words after its name. Alternative: leave it for sweep C.
7. **R7.** Two PRs, sized as in section 3.

## Tests (each fails on the base tree)
**D4**
- Meta: table names equal `DETAIL_EXC`. Fails on base: base has 30 names.
- One-definition scan. Fails on base: `_OverCap` is defined twice.
- Per-class cases: each passes on base. The proof is the meta-test pair plus a mutation of each trigger.
- Mutants:
  - Drop a name from `DETAIL_EXC`: the ratchet rises.
  - Add a dead name: the meta-test fails.
  - Strip the code from one wrapper (e.g. the `FragmentReadError` wrapper's `code`): that case fails.

**D5**
- Each of these returns `None` on base, so the new test fails there:
  - `record_problem` on a synthetic uncoded WARNING record.
  - A record with both a code and a kind.
  - A summary-kind record whose text is no summary.
  - A relay-kind record without a prefix.
  - Logger `pitloomx` (out of scope), with a mutant for the prefix check.
  - INFO versus DEBUG boundary.
- The `_write_error_line` spy sees an uncoded `print_error`.
- Stale-allowance failure: tested with `pytester`, which is available (G). Otherwise a direct fixture call.
- Mutants:
  - Kind and text cross-check removed.
  - `>= INFO` changed to `> INFO`.
  - Each `line_kind` branch reordered (a forged-code summary must not classify as coded).
  - The frame-before-relay case.
  - Each relay call's `extra=` dropped (the runtime fixture flags it).
- Inventory rule: `extra=RELAY_EXTRA` is a relay; `extra=other`, a second keyword, or a locally rebound `RELAY_EXTRA` stays counted. That fixture fails on base, which refuses all keywords.

**D6**
- `universal(Result(stderr="WARNING: own words\n"))` must fail. It passes on base.
- An allowed regex passes.
- `INFO: KEY=VALUE` and a framed `ERROR: loom x: spdx3-validate: ...` pass.

**Per-wheel fix**
- Monkeypatch `find_embedded_sbom` and `read_wheel_name_version_from_path` to raise `InternalError` with two wheels.
- Base: a per-wheel uncoded `ERROR:` and the batch continues.
- Fixed: one handler line and the second wheel is not processed.

**Cross-surface coverage**
- D5 sees the in-process CLI (`main()`), the library, and in-process hook tests.
- Subprocess runs are covered only through `_loom_child` (9 files) and D6.
- 65 other subprocess test files remain blind.
- The Action shell annotations are out of scope (roadmap).

**Platform marking**
- `test_detail_classes_files.py` (archives, special files) is marked `platform`. `line_kind` must strip `\r` (Windows CRLF), with a parametrised CRLF case.
- Everything else is text-only and unmarked; confirm with `--collect-only -m platform`.
- B2 needs the `test-all-os` label: it changes stderr writing and the conftest.

## Gates, risks, unknowns
**Gate A**
- `ruff format`, `ruff check --fix`, `pylint examples/ src/ tests/ tests/*/` (plus `pylint scripts/message_inventory scripts/manual_cli_checks` by hand), `mypy`, `pyright`, `pyrefly check`, `bandit -r`, `flake8`.
- `python -m scripts.message_inventory --check` (baseline 0, unchanged).
- `python scripts/generate_message_reference.py --check` (no generated change expected).
- Full `pytest -n 4`, with branch coverage on changed files.
- An SBOM and `--json` diff against main: **must be empty**.
- Manual checks: `--only 'M/*'`.

**Gate B**
- Full manual matrix `-j 8` (measured: about 650 checks).
- Mutation run on `_line_kind.py`, `record_problem`, `_relay.py`, `_scope.py`.
- Windows dry-run.
- `test-all-os` label with the per-head-SHA check.
- Fresh Opus sweep; fresh read of both skills' `messages.md`.

**Risks, ranked**
1. Silent pass: 65 subprocess test files and the Action stay blind to D5.
2. Silent pass: an allowance regex that is too broad. Mitigated by per-test scope plus stale-allowance failure.
3. Silent pass: a `startswith("pitloom")` slip, or a relay prefix accepted without a frame check.
4. Flaky: a record from a thread leaked by one test is blamed on the next. The `reader_log` tests use threads. Mitigation: the hook keeps the current test's id; on a failure in another test, report the logger and thread.
5. Flaky: a SIGINT/slow_backend test failed under load in my probe, and the known `--cov -n 4` stack-size thread flake. Both predate B.
6. Slow: matching `line_kind` against summaries on every record. Compile once and cache; `trusted_message` already caps line length.

**Unknowns (G)**
- Network-marked and OS-specific tests were not probed (30 deselected); Linux and Windows legs may add markers.
- Whether `pytester` is enabled in this repository.
- Which D4 classes are `signal` rather than `detail`.
- Whether real Hatchling hook runs emit `pitloom.*` records I did not see.


## D4 proof table (Fable review; kind per name, proof site)

| Name | Kind | Proof |
| --- | --- | --- |
| `_NonJsonConstant` | detail | `_sbom_format.py:369`, `json-malformed` `failure=exc` (caught as `ValueError`) |
| `_NotComparableJson` | signal | `same_json` returns `False` (`_fragments_equal.py:95`) |
| `FragmentReadError` | detail | `warn_fragment_unread`: `fragment-unreadable` / `fragment-invalid` |
| `argparse.ArgumentTypeError`, `ArgumentError` | detail, weak | `_LoomParser.error` (`cli/parser.py:140`), `option-invalid` only if `usage_code` matches |
| `on_duplicate` | coded raise | `refuse_duplicate_name` returns `WheelRefused` (`wheel_dist_info.py:204`) |
| `_Unlistable` | carrier (built in B1; silent when errno missing) | `dataset_hash.py:351`, `warn_dir_unlistable` |
| `MarkerShapeError` | signal | `_dep_scope.py:83` coded line without the text; `extra_gate.py:178` silent |
| `ReadBudgetExceeded` | signal | `dataset_hash.py:250,377` over-ceiling warning, text dropped |
| `ParameterCountRejected` | detail | `warn_parameter_count(exc)` at three sites; `.reason` use is (G) |
| `InvalidSpecifier` | signal | `pipfile.py:194` coded `SPECIFIER_LINE` without the text |
| `InvalidRequirement` | mixed | detail only at `lock/requirements.py:192`; elsewhere `not-pep-508` without the text |
| `InvalidMarker` | mixed | detail via `failure=exc` (`requirements.py:212`, `pylock.py:368`, `_setuptools_options.py:158`); signal at `requirements.py:494` |
| `_OverCap` (requirements) | carrier | `requirements.py:200`, `warn_over_cap(over.cap)` |
| `HeaderBlockOverCap` | carrier | `wheel_dist_info.py:509`; `_sdist_scan.py:102` silent when `report` is false |
| `LockFileRefusedError` | mixed | detail for "not a regular file"; carrier with `cap` (`_lock_io.py:122`); never named in an `except` |
| `_MarkersTypeError` | detail, weak | `_poetry_requirements.py:130` catches `TypeError`; no line when `quiet` |
| `NotAModel` | carrier, some paths silent | `say_not_a_model` / `refuse_not_a_model`; silent when `reason is None` or non-strict (`_model_named.py:186`) |
| `MemberReadError` | detail | `scan_step` `except OSError` gives `file-unreadable`; copy-out gives `model-unreadable` |
| `ModelOverCap` | carrier | `scanner.py:331`, `warn_over_cap(model_cap(e.cap))` |
| `_DuplicateKeyError` | detail | `id_registry/_format.py:144`, `registry-malformed` "duplicate key" |
