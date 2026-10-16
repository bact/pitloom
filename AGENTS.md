# Agent instructions

Long-form rationale and examples for the rules below (marked "Why:") are in
[agents-md-rationale.md](working-docs/implementation/agents-md-rationale.md).

## Project context

- SBOM generator targeting Python/Hatchling ecosystem, outputting SPDX 3 JSON-LD.
- Private alpha, one developer. No backward compat needed yet.
- Design docs: `working-docs/design/` -- future work, plans, sketches; may be discarded, not yet built.
- Implementation docs and progress reports: `working-docs/implementation/` -- what WAS built: decisions, why, paths rejected in service of something built, revisions. Not a user manual.
- Rejected paths: `working-docs/archive/` -- evaluations of something wholesale rejected.
- **`roadmap.md` stays a summary, not a duplicate**: when an item's detail outgrows a bullet, move it to its own file (`design/` while unbuilt, `implementation/` once built, `archive/` if abandoned but worth keeping) and trim the bullet to 1-2 lines plus a `See [doc.md](doc.md)` link. Small unbuilt items stay inline. Why: one copy drifts unnoticed.
- Paper notes (sourced raw material for an academic write-up): `working-docs/implementation/sbom-generator-field-notes/` (start at its `README.md`) and `working-docs/implementation/ai-model-scan-security-lessons.md` (an entry page; findings are in its `-*` parts). Add to them when a finding is worth publishing.
- Test fixtures: `tests/fixtures/README.md`
- `working-docs/` is internal notes only -- content can change without notice. The user-facing website (`docs/`) must never link into it. Reference a PR or issue number instead.
- **Global file size**: soft limit ~400-500 lines, hard limit ~800 lines (~30KB), for ALL files (source, tests, docs). Split before crossing it.
- **Naming and grouping**: kebab-case, topic-first filenames. If a topic outgrows 3+ closely related files, group them in a same-named subfolder.
- **Cross-linking**: every split or grouped file gets a "See also" pointer near the top.
- Every commit needs a sign-off line (DCO) in the commit message.
- **CHANGELOG entries**: concise, no background/rationale (link the PR); ~160 chars per bullet (more only for a genuinely complex PR). Merge related PRs into one entry (`[#1], [#2]`); sort entries per section by lowest PR number; skip docs/version-bump/CI-only noise. New entries go in `CHANGELOG.md`; `CHANGELOG-archive.md` (pre-0.19.0) is frozen.

### SBOM output

- Deterministic: bit-for-bit identical across builds when input/environment unchanged.
- Idempotent: no non-deterministic data (timestamps, random UUIDs).
- Schema compliance: validate every SBOM against the primary spec (SPDX) and serialisation format before finalisation.

### Metadata sources

