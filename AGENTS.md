# Agent instructions

## Project context

- SBOM generator targeting Python/Hatchling ecosystem, outputting SPDX 3 JSON-LD.
- Design docs: `working-docs/design/` -- future work, plans, sketches;
  may be discarded, not yet built.
- Implementation docs and progress reports: `working-docs/implementation/`
  -- record of what WAS built: decisions made, why things are the way
  they are, paths considered and rejected in service of something that
  did get built, revisions. Not a user manual.
- Rejected paths: `working-docs/archive/` -- evaluations of something
  wholesale rejected, with nothing built from them (kept separate from
  `implementation/` so they aren't mistaken for how something works).
- Test fixtures: `tests/fixtures/README.md`
- Private alpha, one developer. No backward compat needed yet.
- `working-docs/` is internal notes only -- content can change without
  notice. The user-facing website (`docs/`) must never link into it, in
  any form (relative path, absolute GitHub URL, etc.). Reference a PR or
  issue number instead if a public pointer is needed.
- **`working-docs/` file size**: soft limit ~400-500 lines, hard limit
  ~800 lines (~30KB). Split before crossing it -- one topic per file, not
  one file per topic-and-everything-about-it. A doc mixing what's shipped
  and what's still planned is a split trigger on its own (shipped ->
  `implementation/`, planned -> `design/`), independent of length.
- **Naming and grouping**: kebab-case, topic-first filenames (e.g.
  `hatchling-build-hook.md`). A `design/`+`implementation/` pair for the
  same topic shares one base filename across the two directories, so the
  pair is easy to find by name alone. If a topic outgrows that pair (3+
  closely related files -- shared vocabulary, shared code-review
  taxonomy, etc.), group them in a same-named subfolder (e.g.
  `implementation/provenance/`) rather than growing filenames into
  `topic-facet-subfacet.md` chains.
- **Cross-linking**: every split or grouped file gets a "See also"
  pointer near the top (before the main content) to its sibling file(s).
  This is so a reader -- human or an AI agent that landed on one file via
  grep/search -- finds the rest of the cluster in one hop, without
  needing to open every file in the group to discover its shape. Smaller,
  well-named, cross-linked files also mean an agent loads only the file
  actually relevant to a question instead of scanning one large monolith.

### SBOM output

- Deterministic: SBOMs must be bit-for-bit identical across builds when input/environment unchanged.
- Idempotency: No non-deterministic data (timestamps, random UUIDs).
- Schema compliance: Validate every SBOM against primary spec (CycloneDX/SPDX) and serialization format before finalization. Automated validation mandatory.

### Metadata sources

