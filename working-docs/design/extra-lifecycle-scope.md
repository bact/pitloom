---
Created: 2026-10-10
Last-Modified: 2026-10-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Lifecycle scope for Python extras

See also: [roadmap.md](roadmap.md),
[provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md)
(the provenance taxonomy this is meant to sit beside),
[extras-parity.md](../implementation/extras-parity.md) (what was built),
[sbom-generator-field-notes/spdx-modelling.md](../implementation/sbom-generator-field-notes/spdx-modelling.md)
(paper note, section 4).

**Status:** designed, not built. An optional setting; off by default.

## Problem

SPDX 3.0.1 says *when* a dependency matters through the lifecycle scope on a
`LifecycleScopedRelationship`: `design`, `build`, `development`, `test`,
`runtime` or `other`. Python has no field that says the same. A project
states its dependencies as:

- `[project].dependencies`: required at runtime (Pitloom emits
  `dependsOn` + `runtime`);
- `[project.optional-dependencies]` (extras): *optional*, with a free-form
  name. `dev`, `test`, `lint`, `docs`, `full` and a feature such as `async`
  are all the same kind of thing to a build tool; the name is a convention,
  not a field;
- PEP 735 `[dependency-groups]`: the closest Python analogue of a lifecycle
  scope (a group is never installed with the package, and is not in wheel
  metadata), but groups have no wheel equivalent and are out of scope for the
  extras work;
- `[build-system].requires`: the `build` scope, not an extra.

Pitloom does not guess a scope from an extra's name. Today an extra's edge is
`hasOptionalDependency` with **no** scope: "optional" is known, the lifecycle
is not. Putting `runtime` on a `dev` or `lint` extra would assert a fact the
project never stated.

## Recommended practice (for the user docs)

Name an extra after the lifecycle stage it serves when it serves one, using the
common names: `dev` (or `lint`, `docs`) for development, `test` (or `tests`)
for testing; keep feature names (`full`, `async`, `postgres`) for optional
runtime features. A meaningful name costs nothing and lets a tool map the extra
to a scope, once the project says so (below). Do not depend on Pitloom
inferring it.

## The optional setting

A `[tool.pitloom]` table maps an extra to a scope, stated by the project:

```toml
[tool.pitloom.extra-scopes]
dev = "development"
lint = "development"
test = "test"
```

Rules (decided in outline, 2026-10-10):

- **Never a guess.** An extra with no entry keeps the scope-less
  `hasOptionalDependency` edge. No built-in name table by default.
- **One scope per relationship.** A package in several extras that map to
  *different* scopes gets one edge per distinct scope, each listing only the
  extras that map to it (`extras: dev, lint` on the `development` edge); the
  unmapped extras stay on the scope-less edge. A package also required by
  `[project].dependencies` keeps its `dependsOn` + `runtime` edge in addition.
  Lock-pinned extras get the same edges.
- **Values** are the six SPDX `LifecycleScopeType` names, checked at config
  load with a `WARNING:` and the entry ignored (the unknown-key rule).
- **Configuration cascade.** `pyproject.toml` / `--config`; a bare wheel has no
  project, so it needs `--config` (the Action reads `project-path`).
- **Provenance.** The edge's comment records that the scope came from the
  project's configuration, not from the extra's name.

## Open questions

1. Offer an opt-in preset (`extra-scope-convention = "common"`: dev, lint,
   docs to `development`; test, tests to `test`)? It is a guess the user
   chooses to make; decide with the provenance taxonomy.
2. Should `[dependency-groups]` (PEP 735) be listed at all once a scope can
   be stated (`development` for a `dev` group)? They never reach a wheel, so
   the wheel and sdist routes could not match.
3. Does a mapped extra change `doc_uuid`? Today the uuid seeds on dependency
   strings, not on config.
