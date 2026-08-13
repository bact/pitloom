# Agent instructions

## Project context

- SBOM generator targeting Python/Hatchling ecosystem, outputting SPDX 3 JSON-LD.
- Design docs: `working-docs/design/`
- Implementation docs and progress reports: `working-docs/implementation/`
- Test fixtures: `tests/fixtures/README.md`
- Private alpha, one developer. No backward compat needed yet.
- `working-docs/` is internal notes only -- content can change without
  notice. The user-facing website (`docs/`) must never link into it, in
  any form (relative path, absolute GitHub URL, etc.). Reference a PR or
  issue number instead if a public pointer is needed.

### SBOM output

- Deterministic: SBOMs must be bit-for-bit identical across builds when input/environment unchanged.
- Idempotency: No non-deterministic data (timestamps, random UUIDs).
- Schema compliance: Validate every SBOM against primary spec (CycloneDX/SPDX) and serialization format before finalization. Automated validation mandatory.

### Metadata sources

- The Hatchling build hook (`pitloom.plugins.hatch`) reads project metadata from `self.metadata` (Hatchling's own resolved `hatchling.metadata.core.ProjectMetadata`), via `pitloom.extract.hatchling.metadata_from_hatchling()`, so dynamic version/dependency/license sources resolved by Hatchling plugins are reflected correctly.
- The CLI (`pitloom.__main__`) and `pitloom.assemble.generate_project_sbom()`'s default parsing path both resolve metadata/config from the project directory via the shared `pitloom.extract.project.read_project()` helper (`pyproject.toml` -> `setup.cfg`/`setup.py` -> error), so each parses its inputs once. The CLI passes its already-parsed `project_metadata`/`pitloom_config` into `generate_project_sbom()` so it never re-parses.
- Both paths converge on the same `pitloom.assemble.spdx3.document.build()` assembly layer, so the emitted SBOM shape (file hashes, PURLs, licensing, etc.) is identical regardless of metadata source.

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
- Use pytest patterns, not `unittest.TestCase`.
- `spec`/`autospec` when mocking.
- `time_machine` for time-dependent tests.
- `@pytest.mark.parametrize` for multiple similar inputs.

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
