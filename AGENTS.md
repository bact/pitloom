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

### SBOM output

- Deterministic: SBOMs must be bit-for-bit identical across builds when input/environment unchanged.
- Idempotency: No non-deterministic data (timestamps, random UUIDs).
- Schema compliance: Validate every SBOM against primary spec (CycloneDX/SPDX) and serialization format before finalization.

### Metadata sources

- The Hatchling build hook (`pitloom.plugins.hatch`) reads project metadata from `self.metadata` via `pitloom.extract.hatchling.metadata_from_hatchling()`.
- The CLI (`pitloom.__main__`) and `generate_project_sbom()`'s default parsing path both resolve metadata via `pitloom.extract.project.read_project()`.
- Both paths converge on `pitloom.assemble.spdx3.document.build()`.

## Design principles

- **Honor user intent over silent fallbacks**: Do not implement implicit fallbacks that contradict the user's explicit instructions.
- **No silent deviations**: Always emit a clear `WARNING:` log or stderr message explaining what decision was made and why if deviating from instruction.
- **Respect configuration hierarchy**: Always honor the configuration cascade (CLI flags > `pyproject.toml` > hardcoded defaults).
- **Resource efficiency**: Prevent excessive network access (use caching and route optimization). Prevent memory spikes by streaming data for large structures. Never load entire files (like ML models or archives) into memory. Always use chunked reads (`read(8192)`), memory mapping, or native lazy header extraction (e.g., `np.lib.format` for NumPy, stream loading for fickling/pickle) to extract metadata.

## Code health and continuous refactoring

- **The Boy Scout Rule**: Always leave the codebase cleaner than you found it. Refactor proactively during small changes.
- **Prevent Monoliths**: Never let a single file (like `parser.py` or `__main__.py`) become a dumping ground. Extract cohesive pieces into dedicated modules or subpackages early.
- **Consolidate Patterns**: Extract duplicated logic into shared utilities, constants files, or decorators immediately. Don't copy-paste code.
- **Enforce File Size Limits**: Strictly obey the ~400-500 lines soft limit. Split files *before* they become a problem.

## CLI output

Unix philosophy. Consistent, predictable, parseable.

- Default: line-delimited, one data point per line.
- Key-value: `KEY=VALUE` -- uppercase KEY, no spaces around `=`.
- Errors: `ERROR: <short description>` to stderr.
- Warnings: `WARNING: <short description>` to stderr. Internal `logging.warning()` calls get this prefix automatically.
- Messages get trimmed to essentials and share a literal, grep-able prefix.

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
- Use pytest patterns. Use `spec`/`autospec` when mocking. Use `@pytest.mark.parametrize`.
- **Test suite structure**: Adhere to the same file size limits as source code.
- **Naming**: `test_<area>.py`, 1:1 with the source module. Disambiguate when two source packages could produce the same tail.
- **Grouping**: Group tests in same-named subfolders under `tests/` mirroring `src/pitloom/<package>/` when a source package's tests grow to 3+ related files. No `__init__.py` needed in test folders.
- **No non-deterministic assertions**: Never assert against real wall-clock time (`datetime.now()`, `time.time()`, `date.today()`), unseeded random/UUID values, or set/dict iteration order. Use a fixed/frozen timestamp, mock the random source, or sort before comparing. Elapsed-duration checks (e.g. concurrency regression tests bounding `time.monotonic()` deltas) are a different category and fine with a generous bound.
- **Don't couple tests to undocumented internals**: A `pytest.raises(match=...)` or log-message assertion should target wording the source documents as intentional (a deliberate user-facing error/warning, a documented format's field/member name), not an incidental internal string that could change during a harmless refactor. Prefer a short, stable substring over the full message. SPDX3 field/type assertions must come from the spec (`spdx_python_model.bindings`), not an undocumented Pitloom-internal layout.

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
