---
Created: 2026-11-20
Last-Modified: 2026-11-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 14 (Hub and build): build plan

See also: [message-catalogue-pr14-build.md](message-catalogue-pr14-build.md)
(tests, steps and agents, gates, risks),
[message-catalogue-pr14-rulings.md](message-catalogue-pr14-rulings.md),
[message-catalogue-pr12-18-plan.md](message-catalogue-pr12-18-plan.md),
[message-frames-forward.md](message-frames-forward.md),
[message-catalogue-pr13-plan.md](message-catalogue-pr13-plan.md).

Status (2026-11-20): planned, not built. Read-only plan written by Opus
against `main` at 4c4f55c7 (the reference tree); every line number below is
that tree's. Branch for 14a is `catalogue-build` (worktree
`.claude/worktrees/catalogue-build`). The user decided the points under
"Decisions"; every other Qn is the planner's recommendation, not yet vetoed,
so treat it as accepted unless the user says otherwise at review.

## Decisions (user, 2026-11-20)

- **Q19 accepted: three PRs.** 14a: build, temporary directories, signals and
  frames (ratchet 132 to 121). 14b: Hugging Face Hub and PyPI relay (to 113).
  14c: hook status lines (to 109).
- **Q11 accepted:** a small fix PR comes first, before 14b. It passes a
  timeout to `model_info()`, `dataset_info()` and `list_repo_files()`.
  Redirect checking goes on the roadmap.
- **Q2 accepted:** keep both `option-no-effect` templates; `BUILD_FRAME` does
  not admit `option-no-effect`; no `OPTIONS_FRAME`.
- **Q15 accepted:** drop `pypi_url._refuse`'s WARNING in 14b.

Tags: (V) verified by reading or running on 4c4f55c7; (I) inferred.

## 0. Counts and ratchet

`--check` passes at **132** (V). The table comes from the `scratchpad/inv.jsonl` dump of the old tree (`catalogue-git`, same source as 4c4f55c7), filtered with `_scope.in_scope` and `not coded` (V).

| Sub-PR | Module | Sites (line) | Delta |
| - | - | - | - |
| 14a | `core/_models_wheel_dispatch.py` | 187 | -1 |
| 14a | `core/_models_wheel_build_and_read.py` | 178, 189, 200 | -3 |
| 14a | `core/_models_wheel_build_kill.py` | 125, 136 | -2 |
| 14a | `core/_models_wheel_build_subprocess.py` | 133, 158, 164, 237 | -4 |
| 14a | `core/temp_dirs.py` | 164 | -1 |
| 14b | `extract/remote/huggingface.py` | 149 | -1 |
| 14b | `extract/remote/huggingface_fetch.py` | 98, 143, 225, 247, 273 | -5 |
| 14b | `extract/remote/huggingface_dataset.py` | 104, 133 | -2 |
| 14c | `plugins/hatch.py` | 388, 394, 404, 465 | -4 |

Landing: 14a **121**, 14b **113**, 14c **109**. If Q17 puts hatch.py:86, 97 and 512 in 14c, the landing is 106. If Q8 folds in the Ctrl-C line `__main__.py:85`, subtract one more.

Out of the count, with their decisions:
- `_models_wheel_build_and_read.py:110` (`ARCHIVE= ENTRY=: resolves outside the extraction directory`) goes to **PR 16**. It belongs to the archive-member family, with `archive_member_names.py:162,195` (V). PR 14 changes only that module's parameter type, from `log_prefix: str` to `frame: Frame | None`, and the printed text stays the same.
- `_sdist_scan.py:184` goes to PR 16. So does `wheel_dist_info.py` (4 sites).
- The ratchet does not count two bare-`%s` relays (blind spots, V). PR 14 still converts both, which changes the count by 0:
  - `pypi_url.py:190` (`_refuse`, 7 raise sites at 224 to 249), in 14b.
  - `build_signals.py:269` (`_terminate`), in 14a.
