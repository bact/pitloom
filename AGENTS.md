# Agent instructions

Long-form rationale and examples for the rules below (marked "Why:") are in
[agents-md-rationale.md](working-docs/implementation/agents-md-rationale.md).

## Project context

- SBOM generator targeting Python/Hatchling ecosystem, outputting SPDX 3 JSON-LD.
- Private alpha, one developer. No backward compat needed yet.
- `working-docs/design/`: future work, plans, sketches (not yet built). `working-docs/implementation/`: what WAS built (decisions, why, paths rejected, progress reports). `working-docs/archive/`: evaluations of something wholesale rejected.
- **`roadmap.md` stays a summary**: an item that outgrows a bullet moves to its own file (`design/` unbuilt, `implementation/` built, `archive/` if worth keeping), leaving 1-2 lines plus a `See [doc.md](doc.md)` link. Why: one copy drifts unnoticed.
- Paper notes (sourced raw material for a write-up; add findings worth publishing): `working-docs/implementation/sbom-generator-field-notes/README.md` and `working-docs/implementation/ai-model-scan-security-lessons.md`. Test fixtures: `tests/fixtures/README.md`.
- `working-docs/` is internal notes only -- content can change without notice. The user-facing website (`docs/`) must never link into it; reference a PR or issue number instead.
- **Global file size**: soft limit ~400-500 lines, hard limit ~800 lines (~30KB), for ALL files (source, tests, docs). Split before crossing. Filenames: kebab-case, topic-first; 3+ closely related files go in a same-named subfolder; every split or grouped file gets a "See also" pointer near the top.
- Every commit needs a sign-off line (DCO) in the commit message.
- **CHANGELOG entries** (`CHANGELOG.md`; `CHANGELOG-archive.md` is frozen): concise, no rationale, link the PR; ~160 chars per bullet. Merge related PRs into one entry; sort per section by lowest PR number; skip docs/version-bump/CI-only noise.

### SBOM output

- Deterministic and idempotent: bit-for-bit identical across builds when input/environment unchanged; no random UUIDs, set/dict order or absolute temp paths. The timestamp comes from `--creation-datetime`, else `SOURCE_DATE_EPOCH`, else the clock; a reproducible build or a test pins one of the first two.
- Schema compliance: validate every SBOM against the primary spec (SPDX) and serialisation format before finalisation.

### Metadata sources

- The Hatchling hook reads `self.metadata` via `pitloom.extract.project.hatchling.metadata_from_hatchling()`; the CLI and `generate_project_sbom()`'s default path use `pitloom.extract.project.read_project()`. Both converge on `pitloom.assemble.spdx3.document.build()`.
- **`physical_path` vs `distribution_path`**: on-disk project-relative vs in-package/built path (they diverge for a `src/` layout); `software_File.name` uses `distribution_path`; registry keys come only from `pitloom.id_registry.keys.file_lookup_key`. An `--allow-build` file's `physical_path` is *absolute*: join or embed it only through `pitloom.core.project.project_relative_or_fallback(physical_path, fallback)`. Why: [rationale](working-docs/implementation/agents-md-rationale.md#metadata-sources).
- **Stage-scoped helpers take an explicit stage flag** when a source-stage caller and a build-stage caller share them, so a source-only artefact (`poetry.lock`) cannot leak into the build.

### Usage surfaces

Surfaces: CLI, Hatchling hook, library API, GitHub Action, AI skills (`skills/*/SKILL.md`), Claude Code plugin (`.claude-plugin/`). A change to one ships without the others. Skills/plugin have no tests: when a command/flag/output shape a `SKILL.md` documents changes, grep `skills/` and update it in the same change.