- The Hatchling build hook (`pitloom.plugins.hatch`) reads project metadata from `self.metadata` via `pitloom.extract.hatchling.metadata_from_hatchling()`.
- The CLI (`pitloom.__main__`) and `generate_project_sbom()`'s default path resolve metadata via `pitloom.extract.project.read_project()`.
- Both paths converge on `pitloom.assemble.spdx3.document.build()`.
- **`physical_path` vs `distribution_path`**: on-disk project-relative path vs in-package/built path; they diverge for any `src/`-layout project. `software_File.name` always uses `distribution_path`. Registry keys come only from `pitloom.id_registry.keys.file_lookup_key`. For an `--allow-build` file, `physical_path` is an *absolute* temporary path: any consumer that joins it onto `project_dir` or bakes it into a determinism-sensitive string must call `pitloom.core.project.project_relative_or_fallback(physical_path, fallback)`, not an inline `is_absolute()` check. Why: [rationale](working-docs/implementation/agents-md-rationale.md#metadata-sources).
- **Stage-scoped helpers take an explicit stage flag**: a helper shared by a source-stage caller (`read_pyproject()`) and a build-stage caller (the hook's gap-fill) needs a parameter (`include_locked_dependencies=False`-style), not call-site discipline; a source-only artifact (`poetry.lock`) must not leak into the build stage.

### Usage surfaces

Pitloom runs from several surfaces: CLI (10+ subcommands), the Hatchling hook, the library API, the GitHub Action, the AI skills (`skills/*/SKILL.md`) and the Claude Code plugin (`.claude-plugin/`). A change to one surface/subcommand ships easily without the others, since each surface's own tests keep passing (`--debug` reached the top-level parser, but 7 of 10 subcommand generators called `configure_logging()` again and reverted to `INFO`). Skills/plugin have no test suite: when editing anything a `SKILL.md` documents invoking, grep `skills/` for the changed command/flag/output shape and update it in the same change.

- **Route a cross-cutting choice through one shared, explicit mechanism** every surface already reads (`--debug` -> the `PITLOOM_DEBUG` env var), not per-call-site updates.
- **A docstring/comment saying "how surface X does Y" is a claim, not a fact**: verify it against the entry-point code (`__main__.main()`, `plugins/hatch.py`, the library functions) before trusting or writing it.
- **A pattern hand-copied across 3+ call sites drifts** (e.g. a `WARNING:` naming the skipped SBOM field): factor it into one helper/constant.
- **A test on one surface doesn't cover the others**: for behaviour that must hold across CLI, library, hook and Action, or every subcommand, test each.
- **A skill is discovered through its frontmatter `description` only**, and a body section does not make a command triggerable. On a CLI command/flag add or rename, enumerate `add_parser(` subcommands against every `skills/*/SKILL.md` description; keep *verify* (structural) vs *validate* (schema/SHACL) explicit; give combined asks ("generate SBOM meeting CISA") a hand-off in both skills; give every "ask a follow-up" step a non-interactive fallback. A check or recipe a skill tells the agent to run must be tried on a legitimate input where it should do nothing. Audit: [skills-trigger-coverage.md](working-docs/implementation/skills-trigger-coverage.md).

## Design principles

- **Honour user intent over silent fallbacks**: no implicit fallback that contradicts the user's explicit instruction.
- **No silent deviations**: emit a clear `WARNING:` log or stderr message saying what was decided and why when deviating from an instruction.
- **Respect the configuration cascade**: CLI flags > `pyproject.toml` > hardcoded defaults.
- **Resource efficiency**: cache and route to limit network access; stream large structures; never load whole files (ML models, archives) into memory: chunked reads (`read(8192)`), memory mapping or native lazy header extraction (`np.lib.format`, stream loading for fickling/pickle).
- **Explicit pin beats local environment**: a version pinned by its own data source (lock file, exact `==`/`===`) is authoritative and never overridden by introspecting Pitloom's own environment; introspection is a fallback for the unpinned case only.
- **Absent source data is not an error; a genuine read/access failure is.** Every extractor/metadata source (model readers, project parsers, lock readers, Hub/network fetches) degrades gracefully: a field the source does not carry stays `None`/empty/absent, silently, no `WARNING:`/`ERROR:`, no exception (nothing was deviated from). Reserve `WARNING:`/`ERROR:`/raising for real disruption: corruption, an unreadable/truncated archive, a network error or timeout, a parse failure on data the format's own marker says is well-formed. Line: "had an opinion and failed to deliver it" (log/raise) vs "never had this data" (quiet). Why: [rationale](working-docs/implementation/agents-md-rationale.md#design-principles).

## Code health and continuous refactoring

- **Boy Scout Rule**: leave the codebase cleaner than you found it; refactor proactively during small changes.
- **Prevent monoliths**: extract cohesive pieces into modules/subpackages early (`parser.py`, `__main__.py`); obey the ~400-500 line soft limit, split *before* it is a problem.
- **Consolidate patterns**: extract duplicated logic into shared utilities, constants or decorators immediately.
- **Reuse/dedup is a defensiveness strategy**: two independent implementations of one operation (a hash, a type check, a message string, a cascade rule) can silently disagree later; reuse the shared helper even when the duplicate is small, to make drift structurally impossible.

## Recurring bug patterns

Failure modes that recurred across subsystems; check for them by name.
Detail (war stories, PRs, code shapes) is in
[recurring-bug-patterns.md](working-docs/implementation/recurring-bug-patterns.md) (data and semantics),
[recurring-bug-patterns-platform.md](working-docs/implementation/recurring-bug-patterns-platform.md) (platform, concurrency, test harness, CI) and
[recurring-bug-patterns-review-rounds.md](working-docs/implementation/recurring-bug-patterns-review-rounds.md) (PR #300, #305, #306 and path-key rounds): read them before extending or citing a one-liner.

Data and semantics:

- **`None`/absent vs `[]`/`{}` (empty-but-present) are different signals**: absent = try the next source; empty-but-real = authoritative, stop. Watch truthiness checks, `dict.get(k, [])`, provenance gated on the resolved value not the raw key, presence lost across a merge, a fix applied to one field but not its siblings.
- **Compare identifiers the ecosystem's way**: PEP 503 names, PEP 440 versions (never SemVer: `"1.0"` == `"1.0.0"`), in code, docstrings and lock-file conflict detection.
- **A placeholder (`UNKNOWN`, `N/A`) is not a claim**: keep it weak in a cascade (skip while a later source may know better, emit with provenance only if nothing better); a real "none" ends it; held state is per item.
- **A source that can resolve to zero entries needs its own "is this really a file of this format" check** in a priority cascade.
- **A presence-only check misfires when a key is genuinely boolean** (`Pipfile.lock` `"editable": false`).
- **`dict.get(key, default)` guards absence, not a wrong type**: `isinstance`-check values from external files (`@graph` present but not a list).
- **A parse helper catching only the format's exception (`TOMLDecodeError`, `JSONDecodeError`) can still crash on a bare `UnicodeDecodeError`.**
- **`json.loads(bytes)` strips a UTF-8 BOM; `json.loads(str)` after `.decode()` raises on it**: pass raw bytes where a binary parse matches.
- **Picking one candidate from an unordered collection needs an explicit stable tie-break**; choose a merge survivor from counts over all inputs (load all, rank, prove reversed input order gives the same ids).
- **A dedup/conflict-exclusion fix must cover every path that can produce the same identity**; a conflict branch must skip itself, not the whole cascade.
- **A guard before a side-effecting step drops that effect** (a skip `return` before `reserve_id()` re-minted the id): do the effect first.
- **A fix scoped to "explicit input" needs an explicit flag** (an unreadable-root `ERROR` also hit the implicit default roots).
- **A field added to a dataclass must be set by every constructor call site**, from one shared helper.
- **An opt-out flag that skips filling an accumulator breaks emptiness/exit checks keyed on it**: re-derive from a still-populated proxy.
- **Removing a read to save cost can remove an error-surfacing side effect** (the `PermissionError` a full read raised): use a cheap probe.
- **A ruling that reverses a reading needs a before/after sweep**: run a probe corpus through HEAD and the tree; list inputs that yielded records before and none now.
- **Narrowing a derived field's rule needs an inventory of its writers** (builder, SDK, fragment, hand-built model): run each through the new rule; derive from the value's shape as well as its key (`7B` is no count). A reversed rule is recorded as "tried, reverted".
- **A doc claim "after X, every Y has Z" names the code path deriving Z** and the Y it reaches.
- **A doc/docstring claim about "how this mechanism decides" is re-verified against the code before it is trusted or restated.**
- **Measure the real tools before designing a reader** (`uv export`, `pip lock` write no PEP 751 extras keys): probe each backend, put the matrix in the working doc.
- **A failing manual repro is first suspect for a wrong replication**: use the real call shape (a parsed object, not a raw `str`).
- **`Path.relative_to` does not collapse `..`**: `normpath` lexically first, `realpath` only as fallback.
- **An alias rule must test that the shorter key names no real file**: else two real files with equal bytes (empty `__init__.py`) alias; look up a few built candidate keys, never scan the table.
- **Write the key the lookup used, not the element's name**; a typed path takes its on-disk spelling, a derived one is used as given, both through one helper.

Code shape:

- **Warning/error/log wording drifts across sibling modules**: one shared helper; check siblings when adding a check.
- **A log message in a multi-exit function describes what that branch did**, not the typical path.
- **Reusing a helper outside its contract narrows behaviour silently**: read its docstring preconditions, not only the return type. A shared helper's return type should fit every caller.
- **A private third-party API (`obj._attr`) has no structural guarantee**: verify its shape interactively, prefer the public algorithm. Do not reach into another module's `_name`: promote a public accessor.
- **A circular-import claim needs a live interpreter test** (both import orders).
- **A guard for one direction of a symmetric hazard leaves the mirror open** (write-write vs write-read deadlock): enumerate both; reproduce a concurrency claim with a timeout-bounded run, never reason it through.
- **A context manager whose `__exit__` can be interrupted resets shared state in `__enter__`** (fresh container, identity check, no lock).
- **A version floor asserted in many places drifts and no script checks it**: keep it at the verified minimum; on change grep every spelling (requirement/example move; history stays).
- **An undocumented third-party breaking change can be survived without an upper pin**: detect its runtime shape (`len(Cls.__parameters__)`) plus a `TYPE_CHECKING` branch.
- **Compare a linter's error count to HEAD with the same interpreter** (`pyrefly --python-interpreter`).

Tests, platform and CI:

- **A fixture/mock of an external system is broadened with what production inspects.**
- **A byte-identity test must not let the writer stamp the clock**: `ZipFile.writestr("name", ...)` writes `time.time()` (green locally, red once on CI, #306); use `ZipInfo` (fixed 1980 date), run on a clock that moves every call. A rerun cannot prove a flake gone: perturb the variance source. Grep fixture builders for `writestr(<str>`, mtime, `uuid4`.
- **For `A and B` in a derived rule, one test where only `A` fails and one where only `B` fails**; mutation testing finds the missing one.
- **Mutation testing lies two ways**: an equivalent mutant proves nothing (reinstate the exact pre-fix shape); an assertion on a lazily installed side effect observes nothing.
- **A test helper that normalises what it captures hides the bug class** (`subprocess.run(text=True)` turns CRLF into LF): decode bytes yourself; mutation-test shell/CI changes.
- **A test reaching the network via a subprocess/library (`spdx3-validate` fetches its schema) bypasses the socket block**: mark it `network`, route through `tests/_network.py`.
- **Patching a function on a shared stdlib module (`mod.time.sleep`) patches it for every thread**: import the name into the module under test and patch that.
- **A logging handler bound to `sys.stderr` under `capsys` outlives the capture stream**: `tests/conftest.py` restores the `pitloom` logger after each test; new process-global state a test mutates needs the same.
- **A long `parametrize` value becomes the test id** (Windows `PYTEST_CURRENT_TEST` cap 32,767 chars): short `ids=`; conftest fails ids over 1,000.
- **A `skipif` condition runs at import time on every platform** (`os.geteuid()` fails collection on Windows): use one short-circuited module constant; same for POSIX-only names in decorators and `parametrize`.
- **A hardcoded POSIX path in a test skips the "absolute" branch on Windows**: build it from `tempfile.gettempdir()`.
- **A bit-for-bit POSIX permission assertion is unwinnable on Windows**: spy `os.chmod` arguments; keep the real assertion on POSIX.
- **`Path.write_text("x\n")` writes CRLF on Windows**: `write_bytes` when a digest is asserted.
- **`Path.exists()`/`is_file()` swallow only some errnos** (`PermissionError` propagates on 3.10-3.13, `False` on 3.14): use `os.path.isfile`/`isdir` for "never raises"; gate a test by version, plus a version-independent probe.
- **A textual "under the project" check misses on a case-insensitive file system**: fall back to a `(st_dev, st_ino)` ancestor match (`st_ino == 0` = no identity).
- **Coverage counts one leg (Linux, Python 3.14)**: a branch only macOS/Windows/another Python reaches (NUL in source: `ValueError` <=3.11, `SyntaxError` 3.12+) shows as missing there; cover each `except` portably.
- **Fail-fast CI hides other legs**: read which jobs were cancelled before concluding.
- **GitHub Actions substitutes `${{ }}` even in `run:` shell comments**: put such examples above `env:`, not inside `run: |`.
- **pip's `--no-build-isolation` is invocation-global**: do not mix a self-referential local install with unrelated packages in one `pip install`.
- **A Markdown line starting with `<tag>` is an HTML block, even inside a code span that continues from the previous line** (the page vanished): never start a wrapped code-span line with `<`.
- **Parallel agents**: fence file ownership in writing, tell running agents when a rule is reversed, gate after all land, clean stray files and `pytest-of-*` dirs.

## CLI output

Unix philosophy: consistent, predictable, parseable.

- Default: line-delimited, one data point per line. A data point is one record/entity, not one field: a record with several attributes keeps its `KEY=VALUE` pairs on one space-separated line (`PATH=... ROLE=... REQUIRED=... EXISTS=...`); split across lines only for more than one record (one line per record, e.g. per configured fragment).
- Stdout is data only (`--help`/`--version` excepted): `KEY=VALUE` lines from `pitloom.cli.kv_output.print_kv()`, or the SBOM itself for `-o -` (`_sbom_io.write_stdout_lf()`); counts, summaries, hints and `-v` details are `INFO:` on stderr. A value that may hold a space goes last.
- `KEY=VALUE`: uppercase KEY, no spaces around `=`; several pairs on one line only for one data point (e.g. `FORMAT=%s FILE=%s: ...` for one per-model-file warning).
- Three levels reach stderr, each line starting with exactly one of `ERROR: `, `WARNING: `, `INFO: ` plus a short description. Nothing else is grep-able: no second competing tag, no untagged continuation line.
  - `ERROR:` -- via the CLI's own `print(..., file=sys.stderr)` (`cli_error_handler` in `cli/commands/utils.py` adds it around any raised exception); fatal to the operation.
  - `WARNING:` -- a "no silent deviations" decision or a recovered non-fatal problem; `logging.warning()` gets the prefix automatically.
  - `INFO:` -- a normal status update (e.g. "SBOM generation skipped: hook disabled"); `logging.info()` gets it automatically.
  - `logging.debug()` is developer-only: never prefixed, never on stderr normally.
  - `pitloom.logging_config.configure_logging()` wires all three identically; every CLI command, the hook and every public library-API entry point must call it first. A new entry point that skips it is a bug.
- Within one subsystem use a shared literal sub-prefix (`ID registry: ...`; `FORMAT=%s FILE=%s: ...`) and match a sibling's wording before inventing one. No global schema across unrelated subsystems; the `LEVEL:` tag is the one prefix every consumer keys on.
- Trim messages to essentials.

## Python

- Min version 3.10: no later syntax/features unless via `__future__`; no `A | B` unions outside `TYPE_CHECKING` blocks.
- Verify types with mypy (strict=true); pyright/pytype for second opinions.
- **Untyped third-party dependency**: before an `ignore_missing_imports` override (mypy, pyrefly, ...), look on PyPI for a trusted typeshed `types-<package>` stub package and add it to the `typecheck` group; suppress only when none exists. Why: [rationale](working-docs/implementation/agents-md-rationale.md#python).
- Fully qualified names in docstrings for non-stdlib types (`numpy.ndarray`).
- No `assert` in production (tests only). No wildcard imports. All config in `pyproject.toml` where possible.
- **Import order**: stdlib -> third-party -> local, alphabetical within each; do not reorder imports that a comment says must stay in order (circular import/init). `ruff check --fix --select I` automates it.
- Type completeness: annotate all visible class/instance vars, methods, params and returns; give generic bases type args (except simple literals, enum members, standard dunders).

## Cross-platform compatibility

- Must work on Windows, macOS and Linux. Use `pathlib.Path` for paths. `/tmp/` and POSIX directories do not exist on Windows.
- **Dry-run Windows when you cannot run it**: read each new path test as Windows would: `/` in an expected path (Windows shows `\`), `Path ==` on names differing only in case, a `skipif`/constant naming a POSIX-only API, `..` collapsed by Win32 before the open, a symlink needing privilege. Emulate with `PureWindowsPath`/`ntpath`; ask it in every review agent's brief (macOS green is not Windows green, #280).

## Linting and formatting

Run and fix all errors before committing:

```shell
ruff format
ruff check --fix
pylint examples/ src/ tests/ tests/*/
mypy
pyright
pyrefly check
bandit -r
flake8
```

- pylint needs `tests/*/` too (it does not descend into subfolders without `__init__.py`); pass directories, not single files (a file loses its dotted name: false E0402).
- Avoid ambiguous variable names (E741). Max line length 88 (prefer 80). Remove unused imports and trailing whitespace. Non-ASCII only in human-language messages and diagrams.
- Complexity targets: Returns<=6, Args<=5, Locals<=15, Nesting<=5, Branches<=20, Statements<=80, McCabe<=10, Cognitive<=15. Enforced ceilings in `pyproject.toml`/`.flake8` are interim ratchets (`max-args=6`, `max-locals=18`, McCabe=35, Cognitive=60); backlog: `working-docs/design/complexity-and-file-size-roadmap.md`.
- Pylint suppressions go on the preceding line as `# pylint: disable-next=<msg>` (a bare `# pylint: disable=` before an `except` stopped working in pylint 4.1).

## File headers

Source files carry SPDX tags in this order:

```text
SPDX-FileCopyrightText: <year> <name>
SPDX-FileType: SOURCE                # or DOCUMENTATION
SPDX-License-Identifier: Apache-2.0  # or CC0-1.0 for docs
```

`working-docs/` standalone docs add `Created` and `Last-Modified` (`YYYY-MM-DD`). `SKILL.md` files use `#` YAML comments for these headers at the block's top.

## Testing

- **Bug fixes and regressions**: add a regression test that fails without the fix and passes with it.
- **Guard against vacuous passes**: in a "changed input -> unchanged output" test, assert the input actually changed.
- Use pytest patterns, `spec`/`autospec` for mocks, `@pytest.mark.parametrize`.
- **Keep tests compact**: same coverage and adversarial nature, no redundancy; check whether an existing test hits the branch, fold near-duplicates into one `parametrize` (a case per boundary), share fixtures; never drop the only case killing a mutant.
- **Structure**: same file size limits as source. Naming `test_<area>.py`, 1:1 with the source module (disambiguate tail clashes). Group tests in same-named subfolders mirroring `src/pitloom/<package>/` at 3+ related files (no `__init__.py`).
- **No non-deterministic assertions**: no real wall-clock time, unseeded random/UUID, or set/dict iteration order; freeze time, mock the source or sort. Elapsed-duration bounds (e.g. `time.monotonic()` deltas) with a generous limit are fine.
- **Don't couple tests to undocumented internals**: `raises(match=...)` and log assertions target wording the source documents as intentional (a short stable substring); SPDX3 field/type assertions come from the spec (`spdx_python_model.bindings`), not Pitloom's own layout.
- **Runtime warnings are test failures** (`filterwarnings = ["error"]`): an unavoidable third-party warning gets a narrow module/category-qualified `ignore::` entry with a comment saying why, never a blanket one.
- **Drift-guard test for two independent implementations of one operation**: don't merge them just to dedup; assert both give the same result on one shared fixture.
- **Adversarial edge cases pay most on tri-state (None/empty/absent) and cascade/tie-break logic**: per new field or merge path, one test per boundary (declared-but-empty vs absent, spec-equivalent spellings, candidates needing a tie-break, malformed/truncated input).
- **Test tiers**:
  - Tier 1, editing: touched tests only (`pytest tests/<area> -k ...`, `--lf`), ruff, mypy.
  - Tier 2, each review/fix round: full suite (xdist), every CI linter (pyrefly too), each new regression test failing on the base tree, branch coverage of changed files, the manual CLI checks for the touched area.
  - Tier 3, once per PR before merge: mutation testing (each mutant runs only its module's tests), the full manual CLI checks (before handoff, after merging main), the parity/determinism harness, the Windows dry-run, one fresh-context sweep, a fresh-eyes read of any changed `SKILL.md`.

### Manual CLI integration checks (post-pytest, pre-commit)

pytest runs in-process; it misses the `loom` entry point, argv parsing, real filesystem/archive I/O and CLI/library/hook/skills drift. `.venv/bin/python scripts/manual_cli_checks` runs numbered checks (determinism, surface parity, round trips, registry, fragment merge, offline, `--allow-build`, refused wheels, AI model outcomes), the CLI matrix (subcommand x option x env var) and command sequences in a scratch dir; `--only` takes ids/globs, `--network` adds network ones. When to run:

- docs-, tests- or `working-docs/`-only change: skip;
- each round touching `assemble/`, `extract/`, `core/`, `embed.py`, `__main__.py` or `plugins/hatch.py`: the checks for that area via `--only` ([manual-cli-checks.md](working-docs/implementation/manual-cli-checks.md#when-to-run));
- before handoff, and again after merging main: the full run (`-j 8`).

A new CLI option or subcommand needs an entry in `scripts/manual_cli_checks/_matrix_plan.py` (`M/completeness` fails in CI otherwise).

## Shell scripts

- Account for GNU/BSD/macOS tool differences; defensive variable expansion; quote paths and variables.
- **Composite-action scripts** (`scripts/action/`, tested by `tests/scripts/action/`): CI lints only `examples/ src/ tests/`; run the linters, `shellcheck -x` and `actionlint` on `scripts/` by hand. Notes: [github-action.md](working-docs/implementation/github-action.md).
- **Windows Git Bash / macOS bash 3.2**: native Windows Python ends lines with CR that `$(...)` keeps; Git Bash has no `/dev/stderr`; bash 3.2 has no `readarray` and is quadratic on `${x//pat/}`. Normalise `GITHUB_ACTION_PATH` backslashes; keep `*.sh` and `action.yml` LF (`.gitattributes`).
- **Never let a step log tool output raw**: a `::` line runs as a workflow command. Fence the echo with `::stop-commands::<random token>`; fence, echo and annotations must share one stream (the runner does not order stdout against stderr).

## Naming

- **Python module leading underscore** (`_common.py`) when nothing outside its package directory imports it; none (`wheel.py`) when something does.
- Consult Schema.org, NIEM Model, FIBO and OBO Foundry for ontology naming.

## SPDX / Output Specifics

- SPDX 3 JSON: canonical serialisation and RFC 8785. JSON-LD: RDF canonicalization. Dates: ISO 8601, UTC+0.
- **`spdx3` vocabulary terms are plain `str`**: `spdx3.RelationshipType`/`RelationshipCompleteness` members are `str`-valued NamedIndividual IRIs, not enum instances. Type a parameter as `str`, never as the class (`spdx3.RelationshipCompleteness | None` fails mypy).

## Writing style

- British English for docs, comments and text. American spelling only for code identifiers and for field, key, type or file-format names a specification fixes exactly (`license`, `licenseConcluded`, `Organization`, `graph.initializer`).
- IETF verbal forms (RFC 2119/8174) for internet/web/semantic-web projects; ISO verbal forms for SPDX docs.
- Code comments are direct, concise and about the current implementation; no history. Legitimate current behaviour vs an alternative design is fine.
- **PR text defaults** (when a request gives no style or length; an explicit limit overrides): title <= 60 chars, no markdown; summary <= 280 chars, concise bullets, markdown allowed; description <= 600 chars, structured, with a short rationale. Count characters before presenting; each in its own fenced code block, copy-paste ready.

## Boundaries

**Ask before doing:** large cross-package refactors; new dependencies with broad impact; destructive data or migration changes.

**Never:** edit generated files by hand when a generation workflow exists; use destructive git operations unless explicitly requested; auto-commit (leave all changes uncommitted for the user to review and commit, unless they explicitly ask).