- Not PR 14's: `extract/scanner.py:467` (an INFO "Found N AI model files", PR 4 summary leftover); `extract/env.py` (final sweep).

## 1. Sites

Surfaces (V):
- **Build** (`--allow-build`): the CLI subcommands `project`, `generate` and `embed-wheel` (`add_allow_build_argument` at `generate.py:163`, `embed_wheel.py:322`, `project.py:187`). `loom model` does not take the flag. Library: `generate_project_sbom`, `generate()`, the embed functions. The Action: `allow-build` input (`action.yml:152`).
- **Hook:** never builds. `get_wheel_files(assume_backend="hatchling")` skips dispatch (`_models_wheel_dispatch.py:371`). It never fetches from Git, PyPI or the Hub (I, to be tested). It does reach `temp-dir-left-behind` through its staging directory (`hatch.py:240,478,487`).
- **Hub:** `loom model|generate <hf url>`, `read_huggingface`, the Action.
- **Platform:** the leftover-process kill and its lines are POSIX only (`kill.py:113`, `if sys.platform == "win32": return`).

| # | file:line | Lvl | Text now (abridged) | Exception / caller | Untrusted text / credentials | Maps to |
| - | - | - | - | - | - | - |
| B1 | dispatch:187 | W | `Build: --allow-build is invoking a real PEP 517 build for '<d>' (backend=%r, <reason>) ... executes third-party build-time code<iso>, timeout Ns` | `_try_build_and_read` | `backend` from an untrusted pyproject, printed with `%r` | `build-code-unsafe` (4 lines) |
| B2 | b&r:178 | W | `Build: the real build of '<d>' produced a wheel with no non-.dist-info files -- treating as a discovery failure` | `_build_and_read_wheel` | none | `build-failed` (empty-wheel line) |
| B3 | b&r:189 | W | `Build: build-and-read for '<d>' timed out after Ns (--build-timeout) -- build process tree terminated` or `could not confirm ...` | catches `BuildTimeoutError` | none | `build-timeout` (2 lines) |
| B4 | b&r:200 | W | `Build: build-and-read discovery failed for '<d>': <one_line(exc)>` | `except Exception`: relays B7 to B9, `library-missing` with its code DROPPED, `OSError`, `BadZipFile`, and silently an `InternalError` | the build's last output line is attacker text | split by exception (3.3) |
| B5 | kill:125 | I | `Build: killed processes the build left running (process group N)` | `kill_leftover_descendants` | none | `build-processes-left` INFO |
| B6 | kill:136 | W | `Build: could not confirm the processes ... (process group N) terminated` | `_warn_group_survived` (2 callers) | none | `build-processes-left` WARNING |
| B7 | subprocess:133 | E | `raise RuntimeError("cannot locate the Python interpreter to run PyPA 'build'")` | caught at B4 | none | `build-failed` (interpreter line) |
| B8 | subprocess:158 | E | `BuildSubprocessError("build exited with code N: <last line>")` | caught at B4 | `_last_message_line` strips controls and caps at 200 chars; **no credential masking** (V, :326-334) | `build-failed` (exit line) |
| B9 | subprocess:164 | E | `build produced N wheels, expected exactly 1` | caught at B4 | none | `build-failed` (count line) |
| B10 | subprocess:237 | E | `BuildTimeoutError` text `build timed out after Ns`, never printed | caught at B3 | none | data only; the exception keeps no text of its own |
| T1 | temp_dirs:164 | W | `<prefix>could not fully remove temporary directory '<name>' (in the system temp directory)` | prefixes: `Build: ` (b&r:165, :247), `Git source: ` (git.py:227), `Hugging Face source: ` (`_hub_files.py:135,437`), `PyPI source: ` (pypi.py:129,463), `AI model scan: ` (scanner_wheel.py:172), `Pitloom: ` (hatch.py:60) | name only, not the full path | `temp-dir-left-behind` + frames |
| S1 | build_signals:269 | W | `log.warning("%s", "<pfx>received SIGTERM during\|after <activity> -- exiting after cleanup")` | signal handler, inside `suppress(Exception)` | none | `interrupted` (2 lines) |
| O1 | `_options.py:47-51` | W | `Build: <name>: <option> has no effect <when>` | `build_options.py:163,194` | name masked (`masked_given_path`) | Q2 |
| H1 | huggingface:149 | I | `Hugging Face URL <u> is read as https://huggingface.co/<id>` | `log_hf_url_rewrite` (callers :294 and the CLI) | `sanitize_url` + `loggable` | `target-ambiguous/hf-url` (Q12) |
| H2 | fetch:98 | W | `Downloading '<f>' for <id> without a pinned revision; supply hub_info['sha']...` (once per JSON file: up to 3 times a run) | `_safe_load_json` | none; the advice names a library-internal key | `hub-revision-unpinned`, once per model (Q10) |
| H3 | fetch (`_detect_license_from_hf_files`) | W | `Scanning license files for <id> without a pinned revision; ...` (only reached now when `model_info()` listed files but gave no `sha`) | `_detect_license_from_hf_files` | none | same, the same single site |
| H4 | fetch:143 | W | `Failed to load model card for <id>: <exc> \| Field(s) affected (skipped): ...` | broad `except` around `read_card` | `local_reason` | removed (Q14) |
| H5 | fetch:225 | W | `Failed to load model_info() for <id>: <exc> \| Field(s) affected (skipped): author, sha, ...` | `huggingface_hub.model_info` | `one_line(exc)` masks and escapes; text from the server's answer is untrusted | 3.4 classifier |
| H6 | fetch:247 | W | `Failed to list repo files for <id>: <exc> \| Field(s) affected (skipped): license (file-based detection)` | `list_repo_files` | removed 2026-11-21 (Hub-timeout PR: the names come from `model_info()` `siblings`; its failure line names the loss) | none |
| H7 | dataset:104 | W | `Failed to load dataset_info() for <id>: ... \| Field(s) affected ...` | `dataset_info` | same | 3.4 classifier |
| H8 | dataset:133 | W | `Failed to load dataset card for <id>: ...` | broad `except` around `read_card` | `local_reason` | removed (Q14) |
| P1 | pypi_url:190 | W | `log.warning("%s", error)`, then the CLI's `ERROR: ... [pypi-url-invalid]` | `_refuse`, 7 raises | `sanitize_url` | dropped (Q15) |
| K1 to K4 | hatch:388, 394, 404, 465 | I | `Pitloom build hook: disabled\|target %r is not 'wheel'\|build variant 'editable' skipped`; `Pitloom: staged SBOM '<f>' (N fragment(s)); ...` | `_generate` | the target name comes from the hook's own config | 14c (Q17) |

