---
Created: 2026-11-20
Last-Modified: 2026-11-20
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 14 (Hub and build): tests, steps, gates, risks

See also: [message-catalogue-pr14-plan.md](message-catalogue-pr14-plan.md)
(counts, sites, contradictions, design, rulings Q1 to Q19; sections 0 to 4
of the same plan), [message-catalogue-pr14-rulings.md](message-catalogue-pr14-rulings.md),
[message-catalogue-pr12-18-plan.md](message-catalogue-pr12-18-plan.md),
[message-frames-forward.md](message-frames-forward.md),
[message-catalogue-pr13-plan.md](message-catalogue-pr13-plan.md).
Sections 5 to 8 of the same plan. Reference tree: `main` at 4c4f55c7.

## 5. Tests (one per boundary)

New test files:
- `tests/messages/test_build.py` (entries, lines, fields)
- `tests/messages/test_frames_build.py` (new frames; `test_frames_codes.py` is at 419 lines)
- `tests/messages/test_build_surfaces.py` (CLI, library)
- `tests/core/test_temp_dirs_frames.py`
- `tests/messages/test_hub.py` (14b)
- `tests/messages/test_hook_lines.py` (14c)

Edits: `tests/_message_drift.py` (`SAMPLES`), `tests/messages/test_drift_quotes.py` (one marker per new family), `tests/messages/test_drift_sources.py` (`PENDING`), `tests/messages/test_frames.py` (the table test: 10 frames), and a fixture in `tests/scripts/message_inventory/` for the `raise build_error(...)` shape.

Frames:
- Per frame and per allowed code, a line is trusted after the frame. `over-cap` after `Build: ` is not.
- `emit(frame=BUILD_FRAME)` with `over-cap` raises `InternalError`.
- `temp_dir(frame=<frame without the code>)` raises **on entry**: the test fails if the check moves to cleanup.
- Same for `GuardedActivity(frame, "x")` and an unknown activity.
- The AST drift test is extended. Every call to `temp_dir`, `registered_temp_dir`, `remove_temp_dir`, `weakref.finalize(..., remove_temp_dir, ..., F)` and `GuardedActivity(F, ...)` names a module-level `Frame` that allows the code. `said == frame.codes` for each new frame. `_resolve` handles the pass-through `frame=frame` parameter.
- Q2 guard: `Build: Options: FINGERPRINT=...` is not trusted.

