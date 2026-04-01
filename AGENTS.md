# Agent instructions

## Project context

- SBOM generator targeting Python/Hatchling ecosystem, outputting SPDX 3 JSON-LD.
- Design documents: `docs/design/`
- Implementation documents and progress reports: `docs/implementation/`
- Test fixtures: `tests/fixtures/README.md`
- This project is in private alpha stage with only one developer.
  Do not worry about breaking changes or keeping backward compatibility yet.

### SBOM output

- Deterministic generation: To ensure reproducible builds,
  generated SBOMs must be bit-for-bit identical across builds when the
  input and environment remain unchanged.
- Idempotency: Avoid non-deterministic data (e.g., current timestamps or
  random UUIDs) to maintain reproducibility in the resulting SBOM.
- Schema compliance: Every SBOM must be strictly validated against its
  primary specification (e.g., CycloneDX/SPDX) and its specific serialization
  format (JSON/XML) prior to finalization. Automated validation is mandatory.

## CLI output

Follow Unix philosophy.
Output must be consistent, predictable and parseable.

- Default output: line-delimited, one discrete data point per line.
- Field separator within a line: space or tab (consistent).
- Key-value output: `KEY=VALUE` format — uppercase KEY, no spaces around `=`.
- Error output: `ERROR: <short description>` to stderr.
- Output must work cleanly with `awk`, `wc`, `xargs`, and similar Unix tools.
- Format flags (JSON, CSV, etc.) and file output are supported as options.

## Python

- Minimum supported version: Python 3.10. Do not use syntax or features
  unavailable before 3.10 unless via `__future__` imports.
- Do not use `A | B` union syntax outside `TYPE_CHECKING` blocks if
  the minimum version is below 3.10.
- Use idiomatic Python. Prefer built-in data structures (`list`, `dict`,
  `set`, `tuple`) unless a specialized type from `collections` or
  `collections.abc` is clearly better.
- Complete type annotations for all functions, methods, classes, and
  variables. Minimize use of `Any`. Use `if TYPE_CHECKING:` blocks for
  heavy type-only imports.
- Verify types with mypy (strict=true).
  Use pyright or pytype for second opinions.
  Recheck necessity of `# noqa:` and `# type: ignore`.
  Reset mypy cache if unexpected errors occur.
- For type stubs: if no official stubs are available,
  check <https://github.com/python/typeshed> for stubs;
  if unavailable, find source code on GitHub/GitLab/repo
  and derive correct types.
- Use full qualified names in docstrings for non-stdlib types (e.g.,
  `numpy.ndarray`, not `ndarray`).
- No `assert` in production code — only in tests.
- No mutable default arguments.
- No wildcard imports (`from module import *`).
- No `pickle` for serialization/deserialization (CWE-502).
- No `eval()` unless absolutely necessary and demonstrably safe.
- No hardcoded secrets, credentials, or tokens.
- Defensive coding: check for `None`/empty and handle exceptions for all
  external inputs (function args, file I/O, network I/O).
- Use `time.monotonic()` for durations, not `time.time()`.
- All configuration in `pyproject.toml` where possible.
- `requires-python` must reflect the actual minimum supported version.
- Make packages zip-safe when possible.
- Packaging metadata must follow the Core metadata spec: <https://packaging.python.org/en/latest/specifications/core-metadata/>

### Import order

Group imports: stdlib → third-party → local, then alphabetically within
each group. Do not reorder imports if a comment explains a required order
(circular import or init constraint).

### Type completeness

- All visible class variables, instance variables, and methods are annotated.
- All function/method parameters and return types are annotated.
- Generic base classes have type arguments specified.
- Type annotations can be omitted only for:
  - Simple literal constants (e.g., `MAX = 50`, `RED = '#F00'`),
    preferably with `Final`.
  - Enum member values inside an `Enum` class.
  - Module-level type aliases.
  - `self` and `cls` parameters.
  - `__init__` return type.
  - `__all__`, `__author__`, `__version__`, and similar dunder module attributes.

## Linting and formatting

Run and fix all errors before committing:

```shell
ruff check
mypy
pylint
flake8
ruff format
```

- McCabe complexity must stay ≤ 10; refactor new code that exceeds this.
- Cognitive complexity must stay ≤ 15; refactor new code that exceeds this.
- Remove unused imports and trailing whitespace.
- Code max line length = 88

## File headers

All source files must have SPDX tags in this order (alphabetical):

```text
SPDX-FileCopyrightText: <year> <name>
SPDX-FileType: SOURCE          # or DOCUMENTATION
SPDX-License-Identifier: Apache-2.0  # or CC0-1.0 for docs
```

Sort SPDX metadata keys alphabetically.

## Testing

- Add tests for new behavior — cover success, failure, and edge cases.
- Use pytest patterns, not `unittest.TestCase`.
- Use `spec`/`autospec` when mocking.
- Use `time_machine` for time-dependent tests.
- Use `@pytest.mark.parametrize` for multiple similar inputs.