Also touched, already coded today:
- `option-no-effect`, Q2.
- `library-missing` gets a WARNING line identical to its ERROR line (its WARNING twin), said with the build frame.
- `download-network-failed`, `download-timeout`, `offline-unusable`: summaries widened to cover Hub API calls.
- `REASON_CODES` `timeout`/`network-failed` (`evidence.py:78-79`), PR-C1.

## 2. Contradictions (plans and design text versus the code)

- **C1. Row 14's breakdown is stale.**
  - `hf-input-invalid` no longer exists. `hf-url-invalid` is coded, on the `targets` page.
  - The Hugging Face licence-file reads are already coded (`read_license_file`; `HubFiles.read` calls `warn_instead`).
  - "hf-unpinned 1" is two sites. "build-subprocess 8" is 11 sites plus the temp directory.
  - The row's -20 holds only with its own exclusions. The real figure is -19 (14a+14b) and -23 with 14c.
- **C2. Frames match exact codes, not families.** frames-forward's "Frame interface" and the PR 14 note say `families`; PR 13 built `Frame.codes` and `allows(code, level)` (`_frames.py:55,85`, V). So "collapse `option-no-effect` to one template behind two frames" now over-trusts: a frame allows a code, not a line. For example, `Build: Options: FINGERPRINT=...` would be read as a genuine line (Q2).
- **C3. `temp-dir-unusable` is a different condition** (a download could not be saved, `_remote_fetch.py:227`, effect not-written). "Could not fully remove" is new, and the row's "`temp-dir-unusable`?" is no.
- **C4. `release-unpinned` is a PyPI release (`_pypi_info.py:95`)**, not a Hub revision. The row's "`unpinned`" is the condition word, not that code.
- **C5. The hook's lines are owned by nobody.** frames-forward ruling 1 gives the hook's WARNING/INFO prefix to PR 14 (`HOOK_STEP_FRAME`). No migration row counts hatch.py's 7 sites. Row 4 lists "hook-status 6" (built in #481, but these four are still uncoded), and the pr12-18 plan section 1.3 says "PR 14 or 16".
- **C6. frames-forward's `config_cascade.py:205` `Options:` literal is gone.** `INERT_LOG_PREFIX` is used only by `no_effect.py:35` and `scripts/manual_cli_checks/_matrix.py:57,59` (V). `OPTIONS_FRAME` is needed only if Q2 collapses the templates.
- **C7. frames-forward says the `Build: ` WARNING includes `build_signals.py:102`.** It is now `_termination_message` (:96-105), logged at :269 through a bare `%s`. That line is outside the ratchet (blind spot).
- **C8. frames-forward: "`build_and_read.py:200` ... the line's code is the build condition's, never the inner one".** That would erase `library-missing` (`CodedImportError` from `_require_build_package`, subprocess:170-181). Its `did` already promises "--allow-build found the files without a build, as its Build: lines say" (`_model_stub.py`, V). The inner code must survive (3.3).
- **C9. "PENDING still at `test_drift_sources.py:35`" holds (V).** No writer passes `timeout`/`network-failed` to `evidence_segment` (V, grep). `docs/metadata-provenance.md:154` lists the old names.
- **C10. Settled (the frames-forward "Not decided" item):** no model reader logs at ERROR (grep `extract/ai_model` for `log.error`/`logging.ERROR` is empty, V). `RELAY_FRAME`'s `ERROR` level is unused. Q18.
- **C11. The pr13-build plan's Gate A ran `--only 'M/*/*git*' '8' 'M/completeness'`.** `--only` is `action="append"` with comma splitting (`__main__.py:86-90`, V), so the bare extra arguments were stray positionals. The correct form is `--only 'B*,2,8,M/completeness'`.
- **C12. Found: `huggingface_hub` 2.2.0 has no timeout on its API calls.** `default_client_factory` sets `timeout=None` and `follow_redirects=True` (`huggingface_hub/utils/_http.py:341-348`, V). `model_info()`, `dataset_info()` and `list_repo_files()` pass none either (`hf_api.py:3188`), so a slow or hostile `HF_ENDPOINT` hangs the run. Their redirects bypass Pitloom's URL checks. The "download-timeout" pairing for Hub API calls is unreachable today (Q11).
- **C13. Found:** Pitloom requires `huggingface_hub>=1.29.0` (`pyproject.toml:107`, V), and the venv has 2.2.0. The exception classes must be checked at the floor too (httpx-based in 1.x as well, I).

## 3. Design

### 3.1 Frames (`messages/_frames.py`; `FRAMES` grows from 5 to 10)

| Frame | Template | Levels | Codes | Surface |
| - | - | - | - | - |
| `BUILD_FRAME` | `BUILD_PREFIX` = `Build: ` (moved from `_options.py:34`, the one constant) | W, I | `build-code-unsafe`, `build-failed`, `build-timeout`, `build-processes-left`, `temp-dir-left-behind`, `interrupted`, `library-missing` | `--allow-build` |
| `GIT_FRAME` | as built | W, I | + `temp-dir-left-behind` | as built |
| `HF_FRAME` | `Hugging Face source: ` | W | `temp-dir-left-behind` | Hub fetch directory |
| `PYPI_FRAME` | `PyPI source: ` | W | `temp-dir-left-behind` | PyPI download directory |
| `SCAN_FRAME` | `AI model scan: ` | W | `temp-dir-left-behind`, `interrupted` | wheel model copy |
| `HOOK_STEP_FRAME` | `Pitloom build hook: ` (same text as `HOOK_FRAME`; ruling 1 renames `Pitloom: `) | W, I | `temp-dir-left-behind` (+ the 14c codes) | the hook |

Rules:
- `library-missing` has two WARNING lines. With `BUILD_FRAME` it would also accept `Build: FORMAT=... FILE=...: required library not installed`. Accepted and documented; the alternative is a per-line restriction (Q4).
- **Pass-through API.** `temp_dir(prefix, *, frame)`, `registered_temp_dir(termination, prefix, *, frame)`, `remove_temp_dir(path, frame)`, `rmtree_quietly(path, frame)` and `warn_if_left_behind(path, frame)` take a `Frame`. Each one checks `frame.allows("temp-dir-left-behind", "WARNING")` **on entry** and raises `InternalError`. The check must not wait for the cleanup: a cleanup runs inside `suppress(Exception)` (`build_signals.py:268,320`) or inside `weakref.finalize`, where an `InternalError` vanishes.
- **`GuardedActivity`** becomes a frozen dataclass `(frame: Frame | None, name: str)`. Its `__post_init__` raises `InternalError` unless `frame` allows `interrupted` and `temp-dir-left-behind`, and `name` is in the closed `ACTIVITIES` set. `_NO_ACTIVITY = GuardedActivity(None, "a guarded activity")` is unreachable for the message (handlers install only inside a hold, :20-22); it is said unframed and its name is in the closed set.
- DEBUG lines (`rmtree_quietly`, `_arm`, `_restore`, kill.py) render `frame.render({})` as plain text.
- `archive_member_names.py` (107, 181, 215) takes `frame: Frame | None` and logs `frame.render({}) if frame else ""`. The text is unchanged; PR 16 codes it.

### 3.2 Codes (new, `since="0.25.0"`, actor and effect per R1)

New topic `build` ("Builds and temporary directories"): `build-code-unsafe`, `build-failed`, `build-timeout`, `build-processes-left`, `temp-dir-left-behind`, `interrupted`. New entries go in `messages/_build.py` (plus `_build_say.py` if it passes 300 lines), the public module is `messages/build.py`, and the fields go in `_fields_build.py`, because `_fields.py` is at 461 lines. The Hub codes go in `network` (14.1 KB) in a new `messages/_hub.py`, because `_remote_fetch.py` is at 325 lines.

Templates are proposals. At step 1, Opus fixes them against `template_problem` (a free field may not come first or touch another field, `_types.py:121-144`) and `test_no_two_entries_share_a_line`.

| Code | Lvl | Cond | Effect / actor | Fields | Template (after the frame) |
| - | - | - | - | - | - |
| `build-code-unsafe` | W x4 | unsafe | none / user | dir, backend, seconds | `DIR=%(dir)s: --allow-build runs a real PEP 517 build (build-backend %(backend)s, no discovery module for it), which runs the project's build code in an isolated build environment for up to %(seconds)s seconds`; the same with `its static discovery failed`; and both again with `without build isolation (--no-build-isolation)` |
| `build-failed` | W x5 | build-failed | weaker / user | dir, exit_code, output, number, failure | `DIR=%(dir)s: no Python interpreter to run PyPA build; not built`; `DIR=%(dir)s: the build exited with code %(exit_code)s; last output: %(output)s`; `DIR=%(dir)s: the build wrote %(number)s wheels, not one`; `DIR=%(dir)s: the built wheel holds no file outside .dist-info; read as a failed discovery`; `DIR=%(dir)s: the build could not run or its wheel not be read; %(failure)s` |
| `build-timeout` | W x2 | timeout | weaker / user | dir, seconds | `DIR=%(dir)s: the build timed out after %(seconds)s seconds (--build-timeout); its process tree was stopped`; `...; could not confirm its process tree stopped` (keeps the substring `timed out after` for B1) |
| `build-processes-left` | I, W | unsafe | none / none (I), none / user (W) | process_group | `the build left processes running (process group %(process_group)s); killed`; `the build left processes running (process group %(process_group)s); could not confirm they stopped` |
| `temp-dir-left-behind` | W | unwritable (Q6) | none / user | dir | `DIR=%(dir)s: could not be fully removed; left in the system temp directory` (`dir` is the directory's name, never its path) |
| `interrupted` | W x2 (+E, Q8) | interrupted | not-written / user | signal, activity | `received %(signal)s during %(activity)s; exiting after cleanup`; `received %(signal)s after %(activity)s; exiting after cleanup` |
| `hub-revision-unpinned` | W | unpinned | weaker / user | url | `URL=%(url)s: the Hub stated no revision; files read at the default branch as it is now` (once per model, `emit(once=)`) |
| `hub-response-invalid` | W | invalid | thinner / user | url, failure, outcome | `URL=%(url)s: the Hub's answer could not be read (%(failure)s); %(outcome)s` |
| `target-ambiguous/hf-url` | I | ambiguous | none / none | url, target | `URL=%(url)s: read as Hugging Face model %(target)s` (Q12) |

Changes to codes that already exist (lines or wording only):

| Code | Change |
| - | - |
| `library-missing` | WARNING twin of `LIBRARY_MISSING_ERROR_LINE`, the same template; said with `frame=BUILD_FRAME`; `did` names it |
| `download-network-failed`, `download-timeout`, `offline-unusable` | summary and did name the Hub API calls (`model_info()`, `dataset_info()`, the file list) |
| `option-no-effect` | Q2 (recommended: no line changes; `BUILD_PREFIX` from the frame's constant) |
| `file-discovery-needs-build/-unusable` | none; the line after a failed build still says the fallback (two lines on purpose: cause, then fallback) |

New fields (`_fields_build.py`):
- `exit_code`: `-?[0-9]+`. Negative is a POSIX signal; Windows gives large unsigned values such as 3221225786.
- `output`: free. The build's last non-empty output line, written as: controls stripped, then `masked_text`, then cut to 200 characters by `one_line(limit=)`, then escaped. This is third-party text.
- `process_group`: `[1-9][0-9]*`.
- `signal`: closed, `SIGTERM|SIGHUP|SIGBREAK` as literal strings, never `getattr`.
- `activity`: closed, `the build|the AI model file copy|a guarded activity`.

Widened meanings: `dir` (also a temporary directory's name), `backend` (as dispatch passes it: the lower-cased key, already a round-3 open item), `failure`, `url` (a Hub API request's model URL), `outcome`, `target` (the canonical Hub model URL). Each new field gets a value in `SAMPLES`.

### 3.3 Build failures: which exception says what

- `run_build_subprocess` raises `BuildFailedError(line, **values)`. Its text is the rendered line and it keeps `said = (BUILD_FAILED, values)`, mirroring `remote_error`. One builder, `build_error(line, **values)`. `RuntimeError` (B7) becomes the interpreter line.
- `BuildTimeoutError` keeps `timeout` and `tree_terminated` and no text of its own.
- `_build_and_read_wheel`:

```
except InternalError: raise
except BuildTimeoutError as exc: emit(BUILD_TIMEOUT, line by exc.tree_terminated, frame=BUILD_FRAME)
except BuildFailedError as exc: emit(*exc.said, frame=BUILD_FRAME)
except CodedImportError as exc if code_of(exc) == "library-missing": emit WARNING twin (module, requirement), frame=BUILD_FRAME
except Exception as exc: emit(BUILD_FAILED, residue line, failure=exc, frame=BUILD_FRAME)
```

  The `library-missing` code survives the relay (row 5). `TerminationSignal` and `KeyboardInterrupt` remain `BaseException` and stay uncaught.
- The empty-wheel case (B2) uses the same emit.
- `kill.py`: B5 and B6 call `emit(BUILD_PROCESSES_LEFT, ..., frame=BUILD_FRAME)`.
- The signal path: `_termination_message` returns `(Line, values)`. `_terminate` calls `emit(..., frame=activity.frame)` inside the existing suppress. Correctness is held by the 3.1 entry checks and by a direct test of every `(activity, in_hold)` pair, never only through a real signal.

### 3.4 Hub API failures (14b)

One classifier, `say_hub_failure(log, exc, url, outcome)` in `_hub_files.py`:

| Exception | Said as |
| - | - |
| `InternalError` | re-raised first |
| `OfflineModeIsEnabled` | `offline-unusable` WARNING |
| httpx timeout (only reachable after Q11) | `download-timeout` WARNING, `seconds` = the timeout passed |
| `HfHubHTTPError` and its subclasses, httpx `TransportError` | `download-network-failed` WARNING (`failure_text` masks; the server's text stays on one line) |
| anything else | `hub-response-invalid` |

- **`url`**: `shown_url(f"{hub.base}/{id}")`, or `.../datasets/{id}`. The model URL, not the API path.
- **`outcome`** names what is lost: `author, sha, created_at, last_modified, downloads, tags, safetensors.total and gguf.total not recorded`; `licence files not looked for`; `dataset licence, description, keywords, version and creator not recorded`. The `| Field(s) affected (skipped):` suffix goes (Q13).
- **Unpinned**: said once, in `fetch_hub_data` after `_load_model_info`, when `revision is None` and `hub.asks_hub`. It replaces H2 and H3. The README read at `revision=None` was silent before and is now covered.
- **H4, H8**: the broad `except` around `read_card` is removed. `read_card` says each failure it can meet itself (`readme.py:177-212`, V). What is left is in practice only `InternalError` or `MemoryError`. Its safety net is a probe test (Q14).
- **PR-C1**: `REASON_CODES` becomes `download-timeout` and `download-network-failed` (constants from `messages.network`), `PENDING = frozenset()`. No writer is added (Q9).

### 3.5 Example (stderr, `loom project --allow-build`)

```text
WARNING: Build: DIR=/p: --allow-build runs a real PEP 517 build (build-backend uv_build, no discovery module for it), which runs the project's build code in an isolated build environment for up to 1200 seconds [build-code-unsafe]
WARNING: Build: DIR=/p: the build exited with code 1; last output: ERROR Backend subprocess exited when trying to invoke build_wheel [build-failed]
WARNING: DIR=/p: build-and-read failed and file discovery not backend-aware for build-backend uv_build; Hatchling heuristic used, file list may be inaccurate [file-discovery-needs-build]
WARNING: Build: DIR=pitloom-build-and-read-x1y2z3: could not be fully removed; left in the system temp directory [temp-dir-left-behind]
```

### 3.6 Must not change

- `RemoteSourceError` codes (`huggingface.offline` and the rest), `hf-url-invalid`.
- The exit status of a terminated build: 143 or SIGTERM, 130 for Ctrl-C (B2, B3).
- The fallback path after any build failure (still `None`).
- SBOM bytes, except Q9 if a writer is chosen.

## 4. Rulings (Qn: recommendation, then the alternative)

Moved to [message-catalogue-pr14-rulings.md](message-catalogue-pr14-rulings.md)
(Q1 to Q19; the file-size limit split the plan). The decisions the user made
on 2026-11-20 are listed under "Decisions" above.