Build (`platform`; build fixtures from `tests/build_and_read_shared.py`):
- Each `build-failed` line: interpreter (patch the module's `sys` name); exit 1; exit -9 (POSIX); 0 wheels; 2 wheels; empty wheel; `BadZipFile`; `OSError` from mkdtemp (`strerror` only, no path).
- `library-missing`: patch `find_spec` in the subprocess module, not `importlib.util`. The WARNING line carries `[library-missing]` and the file-discovery line follows. **Fails on base**, which printed it uncoded.
- `InternalError` raised inside the build propagates. **Fails on base**, which swallowed it.
- Output tail: `\x1b[31m`, `\r\n`, `::error::`, `token=ghp_` + 36 characters, `https://u:s3cret@h/`, a token after a TAB, and a 300-character line whose token straddles the cut. Result: one line, no secret, cut at 200. Plus `trusted_message`.
- Timeout, both lines (`tree_terminated` true/false); B1's substring is kept.
- Leftover processes: INFO once, WARNING when `_wait_for_group_exit` is false, and the `killpg` `OSError` branch. POSIX only, through one module constant.

Signals:
- Each `(activity, in_hold)` pair emits through the real `_terminate` text builder (direct call, no signal) and gives a coded, trusted line.
- An unknown activity raises at construction.
- A cleanup whose emit would fail: the test proves that construction fails first.

Temp directories, per surface: Git, PyPI, Hub, scan, hook staging (`weakref.finalize` run in-process with `.finalize()`), build work and extraction. Each makes the removal fail by patching `pitloom.core.temp_dirs.rmtree`, the module name and never `shutil`. Each gives one coded line with the right frame and the name only, never the path.

`option-no-effect`: Build and Options lines unchanged (V against the HEAD text).

Hub (14b, local HTTP or fake `huggingface_hub`, `loopback`):
- `OfflineModeIsEnabled`, `RepositoryNotFoundError`, `GatedRepoError` (401), httpx `ConnectError`, httpx `ReadTimeout` (after Q11), `ValueError`, `InternalError` (propagates).
- Server text with `\n`, `\x1b`, a fake ` [over-cap]` and `Bearer hf_...` gives one masked line.
- Unpinned: said once for a model with 3 JSON files + licence + README; no line when the sha is given; no line when the Hub is refused (`asks_hub` false: the `A and B` rule, one test per side).
- URL rewrite: `hf.co`, `HTTP://`, `www.`, mixed case; the canonical URL prints no line; credentials and `?token=` masked.
- `read_card` probe (Q14).
- `parse_pypi_url` errors: CLI exactly one stderr line (fails on base: two); library `caplog` empty; each of the 7 refusals.

Surfaces:
- CLI `loom project|generate|embed-wheel --allow-build`: line, `[code]`, exit code.
- Library `generate_project_sbom(allow_build=...)` (`caplog` code).
- Hook staging leftover.
- `loom model hf.co/...` with Hub API and HTTP failures through a local server.

Determinism: SBOM bytes with `--creation-datetime 2026-01-01T00:00:00Z` are equal to `main` for a static build, a failed build and a Hub fixture.

Platform: classify each file (`pytest <f> -m platform --collect-only -q`); build, signal, temp and path tests are `pytestmark = pytest.mark.platform`. Label the PR `test-all-os`.

Windows dry-run notes (put in every brief):
- `kill_leftover_descendants` returns early, so there is no `build-processes-left`.
- `kill_process_tree` goes through `taskkill`; on failure `tree_terminated` is false, so the unconfirmed line.
- `SIGHUP` is absent and `SIGBREAK` present: the `signal` field is literal strings.
- Exit codes like 3221225786.
- `sys.executable` ends in `python.exe`.
- `mkdtemp` names are fine; never `repr(Path)`.
- `tempfile.gettempdir()`, never `/tmp`.
- A CRLF build log is handled by `splitlines`.
- A cp1252 console: `PYTHONIOENCODING` is set.
- `PureWindowsPath` for the `dir` of the project.

Mutation targets (Gate B):
- the entry check in `temp_dir`/`GuardedActivity`
- `allows` in each new frame
- `except InternalError: raise` (b&r, Hub loaders)
- the `library-missing` branch
- `tree_terminated` line choice
- `in_hold` during/after
- `_last_message_line` mask-before-cut order
- the classifier's branch order (`OfflineModeIsEnabled` is an `HfHubHTTPError`?, checked by the test)
- unpinned `asks_hub and revision is None`
- the `once` key
- B4's negative check (move it to the code)

## 6. Steps and agents (per sub-PR; branch from fresh `origin/main`, created by the user)

Before step 1: `git log --oneline -3`; `--check` passes at 132 (or the number the previous sub-PR left).

### 14a

**Step 1, Opus (core; anything touching frames, untrusted text, relay drops or signal and kill semantics).** One commit.

Fence:
- `src/pitloom/messages/**` (new `_build.py`, `build.py`, `_fields_build.py`; `_frames.py`, `_options.py`, `_topics.py`, `_catalogue.py`, `__init__.py`, `_model_stub.py` twin)
- `src/pitloom/core/temp_dirs.py`, `build_signals.py`, `_models_wheel_build_subprocess.py`, `_models_wheel_build_kill.py`, `_models_wheel_build_and_read.py`
- `scripts/generate_message_reference.py`, `scripts/_message_reference_frames.py`, `scripts/message_inventory/` (only if a shape needs it)
- `tests/messages/test_frames*.py`, `mkdocs.yml` (nav `build`)

Work:
1. Frames, `GuardedActivity`, temp API with entry checks.
2. Entries, fields, `SAMPLES` stubs.
3. `build_error`, `BuildFailedError.said`, the except chain (3.3), tail masking.
4. Kill and signal emits.
5. `--write` the reference.
6. Tier 1 (`pytest tests/messages tests/core/test_temp_dirs.py tests/core/test_build_signals.py tests/core/models_wheel -n 4`, mypy on touched files).
7. Import-order test both ways (`core/temp_dirs` now imports `pitloom.messages`).
8. Export the names to the Sonnets.

**Step 2, three Sonnets in parallel.**

Common brief:
- Read CLAUDE.md. British English. ASCII in comments.
- No `%r`, no raw `exc`. Messages only through `emit`/helpers.
- Never edit generated pages or the baseline. No git writes. No `sed -i`: use the Edit tool.
- Touched tests only, `ruff format`/`check`, mypy on touched files.
- The Windows notes above.
- Never put a frame on an exception's text.
- `except InternalError: raise` before any broad `except` around an emit.
- Report every changed stderr text.

| Agent | Fence | Brief |
| - | - | - |
| A (conversions) | `core/_models_wheel_dispatch.py`, `_models_wheel_types.py` (drop `BUILD_LOG_PREFIX`; importers use `BUILD_FRAME`), `core/no_effect.py`, `core/build_options.py`, `core/archive_member_names.py` (parameter type only), `extract/remote/{git.py,pypi.py,_hub_files.py}` (the `temp_dir` call only), `extract/scanner_wheel.py`, `plugins/hatch.py` (`_LOG_PREFIX` uses only, to `HOOK_STEP_FRAME`), `scripts/manual_cli_checks/_checks_build.py` (B1/B4/B5: B4 asserts no `[build-timeout]`), `scripts/compare_allow_build.py` if it pins text; tests under `tests/core/models_wheel/`, `tests/core/test_no_effect.py`, `test_build_options.py`, `tests/test_build_flag_warnings.py`, `tests/assemble/test_build_termination.py`, `test_embed_*` | Convert B1, and every `log_prefix` call site to `frame=`; update pinned tests in the fence |
| B (docs, skills) | `docs/allow-build.md` (123, 149, 159-160, 226), `docs/pypi-urls.md:324`, `docs/git-urls.md:463` (unchanged if Q2), `docs/messages.md` (frames list), `skills/sbom-generate/references/build-timeout.md` (131, 156, 165, 169), `references/git-url.md:35`, `SKILL.md:278`, `CHANGELOG.md` | Rewrite each quote to the regenerated `docs/message-codes-build.md` text with `[code]`; `pytest tests/messages/test_drift_quotes.py tests/test_docs*.py -n 4` |
| C (new tests) | the new test files of section 5, `tests/_message_drift.py`, `test_drift_quotes.py`, `tests/scripts/message_inventory/` | Section 5's 14a tests. Fail-on-base: `git archive main` into a scratch directory, `PYTHONPATH=<it>/src`, record each regression failing. Short `ids=`. Classify each file |

**Step 3, Haiku sweep** (after A; fence: tests outside A, B, C; no `src/`).
- Grep `tests/` for: `Build: `, `could not fully remove`, `received SIG`, `build-and-read for`, `build-and-read discovery failed`, `killed processes`, `could not confirm the processes`, `Pitloom: `, `BUILD_LOG_PREFIX`, `log_prefix=`, `INERT_LOG_PREFIX`.
- Known: 13 files hold `Build: ` (33 lines), 6 files hold `could not fully remove`, 4 hold `received SIG`, 27 hold `build-and-read` (V counts).
- Update each to the new text and run that file. Report any touched file over 450 lines.

**Step 4, Opus: integrate.**
- `--write`; `--write-baseline` (expect 121); page sizes under 30,000 B and 800 lines.
- Stderr sweep (6.1).
- Review round 1: a fresh-context Opus given the diff only, with the Windows notes. Batch fixes.
- Review round 2: a fresh Opus re-checks round 1's fixes and the diff since.
- Gates A and B.
- Working docs.

### 14b (after the Q11 fix PR)

**Opus, step 1.** Fence:
- `messages/` (new `_hub.py`, `target-ambiguous/hf-url` in `_sbom_target.py`, summaries in `_remote_fetch.py`)
- `extract/remote/_hub_files.py` (classifier), `huggingface_fetch.py`, `huggingface_dataset.py`
- `core/evidence.py`, `tests/messages/test_drift_sources.py`

These involve untrusted server text and the `InternalError` ordering.

Then:
- **Sonnet A**: `huggingface.py` H1, `pypi_url.py` P1, `tests/extract/remote/test_huggingface_*.py` (pins: `Hugging Face URL` in 7 files, `Failed to load` in 5, `pinned revision` in 1).
- **Sonnet B**: `docs/pypi-urls.md:296` row, `docs/metadata-provenance.md:154`, any Hub doc, `skills/sbom-generate/references/*hf*`/`model*` quotes, CHANGELOG.
- **Sonnet C**: section 5's Hub tests.
- **Haiku sweep**, then Opus with two review rounds. Expected ratchet 113.

### 14c

Split `plugins/hatch.py` first (538 lines, Sonnet with an Opus-checked plan). Then one Sonnet does K1 to K4 under `HOOK_STEP_FRAME` (fence: `plugins/`, `messages/_hook.py`, `tests/plugins/`, `docs/hatchling-build-hook.md`), one Opus review, ratchet 109.

### 6.1 Stderr sweep (HEAD versus the tree, offline)

Run each case on a `git archive` of `main` (`PYTHONPATH` pinned) and on the tree, then diff stderr, exit code and SBOM bytes.
- **14a**: uv_build project `--allow-build` (passes); a failing backend; a slow backend with `--build-timeout 5`; a backend leaving a `sleep` child; `build` uninstalled (patched venv); `--no-build-isolation`; SIGTERM and SIGINT mid-build; a read-only file in the work directory (leftover); `--build-timeout` without `--allow-build`; Git and PyPI offline cases with a forced leftover (in-process harness).
- **14b**: a local Hub with 404, 401, 500, malformed JSON, `HF_HUB_OFFLINE`, no sha; `hf.co` URL.
- Expect: same exit codes and SBOMs; every changed line gains `[code]`; the Q15 duplicate WARNING is gone.

## 7. Gates

Tier 1 between rounds: `.venv/bin/pytest <touched> -n 4 --lf`; linters on touched files; `--check`.

Gate A, from the worktree root (read every exit code directly, never through `| tail`):

```shell
export PYTHONPATH=src
PY=/Users/arthit/projects/pitloom/.venv/bin/python
$PY -m ruff format examples/ src/ tests/
$PY -m ruff check --fix examples/ src/ tests/
$PY -m flake8 examples/ src/ tests/; echo "flake8=$?"
$PY -m pylint examples/ src/ tests/ tests/*/; echo "pylint=$?"
$PY -m mypy examples/ src/ tests/; echo "mypy=$?"
.venv/bin/pyright --pythonpath "$PY" examples/ src/ tests/; echo "pyright=$?"
.venv/bin/pyrefly check --python-interpreter-path "$PY" examples/ src/ tests/; echo "pyrefly=$?"
$PY -m bandit -r src/pitloom; echo "bandit=$?"
$PY -m scripts.message_inventory --check; echo "ratchet=$?"
$PY scripts/generate_message_reference.py --check; echo "reference=$?"
$PY -m pytest tests/ -n 4; echo "pytest=$?"
$PY -m pytest tests/messages tests/core tests/assemble tests/extract/remote -n 4 \
  --cov=pitloom --cov-branch --cov-report=term-missing \
  | grep -E "messages/(_frames|_emit|_build|build|_fields_build|_hub|_options)|core/(temp_dirs|build_signals|_models_wheel_build)|_hub_files|huggingface_(fetch|dataset)|pypi_url"
# 14a:
$PY scripts/manual_cli_checks --only 'B*,2,8,S8,M/completeness'; echo "manual=$?"
# 14b:
$PY scripts/manual_cli_checks --only 'M/model/target/hf-offline,M/*/target/pypi-url-offline,8,M/completeness'; echo "manual=$?"
```

- If tests fail on `main` too, build the licence database first (`licenseid update --source packaged`).
- Never use `sed -i` on macOS.
- Delete the `pytest-of-*` scratch after runs.

Gate B:
- Mutation testing (section 5 targets; each mutant runs only its module's tests).
- `scripts/manual_cli_checks -j 8` in full.
- `--network --only '10,M/model/target/hf,M/model/target/hf-over-cap'`.
- `pytest -m network tests/core/models_wheel/test_models_wheel_uv_build_real_world.py` (not `--network`).
- Determinism; the Windows dry-run; a fresh-context sweep agent.
- A fresh read of `build-timeout.md` and `SKILL.md`.
- `gh pr view <n> --json labels` shows `test-all-os`, and `Unit tests` and `Build wheels` ran on the head commit after the label was added.

Docs, skills, CHANGELOG, working docs:
- Regenerate: the new `message-codes-build.md` and the skills' twins; `network`, `targets` and `models` pages; `mkdocs.yml` nav by hand.
- `_MARKERS` gets one marker per new family (6 in 14a, 2 + 1 variant in 14b).
- No CLI flag changes, so no `_matrix_plan.py` entry and no `SKILL.md` description change.
- CHANGELOG: fold into the existing catalogue bullet, with the PR link.
- Working docs:
  - migration row 14 (C1, actual counts);
  - frames-forward: PR 14 section marked built, rule 3 updated for exact codes (C2), "Not decided" item closed (C10);
  - review-rounds Round 5;
  - roadmap/known-bugs: C12, the Hub API via `fetch_json`, dataset revision parity, the TOKEN_RE root cause (still open from Round 4).
- Format-gap ledger: none.

## 8. Risks and unknowns (ranked)

1. **A silent `InternalError` in a cleanup or signal path.** It is swallowed by `suppress(Exception)` (`build_signals.py:268,320`), by `weakref.finalize` at exit, and by the broad `except` blocks in b&r and the Hub loaders. Mitigation: frames validated at entry and construction; `except InternalError: raise`; direct tests per activity and surface.
2. **Untrusted build and Hub text.** The build tail, the Hub exception text and the HF endpoint server's text. Mitigation: mask before the cut and before escaping; one credential test per field (`output`, `failure`, `url`); the Round 4 token-after-TAB case.
3. **Codes dropped by frames.** `relay_extra` returns `None` silently; a too-narrow `BUILD_FRAME` strips `library-missing`. Mitigation: the AST pass-through test, `said == codes` per frame, and the `library-missing` fail-on-base test.
4. **Exact-code over-trust** (Q2, Q4). Mitigation: keep `option-no-effect`'s literals; pin the accepted case in a test.
5. **Pins outside the fences and vacuous negatives.** B4's `"timed out" not in` check; network-marked uv_build tests; `scripts/compare_allow_build.py`. Mitigation: the Haiku sweep, the full suite, B4 rewritten to the code, the network run at Gate B.
6. **The Hub API hang (C12)** stays until the Q11 PR lands. The timeout line is untestable before it.
7. **File sizes.** `hatch.py` 538, `huggingface_field.py` 513 (not touched), `_fields.py` 461, `generate_message_reference.py` 593 (the frames helper takes the new note), `test_frames_codes.py` 419, `test_build_signals.py` 494: new code goes in new files.

Unknown:
- Whether the inventory counts `raise build_error(...)` and a text-less `BuildTimeoutError` as coded (I; check with a fixture at step 1).
- The `huggingface_hub` exception classes at the 1.29 floor (C13).
- The `targets` and `network` page sizes after regeneration (about 26.6 KB and 16 KB, I).
- Whether any route catches a `parse_pypi_url` error and goes on (I: none seen; the Q15 tests settle it).
- Whether the hook can reach the Hub or Git, through the registry or the model scan (I: no).

Later PRs or the roadmap, not PR 14:
- PR 16: `build_and_read.py:110`, `archive_member_names.py:162,195`, `_sdist_scan.py:184`, `wheel_dist_info.py` (4), `hatch.py:86,97,512`.
- Final sweep: `extract/scanner.py:467` INFO, `extract/env.py`.
- Roadmap: C12 (Hub API timeout and redirects; `fetch_json` instead of `huggingface_hub` API calls), the dataset route's silent unpinned revision, the PR-C1 evidence writer.
