# Agent instructions

## Project context

- SBOM generator targeting Python/Hatchling ecosystem, outputting SPDX 3 JSON-LD.
- Design docs: `working-docs/design/` -- future work, plans, sketches; may be discarded, not yet built.
- Implementation docs and progress reports: `working-docs/implementation/` -- record of what WAS built: decisions made, why things are the way they are, paths considered and rejected in service of something that did get built, revisions. Not a user manual.
- Rejected paths: `working-docs/archive/` -- evaluations of something wholesale rejected.
- Test fixtures: `tests/fixtures/README.md`
- Private alpha, one developer. No backward compat needed yet.
- `working-docs/` is internal notes only -- content can change without notice. The user-facing website (`docs/`) must never link into it. Reference a PR or issue number instead.
- **Global file size**: soft limit ~400-500 lines, hard limit ~800 lines (~30KB). This applies to ALL files (source code, tests, documentation). Split before crossing it.
- **Naming and grouping**: kebab-case, topic-first filenames. If a topic outgrows 3+ closely related files, group them in a same-named subfolder.
- **Cross-linking**: every split or grouped file gets a "See also" pointer near the top.
- Every commit need a sign-off line (DCO) in the commit message.
- **CHANGELOG entries**: concise, to the point. No background/rationale -- link the PR for that. Target ~160 chars per bullet; exception for a genuinely complex PR.

### SBOM output

- Deterministic: SBOMs must be bit-for-bit identical across builds when input/environment unchanged.
- Idempotency: No non-deterministic data (timestamps, random UUIDs).
- Schema compliance: Validate every SBOM against primary spec (CycloneDX/SPDX) and serialization format before finalization.

### Metadata sources

- The Hatchling build hook (`pitloom.plugins.hatch`) reads project metadata from `self.metadata` via `pitloom.extract.hatchling.metadata_from_hatchling()`.
- The CLI (`pitloom.__main__`) and `generate_project_sbom()`'s default parsing path both resolve metadata via `pitloom.extract.project.read_project()`.
- Both paths converge on `pitloom.assemble.spdx3.document.build()`.
- **`physical_path` vs `distribution_path`**: on-disk project-root-relative path vs in-package/built path -- diverge for any `src/`-layout project. `software_File.name` in the SPDX graph always uses `distribution_path`. Any file-lookup/registry code keyed by path must check both, not just `physical_path`.
- **Stage-scoped helpers must take an explicit stage flag**: a helper shared by both a source-stage caller (e.g. `read_pyproject()`) and a build-stage caller (e.g. the Hatchling hook's metadata gap-fill) must not rely on call-site discipline to stay stage-appropriate -- thread an explicit parameter (`include_locked_dependencies=False`-style) through it. A source-stage-only artifact (e.g. `poetry.lock`) silently leaking into a build-stage helper because both callers happened to share one function is the same class of bug the `physical_path`/`distribution_path` split above warns about.

## Design principles

- **Honor user intent over silent fallbacks**: Do not implement implicit fallbacks that contradict the user's explicit instructions.
- **No silent deviations**: Always emit a clear `WARNING:` log or stderr message explaining what decision was made and why if deviating from instruction.
- **Respect configuration hierarchy**: Always honor the configuration cascade (CLI flags > `pyproject.toml` > hardcoded defaults).
- **Resource efficiency**: Prevent excessive network access (use caching and route optimization). Prevent memory spikes by streaming data for large structures. Never load entire files (like ML models or archives) into memory. Always use chunked reads (`read(8192)`), memory mapping, or native lazy header extraction (e.g., `np.lib.format` for NumPy, stream loading for fickling/pickle) to extract metadata.
- **Explicit pin beats local environment**: when a dependency's version is explicitly pinned by its own data source (a lock file, an exact `==`/`===` in the spec), that pin is always authoritative -- never silently overridden by introspecting Pitloom's own execution environment, which has no relationship to the target project's environment. Environment introspection is a fallback signal only for the unpinned case.

## Code health and continuous refactoring

- **The Boy Scout Rule**: Always leave the codebase cleaner than you found it. Refactor proactively during small changes.
- **Prevent Monoliths**: Never let a single file (like `parser.py` or `__main__.py`) become a dumping ground. Extract cohesive pieces into dedicated modules or subpackages early.
- **Consolidate Patterns**: Extract duplicated logic into shared utilities, constants files, or decorators immediately. Don't copy-paste code.
- **Enforce File Size Limits**: Strictly obey the ~400-500 lines soft limit. Split files *before* they become a problem.

## CLI output

Unix philosophy. Consistent, predictable, parseable.

- Default: line-delimited, one data point per line.
- Key-value: `KEY=VALUE` -- uppercase KEY, no spaces around `=`.
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
  messages are easy to compare/grep as a group (e.g. `Registry: ...` for
  every `pitloom.ids`/`IdRegistry` warning, `FORMAT=%s FILE=%s: ...` for
  per-model-file scanning warnings) -- match an existing sibling
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

## Linting and formatting

Run and fix all errors before committing. Our linters strictly enforce code style, formatting, unused imports, and complexity thresholds:

```shell
ruff format
ruff check --fix
pylint
mypy
pyright
pyrefly check
bandit -r
flake8
```

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
- Place `# pylint: disable=` comments on the preceding line rather than inline to save line length.

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
- **Test suite structure**: Adhere to the same file size limits as source code.
- **Naming**: `test_<area>.py`, 1:1 with the source module. Disambiguate when two source packages could produce the same tail.
- **Grouping**: Group tests in same-named subfolders under `tests/` mirroring `src/pitloom/<package>/` when a source package's tests grow to 3+ related files. No `__init__.py` needed in test folders.
- **No non-deterministic assertions**: Never assert against real wall-clock time (`datetime.now()`, `time.time()`, `date.today()`), unseeded random/UUID values, or set/dict iteration order. Use a fixed/frozen timestamp, mock the random source, or sort before comparing. Elapsed-duration checks (e.g. concurrency regression tests bounding `time.monotonic()` deltas) are a different category and fine with a generous bound.
- **Don't couple tests to undocumented internals**: A `pytest.raises(match=...)` or log-message assertion should target wording the source documents as intentional (a deliberate user-facing error/warning, a documented format's field/member name), not an incidental internal string that could change during a harmless refactor. Prefer a short, stable substring over the full message. SPDX3 field/type assertions must come from the spec (`spdx_python_model.bindings`), not an undocumented Pitloom-internal layout.
- **Runtime warnings are test failures**: `filterwarnings = ["error"]` (OpenSSF `warnings_strict`) turns every `DeprecationWarning`/`ResourceWarning`/pytest-internal warning into a hard failure -- there is no silent "printed but ignored" path. If a genuinely unavoidable third-party warning appears, add a specific, narrowly-scoped `ignore::` filter entry (module/category-qualified), never a blanket one, and say why in a comment next to it.

## Shell scripts

- Account for GNU/BSD/macOS/Unix tool differences.
- Defensive variable expansion; quote paths and variables.

## Naming

- **Python module leading underscore**: a module gets a leading underscore (e.g. `_gguf.py`) when nothing outside its own package directory imports it. No prefix (e.g. `wheel.py`) when something outside the package imports it. Check actual importers (`grep`) or public API markers before renaming.
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

## Boundaries

**Ask before doing:**

- Large cross-package refactors.
- New dependencies with broad impact.
- Destructive data or migration changes.

**Never:**

- Edit generated files by hand when generation workflow exists.
- Use destructive git operations unless explicitly requested.
- Auto-commit changes; leave all changes uncommitted in the working directory for the user to review and commit manually, unless they explicitly request otherwise.
