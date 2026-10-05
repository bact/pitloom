# Agent instructions

## Project context

- SBOM generator targeting Python/Hatchling ecosystem, outputting SPDX 3 JSON-LD.
- Design docs: `working-docs/design/` -- future work, plans, sketches; may be discarded, not yet built.
- **`roadmap.md` stays a summary, not a duplicate**: once a roadmap item's design/open-questions detail grows enough to warrant its own file under `working-docs/design/`, move the detail there and trim the `roadmap.md` bullet back to one-to-two lines plus a `See [doc.md](doc.md)` link. Don't leave full detail in both places -- one will drift from the other unnoticed. The same split applies by kind, not just size: a completed item's decisions/rationale/paths-rejected belongs in `working-docs/implementation/` (not `design/`), trimmed from `roadmap.md` the same way once it has its own doc. A roadmap item that's abandoned or superseded but still worth keeping to prevent re-litigating it later moves to `working-docs/archive/` instead of staying in the active list. A still-unimplemented item that's genuinely small (a few lines, no real design decisions yet) is fine to keep inline in `roadmap.md` with no dedicated file -- split it out only once it grows enough to actually warrant one.
- Implementation docs and progress reports: `working-docs/implementation/` -- record of what WAS built: decisions made, why things are the way they are, paths considered and rejected in service of something that did get built, revisions. Not a user manual.
- Rejected paths: `working-docs/archive/` -- evaluations of something wholesale rejected.
- Test fixtures: `tests/fixtures/README.md`
- Private alpha, one developer. No backward compat needed yet.
- `working-docs/` is internal notes only -- content can change without notice. The user-facing website (`docs/`) must never link into it. Reference a PR or issue number instead.
- **Global file size**: soft limit ~400-500 lines, hard limit ~800 lines (~30KB). This applies to ALL files (source code, tests, documentation). Split before crossing it.
- **Naming and grouping**: kebab-case, topic-first filenames. If a topic outgrows 3+ closely related files, group them in a same-named subfolder.
- **Cross-linking**: every split or grouped file gets a "See also" pointer near the top.
- Every commit need a sign-off line (DCO) in the commit message.
- **CHANGELOG entries**: concise, to the point. No background/rationale -- link the PR for that. Target ~160 chars per bullet; exception for a genuinely complex PR. Merge related PRs into one entry (`[#1], [#2]`); sort entries per section by lowest PR number; skip docs/version-bump/CI-only noise. New entries go in `CHANGELOG.md`; `CHANGELOG-archive.md` (pre-0.19.0) is frozen.

### SBOM output

- Deterministic: SBOMs must be bit-for-bit identical across builds when input/environment unchanged.
- Idempotency: No non-deterministic data (timestamps, random UUIDs).
- Schema compliance: Validate every SBOM against primary spec (CycloneDX/SPDX) and serialization format before finalization.

### Metadata sources