## Git and pull requests

- Write commit messages focused on user impact, not implementation details.
- Follow: <https://chris.beams.io/posts/git-commit/>
- Every pull request must address: **What changed?** / **Why?** / **Breaking changes?**
- Update `CHANGELOG.md` for significant changes following
  Keep a Changelog (<https://keepachangelog.com/>) and
  Semantic Versioning (<https://semver.org/>). Mark breaking changes
  clearly and provide migration instructions.

## Project metadata consistency

Keep these files in sync: `pyproject.toml`, `codemeta.json`,
`CITATION.cff`, and other metadata files.

Fields to keep consistent: project name, version, author/contributor
names, license, description, repository URL, keywords/tags (same order).

## Dependencies

- Sort dependencies in `pyproject.toml` and `requirements.txt`.
- Use the most current version compatible with the OS/framework.
- Verify package names carefully — guard against typosquatting and slopsquatting.
- Remove unused imports and dependencies.
- Warn about abandoned packages and suggest maintained replacements.

## Security

- No deprecated, obsolete, or insecure libraries/APIs.
- Validate and sanitize all user inputs (SQL injection, XSS, buffer
  overflows, path traversal CWE-22).
- No hardcoded secrets. Use environment variables or secret managers.
- Use strong, well-established cryptographic algorithms and key sizes.
- Follow OAuth2/OpenID Connect for authentication/authorization.
- Regularly update dependencies to their latest secure versions.

## Shell scripts

- Account for differences between GNU, BSD, macOS, and other Unix tool implementations.
- Be defensive with variable expansion; quote paths and variables appropriately.
- Be mindful of single-quote vs double-quote semantics.

## Naming

- ASCII letters, digits, hyphens (`-`), and underscores (`_`) only in names.
- Follow standard naming conventions for the language/framework in use.
- Noun number consistency: Maintain strict intentionality regarding singular
  vs. plural forms. Use singular names for classes representing a single entity
  and reserve plural names only for collections, utility modules, or clear
  aggregates.
- Ontology/vocabulary: consult Schema.org vocabularies for naming decisions,
  also FIBO naming conventions
  <https://github.com/edmcouncil/fibo/blob/master/ONTOLOGY_GUIDE.md>
  and OBO Foundary naming conventions
  <https://obofoundry.org/principles/fp-012-naming-conventions.html>
- URLs/IRIs: lowercase letters and hyphens; follow W3C Cool URIs: <https://www.w3.org/TR/cooluris/>
- Consult SEMIC Style Guide for Semantic Engineers
  <https://semiceu.github.io/style-guide/1.0.0/index.html>

## JSON

- Enclose decimal values (e.g., `xs:decimal`) in quotes to preserve precision.
- Output must be valid and well-formatted JSON.

## Markdown

- Metadata as YAML front matter between triple-dashed lines (Hugo/Jekyll style).
- Use standard Markdown; avoid GitHub-specific extensions for portability.
- Use `sentence case` for headings and titles.
- Max line length = 80
- Run Markdownlint to detect issues.

## HTML and CSS

- Valid, well-formatted HTML with no trailing whitespace.
- Follow W3C accessibility recommendations.
- Sensible, concise element IDs and names; group related names.
- No unused CSS styles.

## API

- Follow the latest OpenAPI specification: <https://spec.openapis.org/oas/>
- Use proper HTTP status codes.
- Follow web best practices from OpenAPI, IETF, and W3C.

## Writing style

- British English spelling for documentation, comments, and other text.
- American English spelling only for code.
- Active voice; concise sentences; no jargon or idioms.
- Short comments — do not restate the obvious.
- Consistent terminology throughout code and documentation.
- Define acronyms on first use.
- Parallel structure in lists.
- Use IETF verbal forms (RFC 2119/8174) for internet/web/semantic web
  projects; ISO verbal forms for SPDX documents.
- Dates: ISO 8601. Numbers and units: SI conventions. Timezone: UTC+0.
  Currency: Euros (€) primary, USD in parentheses.
- Citations: Chicago style unless otherwise specified.

## Diagrams (ASCII/text)

Count characters and align lines carefully. Misaligned ASCII diagrams are a bug.

## Versions

When suggesting dependencies, verify the version exists and is compatible
with the current system and other dependencies. Prefer Semantic Versioning.

## Boundaries

**Ask before doing:**

- Large cross-package refactors.
- New dependencies with broad impact.
- Destructive data or migration changes.

**Never:**

- Commit secrets, credentials, or tokens.
- Edit generated files by hand when a generation workflow exists.
- Use destructive git operations unless explicitly requested.

## More guidelines and best practices

- Look at `docs/resources.md` for resources, guidelines, and best practices
  for SBOM, AIBOM, SPDX, and standards.