- The Hatchling build hook (`pitloom.plugins.hatch`) reads project metadata from `self.metadata` (Hatchling's own resolved `hatchling.metadata.core.ProjectMetadata`), via `pitloom.extract.hatchling.metadata_from_hatchling()`, so dynamic version/dependency/license sources resolved by Hatchling plugins are reflected correctly.
- The CLI (`pitloom.__main__`) and `pitloom.assemble.generate_project_sbom()`'s default parsing path both resolve metadata/config from the project directory via the shared `pitloom.extract.project.read_project()` helper (`pyproject.toml` -> `setup.cfg`/`setup.py` -> error), so each parses its inputs once. The CLI passes its already-parsed `project_metadata`/`pitloom_config` into `generate_project_sbom()` so it never re-parses.
- Both paths converge on the same `pitloom.assemble.spdx3.document.build()` assembly layer, so the emitted SBOM shape (file hashes, PURLs, licensing, etc.) is identical regardless of metadata source.

## Design principles

- **Honor user intent over silent fallbacks**: Do not implement implicit fallbacks that contradict the user's explicit instructions or command semantics (e.g. if the user specifies a standalone mode, do not silently parse a project directory).
- **No silent deviations**: If Pitloom must deviate from the user's instruction to ensure correctness or safety, it must never do so silently. Always emit a clear `WARNING:` log or stderr message explaining what decision was made and why.
- **Respect configuration hierarchy**: Always honor the configuration cascade (CLI flags > `pyproject.toml` > hardcoded defaults). Ensure configuration intent is properly propagated through the assembly layer.
- **Resource efficiency**: Be mindful of performance and memory. Prevent excessive network access by combining API requests where possible, using caching (`lru_cache`), and leveraging route optimization (`HEAD` before `GET` to avoid rate limits). Prevent memory spikes by streaming data instead of loading large structures (like NumPy arrays, PyTorch weights, or big archives) entirely into memory.

## CLI output

Unix philosophy. Consistent, predictable, parseable.

- Default: line-delimited, one data point per line.
- Field separator: space or tab (consistent).
- Key-value: `KEY=VALUE` -- uppercase KEY, no spaces around `=`.
- Errors: `ERROR: <short description>` to stderr.
- Warnings: `WARNING: <short description>` to stderr -- same rule, one
  level down. Internal `logging.warning()` calls (library code under
  `src/pitloom/`, not the CLI's own top-level `print()`s) get this
  prefix automatically: the CLI entry point (`pitloom.__main__.main()`)
  attaches a `%(levelname)s: %(message)s` formatter to the `pitloom`
  logger, so don't hand-prefix individual `log.warning(...)` call sites.
- Must work with `awk`, `wc`, `xargs`, similar Unix tools.
- Messages get trimmed to essentials and share a literal, grep-able prefix.
- JSON/CSV/file output supported as options.

## Code style

- Code comments must direct, concise and about current implementation.
  Do not discuss history. Legimate current behavior vs alternative design is ok.

## Python

- Min version: Python 3.10. No syntax/features unavailable before 3.10 unless via `__future__`.
- No `A | B` union syntax outside `TYPE_CHECKING` blocks below 3.10.
- Idiomatic Python. Prefer built-ins (`list`, `dict`, `set`, `tuple`) unless `collections`/`collections.abc` clearly better.
- Full type annotations on all functions, methods, classes, variables. Minimize `Any`. Use `if TYPE_CHECKING:` for heavy type-only imports.
- Verify types with mypy (strict=true). Use pyright/pytype for second opinions. Recheck `# noqa:` and `# type: ignore`. Reset mypy cache on unexpected errors.
- Type stubs: no official stubs -> check <https://github.com/python/typeshed> for stubs; unavailable -> derive from source on GitHub/GitLab.
- Fully qualified names in docstrings for non-stdlib types (e.g., `numpy.ndarray`, not `ndarray`).
- No `assert` in production -- tests only.
- No mutable default arguments.
- No wildcard imports (`from module import *`).
- No `pickle` (CWE-502).
- No `eval()` unless absolutely necessary and demonstrably safe.
- No hardcoded secrets/credentials/tokens.
- Defensive coding: check `None`/empty, handle exceptions for all external inputs.
- `time.monotonic()` for durations, not `time.time()`.
- All config in `pyproject.toml` where possible.
- `requires-python` must match actual min version.
- Make packages zip-safe when possible.
- Packaging metadata follows Core metadata spec: <https://packaging.python.org/en/latest/specifications/core-metadata/>

## Cross-platform compatibility

- Pitloom must work seamlessly across Windows, macOS, and Linux.
- Be vigilant about OS differences: file locking semantics (e.g. Windows `PermissionError` when replacing or deleting an open file), path separators (`\` vs `/`), pipe behaviors, and filesystem case-sensitivity.
- Always use `pathlib.Path` for file resolution and manipulation; never concatenate paths as strings.
- Ensure automated tests run smoothly across platforms without leaving orphaned temporary files behind.

### Import order

Groups: stdlib -> third-party -> local, alphabetically within each. Don't reorder imports with comments explaining required order (circular import/init constraint).

### Type completeness

- All visible class vars, instance vars, methods annotated.
- All function/method params and return types annotated.
- Generic base classes have type args specified.
- Omit annotations only for:
  - Simple literal constants (e.g., `MAX = 50`, `RED = '#F00'`), preferably `Final`.
  - Enum member values inside `Enum`.
  - Module-level type aliases.
  - `self` and `cls` params.
  - `__init__` return type.
  - `__all__`, `__author__`, `__version__`, similar dunder module attrs.

## Linting and formatting

Run and fix all errors before committing:

```shell
ruff check --fix
pylint
mypy
pyright
pyrefly check
bandit -r
ruff format
flake8
```

- Return statements ≤ 6; refactor if exceeded.
- Arguments ≤ 5; refactor if exceeded.
- Local variables ≤ 15; refactor if exceeded.
- Nested blocks ≤ 5; refactor if exceeded.
- McCabe complexity ≤ 10; refactor if exceeded.
- Cognitive complexity ≤ 15; refactor if exceeded.
- Remove unused imports and trailing whitespace.
- Max line length = 88; Try to be within 80.
- Stick with ASCII characters in source code;
  Only use non-ASCII when native human language scripts provides clearer message;
  or it provides more readable diagram/box drawing.
- Avoid ambiguous variable name (E741)

## File headers

All source files must have SPDX tags in this order (alphabetical):

```text
SPDX-FileCopyrightText: <year> <name>
SPDX-FileType: SOURCE                # or DOCUMENTATION
SPDX-License-Identifier: Apache-2.0  # or CC0-1.0 for docs
```

Sort SPDX metadata keys alphabetically.

`working-docs/design/*.md`, `working-docs/implementation/*.md`, and other
standalone docs (e.g. `docs/resources.md`) additionally carry `Created` and
`Last-Modified` (`YYYY-MM-DD`) in the same front-matter block, sorted
alphabetically alongside the SPDX keys:

```text
Created: 2026-02-06
Last-Modified: 2026-07-06
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
```

`SKILL.md` files are the exception: their YAML front matter is limited
to the keys the Agent Skill spec recognises (`name`, `description`,
`license`, ...), so `Created`/`Last-Modified`/SPDX tags can't be real
front-matter keys there. Put them as `#` YAML comments at the top of the
same front-matter block instead, ordered alphabetically same as the
normal case, followed by a blank line before the real keys. (HTML
comments were tried first, per the general Markdown convention below,
but they render as visible literal text in the Claude Code UI, so `#`
comments -- invisible in any YAML-aware renderer, and native YAML syntax
-- are used instead.)

```markdown
---
# Created: 2026-07-05
# Last-Modified: 2026-07-06
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

name: enrich
description: >-
  ...
license: Apache-2.0
---
```

Set `Created` once, when the file is added. Bump `Last-Modified` to the
current date on every substantive edit to that doc -- this is what lets
a human or agent judge a doc's staleness without checking git history.

## Testing

- Add tests for new behavior -- cover success, failure, edge cases.
- **Bug fixes and regressions**: When fixing a bug, always add a regression test that fails without the fix and passes with it. Prove the bug is dead and ensure it stays dead.
- Use pytest patterns, not `unittest.TestCase`.
- `spec`/`autospec` when mocking.
- `time_machine` for time-dependent tests.
- `@pytest.mark.parametrize` for multiple similar inputs.

### Test suite structure

- **File size**: soft limit ~400-500 lines, hard limit ~800 lines --
  same numbers as `working-docs/` (see Project context above), for
  the same reason: keeps a file within a reasonable AI-agent context
  window and makes selective test runs actually selective. Split
  before crossing it -- one area of behaviour per file, not one file
  per source module and everything it does.
- **Naming**: `test_<area>.py`, snake_case, 1:1 with the source module
  it exercises where a 1:1 mapping exists (`test_extract_gguf.py` <->
  `extract/_gguf.py`). Disambiguate when two source packages could
  produce the same tail -- name by the fuller source-path shape, not
  just the leaf module name (e.g. don't let a `core/project.py` test
  and an `extract/project.py` test both reduce to "test ... project").
- **Grouping**: once a source package's tests grow to 3+ related
  files, group them in a same-named subfolder under `tests/` mirroring
  `src/pitloom/<package>/` (e.g. `tests/extract/`, `tests/cli/`) --
  same 3+-files threshold `working-docs/` already uses for its own
  subfolder grouping. Areas with 1-2 test files stay flat at `tests/`
  root; don't create a folder for a single file.
- No `__init__.py` needed in test folders --
  `--import-mode=importlib` (`pyproject.toml`'s
  `[tool.pytest.ini_options]`) already allows same-named test files
  across different directories without one.
- Folder-level `conftest.py` for fixtures scoped to that area; keep
  root `tests/conftest.py` for fixtures genuinely shared across areas.

## Git and pull requests

- Commit messages: user impact, not implementation details.
- Follow: <https://chris.beams.io/posts/git-commit/>
- Every PR must address: **What changed?** / **Why?** / **Breaking changes?**
- Update `CHANGELOG.md` for significant changes per Keep a Changelog (<https://keepachangelog.com/>) and Semantic Versioning (<https://semver.org/>). Mark breaking changes clearly with migration instructions.

## Project metadata consistency

Keep in sync: `pyproject.toml`, `codemeta.json`, `CITATION.cff`, other metadata files.

Consistent fields: project name, version, author/contributor names, license, description, repository URL, keywords/tags (same order).

## Dependencies

- Sort in `pyproject.toml` and `requirements.txt`.
- Use most current compatible version.
- Verify package names -- guard against typosquatting/slopsquatting.
- Remove unused imports and dependencies.
- Warn about abandoned packages; suggest maintained replacements.

## Security

- No deprecated/obsolete/insecure libraries/APIs.
- Validate/sanitize all user inputs (SQL injection, XSS, buffer overflows, path traversal CWE-22).
- No hardcoded secrets. Use env vars or secret managers.
- Strong, well-established crypto algorithms and key sizes.
- OAuth2/OpenID Connect for auth.
- Regularly update dependencies to latest secure versions.

## Shell scripts

- Account for GNU/BSD/macOS/Unix tool differences.
- Defensive variable expansion; quote paths and variables.
- Mind single-quote vs double-quote semantics.

## Naming

- ASCII letters, digits, hyphens (`-`), underscores (`_`) only.
- Standard naming conventions for the language/framework.
- Noun number: singular for single-entity classes, plural only for collections/utility modules/aggregates.
- **Python module leading underscore**: a module gets a leading
  underscore (e.g. `_gguf.py`) when nothing outside its own package
  directory imports it -- an internal adapter, parser, or helper with
  no stability contract. No prefix (e.g. `wheel.py`, `hatchling.py`)
  when something outside the package imports it -- a stable entry
  point. Two checks before naming or renaming a module, don't infer
  the rule from a neighbouring file's name: (1) `grep` its actual
  importers -- module-qualified imports only (`from pkg.module import
  x`, not docstring/comment mentions); (2) check for an explicit
  `__all__` and a "public API" docstring marker -- a deliberate
  facade for external consumers of the library can legitimately have
  zero *internal* importers and should stay unprefixed regardless
  (e.g. `pitloom/extract/dataset.py` re-exports `read_croissant` for
  outside callers even though nothing inside `pitloom` imports it).
  Worked example in `pitloom/extract/`: `_gguf.py`, `_hdf5.py`,
  `_pytorch.py`, etc. are per-format parsers only their aggregator
  (`ai_model.py`) imports internally and carry no `__all__`, so they
  stay underscored regardless of domain (AI model formats vs. Python
  packaging formats); `wheel.py`, `hatchling.py`, `env.py` are
  imported from outside `extract/` (`assemble/__init__.py`,
  `plugins/hatch.py`), so they stay unprefixed.
- Ontology/vocab: consult Schema.org; also NIEM Model <https://github.com/niemopen/niem-model> <https://docs.oasis-open.org/niemopen/niem-model/v6.0/niem-model-v6.0.html>, FIBO <https://github.com/edmcouncil/fibo/blob/master/ONTOLOGY_GUIDE.md> and OBO Foundry <https://obofoundry.org/principles/fp-012-naming-conventions.html>
- URLs/IRIs: lowercase + hyphens; W3C Cool URIs: <https://www.w3.org/TR/cooluris/>
- Consult SEMIC Style Guide: <https://semiceu.github.io/style-guide/1.0.0/index.html>

## JSON

- Decimal values (e.g., `xs:decimal`) in quotes to preserve precision.
- Valid, well-formatted JSON.
- SPDX 3 JSON: follow canonical serialization <https://spdx.github.io/spdx-spec/v3.0.1/serializations/#canonical-serialization>
- Follow RFC 8785 JCS <https://www.rfc-editor.org/rfc/rfc8785>
- JSON-LD: follow RDF canonicalization <https://www.w3.org/TR/rdf-canon/>

## Markdown

- Metadata as YAML front matter between triple-dashed lines (Hugo/Jekyll style).
- Standard Markdown; avoid GitHub-specific extensions.
- `sentence case` for headings/titles.
- Max line length = 80; Except diagram, table, and URLs.
- Run Markdownlint.

## HTML and CSS

- Valid, well-formatted HTML, no trailing whitespace.
- W3C accessibility recommendations.
- Concise element IDs/names; group related names.
- No unused CSS styles.

## API

- Latest OpenAPI spec: <https://spec.openapis.org/oas/>
- Proper HTTP status codes.
- Follow OpenAPI, IETF, W3C web best practices.

## Writing style

- British English for docs, comments, text. American English for code only.
- Active voice; concise sentences; no jargon/idioms.
- Short comments -- don't restate the obvious.
- Consistent terminology throughout.
- Define acronyms on first use.
- Parallel structure in lists.
- IETF verbal forms (RFC 2119/8174) for internet/web/semantic web projects; ISO verbal forms for SPDX docs.
- Dates: ISO 8601. Numbers/units: SI. Timezone: UTC+0. Currency: Euros (€) primary, USD in parentheses.
- Citations: Chicago style unless specified.

## Diagrams (ASCII/text)

Count characters, align carefully. Misaligned ASCII = bug.

## Versions

Verify version exists and is compatible before suggesting. Prefer Semantic Versioning.

## Boundaries

**Ask before doing:**

- Large cross-package refactors.
- New dependencies with broad impact.
- Destructive data or migration changes.

**Never:**

- Commit secrets, credentials, or tokens.
- Edit generated files by hand when generation workflow exists.
- Use destructive git operations unless explicitly requested.

## More guidelines and best practices

See `docs/resources.md` for SBOM, AIBOM, SPDX, standards resources and best practices.
