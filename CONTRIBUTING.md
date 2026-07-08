---
Created: 2026-07-08
Last-Modified: 2026-07-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Contributing to Pitloom

Thanks for your interest in contributing. This guide covers the developer
setup and conventions used in this repository.

## Dev install

For development (lint + test), using pip >= 25:

```bash
pip install --group dev -e .
```

Or with uv:

```bash
uv sync --group dev
```

## Running tests

```bash
pytest
```

## Linting & type-checking

```bash
ruff check src/ tests/
```

Code must be formatted with `ruff format` before opening a pull request.
`pylint` and `mypy` (strict mode) are also part of the project's quality
gate -- run them before opening a pull request.

## Building

```bash
pip install build
python -m build
```

## Project structure

See [working-docs/implementation/summary.md](working-docs/implementation/summary.md)
for the canonical, up-to-date project tree.

## Design documents

Internal, AI-agent-facing design and implementation notes live under
`working-docs/`:

- [working-docs/design/architecture-overview.md](working-docs/design/architecture-overview.md)
  -- overall system design.
- [working-docs/design/adoption-surfaces.md](working-docs/design/adoption-surfaces.md)
  -- how Pitloom's surfaces (CLI, API, build hook, Action, Skills, plugin)
  fit together.
- [working-docs/design/metadata-provenance.md](working-docs/design/metadata-provenance.md)
  -- provenance tracking design.
- [working-docs/design/roadmap.md](working-docs/design/roadmap.md) -- what's
  planned next.
- Browse [working-docs/design/](working-docs/design/) and
  [working-docs/implementation/](working-docs/implementation/) for the full
  set.

## Roadmap

See [working-docs/design/roadmap.md](working-docs/design/roadmap.md).

## Reporting issues & proposing changes

- Open a [GitHub issue](https://github.com/bact/pitloom/issues) to report a
  bug or propose a change before starting significant work.
- Pull requests are welcome. Keep changes focused and scoped to one concern.
- Update `CHANGELOG.md` for user-visible changes, following
  [Keep a Changelog](https://keepachangelog.com/).

## Commit & branch conventions

- Branch off `main`.
- Write descriptive commit messages that explain user impact, not just
  implementation details (see
  [How to Write a Git Commit Message](https://chris.beams.io/posts/git-commit/)).

## Sign-off (DCO)

Commits must be signed off, certifying you have the right to submit the
work under the project's license (Developer Certificate of Origin):

```bash
git commit -s
```