- The Hatchling build hook (`pitloom.plugins.hatch`) reads project metadata from `self.metadata` via `pitloom.extract.hatchling.metadata_from_hatchling()`.
- The CLI (`pitloom.__main__`) and `generate_project_sbom()`'s default parsing path both resolve metadata via `pitloom.extract.project.read_project()`.
- Both paths converge on `pitloom.assemble.spdx3.document.build()`.
- **`physical_path` vs `distribution_path`**: on-disk project-root-relative path vs in-package/built path -- diverge for any `src/`-layout project. `software_File.name` in the SPDX graph always uses `distribution_path`. Any file-lookup/registry code keyed by path must check both, not just `physical_path`. A second hazard, distinct from the `src/`-layout divergence: for a `--allow-build` build-and-read discovered file, `physical_path` is an *absolute* path into a temporary extraction directory, not project-relative at all (see `ProjectFile.physical_path`'s own docstring in `core/project.py`). This recurred three times across independent consumers before being consolidated (PR #215) into one shared helper, `pitloom.core.project.project_relative_or_fallback(physical_path, fallback)` -- any new consumer that joins `physical_path` onto `project_dir`, uses it as a registry-lookup key, or bakes it into a determinism-sensitive string should call this helper instead of writing a new inline `Path(...).is_absolute()` check by hand.
- **Stage-scoped helpers must take an explicit stage flag**: a helper shared by both a source-stage caller (e.g. `read_pyproject()`) and a build-stage caller (e.g. the Hatchling hook's metadata gap-fill) must not rely on call-site discipline to stay stage-appropriate -- thread an explicit parameter (`include_locked_dependencies=False`-style) through it. A source-stage-only artifact (e.g. `poetry.lock`) silently leaking into a build-stage helper because both callers happened to share one function is the same class of bug the `physical_path`/`distribution_path` split above warns about.

### Usage surfaces

Pitloom is invoked from several usage surfaces (CLI, the Hatchling build hook, the public library API, the GitHub Action, the AI skills in `skills/*/SKILL.md`, and the Claude Code plugin in `.claude-plugin/`), and the CLI itself branches into 10+ subcommands. A change that updates one surface/subcommand and not the others is easy to ship by accident, because each surface's own tests keep passing in isolation -- only a cross-surface check catches the gap. (E.g.: `--debug` was wired into the top-level parser but 7 of 10 subcommand generators each called `configure_logging()` again with no arguments, silently reverting to `INFO` -- every subcommand's *own* tests passed.) The skills/plugin surfaces have no test suite of their own -- a CLI flag rename, a changed output format, or a new required argument silently goes stale there unless it's checked by hand; when editing anything a `SKILL.md` documents invoking, grep `skills/` for the changed command/flag/output shape and update it in the same change.

- **Route a cross-cutting choice through one shared, explicit mechanism** that every surface already calls or reads, instead of updating each surface's call site by hand. E.g. `--debug` threads through the `PITLOOM_DEBUG` env var so every downstream no-argument `configure_logging()` call agrees, rather than requiring every subcommand generator to remember to pass `debug=True` itself.
- **A docstring or comment describing "how surface X does Y" is a claim, not a fact.** Verify it against that surface's actual entry-point code (`__main__.main()`, `plugins/hatch.py`, the public library-API functions) before trusting or writing it -- a stale claim invites the exact regression it was meant to prevent, the moment someone trusts it instead of rereading the code.
- **A pattern hand-copied across 3+ call sites drifts.** When the same kind of message/check/value is written at several call sites (e.g. a `WARNING:` naming which SBOM field a failure skips), factor the shared shape into one helper/constant instead of retyping it per site -- otherwise wording or behavior silently diverges between sites with no single place to notice or fix it.
- **A test asserting on one surface doesn't cover the others.** When behavior must hold identically across surfaces (CLI vs library API vs Hatchling hook vs GitHub Action) or across every subcommand, add a regression test that exercises each surface/subcommand it's meant to hold for -- not just whichever one was easiest to reach from a test.
- **A skill is discovered through its frontmatter `description` only.** A body section documenting a command does not make it triggerable, and the skills have no tests. When a CLI command/flag is added or renamed, enumerate `add_parser(` subcommands against every `skills/*/SKILL.md` description; keep Pitloom's *verify* (structural) vs *validate* (schema/SHACL) distinction explicit, since users treat them as synonyms; give combined asks ("generate SBOM meeting CISA") an explicit hand-off in both skills; and give every "ask a follow-up" step a non-interactive fallback. Audit method, decisions and the deferred gaps: [skills-trigger-coverage.md](working-docs/implementation/skills-trigger-coverage.md).

## Design principles

- **Honor user intent over silent fallbacks**: Do not implement implicit fallbacks that contradict the user's explicit instructions.
- **No silent deviations**: Always emit a clear `WARNING:` log or stderr message explaining what decision was made and why if deviating from instruction.
- **Respect configuration hierarchy**: Always honor the configuration cascade (CLI flags > `pyproject.toml` > hardcoded defaults).
- **Resource efficiency**: Prevent excessive network access (use caching and route optimization). Prevent memory spikes by streaming data for large structures. Never load entire files (like ML models or archives) into memory. Always use chunked reads (`read(8192)`), memory mapping, or native lazy header extraction (e.g., `np.lib.format` for NumPy, stream loading for fickling/pickle) to extract metadata.
- **Explicit pin beats local environment**: when a dependency's version is explicitly pinned by its own data source (a lock file, an exact `==`/`===` in the spec), that pin is always authoritative -- never silently overridden by introspecting Pitloom's own execution environment, which has no relationship to the target project's environment. Environment introspection is a fallback signal only for the unpinned case.
- **Absent source data is not an error; a genuine read/access failure is.** Every extractor and metadata source (AI model format readers, project metadata parsers, lock-file readers, Hugging Face Hub / network fetches, etc.) must degrade gracefully -- a field the source simply doesn't carry stays `None`/empty/absent, silently, with no `WARNING:`/`ERROR:` and no raised exception; that's not a "no silent deviations" violation, since nothing was deviated from -- the source never claimed to carry it. This is already the convention every AI model extractor follows (`read_numpy()`'s docstring enumerates which fields stay `None`; PT2/GGUF/Safetensors do the same for their own always-absent fields) -- treat it as a general rule for any current or future extraction source, not a per-format decision to re-derive each time. Reserve `WARNING:`/`ERROR:` and raised exceptions for genuine disruptions: file corruption, an unreadable/truncated archive, a network error or timeout fetching from a remote source, a parse failure on data the format's own marker already confirmed should be well-formed. The dividing line is "did the source have an opinion and fail to deliver it" (real failure, log/raise) vs. "the source never had this data to begin with" (normal absence, stay quiet).

## Code health and continuous refactoring

- **The Boy Scout Rule**: Always leave the codebase cleaner than you found it. Refactor proactively during small changes.
- **Prevent Monoliths**: Never let a single file (like `parser.py` or `__main__.py`) become a dumping ground. Extract cohesive pieces into dedicated modules or subpackages early.
- **Consolidate Patterns**: Extract duplicated logic into shared utilities, constants files, or decorators immediately. Don't copy-paste code.
- **Reuse/dedup is a defensiveness strategy, not just an efficiency one**: with this many usage surfaces, backends, and file formats (see "Usage surfaces" below), two independent implementations of the same operation (a hash, a type check, a message string, a cascade rule) don't just cost extra lines -- they're two places that can silently disagree the next time either one is touched. Reuse a shared helper even when the duplicate is small/cheap and the duplication itself wastes nothing measurable; the point is to make drift structurally impossible, not to save a few lines.
- **Enforce File Size Limits**: Strictly obey the ~400-500 lines soft limit. Split files *before* they become a problem.

## Recurring bug patterns

General-purpose failure modes that have recurred across more than one
subsystem -- worth checking for by name in any code that resembles the
shape described, not just the module where each was first found. Full
detail (war stories, PR references, exact code shapes) lives in
[working-docs/implementation/recurring-bug-patterns.md](working-docs/implementation/recurring-bug-patterns.md)
(data and semantics) and
[recurring-bug-patterns-platform.md](working-docs/implementation/recurring-bug-patterns-platform.md)
(platform, concurrency, test harness, CI) -- read them before extending
or citing any of these one-liners.

- **`None` vs `[]`/`{}` (empty-but-present) is a distinct signal, not two
  spellings of the same thing.** `None`/absent means "this source doesn't
  apply, try the next one"; an empty-but-real container means "authoritative,
  zero results, stop looking." Recurs as: truthiness checks colliding "any
  result at all" with "was populated"; `dict.get(key, [])` conflating
  "legitimately absent" with "present but empty"; provenance dicts gated on
  resolved-value truthiness instead of raw-source-key presence (missed this
  way in 5 separate `ProjectMetadata` producers in one PR); the presence
  signal getting lost across a merge/inheritance boundary
  (`merge_project_metadata()`, `configparser`'s `[DEFAULT]` section); the
  same tri-state rule applying to scalars that can legitimately be `None`,
  not just containers; a fix applied to one field in a same-shaped set
  missing its siblings (`requires_python`/`license_name`/`version` in
  `extract/project/installed.py`).
- **Compare domain identifiers the way the ecosystem/spec does, not as raw
  strings.** PEP 503 name canonicalization, PEP 440 version equality (never
  SemVer -- `"1.0"` == `"1.0.0"`, not a compatibility range) apply both to
  equality checks in prose/docstrings and to conflict detection across a
  lock file's duplicate-name entries.
- **A placeholder value (`UNKNOWN`, `N/A`) is not a claim: keep it weak in a
  cascade.** Skip it while a later source may know better, remember the
  first, emit it (with that source's provenance) only if nothing better
  turns up; a real "none" ends the cascade, absent stays absent, and the held
  state is per item, never shared across a call's items (PR #276,
  [recurring-bug-patterns.md](working-docs/implementation/recurring-bug-patterns.md)).
- **A private third-party API (`obj._attr`) owes no structural guarantee
  beyond what it returns today** (e.g. `packaging.markers.Marker()._markers`
  doesn't pre-group same-precedence boolean terms) -- verify its shape
  interactively, prefer the library's own public algorithm.
- **Warning/error/log wording drifts across sibling modules doing the same
  check** -- factor the shared message into one helper, check siblings when
  adding a check to one.
- **A decode/parse helper catching only the format-specific exception
  (`TOMLDecodeError`, `json.JSONDecodeError`) can still crash on a bare
  `UnicodeDecodeError`** from the underlying encoding layer.
- **A doc/docstring claim about "how this mechanism decides" must be
  re-verified against the actual code before being trusted or restated.**
- **Picking one candidate from an unordered collection needs an explicit,
  stable tie-break for determinism** -- never rely on dict/set iteration
  order.
- **Reusing a helper outside the contract it was built for silently narrows
  behavior** -- check its docstring's stated preconditions, not just the
  return type, before reusing at a new call site.
- **A dedup/conflict-exclusion fix must cover every path that can produce
  the same identity**, not just the path the original bug was in --
  otherwise a passthrough bucket reintroduces the double-emission it fixed.
- **A test fixture/mock modeling an external system's shape must be
  broadened in lockstep with what the production code inspects**, or new
  branches go untested despite "the tests pass."
- **A source that can legitimately resolve to zero entries needs its own
  "is this genuinely a file of this format" check** in a priority cascade,
  or an empty-but-real result loses to an unrelated file of the same name.
- **A presence-only check misfires the moment one key in the set is
  genuinely boolean-valued instead of presence-implies-true** (e.g.
  `Pipfile.lock`'s `"editable": false`).
- **An opt-out flag that skips populating an accumulator breaks any
  pre-existing emptiness/exit check keyed off that list** -- re-derive the
  check from a proxy still unconditionally populated (PR #213).
- **Removing a read/computation to save cost can silently remove an
  error-surfacing side effect** (e.g. the `PermissionError` a full
  `read_bytes()` call incidentally raised) -- replace with a cheap probe
  that still triggers the same failure path (PR #213).
- **A guard added for one direction of a symmetric hazard often leaves the
  mirror direction open** (PR #215's write-then-write vs. write-then-read
  deadlock) -- enumerate every symmetric interaction, and for a
  concurrency claim, write a live timeout-bounded repro rather than
  reasoning statically.
- **A log message inside a function with multiple exit branches must
  describe what that branch actually did**, not the function's typical
  behavior (PR #215).
- **A shared helper's return type should match what every caller needs**,
  not force each to re-narrow it (`_resolve_bool_cascade()`, PR #215).
- **Reaching into another module's leading-underscore name from outside is
  a maintenance trap** even when it currently works -- promote a narrow
  public accessor instead (PR #215).
- **A circular-import claim needs a live interpreter test** (both import
  orders), not static reasoning about import order (PR #215).
- **A hardcoded POSIX-style path literal in a test silently stops
  exercising the "genuinely absolute" branch on Windows** --
  `PureWindowsPath.is_absolute()` requires a drive letter. Build the
  literal from real `tempfile.gettempdir()` at test-run time instead (PR
  #220, [windows-macos-ci.md](working-docs/implementation/windows-macos-ci.md)).
- **A bit-for-bit POSIX permission assertion is unwinnable on Windows** --
  NTFS only tracks a single read-only attribute. Spy on the `os.chmod`
  call's arguments (`Mock(wraps=os.chmod)`) instead of asserting `stat()`
  there; keep the real bit-for-bit assertion on POSIX (PR #220,
  [windows-macos-ci.md](working-docs/implementation/windows-macos-ci.md)).
- **A third-party library's undocumented breaking API change can be
  survived without an upper version pin** by detecting its actual
  runtime shape (e.g. `len(SomeClass.__parameters__)` for a changed
  generic arity) instead of hardcoding a version check, paired with a
  `TYPE_CHECKING` branch so static analysis still sees one concrete shape
  (PR #222, [hatchling-build-hook.md](working-docs/implementation/hatchling-build-hook.md)).
- **GitHub Actions substitutes `${{ }}` even inside a `run:` block's
  shell comments** -- a literal `${{ }}` example written to explain the
  syntax, if placed inside `run: |` rather than above it (e.g. in a
  step-level comment before `env:`), becomes a malformed expression and
  fails the whole workflow/action to load, reported at the block's line,
  not the actual one (PR #222,
  [ci-install-composite-action.md](working-docs/implementation/ci-install-composite-action.md)).
- **A version floor asserted in many places drifts, and no script checks
  it** (`check_version_consistency.py` covers only Pitloom's own version).
  Keep a dependency floor at its empirically verified technical minimum
  (raising it to "latest known-good" defeats a version-agnostic compat
  fix), and when changing it grep every spelling, classifying each hit as
  enforced requirement / illustrative example (both move) or historical
  narrative (stays factual) (PR #223,
  [recurring-bug-patterns.md](working-docs/implementation/recurring-bug-patterns.md)).
- **A manual repro that fails is first suspect for a wrong replication**
  (missing install steps, a raw `str` where the real call site passes a
  parsed object) -- replicate the real call shape before calling it an
  incompatibility (PR #223, same doc).
- **pip's `--no-build-isolation` is invocation-global, not per-package**
  -- combining a self-referential local-package install with unrelated
  `--group`/extras packages in one `pip install` call forces isolation
  off for all of them, a real risk for any of those packages that needs
  to build from source (PR #222,
  [ci-install-composite-action.md](working-docs/implementation/ci-install-composite-action.md)).
- **A test helper that normalises what it captures hides the bug class
  under test** -- `subprocess.run(text=True)` turns CRLF into LF, so no
  assertion could see a stray CR (PR #224). Decode bytes yourself, and
  mutation-test a shell/CI change (break key lines one at a time; a
  surviving mutant is a missing or blind test).
- **`Path.exists()`/`.is_file()` only swallow a specific errno set** --
  `PermissionError` propagates on 3.10-3.13 but returns `False` on 3.14
  (PR #217, #226). Use `os.path.isfile`/`isdir` for "never raises"; a
  missing-vs-unreadable classifier must OR errno and winerror checks; in
  a test, gate the raising assertion on the version and keep a
  version-independent probe (`read_bytes()`)
  ([recurring-bug-patterns-platform.md](working-docs/implementation/recurring-bug-patterns-platform.md)).
- **A textual "is this path under the project" check misses on a
  case-insensitive file system**: `os.getcwd()` after `chdir()` gives the
  on-disk case, `Path.resolve()` keeps the caller's (macOS). Fall back to
  a `(st_dev, st_ino)` ancestor match, treating `st_ino == 0` (FAT/exFAT)
  as no identity (PR #257,
  [recurring-bug-patterns-platform.md](working-docs/implementation/recurring-bug-patterns-platform.md)).
- **A `skipif` decorator's condition is evaluated at import time, on
  every platform.** `@pytest.mark.skipif(os.geteuid() != 0, ...)` raises
  `AttributeError` while *collecting* the module on Windows, so the whole
  file errors out and the skip never applies -- one red leg, everything
  else green. Compute one short-circuited module constant
  (`sys.platform != "win32" and os.geteuid() != 0`) and pass that; same
  trap for any POSIX-only name in a decorator argument, a default
  argument or a module-level `parametrize` list (PR #226).
- **A long `parametrize` value becomes the test id, which Windows rejects
  in `PYTEST_CURRENT_TEST` (32,767-char env cap)** -- give it short `ids=`;
  `tests/conftest.py` fails any id over 1,000 chars (PR #276, same doc).
- **A context manager whose `__exit__` can be interrupted must reset its
  shared state in `__enter__`** -- without taking its lock, installing a
  fresh container, detecting "my block ended" by object identity; an
  interrupt handler releases only its own resources (PR #226, same doc).
  Reproduce a concurrency claim, never reason it through.
- **Mutation testing lies in two ways**: an *equivalent* mutant (a
  rearrangement that changes no semantics) cannot be killed and proves
  nothing, so reinstate the exact pre-fix shape; and an assertion aimed
  at a lazily-installed side effect (signal handlers installed at first
  use) observes nothing and passes either way (PR #226).
- **A test that reaches the network through a subprocess or library
  (`spdx3-validate` downloads its schema on every run) bypasses the
  conftest socket block and fails on any flake.** Mark it `network` and
  route its result through `tests/_network.py`, so a network cause skips
  with the reason and any other failure still fails (PR #238,
  [recurring-bug-patterns-platform.md](working-docs/implementation/recurring-bug-patterns-platform.md)).
- **Monkeypatching a function on a shared stdlib module
  (`monkeypatch.setattr(mod.time, "sleep", ...)`) patches it for every
  thread in the process**, so a thread another test left running feeds
  the fake too -- green alone, red under xdist. Import the name into the
  module under test (`from time import sleep`) and patch that (PR #259,
  same doc).
- **A logging handler bound to `sys.stderr` during a test outlives the
  test's capture stream.** `configure_logging()` under `capsys`/`capfd`
  binds to pytest's capture file, closed at teardown; a later test on the
  same xdist worker that logs gets `--- Logging error ---` on stderr, so an
  "empty stderr" assertion fails by test order only (1 in 10 local runs,
  one CI leg). `tests/conftest.py` restores the `pitloom` logger's
  handlers and level after every test; any new process-global state a
  test can mutate needs the same treatment (PR #263, same doc).
- **`json.loads(bytes)` auto-strips a leading UTF-8 BOM; `json.loads(str)`
  after `.decode("utf-8")` raises on one instead.** Recurred twice,
  independently, in the same PR (#217) -- once fixed, then found again
  in a different file nobody thought to re-check. Prefer
  `json.loads(raw_bytes)` directly for any JSON read meant to match a
  binary-file-handle parse elsewhere.
- **`dict.get(key, default)` only guards the key's absence, not the key
  being present with the wrong type** -- `data.get("@graph", [])` still
  yields a non-list and crashes `len()` if `@graph` is present but not a
  list (PR #217). Add an explicit `isinstance` check on the value for
  any external/user-editable file.

## CLI output

Unix philosophy. Consistent, predictable, parseable.

- Default: line-delimited, one data point per line. A "data point" is one
  record/entity, not one field -- a record with several attributes (e.g.
  one configured fragment's path/role/required/exists/element-count/
  hash-status/modified-time) is still one data point, and its `KEY=VALUE`
  pairs belong together on that one line, space-separated (e.g. `PATH=...
  ROLE=... REQUIRED=... EXISTS=...`), not split one-field-per-line. Only
  split across lines when there's more than one record to list (one line
  per record, e.g. one line per configured fragment).
- Stdout is data only (`--help`/`--version` excepted): `KEY=VALUE` lines
  from `pitloom.cli.kv_output.print_kv()`, or the SBOM itself for `-o -`
  (`_sbom_io.write_stdout_lf()`); counts, summaries, hints and `-v` details
  are `INFO:` on stderr. A value that may hold a space goes last.
- Key-value: `KEY=VALUE` -- uppercase KEY, no spaces around `=`. Several
  `KEY=VALUE` pairs on the same line are fine when they describe the same
  data point (see above) -- e.g. `FORMAT=%s FILE=%s: ...` for a single
  per-model-file scanning warning, or `pitloom fragment list`'s one line
  per configured fragment.
- Three levels reach stderr, every line starting with exactly one:
  `ERROR: <short description>`, `WARNING: <short description>`,
  `INFO: <short description>`. Nothing else is grep-able output -- a
  message doesn't get a second competing tag, and isn't split across a
  tagged line and an untagged continuation line.
  - `ERROR:` -- via the CLI's own `print(..., file=sys.stderr)` calls
    (`cli_error_handler` in `cli/commands/utils.py` adds it
    automatically around any raised exception). Fatal to the current
    operation.
  - `WARNING:` -- a "no silent deviations" decision or a recovered,
    non-fatal problem. Internal `logging.warning()` calls get this
    prefix automatically.
  - `INFO:` -- a normal status update worth a human seeing (e.g. "SBOM
    generation skipped: hook disabled"), not an error or a deviation.
    Internal `logging.info()` calls get this prefix automatically.
  - `logging.debug()` stays a developer-only diagnostic -- never
    prefixed, never reaches stderr in a normal invocation.
  - All three are wired up once, identically, by
    `pitloom.logging_config.configure_logging()` -- every CLI command,
    the Hatchling build hook, and every public library-API entry point
    (`generate_project_sbom()`, etc.) call it first, so the same
    `log.warning(...)` call looks identical regardless of which one
    invoked Pitloom. A new entry point that skips this call is a bug,
    not a style choice.
- Within one subsystem, prefer a shared, literal sub-prefix so its
  messages are easy to compare/grep as a group (e.g. `ID registry: ...`
  for every `pitloom.id_registry`/`IdRegistry` warning, `FORMAT=%s
  FILE=%s: ...` for per-model-file scanning warnings) -- match an existing sibling
  message's wording before inventing a new phrasing for the same kind of
  event. Not a single global schema across unrelated subsystems: forcing
  one would make many messages read unnaturally for no parsing benefit
  beyond the `LEVEL:` tag itself, which is the one prefix every consumer
  (grep, `caplog`) actually keys on.
- Messages get trimmed to essentials.

## Python

- Min version: Python 3.10. No syntax/features unavailable before 3.10 unless via `__future__`.
- No `A | B` union syntax outside `TYPE_CHECKING` blocks below 3.10.
- Verify types with mypy (strict=true). Use pyright/pytype for second opinions.
- **Untyped third-party dependency**: before adding an `ignore_missing_imports`/`ignore-missing-imports` override (mypy `[[tool.mypy.overrides]]`, `[tool.pyrefly] ignore-missing-imports`, etc.), check PyPI for a legitimate, trusted `types-<package>` stub package (the typeshed-maintained ones, e.g. `types-PyYAML`, `types-setuptools`). Add it to the `typecheck` dependency group instead -- real stubs catch genuine type errors an `Any`-blanket override would hide, and (unlike a suppression) don't need re-verifying every time a type checker changes how it treats an unresolvable/stub-less import (e.g. pyrefly 1.2 vs 1.3 disagreeing on whether `ignore-missing-imports` still applies once a module is merely stub-incomplete rather than fully unresolvable). Only fall back to a suppression override when no such stub package exists.
- Fully qualified names in docstrings for non-stdlib types (e.g., `numpy.ndarray`).
- No `assert` in production -- tests only.
- All config in `pyproject.toml` where possible.
- No wildcard imports (e.g., `from module import *`). Always use explicit imports.
- **Import order**: Groups: stdlib -> third-party -> local, alphabetically within each. Don't reorder imports with comments explaining required order (circular import/init constraint). Use `ruff check --fix --select I` to automate this.
- Type completeness: All visible class vars, instance vars, methods, params, and return types must be annotated. Generic base classes must have type args specified. (Except simple literals, enum members, and standard dunders).

## Cross-platform compatibility

- Pitloom must work seamlessly across Windows, macOS, and Linux.
- Always use `pathlib.Path` for file resolution and manipulation.
- `/tmp/` and POSIX-directories are not exist on Windows.
- **Dry-run Windows when you cannot run it.** For every new test or
  assertion that touches a path, read it as Windows would and check: an
  expected path string with `/` (Windows shows `\`), `Path ==` between
  names differing only in case (equal on `WindowsPath`), a `skipif` or
  module constant naming a POSIX-only API, `..` collapsed by Win32 before
  the open, a symlink needing privilege. Emulate with `PureWindowsPath`/
  `ntpath` in a REPL. Ask the same of every review agent's brief: macOS
  green is not Windows green (PR #280: six tests expected `p/pyproject.toml`
  and failed only on the Windows CI leg).

## Linting and formatting

Run and fix all errors before committing. Our linters strictly enforce code style, formatting, unused imports, and complexity thresholds:

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

- pylint needs `tests/*/` as well as `tests/`: it does not descend from the
  `tests/` package into subfolders without `__init__.py`, so `pylint tests/`
  alone silently skips every test file in them. Pass directories, not single
  test files: a file argument loses its dotted name (false E0402).
- Avoid ambiguous variable name (E741).
- Complexity targets: Returns≤6, Args≤5, Locals≤15, Nesting≤5, Branches≤20, Statements≤80, McCabe≤10, Cognitive≤15.
  Enforced ceilings in `pyproject.toml`/`.flake8` are currently interim
  ratchets above some of these targets (`max-args=6`, `max-locals=18`,
  McCabe=35, Cognitive=60) -- see
  `working-docs/design/complexity-and-file-size-roadmap.md` for the
  backlog that has to shrink before each ceiling can drop to its target.
- Enforce max line length 88 (prefer 80).
- Sort all imports alphabetically and logically (enforced by `ruff` / `isort`).
- Remove unused imports and trailing whitespace.
- Restrict non-ASCII characters to human language messages and diagrams.
- Place pylint suppressions on the preceding line as `# pylint: disable-next=<msg>` rather than inline, to save line length. A bare `# pylint: disable=` line before an `except` clause stopped suppressing it in pylint 4.1.

## File headers

All source files must have SPDX tags in this order (alphabetical):

```text
SPDX-FileCopyrightText: <year> <name>
SPDX-FileType: SOURCE                # or DOCUMENTATION
SPDX-License-Identifier: Apache-2.0  # or CC0-1.0 for docs
```

For `working-docs/` standalone docs, include `Created` and `Last-Modified` (`YYYY-MM-DD`).
`SKILL.md` files are the exception: use `#` YAML comments for these headers at the top of the block.

## Testing

- **Bug fixes and regressions**: Always add a regression test that fails without the fix and passes with it.
- **Guard against vacuous passes**: for a "changed input -> unchanged output" test (e.g. stability/idempotency), assert the input actually changed, not just that the output didn't -- a misplaced setup edit can make the test pass without exercising anything.
- Use pytest patterns. Use `spec`/`autospec` when mocking. Use `@pytest.mark.parametrize`.
- **Keep tests compact**: same coverage, same adversarial nature, no redundant tests. Before adding a test, check whether an existing one already exercises the branch; fold near-duplicates into one `@pytest.mark.parametrize` (one case per boundary) and share fixtures/helpers. Never drop a case that is the only one killing a mutant or covering a bug class.
- **Test suite structure**: Adhere to the same file size limits as source code.
- **Naming**: `test_<area>.py`, 1:1 with the source module. Disambiguate when two source packages could produce the same tail.
- **Grouping**: Group tests in same-named subfolders under `tests/` mirroring `src/pitloom/<package>/` when a source package's tests grow to 3+ related files. No `__init__.py` needed in test folders.
- **No non-deterministic assertions**: Never assert against real wall-clock time (`datetime.now()`, `time.time()`, `date.today()`), unseeded random/UUID values, or set/dict iteration order. Use a fixed/frozen timestamp, mock the random source, or sort before comparing. Elapsed-duration checks (e.g. concurrency regression tests bounding `time.monotonic()` deltas) are a different category and fine with a generous bound.
- **Don't couple tests to undocumented internals**: A `pytest.raises(match=...)` or log-message assertion should target wording the source documents as intentional (a deliberate user-facing error/warning, a documented format's field/member name), not an incidental internal string that could change during a harmless refactor. Prefer a short, stable substring over the full message. SPDX3 field/type assertions must come from the spec (`spdx_python_model.bindings`), not an undocumented Pitloom-internal layout.
- **Runtime warnings are test failures**: `filterwarnings = ["error"]` (OpenSSF `warnings_strict`) turns every `DeprecationWarning`/`ResourceWarning`/pytest-internal warning into a hard failure -- there is no silent "printed but ignored" path. If a genuinely unavoidable third-party warning appears, add a specific, narrowly-scoped `ignore::` filter entry (module/category-qualified), never a blanket one, and say why in a comment next to it.
- **Drift-guard test for two independent implementations of the same
  operation**: when a public-API path and an internal path both do
  "find then parse" (or similar) over separate code, don't refactor one
  into the other just to kill the duplication -- add a test asserting
  both resolve to the exact same result for one shared fixture. Cheap,
  catches one side changing without the other, no risk to working code.
- **Adversarial edge-case tests pay off most on tri-state (None/empty/
  absent) and cascade/tie-break logic**: per new field or merge path,
  one test per boundary -- declared-but-empty vs. absent, spec-
  equivalent-but-differently-formatted values (not a real conflict),
  multiple candidates needing a deterministic tie-break, malformed/
  truncated input. Catches the bug classes under "Recurring bug
  patterns" above before real-world input does.
- **Test tiers -- run less while editing, everything before merge.**
  - Tier 1, while editing: the touched or affected tests only
    (`pytest tests/<area> -k ...`, `--lf`), ruff, mypy.
  - Tier 2, each review/fix round: the full suite (xdist), every CI linter
    (see "Linting and formatting", pyrefly included), each new regression
    test failing on the base tree, branch coverage of the changed files,
    and the manual CLI checks for the touched area (below).
  - Tier 3, once per PR before merge: mutation testing (each mutant runs
    only its module's test files), the full manual CLI checks (before
    handoff, and again after merging main), the
    parity/determinism harness, the Windows dry-run, one fresh-context
    sweep, a fresh-eyes read of any changed `SKILL.md`.

### Manual CLI integration checks (post-pytest, pre-commit)

pytest exercises functions in-process only -- it misses the `loom` entry
point, argv parsing, real filesystem/archive I/O and drift between the
CLI/library-API/Hatchling-hook/skills surfaces (see "Usage surfaces").
`.venv/bin/python scripts/manual_cli_checks` runs, in a scratch dir, the
numbered checks (determinism, surface parity, embed/verify/validate round
trips, registry, fragment merge, offline, `--allow-build`, refused wheels,
AI model outcomes), the declared CLI matrix (subcommand x option x
environment variable) and order-dependent command sequences; `--only`
takes ids and globs, `--network` adds the network ones. They complement
pytest: real stderr `WARNING:` wording and count, `--debug` threading,
CLI/library parity. When to run:

- docs-, tests- or `working-docs/`-only change: skip;
- each round touching `assemble/`, `extract/`, `core/`, `embed.py`,
  `__main__.py` or `plugins/hatch.py`: the checks for that area, by
  `--only` (area map and full commands in
  [manual-cli-checks.md](working-docs/implementation/manual-cli-checks.md#when-to-run));
- once before handoff, and again after merging main into the branch: the
  full run (`-j 8`).

A new CLI option or subcommand must get an entry in
`scripts/manual_cli_checks/_matrix_plan.py` -- `M/completeness` fails in
CI until it does.

## Shell scripts

- Account for GNU/BSD/macOS/Unix tool differences.
- Defensive variable expansion; quote paths and variables.
- **Composite-action scripts** (`scripts/action/`, tested by `tests/scripts/action/` against stub programs): CI lints only `examples/ src/ tests/`, so run the linters, `shellcheck -x` and `actionlint` on `scripts/` by hand. Notes: [github-action.md](working-docs/implementation/github-action.md).
- **Windows Git Bash / macOS bash 3.2**: native Windows Python ends lines with CR that `$(...)` keeps; Git Bash has no `/dev/stderr`; bash 3.2 has no `readarray` and is quadratic on `${x//pat/}`. Normalise `GITHUB_ACTION_PATH` backslashes; keep `*.sh` and `action.yml` LF (`.gitattributes`).
- **Never let a step log tool output raw**: a `::` line is run as a workflow command. Fence the echo with `::stop-commands::<random token>`; the runner does not order stdout against stderr, so fence, echo and annotations must share one stream.

## Naming

- **Python module leading underscore**: a module gets a leading underscore (e.g. `_common.py`) when nothing outside its own package directory imports it. No prefix (e.g. `wheel.py`) when something outside the package imports it. Check actual importers (`grep`) or public API markers before renaming.
- Consult Schema.org, NIEM Model, FIBO, and OBO Foundry for ontology naming.

## SPDX / Output Specifics

- SPDX 3 JSON: follow canonical serialization and RFC 8785.
- JSON-LD: follow RDF canonicalization.
- Dates: ISO 8601. Timezone: UTC+0.
- **`spdx3` vocabulary terms are plain `str`, not enum instances**: `spdx3.RelationshipType`/`RelationshipCompleteness`/etc. members (e.g. `spdx3.RelationshipCompleteness.complete`) are `str`-valued NamedIndividual IRIs, not instances of an enum type. Type a parameter accepting one as `str`, never as the class name -- `spdx3.RelationshipCompleteness | None` fails mypy since the actual runtime value is `str`.

## Writing style

- British English for docs, comments, text. American English for code only.
- IETF verbal forms (RFC 2119/8174) for internet/web/semantic web projects; ISO verbal forms for SPDX docs.
- Code comments must direct, concise and about current implementation. Do not discuss history. Legimate current behavior vs alternative design is ok.
- **PR text defaults** (when a request for a PR title/summary/description gives no style or length; an explicit per-request limit overrides): title <= 60 chars, no markdown; summary <= 280 chars, concise bullets, markdown allowed; description <= 600 chars, concise, structured, with a short rationale/why. Count characters before presenting. Give each in its own fenced code block, copy-paste ready.

## Boundaries

**Ask before doing:**

- Large cross-package refactors.
- New dependencies with broad impact.
- Destructive data or migration changes.

**Never:**

- Edit generated files by hand when generation workflow exists.
- Use destructive git operations unless explicitly requested.
- Auto-commit changes; leave all changes uncommitted in the working directory for the user to review and commit manually, unless they explicitly request otherwise.
