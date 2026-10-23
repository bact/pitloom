---
Created: 2026-10-23
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns: fuller wording of the AGENTS.md entries

See also: [recurring-bug-patterns.md](recurring-bug-patterns.md),
[recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md),
[recurring-bug-patterns-review-rounds.md](recurring-bug-patterns-review-rounds.md),
[agents-md-rationale.md](agents-md-rationale.md).

`AGENTS.md` keeps each rule to what an agent needs to apply it. Where an entry
lost an example, a PR number or an explanation when it was shortened, the
original line is kept here word for word, under the section it came from, so
the example can be found when the rule is extended or cited.

## Project context

- Implementation docs and progress reports: `` -- what WAS built: decisions, why, paths rejected in service of something built, revisions. Not a user manual.
- **`roadmap.md` stays a summary, not a duplicate**: when an item's detail outgrows a bullet, move it to its own file (`design/` while unbuilt, `implementation/` once built, `archive/` if abandoned but worth keeping) and trim the bullet to 1-2 lines plus a `See [doc.md](doc.md)` link. Small unbuilt items stay inline. Why: one copy drifts unnoticed.
- Paper notes (sourced raw material for an academic write-up): `sbom-generator-field-notes/` (start at its `README.md`) and `ai-model-scan-security-lessons.md` (an entry page; findings are in its `-*` parts). Add to them when a finding is worth publishing.
- `working-docs/` is internal notes only -- content can change without notice. The user-facing website (`docs/`) must never link into it. Reference a PR or issue number instead.
- **Global file size**: soft limit ~400-500 lines, hard limit ~800 lines (~30KB), for ALL files (source, tests, docs). Split before crossing it.
- **Naming and grouping**: kebab-case, topic-first filenames. If a topic outgrows 3+ closely related files, group them in a same-named subfolder.
- **CHANGELOG entries**: concise, no background/rationale (link the PR); ~160 chars per bullet (more only for a genuinely complex PR). Merge related PRs into one entry (`[#1], [#2]`); sort entries per section by lowest PR number; skip docs/version-bump/CI-only noise. New entries go in `CHANGELOG.md`; `CHANGELOG-archive.md` (pre-0.19.0) is frozen.

## SBOM output

- Deterministic: bit-for-bit identical across builds when input/environment unchanged. A timestamp is allowed (SPDX requires `created`) but must come from a pinned source: `--creation-datetime`, else `SOURCE_DATE_EPOCH`, else the clock. A reproducible build or a test pins one of the first two.

## Metadata sources

