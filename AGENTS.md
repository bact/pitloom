---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: Apache-2.0
---

# AGENTS instructions

## Coding Standards

- Maintain compatibility with Python 3.10.
- Provide type hints as much as possible. Minimize the use of `Any`.
- No `assert` in production code.
- `time.monotonic()` for durations, not `time.time()`.
- Imports at top of file. Valid exceptions: circular imports, lazy loading for
  worker isolation, `TYPE_CHECKING` blocks.
- Guard heavy type-only imports with `TYPE_CHECKING`.
- SPDX header on all new files, with these keys: `SPDX-FileCopyrightText`,
  `SPDX-FileType`, `SPDX-License-Identifier`, in that alphabetical order.
- Run `flake8`, `ruff`, `mypy` and fixes any errors.

## Testing Standards

- Add tests for new behavior — cover success, failure, and edge cases.
- Use pytest patterns, not `unittest.TestCase`.
- Use `spec`/`autospec` when mocking.
- Use `time_machine` for time-dependent tests.
- Use `@pytest.mark.parametrize` for multiple similar inputs.

## Commits and Pull Requests

- Write commit messages focused on user impact, not implementation details.
- Every pull request should answer:
  - **What changed?**
  - **Why?**
  - **Breaking changes?**

## Boundaries

- **Ask first**
  - Large cross-package refactors.
  - New dependencies with broad impact.
  - Destructive data or migration changes.
- **Never**
  - Commit secrets, credentials, or tokens.
  - Edit generated files by hand when a generation workflow exists.
  - Use destructive git operations unless explicitly requested.
