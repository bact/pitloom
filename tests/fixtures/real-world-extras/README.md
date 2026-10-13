---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Real-world extras fixtures

See also: [../real-world-locks/README.md](../real-world-locks/README.md)
(real lock files, a different concern);
[`../../extract/project/test_real_world_extras.py`](../../extract/project/test_real_world_extras.py)
(the test that reads these).

Each `<backend>/<project>-<version>/` directory holds the project's real,
unmodified `pyproject.toml` at the release tag, its `README` and its
`LICENSE`/`COPYING` (the metadata may name them), plus any requirements
file `[tool.setuptools.dynamic]` names. No source code, no lock
file, no history. They exercise how each build backend's extras
(`[project.optional-dependencies]` or `[tool.poetry.extras]`) are read by
`pitloom.extract.project.read_project()`.

The directory is excluded from Pitloom's sdist (`pyproject.toml`), wheel
and type checking, and holds no Python files, so linters skip it.
`.gitattributes` (`-text`), `.editorconfig` and `.markdownlintignore`
keep the vendored files byte for byte.

| Backend | Project | Version | Licence | Source |
|---|---|---|---|---|
| `flit_core` | [brettcannon/mousebender](https://github.com/brettcannon/mousebender) | 2025.1 | BSD-3-Clause | GitHub tag `v2025.1` |
| `flit_core` | [google/etils](https://github.com/google/etils) | 1.14.0 | Apache-2.0 | GitHub tag `v1.14.0` |
| `flit_core` | [pypa/flit](https://github.com/pypa/flit) | 4.1.0 | BSD-3-Clause | GitHub tag `4.1.0` |
| `hatchling` | [pyca/service-identity](https://github.com/pyca/service-identity) | 26.1.0 | MIT | GitHub tag `26.1.0` |
| `hatchling` | [pyupio/dparse](https://github.com/pyupio/dparse) | 0.6.4 | MIT | GitHub tag `0.6.4` |
| `setuptools` | [qurator-spk/dinglehopper](https://github.com/qurator-spk/dinglehopper) | 0.11.0 | Apache-2.0 | GitHub tag `v0.11.0` |
| `setuptools` | [jelmer/dulwich](https://github.com/jelmer/dulwich) | 1.2.17 | Apache-2.0 OR GPL-2.0-or-later | GitHub tag `dulwich-1.2.17` |
| `setuptools` | [sarugaku/resolvelib](https://github.com/sarugaku/resolvelib) | 1.2.1 | ISC | GitHub tag `1.2.1` |
| `poetry-core` | [sdispater/cachy](https://github.com/sdispater/cachy) | 0.3.0 | MIT | GitHub tag `0.3.0` |

Notes:

- Licences are as the repositories declare them; check the vendored
  `LICENSE` before relying on this column.
- Flit projects log "dynamic metadata resolution failed" because the
  package source is not vendored. The extras still come from the static
  tables.
- `etils` is the large case: 66 extra-gated requirements, several of them
  `etils[x]` self-references, which Pitloom expands (123 requirements).
- `dinglehopper` takes `dependencies` and its `dev` extra from
  `requirements.txt` and `requirements-dev.txt` through
  `[tool.setuptools.dynamic]`; it declares no `build-backend`.
- `cachy` uses the legacy `[tool.poetry.extras]` table.
- `dparse` is a Hatchling project, not Poetry.
