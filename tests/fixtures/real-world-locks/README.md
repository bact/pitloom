---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Real-world lock-file fixtures

See also: [../real-world-projects/README.md](../real-world-projects/README.md)
(the sibling fixture set for build-backend wheel-file discovery -- a
different concern, vendoring a full sdist archive per project; this
directory only ever needs two small text files);
[../projects/README.md](../projects/README.md) (small, synthetic,
single-behaviour lock fixtures, e.g. malformed/edge-case content written
inline in each format's own test file, not vendored here);
[`../../../working-docs/implementation/lock-file-cascade.md`](../../../working-docs/implementation/lock-file-cascade.md)
for the priority-cascade mechanism these fixtures exercise;
[`../../extract/test_locked_dependencies.py`](../../extract/test_locked_dependencies.py)
for the cascade's own mechanism tests.

## What's here

Each `<format>/<project>-<version>/` directory holds:

- The project's real metadata file -- `pyproject.toml` for every format
  except `Pipfile.lock` (which pairs with a real `setup.py` instead --
  see the table's "Metadata source" column and the note below).
- The project's real, unmodified lock/pin file for that format
  (`pylock.toml`, `poetry.lock`, `uv.lock`, `pdm.lock`, `Pipfile.lock`,
  or `requirements.txt`), committed as plain text.
- Occasionally a third file the metadata file itself references (e.g.
  `snowflake-cli`'s `LICENSE`, required because its `pyproject.toml`
  declares `license = { file = "LICENSE" }`).

No sdist archive, no `.git` history, no source code -- these fixtures
exist only to exercise `pitloom.extract.project.read_project()`'s lock
cascade (`pitloom.extract._locked_dependencies.apply_locked_dependencies`),
which only ever reads a project's metadata file and a sibling lock file
by name. Each pair is a few KB to a couple hundred KB of plain text.

**Important, checked and confirmed, not assumed:** almost none of these
lock files ship inside the project's own PyPI sdist (lock files are
dev-time artifacts, routinely excluded from `MANIFEST`/sdist packaging)
-- only `flask`'s `uv.lock` was found there. Every other lock file here
was fetched from the project's GitHub repository at the release tag
matching the chosen PyPI version instead
(`raw.githubusercontent.com/<org>/<repo>/<tag>/<lockfile>`), paired with
that same tag's metadata file. This is a deliberate difference from
`real-world-projects/`'s "vendor the sdist verbatim, don't reach into
git" method -- the sdist doesn't contain what these fixtures need, and
vendoring a whole sdist archive just to reach two small files inside it
would be unjustified bloat.

This directory (like the rest of `tests/fixtures/`) is excluded from
Pitloom's own published sdist and wheel
(`pyproject.toml`'s `[tool.hatch.build.targets.sdist]`/`[tool.hatch.build.targets.wheel]`),
to avoid redistributing vendored third-party source in a release
artifact.

## Notable cases

- **`Pipfile.lock`'s metadata source is `setup.py`, not `pyproject.toml`.**
  `Pipfile.lock` (Pipenv) predates PEP 621 almost entirely -- every real
  project checked that ships one uses a bare `setup.py`. This is exactly
  the case `read_project()`'s cascade wiring (rather than being wired
  only inside `read_pyproject()`) exists to cover -- see
  `lock-file-cascade.md`. Both `requests-html`'s and `responder`'s
  `setup.py` declare `name`/`version` via module-level constants
  (`NAME = 'requests-html'`, `setup(name=NAME, ...)`), which
  `_setuptools_py.py`'s AST-literal extractor can't resolve (a known,
  separate, pre-existing gap -- see the `pyyaml` entry in
  `real-world-projects/README.md`) -- so `metadata.name` won't resolve
  for either. Tests against these two fixtures assert on
  `locked_dependencies`/`provenance`, not `metadata.name`.
- **`pipenv`'s `pylock.toml` fixture reuses a version already vendored
  elsewhere.** `pypa/pipenv` `2026.8.0` is the same release already
  vendored as a full sdist in
  `../real-world-projects/setuptools/pipenv-2026.8.0/` for the
  unrelated wheel-file-discovery fixture set. Deliberate reuse of the
  same upstream release for a different, much smaller purpose here --
  not a duplicate.
- **`tomlkit` resolves to zero locked dependencies.** `tomlkit` is a
  standalone TOML library with no runtime dependencies at all -- every
  entry in its `poetry.lock` belongs to the `dev`/docs/test groups, none
  to `main`. A real, valid "empty resolved set" case, not a broken
  fixture.
- **`pendulum` and `cleo`/`tomlkit`/`pastel` diversify `[tool.poetry]`
  detection.** `pendulum`'s `pyproject.toml` has both `[project]` and
  `[tool.poetry]` (hybrid); the other three have `[tool.poetry]` only,
  no `[project]` table at all -- both of `read_pyproject()`'s
  Poetry-detection shapes get real coverage.

## Fixtures

| Format | Project | Version | License | Metadata source | Lock file source |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `pylock.toml` (PEP 751) | [snowflakedb/snowflake-cli](https://github.com/snowflakedb/snowflake-cli) | 3.26.0 | Apache-2.0 | GitHub tag `v3.26.0` | GitHub tag `v3.26.0` |
| `pylock.toml` (PEP 751) | [pypa/pipenv](https://github.com/pypa/pipenv) | 2026.8.0 | MIT | GitHub tag `v2026.8.0` | GitHub tag `v2026.8.0` |
| `poetry.lock` | [sdispater/pendulum](https://github.com/sdispater/pendulum) | 3.2.0 | MIT | PyPI sdist (hybrid `[project]` + `[tool.poetry]`) | GitHub tag `3.2.0` |
| `poetry.lock` | [python-poetry/cleo](https://github.com/python-poetry/cleo) | 2.1.0 | MIT | PyPI sdist (`[tool.poetry]` only) | GitHub tag `2.1.0` |
| `poetry.lock` | [python-poetry/tomlkit](https://github.com/python-poetry/tomlkit) | 0.15.1 | MIT | PyPI sdist (`[tool.poetry]` only) | GitHub tag `0.15.1` |
| `poetry.lock` | [sdispater/pastel](https://github.com/sdispater/pastel) | 0.2.1 | MIT | PyPI sdist (`[tool.poetry]` only) | GitHub tag `0.2.1` |

`uv.lock`, `pdm.lock`, `Pipfile.lock`, and pinned `requirements.txt`
fixtures land in their own follow-up changes, alongside each format's
own extractor -- see `working-docs/design/roadmap.md`'s "Remaining lock
formats as a resolved-dependency source" item.
