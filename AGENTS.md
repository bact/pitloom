---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: Apache-2.0
---

# Agent instructions

## Project context

- SBOM generator targeting Python/Hatchling ecosystem, outputting SPDX 3.0 JSON-LD.
- Design documents: `docs/design/`
- Implementation documents and progress reports: `docs/implementation/`
- Test fixtures: `tests/fixtures/README.md`

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
ruff format
flake8
mypy
```

- McCabe complexity must stay ≤ 10; refactor new code that exceeds this.
- Cognitive complexity must stay ≤ 15; refactor new code that exceeds this.
- Remove unused imports and trailing whitespace.

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
- Ontology/vocabulary: consult Schema.org vocabularies for naming decisions.
- URLs/IRIs: lowercase letters and hyphens; follow W3C Cool URIs: <https://www.w3.org/TR/cooluris/>

## JSON

- Enclose decimal values (e.g., `xs:decimal`) in quotes to preserve precision.
- Output must be valid and well-formatted JSON.

## Markdown

- Metadata as YAML front matter between triple-dashed lines (Hugo/Jekyll style).
- Use standard Markdown; avoid GitHub-specific extensions for portability.
- Use `sentence case` for headings and titles.
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

- American English spelling.
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

## SPDX resources

- SPDX project: <https://spdx.dev/>
- SPDX 3.0 spec: <https://spdx.github.io/spdx-spec/v3.0/>
  - Model: <https://spdx.org/rdf/3.0/spdx-model.ttl>
  - JSON Schema: <https://spdx.org/schema/3.0/spdx-json-schema.json>
  - JSON-LD context: <https://spdx.org/rdf/3.0/spdx-context.jsonld>
- SPDX 3.1 spec (dev): <https://spdx.github.io/spdx-spec/v3.1-dev/>
  - Terms: <https://spdx.github.io/spdx-spec/v3.1-dev/terms-and-definitions/>
  - Model: <https://spdx.github.io/spdx-spec/v3.1/rdf/spdx-model.ttl>
  - JSON Schema: <https://spdx.github.io/spdx-spec/v3.1/rdf/schema.json>
  - JSON-LD context: <https://spdx.github.io/spdx-spec/v3.1/rdf/spdx-context.jsonld>
- SPDX 3 JSON validation guide: <https://github.com/spdx/spdx-3-model/blob/develop/serialization/jsonld/validation.md>
- SPDX 3 model format and style guide: <https://github.com/spdx/spdx-3-model/blob/develop/docs/format.md>
- SPDX 3 model Python binding: <https://github.com/spdx/spdx-python-model>
- SPDX examples: <https://github.com/spdx/spdx-examples>
- SBOM example using SPDX 3.0 AI and Dataset profile: <https://github.com/bact/sentimentdemo>
- NTIA Conformance Checker test corpus: <https://github.com/spdx/ntia-conformance-checker/tree/main/tests>
- Validator: `spdx3-validate` on PyPI
  (<https://pypi.org/project/spdx3-validate/>);
  GitHub: <https://github.com/JPEWdev/spdx3-validate>

## SBOM resources

- OpenChain SBOM Document Quality Guide Compliance Management Guide for
  the Supply Chain version 1.0.0:
  <https://docs.google.com/document/d/1iuXX8j10N70dfce1-CZFWhW6S2jEqc--flcCgXMMdjg/edit?usp=sharing>
- 2025 Minimum Elements for a Software Bill of Materials (SBOM) (draft):
  <https://www.cisa.gov/resources-tools/resources/2025-minimum-elements-software-bill-materials-sbom>
  <https://www.cisa.gov/sites/default/files/2025-08/2025_CISA_SBOM_Minimum_Elements.pdf>
- OpenChain AI SBOM Compliance Management Guide for the Supply Chain version 1.0:
  <https://github.com/OpenChain-Project/Reference-Material/blob/master/AI-SBOM-Compliance/en/Artificial-Intelligence-System-Bill-of-Materials-Compliance-Management-Guide.md>
- The State of Software Bill of Materials (SBOM) and Cybersecurity Readiness:
  <https://www.linuxfoundation.org/research/the-state-of-software-bill-of-materials-sbom-and-cybersecurity-readiness>
- SBOMs in the Era of the CRA: Toward a Unified and Actionable Framework:
  <https://openssf.org/blog/2025/10/22/sboms-in-the-era-of-the-cra-toward-a-unified-and-actionable-framework/>
- Challenges Facing the Security of the Software Supply Chain:
  <https://linuxfoundation.eu/newsroom/the-state-of-the-secure-software-supply-chain>
- Building an Open AIBOM Standard in the Wild:
  <https://arxiv.org/abs/2510.07070> (design notes on SPDX 3.0 AI profile)
- What We Know about AIBOMs: Results from a Multivocal Literature Review on
  Artificial Intelligence Bill of Materials:
  <https://dl.acm.org/doi/10.1145/3786773>
- AIBoMGen: Generating an AI Bill of Materials for Secure, Transparent,
  and Compliant Model Training
  <https://arxiv.org/abs/2601.05703>
- An Empirical Study on Software Bill of Materials: Where We Stand and
  the Road Ahead:
  <https://arxiv.org/abs/2301.05362>
- A shared G7 vision on software bill of materials for AI: Transparency and
  Cybersecurity along the AI supply chain:
  <https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/KI/SBOM-for-AI_Food-for-thoughts.html>
- BOMs Away! Inside the Minds of Stakeholders: A Comprehensive Study of Bills
  of Materials for Software Systems:
  <https://arxiv.org/abs/2309.12206>
- A Landscape Study of Open-Source Tools for Software Bill of Materials (SBOM)
  and Supply Chain Security:
  <https://arxiv.org/abs/2402.11151>

## AI documentation resources

- AIDOC-AP: An Application Profile for Technical Documentation of AI Systems:
  <https://www.semantic-web-journal.net/system/files/swj4042.pdf>
  <https://github.com/CERTAIN-Project/aidoc-ap>
  <https://certain-project.github.io/aidoc-ap/>
- TechOps: Technical Documentation Templates for the AI Act:
  <https://arxiv.org/abs/2508.08804>
- AICat: An AI Cataloguing Approach to Support the EU AI Act:
  <https://arxiv.org/abs/2501.04014>