- **`physical_path` vs `distribution_path`**: on-disk project-relative path vs in-package/built path; they diverge for any `src/`-layout project. `software_File.name` always uses `distribution_path`. Registry keys come only from `pitloom.id_registry.keys.file_lookup_key`. For an `--allow-build` file, `physical_path` is an *absolute* temporary path: any consumer that joins it onto `project_dir` or bakes it into a determinism-sensitive string must call `pitloom.core.project.project_relative_or_fallback(physical_path, fallback)`, not an inline `is_absolute()` check. Why: [rationale](agents-md-rationale.md#metadata-sources).
- **Stage-scoped helpers take an explicit stage flag**: a helper shared by a source-stage caller (`read_pyproject()`) and a build-stage caller (the hook's gap-fill) needs a parameter (`include_locked_dependencies=False`-style), not call-site discipline; a source-only artefact (`poetry.lock`) must not leak into the build stage.

## Usage surfaces

Pitloom runs from several surfaces: CLI (10+ subcommands), the Hatchling hook, the library API, the GitHub Action, the AI skills (`skills/*/SKILL.md`) and the Claude Code plugin (`.claude-plugin/`). A change to one surface/subcommand ships easily without the others, since each surface's own tests keep passing (`--debug` reached the top-level parser, but 7 of 10 subcommand generators called `configure_logging()` again and reverted to `INFO`). Skills/plugin have no test suite: when editing anything a `SKILL.md` documents invoking, grep `skills/` for the changed command/flag/output shape and update it in the same change.
- **A skill is discovered through its frontmatter `description` only**, and a body section does not make a command triggerable. On a CLI command/flag add or rename, enumerate `add_parser(` subcommands against every `skills/*/SKILL.md` description; keep *verify* (structural) vs *validate* (schema/SHACL) explicit; give combined asks ("generate SBOM meeting CISA") a hand-off in both skills; give every "ask a follow-up" step a non-interactive fallback. A check or recipe a skill tells the agent to run must be tried on a legitimate input where it should do nothing. Audit: [skills-trigger-coverage.md](skills-trigger-coverage.md).

## Design principles

- **Resource efficiency**: cache and route to limit network access; stream large structures; never load whole files (ML models, archives) into memory: chunked reads (`read(8192)`), memory mapping or native lazy header extraction (`np.lib.format`, stream loading for fickling/pickle).
- **Explicit pin beats local environment**: a version pinned by its own data source (lock file, exact `==`/`===`) is authoritative and never overridden by introspecting Pitloom's own environment; introspection is a fallback for the unpinned case only.
- **Absent source data is not an error; a genuine read/access failure is.** Every extractor/metadata source (model readers, project parsers, lock readers, Hub/network fetches) degrades gracefully: a field the source does not carry stays `None`/empty/absent, silently, no `WARNING:`/`ERROR:`, no exception (nothing was deviated from). Reserve `WARNING:`/`ERROR:`/raising for real disruption: corruption, an unreadable/truncated archive, a network error or timeout, a parse failure on data the format's own marker says is well-formed. Line: "had an opinion and failed to deliver it" (log/raise) vs "never had this data" (quiet). Why: [rationale](agents-md-rationale.md#design-principles).

## Code health and continuous refactoring

- **Boy Scout Rule**: leave the codebase cleaner than you found it; refactor proactively during small changes.
- **Prevent monoliths**: extract cohesive pieces into modules/subpackages early (`parser.py`, `__main__.py`); obey the ~400-500 line soft limit, split *before* it is a problem.
- **Consolidate patterns**: extract duplicated logic into shared utilities, constants or decorators immediately.
- **Reuse/dedup is a defensiveness strategy**: two independent implementations of one operation (a hash, a type check, a message string, a cascade rule) can silently disagree later; reuse the shared helper even when the duplicate is small, to make drift structurally impossible.

## Recurring bug patterns

Failure modes that recurred across subsystems; check for them by name.
Detail (war stories, PRs, code shapes) is in
[recurring-bug-patterns.md](recurring-bug-patterns.md) (data and semantics),
[recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md) (platform, concurrency, test harness, CI) and
[recurring-bug-patterns-review-rounds.md](recurring-bug-patterns-review-rounds.md) (PR #300, #305, #306, #311 to #315 and path-key rounds): read them before extending or citing a one-liner.
- **A presence-only check misfires when a key is genuinely boolean** (`Pipfile.lock` `"editable": false`).
- **`dict.get(key, default)` guards absence, not a wrong type**: `isinstance`-check values from external files (`@graph` present but not a list).
- **A parse helper catching only the format's exception (`TOMLDecodeError`, `JSONDecodeError`) can still crash on a bare `UnicodeDecodeError`.**
- **Picking one candidate from an unordered collection needs an explicit stable tie-break**; choose a merge survivor from counts over all inputs (load all, rank, prove reversed input order gives the same ids).
- **A guard before a side-effecting step drops that effect** (a skip `return` before `reserve_id()` re-minted the id): do the effect first.
- **"No digest" is not "not a file"**: an empty directory, an over-ceiling or unreadable file also hash to `None`, and a dangling link is a path; ask existence with `kind`/`lexists`. Two helpers answering "is it a path" get a test on the cases they can disagree on.
- **Every route that builds one entity shares its identity rule** (the SDK keyed datasets by raw string while the card routes folded by `dataset_key`): one function, plus a test comparing the routes' counts. A fold that keeps the first says so (`INFO:`) and warns on a dropped keyed fact (a registry pin under the later spelling).
- **A fix scoped to "explicit input" needs an explicit flag** (an unreadable-root `ERROR` also hit the implicit default roots).
- **Removing a read to save cost can remove an error-surfacing side effect** (the `PermissionError` a full read raised): use a cheap probe.
- **Narrowing a derived field's rule needs an inventory of its writers** (builder, SDK, fragment, hand-built model): run each through the new rule; derive from the value's shape as well as its key (`7B` is no count). A reversed rule is recorded as "tried, reverted".
- **Measure the real tools before designing a reader** (`uv export`, `pip lock` write no PEP 751 extras keys): probe each backend, put the matrix in the working doc.
- **A failing manual repro is first suspect for a wrong replication**: use the real call shape (a parsed object, not a raw `str`).
- **An alias rule must test that the shorter key names no real file**: else two real files with equal bytes (empty `__init__.py`) alias; look up a few built candidate keys, never scan the table.
- **A path in a message goes through one helper** (`quote_source`: `str()`, quoted, control characters escaped): `repr(Path)` writes `/` on Windows and `repr(str)` doubles backslashes. `loggable()` every interpolated value (the kept name, a registry id), test with a newline, and test each emitter with a repeated input (said once).
- **A private third-party API (`obj._attr`) has no structural guarantee**: verify its shape interactively, prefer the public algorithm. Do not reach into another module's `_name`: promote a public accessor.
- **A check on the URL does not cover every client a fetch starts** (git-lfs reads the repository's `.lfsconfig`): list each program run, switch off what is not needed. Server and subprocess text is attacker text: `loggable()`, one line, credentials masked where the message is built (test with `user:SECRET@`). A fallback names the condition it is for. Detail: [rationale](recurring-bug-patterns-review-rounds.md).
- **A guard for one direction of a symmetric hazard leaves the mirror open** (write-write vs write-read deadlock): enumerate both; reproduce a concurrency claim with a timeout-bounded run, never reason it through.
- **A context manager whose `__exit__` can be interrupted resets shared state in `__enter__`** (fresh container, identity check, no lock).
- **An undocumented third-party breaking change can be survived without an upper pin**: detect its runtime shape (`len(Cls.__parameters__)`) plus a `TYPE_CHECKING` branch.
- **Read a linter's messages and exit code, not its score** (pylint printed `10.00/10` beside an R0902); run CI's exact command. Build the licence database first (`licenseid update`, `licenseid` 0.5.0 or later, which fetches the list from a host the sandbox allows); without it 73 tests fail on `main`. In any other degraded sandbox compare failing test-id sets against a stashed baseline, not counts.
- **A fixture/mock of an external system is broadened with what production inspects.**
- **A byte-identity test must not let the writer stamp the clock**: `ZipFile.writestr("name", ...)` writes `time.time()` (green locally, red once on CI, #306); use `ZipInfo` (fixed 1980 date), run on a clock that moves every call. A rerun cannot prove a flake gone: perturb the variance source. Grep fixture builders for `writestr(<str>`, mtime, `uuid4`.
- **A test helper that normalises what it captures hides the bug class** (`subprocess.run(text=True)` turns CRLF into LF): decode bytes yourself; mutation-test shell/CI changes.
- **A test reaching the network via a subprocess/library (`spdx3-validate` fetches its schema) bypasses the socket block**: mark it `network`, route through `tests/_network.py`.
- **A logging handler bound to `sys.stderr` under `capsys` outlives the capture stream**: `tests/conftest.py` restores the `pitloom` logger after each test; new process-global state a test mutates needs the same.
- **A `skipif` condition runs at import time on every platform** (`os.geteuid()` fails collection on Windows): use one short-circuited module constant; same for POSIX-only names in decorators and `parametrize`.
- **A test making case-variant paths (`Org/`, `org/`) probes the file system first** (`mkdir Probe`, test `probe`, skip, then create): macOS raised `FileExistsError` before a later skip ran.
- **Coverage counts one leg (Linux, Python 3.14)**: a branch only macOS/Windows/another Python reaches (NUL in source: `ValueError` <=3.11, `SyntaxError` 3.12+) shows as missing there; cover each `except` portably.
- **Python 3.14 reports a temp file closed by `__del__` (`urllib.error.HTTPError`) as unraisable**: `with exc:`, and `gc.collect()` in the test. **`os.killpg` on an exited, unreaped group is `ESRCH` on Linux, `EPERM` on macOS**: catch both. Wait for a condition, never a fixed sleep.
- **Run the whole suite before a PR**: a new target kind adds rows to registries area tests never touch (inert options, cap warnings, skill size limits).
- **Fail-fast CI hides other legs**: read which jobs were cancelled before concluding.
- **GitHub Actions substitutes `${{ }}` even in `run:` shell comments**: put such examples above `env:`, not inside `run: |`.
- **pip's `--no-build-isolation` is invocation-global**: do not mix a self-referential local install with unrelated packages in one `pip install`.
- **A Markdown line starting with `<tag>` is an HTML block, even inside a code span that continues from the previous line** (the page vanished): never start a wrapped code-span line with `<`.

## CLI output

- Default: line-delimited, one data point per line. A data point is one record/entity, not one field: a record with several attributes keeps its `KEY=VALUE` pairs on one space-separated line (`PATH=... ROLE=... REQUIRED=... EXISTS=...`); split across lines only for more than one record (one line per record, e.g. per configured fragment).
- Stdout is data only (`--help`/`--version` excepted): `KEY=VALUE` lines from `pitloom.cli.kv_output.print_kv()`, or the SBOM itself for `-o -` (`_sbom_io.write_stdout_lf()`); counts, summaries, hints and `-v` details are `INFO:` on stderr. A value that may hold a space goes last.
- `KEY=VALUE`: uppercase KEY, no spaces around `=`; several pairs on one line only for one data point (e.g. `FORMAT=%s FILE=%s: ...` for one per-model-file warning).
- Three levels reach stderr, each line starting with exactly one of `ERROR: `, `WARNING: `, `INFO: ` plus a short description. Nothing else is grep-able: no second competing tag, no untagged continuation line.
  - `ERROR:` -- via the CLI's own `print(..., file=sys.stderr)` (`cli_error_handler` in `cli/commands/utils.py` adds it around any raised exception); fatal to the operation.
  - `INFO:` -- a normal status update (e.g. "SBOM generation skipped: hook disabled"); `logging.info()` gets it automatically.
  - `pitloom.logging_config.configure_logging()` wires all three identically; every CLI command, the hook and every public library-API entry point must call it first. A new entry point that skips it is a bug.
- Within one subsystem use a shared literal sub-prefix (`ID registry: ...`; `FORMAT=%s FILE=%s: ...`) and match a sibling's wording before inventing one. No global schema across unrelated subsystems; the `LEVEL:` tag is the one prefix every consumer keys on.
- Trim messages to essentials.

## Python

- Verify types with mypy (strict=true); pyright/pytype for second opinions.
- **Untyped third-party dependency**: before an `ignore_missing_imports` override (mypy, pyrefly, ...), look on PyPI for a trusted typeshed `types-<package>` stub package and add it to the `typecheck` group; suppress only when none exists. Why: [rationale](agents-md-rationale.md#python).

## Cross-platform compatibility

- **Dry-run Windows when you cannot run it**: read each new path test as Windows would: `/` in an expected path (Windows shows `\`), `Path ==` on names differing only in case, a `skipif`/constant naming a POSIX-only API, `..` collapsed by Win32 before the open, a symlink needing privilege. Emulate with `PureWindowsPath`/`ntpath`; ask it in every review agent's brief (macOS green is not Windows green, #280).

## Linting and formatting

- Complexity targets: Returns<=6, Args<=5, Locals<=15, Nesting<=5, Branches<=20, Statements<=80, McCabe<=10, Cognitive<=15. Enforced ceilings in `pyproject.toml`/`.flake8` are interim ratchets (`max-args=6`, `max-locals=17`, McCabe=14, Cognitive=20); backlog: `working-docs/design/complexity-and-file-size-roadmap.md`.

## Testing

- **Guard against vacuous passes**: in a "changed input -> unchanged output" test, assert the input actually changed.
- **Keep tests compact**: same coverage and adversarial nature, no redundancy; check whether an existing test hits the branch, fold near-duplicates into one `parametrize` (a case per boundary), share fixtures; never drop the only case killing a mutant.
- **Structure**: same file size limits as source. Naming `test_<area>.py`, 1:1 with the source module (disambiguate tail clashes). Group tests in same-named subfolders mirroring `src/pitloom/<package>/` at 3+ related files (no `__init__.py`).
- **No non-deterministic assertions**: no real wall-clock time, unseeded random/UUID, or set/dict iteration order; freeze time, mock the source or sort. Elapsed-duration bounds (e.g. `time.monotonic()` deltas) with a generous limit are fine.
- **Don't couple tests to undocumented internals**: `raises(match=...)` and log assertions target wording the source documents as intentional (a short stable substring); SPDX3 field/type assertions come from the spec (`spdx_python_model.bindings`), not Pitloom's own layout.
- **Runtime warnings are test failures** (`filterwarnings = ["error"]`): an unavoidable third-party warning gets a narrow module/category-qualified `ignore::` entry with a comment saying why, never a blanket one.
- **Drift-guard test for two independent implementations of one operation**: don't merge them just to dedup; assert both give the same result on one shared fixture.
- **Adversarial edge cases pay most on tri-state (None/empty/absent) and cascade/tie-break logic**: per new field or merge path, one test per boundary (declared-but-empty vs absent, spec-equivalent spellings, candidates needing a tie-break, malformed/truncated input).
  - Tier 2, each review/fix round: full suite (xdist), every CI linter (pyrefly too), each new regression test failing on the base tree, branch coverage of changed files, the manual CLI checks for the touched area.
  - Tier 3, once per PR before merge: mutation testing (each mutant runs only its module's tests), the full manual CLI checks (before handoff, after merging main), the parity/determinism harness, the Windows dry-run, one fresh-context sweep, a fresh-eyes read of any changed `SKILL.md`.

## Manual CLI integration checks (post-pytest, pre-commit)

pytest runs in-process; it misses the `loom` entry point, argv parsing, real filesystem/archive I/O and CLI/library/hook/skills drift. `.venv/bin/python scripts/manual_cli_checks` runs numbered checks (determinism, surface parity, round trips, registry, fragment merge, offline, `--allow-build`, refused wheels, AI model outcomes), the CLI matrix (subcommand x option x env var) and command sequences in a scratch dir; `--only` takes ids/globs, `--network` adds network ones. When to run:

## Shell scripts

- **Windows Git Bash / macOS bash 3.2**: native Windows Python ends lines with CR that `$(...)` keeps; Git Bash has no `/dev/stderr`; bash 3.2 has no `readarray` and is quadratic on `${x//pat/}`. Normalise `GITHUB_ACTION_PATH` backslashes; keep `*.sh` and `action.yml` LF (`.gitattributes`).

## SPDX / Output Specifics

- **Format gaps go in a ledger**: when an SBOM format or a mapping cannot record a fact precisely (no property, a stretched or two-meaning property, a mapping that reads another property), add an entry to `working-docs/design/sbom-format-gaps.md` in the same change, for later proposals to SPDX (and CycloneDX). Never work around a gap silently.
- **`spdx3` vocabulary terms are plain `str`**: `spdx3.RelationshipType`/`RelationshipCompleteness` members are `str`-valued NamedIndividual IRIs, not enum instances. Type a parameter as `str`, never as the class (`spdx3.RelationshipCompleteness | None` fails mypy).

## Writing style

- **PR text defaults** (when a request gives no style or length; an explicit limit overrides): title <= 60 chars, no markdown; summary <= 280 chars, concise bullets, markdown allowed; description <= 600 chars, structured, with a short rationale. Count characters before presenting; each in its own fenced code block, copy-paste ready.