- **Route a cross-cutting choice through one shared, explicit mechanism** every surface already reads, not per-call-site updates.
- **A docstring/comment saying "how surface X does Y" (or "how this mechanism decides") is a claim, not a fact**: verify it against the entry-point code (`__main__.main()`, `plugins/hatch.py`, the library) before trusting or writing it.
- **A pattern hand-copied across 3+ call sites drifts**: factor it into one helper/constant.
- **A test on one surface doesn't cover the others**: for behaviour that must hold across CLI, library, hook and Action, or every subcommand, test each.
- **A skill is discovered through its frontmatter `description` only**: on a CLI command/flag add/rename, check `add_parser(` subcommands against every `skills/*/SKILL.md` description; keep *verify* vs *validate* explicit; try a skill's check on a legitimate input where it should do nothing. Hand-offs, fallbacks: [rationale](working-docs/implementation/agents-md-rationale.md#usage-surfaces); audit: [skills-trigger-coverage.md](working-docs/implementation/skills-trigger-coverage.md).

## Design principles

- **Honour user intent over silent fallbacks**: no implicit fallback that contradicts the user's explicit instruction.
- **No silent deviations**: emit a clear `WARNING:` log or stderr message saying what was decided and why when deviating from an instruction. A rejected input (URL, scheme, ref) is logged as well as raised.
- **Respect the configuration cascade**: CLI flags > `pyproject.toml` > hardcoded defaults.
- **Resource efficiency**: cache and route to limit network access; stream large structures; never load whole files (ML models, archives) into memory: chunked reads (`read(8192)`), memory mapping or lazy header extraction.
- **Explicit pin beats local environment**: a version pinned by its own data source is authoritative and never overridden by introspecting Pitloom's own environment, which is a fallback for the unpinned case only.
- **Absent source data is not an error; a read/access failure is.** A field a source lacks stays `None`/empty/absent, silently; `WARNING:`/`ERROR:`/raising only for real disruption (corruption, a truncated archive, a network error, a parse failure on data its format marker says is well-formed). Why: [rationale](working-docs/implementation/agents-md-rationale.md#design-principles).
- **Caps bound reading, never reporting; every fact has an evidence level**: a size or time cap is for security and hangs only; record the first of **measured**, **declared** (with its source, never passed off as measured), a **lower bound** (provenance only), else `not_measured` and why. A declared value never gates a cap or a read. Rule: [evidence-levels.md](working-docs/design/evidence-levels.md#the-agentsmd-rule).

## Code health and continuous refactoring

- **Boy Scout Rule**: leave the codebase cleaner than you found it; refactor during small changes.
- **Prevent monoliths**: extract cohesive pieces into modules/subpackages early; split *before* the ~400-500 line soft limit.
- **Consolidate patterns**: extract duplicated logic into shared utilities, constants or decorators at once; reuse the shared helper even for a small duplicate (two copies drift).

## Recurring bug patterns

Failure modes that recurred; check by name. Read the detail before extending or
citing a one-liner: [data](working-docs/implementation/recurring-bug-patterns.md),
[platform](working-docs/implementation/recurring-bug-patterns-platform.md),
[test harness](working-docs/implementation/recurring-bug-patterns-test-harness.md),
[CI matrix](working-docs/implementation/recurring-bug-patterns-ci-matrix.md),
[review rounds](working-docs/implementation/recurring-bug-patterns-review-rounds.md),
[fuller wording](working-docs/implementation/recurring-bug-patterns-examples.md).

Data and semantics:

- **`None`/absent vs `[]`/`{}` (empty-but-present) are different signals**: absent = try the next source; empty-but-real = authoritative, stop. Watch truthiness, `dict.get(k, [])`, a merge, sibling fields.
- **A schema validator may not check a relationship's end types**: test the ends from the spec bindings and check them at the fragment merge.
- **Keying a merge on an identifier's spelling unifies what only the spelling shares**: unify a `LicenseRef-` only when its spelling proves it is content-derived (`LicenseRef-loom-text-<16 hex>`).
- **Compare identifiers the ecosystem's way**: PEP 503 names, PEP 440 versions, in code, docstrings and lock-file conflict detection.
- **A placeholder (`UNKNOWN`, `N/A`) is not a claim**: keep it weak in a cascade (emit it only if nothing better); a real "none" ends it; held state is per item.
- **A source that can resolve to zero entries needs its own "is this really a file of this format" check** in a priority cascade.
- **A presence-only check misfires when a key is genuinely boolean**.
- **`dict.get(key, default)` guards absence, not a wrong type**: `isinstance`-check values from external files.
- **A parse helper catching only the format's exception can still die on a bare `UnicodeDecodeError`.**
- **`json.loads(bytes)` strips a UTF-8 BOM; `json.loads(str)` after `.decode()` raises on it**: pass raw bytes where a binary parse matches.
- **Picking one candidate from an unordered collection needs a stable tie-break**; choose a merge survivor from counts over all inputs.
- **A dedup/conflict-exclusion fix must cover every path that can produce the same identity**; a conflict branch must skip itself, not the whole cascade.
- **A guard before a side-effecting step drops that effect**: do the effect first.
- **"No digest" is not "not a file"**: an empty directory, an over-ceiling or unreadable file also hash to `None`; a dangling link is a path. Ask existence with `kind`/`lexists`; test two "is it a path" helpers where they can disagree.
- **Every route that builds one entity shares its identity rule**: one function, plus a test comparing the routes' counts; a fold says (`INFO:`) what it kept.
- **An identity key must carry every field that tells two releases apart** (a package's version), else every release shares one id, silently.
- **A fix scoped to "explicit input" needs an explicit flag.**
- **A field added to a dataclass must be set by every constructor call site**, from one shared helper.
- **An opt-out flag that skips filling an accumulator breaks emptiness/exit checks keyed on it**: re-derive from a populated proxy.
- **Removing a read to save cost can remove an error-surfacing side effect**: use a cheap probe.
- **A ruling that reverses a reading needs a before/after sweep**: run a probe corpus through HEAD and the tree; list inputs that yielded records before and none now.
- **Narrowing a derived field's rule needs an inventory of its writers**: run each through the new rule; derive from the value's shape as well as its key.
- **A doc claim "after X, every Y has Z" names the code path deriving Z** and the Y it reaches.
- **Measure the real tools before designing a reader**: probe each backend, put the matrix in the working doc.
- **A model reader records what the file stores, not what a binding defaults**, and a new format maps every field its siblings do: [model-format-mapping-parity.md](working-docs/implementation/model-format-mapping-parity.md).
- **A failing manual repro is first suspect for a wrong replication**: use the real call shape.
- **`Path.relative_to` does not collapse `..`**: `normpath` lexically first, `realpath` only as fallback.
- **An alias rule must test that the shorter key names no real file**, else two real files with equal bytes alias.
- **Write the key the lookup used, not the element's name**; a typed path takes its on-disk spelling, a derived one is used as given, both through one helper.

Code shape:

- **A path in a message goes through one helper** (`quote_source`, never `repr()`); `loggable()` every interpolated value, test with a newline, test each emitter with a repeated input (said once).
- **A provenance string is built only through `provenance_source`/`provenance_segment`** (a `|` in a name forges a segment); `tests/test_provenance_builders_lint.py` enforces it.
- **A log message in a multi-exit function describes what that branch did**, not the typical path.
- **Reusing a helper outside its contract narrows behaviour silently**: read its docstring preconditions, not only the return type. A shared helper's return type should fit every caller.
- **A private third-party API (`obj._attr`) has no structural guarantee**: verify its shape interactively; prefer the public algorithm. Do not reach into another module's `_name`: promote a public accessor.
- **A check on the URL does not cover every client a fetch starts**: list each program run, switch off what is not needed. Server and subprocess text is attacker text: `loggable()`, one line, credentials masked where built. A fallback names its condition.
- **A circular-import claim needs a live interpreter test** (both import orders).
- **A guard for one direction of a symmetric hazard leaves the mirror open**: enumerate both; reproduce a concurrency claim with a timeout-bounded run.
- **A context manager whose `__exit__` can be interrupted resets shared state in `__enter__`.**
- **A version floor asserted in many places drifts unchecked**: keep it at the verified minimum; on change grep every spelling (requirement/example move; history stays).
- **An undocumented third-party breaking change can be survived without an upper pin**: detect its runtime shape plus a `TYPE_CHECKING` branch.
- **Linters**: read messages and exit code, not the score, with CI's exact command; compare an error count to HEAD with the same interpreter (`pyrefly --python-interpreter`); a `# type: ignore` that a library's type change flips becomes an `Any` view plus `cast`, checked on the lowest supported version. Build the licence database first (`licenseid update --source packaged`, `licenseid` >= 0.9.3; rebuild after an upgrade), else tests fail on `main`; in another degraded sandbox compare failing test-id sets against a baseline.

Tests, platform and CI:

- **A fixture/mock of an external system carries what production inspects.**
- **A byte-identity test must not let the writer stamp the clock** (`ZipFile.writestr("name", ...)`): use `ZipInfo`, run on a clock that moves every call. A rerun cannot prove a flake gone: perturb the variance source.
- **For `A and B` in a derived rule, one test where only `A` fails and one where only `B` fails**; mutation testing finds the missing one.
- **Mutation testing lies two ways**: an equivalent mutant proves nothing (reinstate the exact pre-fix shape); asserting a lazily installed side effect observes nothing.
- **A test helper that normalises what it captures hides the bug class** (`text=True` turns CRLF into LF): decode bytes yourself; mutation-test shell/CI changes.
- **A guard or mock raising inside a stdlib call must raise what that call cleans up on, or close the resource itself**: a third-party `ResourceWarning` in a flaky test is first suspect for our harness.
- **A test reaching the network via a subprocess/library bypasses the socket block**: mark it `network` (real host), route through `tests/_network.py`; a local server is `loopback`.
- **Patching a function on a shared stdlib module patches it for every thread**: import the name into the module under test and patch that.
- **A logging handler bound to `sys.stderr` under `capsys` outlives the capture stream**: `tests/conftest.py` resets the `pitloom` logger per test; new process-global state a test mutates needs the same.
- **A long `parametrize` value becomes the test id** (a Windows cap): short `ids=`; conftest fails ids over 1,000.
- **A `skipif` condition runs at import time on every platform**: use one short-circuited module constant; same for POSIX-only names in decorators and `parametrize`.
- **OS traps in path tests**: build an absolute path from `tempfile.gettempdir()`; probe the file system before making case-variant paths; spy `os.chmod` (assert the mode on POSIX); `write_bytes` when a digest is asserted (`write_text` writes CRLF on Windows); `os.path.isfile`/`isdir` for "never raises" (`Path.exists()` varies by version); a textual "under the project" check falls back to a `(st_dev, st_ino)` ancestor match.
- **Coverage counts one leg (Linux, Python 3.14)**: a branch only another OS/Python reaches shows as missing; cover each `except` portably.
- **Python 3.14 reports a temp file closed by `__del__` (`urllib.error.HTTPError`) as unraisable**: `with exc:`, `gc.collect()` in the test. **`os.killpg` on an exited, unreaped group is `ESRCH` (Linux) or `EPERM` (macOS)**: catch both. Wait for a condition, never a fixed sleep.
- **Run the whole suite before a PR**; **fail-fast CI hides legs**: read the cancelled jobs.
- **CI installs the newest release in a declared range, on another interpreter patch version**: compare the CI log's versions with yours before a push ([detail](working-docs/implementation/recurring-bug-patterns-ci-matrix.md)).
- **Tool traps**: Actions substitutes `${{ }}` even in `run:` comments (put examples above `env:`); pip's `--no-build-isolation` is invocation-global (no self-referential local install beside other packages); never start a wrapped Markdown code-span line with `<` (an HTML block).
- **Parallel agents**: fence file ownership in writing, announce a reversed rule, gate after all land, clean stray files.

## CLI output

Unix philosophy: consistent, predictable, parseable.

- Default: line-delimited, one data point per line. A data point is one record/entity, not one field: its attributes are `KEY=VALUE` pairs (uppercase KEY, no spaces around `=`) on one space-separated line.
- Stdout is data only (`--help`/`--version` excepted): `KEY=VALUE` lines from `pitloom.cli.kv_output.print_kv()`, or the SBOM itself for `-o -` (`_sbom_io.write_stdout_lf()`); counts, summaries, hints and `-v` details go to stderr as `INFO:`. A value that may hold a space goes last.
- Three levels reach stderr, each line starting with exactly one of `ERROR: ` (fatal; `print_error()` with the exception's `[code]`, `cli_error_handler` wraps any raised exception), `WARNING: ` (a "no silent deviations" decision or a recovered problem) or `INFO: ` (status); `logging.warning()`/`info()` add it. No second tag, no untagged continuation line; `logging.debug()` is never prefixed, never on stderr normally.
  - `pitloom.logging_config.configure_logging()` wires all three identically; every CLI command, the hook and every public library-API entry point must call it first. Skipping it is a bug.
- Within one subsystem use a shared literal sub-prefix (`ID registry: ...`) and match a sibling's wording before inventing one. The `LEVEL:` tag is the one prefix every consumer keys on until the catalogue is built.
- **The message catalogue is the contract with the skills** (a message's level, condition, lines and advice are an interface). Adding or changing a message: reuse an existing code first (`src/pitloom/messages/`, `docs/message-codes*.md`); say it through `pitloom.messages` (code `family[/variant]`, by cause, as `pitloom_code`), never a bare `log.*`, `raise ValueError("...")` or `print_error("...")`; shape `LEVEL: [SUBJECT=value: ]CONDITION[; ACTION]`; attacker text through the field writers; a programming error raises `InternalError`. Change it, the generated reference and skill quotes together. Before handoff `python -m scripts.message_inventory --check`, `python scripts/generate_message_reference.py --check` and `pytest tests/messages tests/test_message_ratchet.py` pass; the uncoded count only falls. Steps, traps: [message-catalogue-agent-rules.md](working-docs/implementation/message-catalogue-agent-rules.md); plan: [message-catalogue-and-skills.md](working-docs/design/message-catalogue-and-skills.md).

## Python

- Min version 3.10: no later syntax/features unless via `__future__`; no `A | B` unions outside `TYPE_CHECKING` blocks.
- Verify types with mypy (strict=true); pyright/pytype as second opinions.
- **Untyped third-party dependency**: add a trusted `types-<package>` stub to the `typecheck` group; an `ignore_missing_imports` override only if none exists. Why: [rationale](working-docs/implementation/agents-md-rationale.md#python).
- Fully qualified names in docstrings for non-stdlib types.
- No `assert` in production (tests only). No wildcard imports. All config in `pyproject.toml` where possible.
- **Import order**: stdlib -> third-party -> local, alphabetical within each; do not reorder imports that a comment says must stay in order (circular import/init). `ruff check --fix --select I` automates it.
- Type completeness: annotate all visible class/instance vars, methods, params and returns; give generic bases type args (except simple literals, enum members, standard dunders).

## Cross-platform compatibility

- Must work on Windows, macOS and Linux. Use `pathlib.Path` for paths. `/tmp/` and POSIX directories do not exist on Windows.
- **Dry-run Windows when you cannot run it**: read each path test as Windows would (separators, case, POSIX-only APIs, `..` collapsed before the open, symlink privilege); emulate with `PureWindowsPath`/`ntpath`; put it in each review agent's brief.

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
- Avoid ambiguous variable names (E741). Max line length 88 (prefer 80). Remove unused imports and trailing whitespace.
- Complexity targets: Returns<=6, Args<=5, Locals<=15, Nesting<=5, Branches<=20, Statements<=80, McCabe<=10, Cognitive<=15. Enforced ceilings (`pyproject.toml`, `.flake8`) are interim ratchets; backlog: `working-docs/design/complexity-and-file-size-roadmap.md`.
- Pylint suppressions go on the preceding line as `# pylint: disable-next=<msg>`.

## File headers

Source files carry SPDX tags in this order:

```text
SPDX-FileCopyrightText: <year> <name>
SPDX-FileType: SOURCE                # or DOCUMENTATION
SPDX-License-Identifier: Apache-2.0  # or CC0-1.0 for docs
```

`working-docs/` standalone docs add `Created` and `Last-Modified` (`YYYY-MM-DD`). `SKILL.md` files use `#` YAML comments for these headers at the block's top.

## Testing

- **Bug fix**: add a regression test failing without the fix, passing with it.
- **Guard against vacuous passes**: in a "changed input -> unchanged output" test, assert the input changed.
- Pytest style; `spec`/`autospec` for mocks.
- **Keep tests compact**: same coverage and adversarial nature; fold near-duplicates into one `parametrize` (a case per boundary), share fixtures; never drop the only case killing a mutant.
- **Structure**: naming `test_<area>.py`, 1:1 with the source module (disambiguate tail clashes). Group tests in same-named subfolders mirroring `src/pitloom/<package>/` at 3+ related files (no `__init__.py`).
- **No non-deterministic assertions**: no real wall-clock time, unseeded random/UUID, or set/dict iteration order; freeze time, mock the source or sort. Generous `time.monotonic()` bounds are fine.
- **Don't couple tests to undocumented internals**: `raises(match=...)` and log assertions target wording documented as intentional (a short stable substring); SPDX3 field/type assertions come from the spec (`spdx_python_model.bindings`).
- **Runtime warnings are test failures** (`filterwarnings = ["error"]`): an unavoidable third-party warning gets a narrow module/category-qualified `ignore::` entry with a comment, never a blanket one.
- **A test fails on an uncoded `INFO:`/`WARNING:`/`ERROR:` line** (not a summary, detail or relay) unless `@pytest.mark.uncoded_output(<regex>)` allows it: [rules](working-docs/implementation/message-catalogue-agent-rules.md).
- **Drift-guard test for two independent implementations of one operation**: assert both agree on one shared fixture rather than merging them.
- **Adversarial edge cases pay most on tri-state (None/empty/absent) and cascade/tie-break logic**: one test per boundary per new field or merge path.
- **OS coverage in CI is partial on a PR**: Linux runs all tests, Windows and macOS only `-m platform` (`tests/_platform.py`). A new or changed test touching paths, files, processes, encodings, line ends, permissions or packaging: run `pytest <file> -m platform --collect-only -q`; nothing collected: add `pytestmark = pytest.mark.platform` (or extend `OS_USE`); unsure: mark it. Label such a PR `test-all-os`.
- **Green CI is merge-ready only once the full tests ran on every OS**: the PR has `test-all-os` and the `Unit tests` and `Build wheels` runs for the head SHA started after the label (re-run if not); else report "green on the platform subset only", name the label, ask the user. Neither `Unit tests` alone nor the push-to-`main` run counts. Detail: [rationale](working-docs/implementation/agents-md-rationale.md#tests-platform-and-ci).
- **Test tiers, two gates per PR** ([policy](working-docs/implementation/testing-and-review-policy.md)):
  - Tier 1, between gates and review/fix rounds: touched tests (`-k`, `--lf`), linters, an SBOM/stderr/`--json` diff vs main; never the full suite or coverage.
  - Gate A, once reviews converge: full suite (`-n 4` max), every CI linter (pyrefly too), each new regression test failing on the base tree, branch coverage of changed files; timing tests use small inputs.
  - Gate B (Tier 3), before handoff: mutation testing, full manual CLI checks, parity/determinism harness, Windows dry-run, a fresh-context sweep, a fresh read of changed `SKILL.md`s.
  - Batch review fixes; a main merge of only CHANGELOG links, baselines or generated pages runs just the tests reading them.

### Manual CLI integration checks (post-pytest, pre-commit)

`.venv/bin/python scripts/manual_cli_checks` covers what in-process pytest misses (entry point, argv, real I/O, surface drift). Skip it for a docs-, tests- or `working-docs/`-only change; Gate A touching `assemble/`, `extract/`, `core/`, `embed.py`, `__main__.py` or `plugins/hatch.py`: that area's `--only` set ([when to run](working-docs/implementation/manual-cli-checks.md#when-to-run)); Gate B, and after a main merge with code: the full run (`-j 8`).

A new CLI option or subcommand needs an entry in `scripts/manual_cli_checks/_matrix_plan.py` (`M/completeness` fails in CI otherwise).

## Shell scripts

- Account for GNU/BSD/macOS tool differences; defensive variable expansion; quote paths and variables.
- **Composite-action scripts** (`scripts/action/`): CI lints only `examples/ src/ tests/`; run the linters, `shellcheck -x` and `actionlint` on `scripts/` by hand. Notes: [github-action.md](working-docs/implementation/github-action.md).
- **Windows Git Bash / macOS bash 3.2**: strip the CR `$(...)` keeps from Windows Python; no `/dev/stderr`, `readarray` or `${x//pat/}` on long input; normalise `GITHUB_ACTION_PATH` backslashes; keep `*.sh`, `action.yml` LF.
- **Never let a step log tool output raw**: a `::` line runs as a workflow command. Fence the echo with `::stop-commands::<random token>`; fence, echo and annotations must share one stream.

## Naming

- **Python module leading underscore** when nothing outside its package directory imports it; none when something does.
- Consult Schema.org, NIEM Model, FIBO and OBO Foundry for ontology naming.

## SPDX / Output Specifics

- SPDX 3 JSON: canonical serialisation and RFC 8785. JSON-LD: RDF canonicalization. Dates: ISO 8601, UTC+0.
- **Format gaps go in a ledger**: a fact a format or mapping cannot record precisely gets an entry in `working-docs/design/sbom-format-gaps.md` in the same change; never work around a gap silently.
- **`spdx3` vocabulary terms are plain `str`** (`RelationshipType`/`RelationshipCompleteness` members are IRIs, not enum instances): type a parameter as `str`, never as the class.

## Writing style

- British English for docs, comments and text. American spelling only for code identifiers and for field, key, type or file-format names a specification fixes exactly.
- IETF verbal forms (RFC 2119/8174) for internet/web/semantic-web projects; ISO verbal forms for SPDX docs.
- Code comments are direct, concise and about the current implementation; no history. Legitimate current behaviour vs an alternative design is fine.
- **No invisible or uncommon characters in source**: write an escape (`\u200b`, `\ufeff`, `\x1b`) for an invisible space, BOM, bidi mark or control character; in comments and docstrings `--`, `-`, straight quotes, `...`, `->`, not their typographic forms (they defeat grep). Non-ASCII only in human-language messages and diagrams. Why: [rationale](working-docs/implementation/agents-md-rationale.md#writing-style).
- **Product name**: write LicenseID, never licenseid, for the product in prose; lowercase `licenseid` only for the package, command, import, requirement or an identifier.
- **PR text defaults** (an explicit limit overrides): title <= 60 chars, no markdown; summary <= 280 chars, concise bullets, markdown allowed; description <= 600 chars, structured, with a short rationale. Count characters; use code blocks.

## Boundaries

**Ask before doing:** large cross-package refactors; new dependencies with broad impact; destructive data or migration changes.

**Never:** edit generated files by hand when a generation workflow exists; use destructive git operations unless explicitly requested; auto-commit (leave all changes uncommitted for the user to review and commit, unless they explicitly ask).
