---
Created: 2026-09-15
Last-Modified: 2026-11-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Retire the letter-number use-case codename taxonomy

See also: [roadmap.md](roadmap.md) (Near-term -- "Internal codenames"),
`working-docs/implementation/provenance/use-case-catalog.md` (the
catalog this taxonomy comes from).

Split out of `roadmap.md` (2026-09-15) once this item's detail grew
past a summary -- this file, not the roadmap bullet, is now the source
of truth for scope and approach.

## Scope

Retire the whole letter-number use-case codename taxonomy, not just
"G2". `working-docs/implementation/provenance/use-case-catalog.md`
defines a full scheme -- G1-G7 (generation), A1-A2 (aggregation), E1-E2
(enrichment), P1 (preservation), N1-N6 (Phase-2 native-backfill
checklist), plus others found the same way (R1, M1-M4, L6, L8, U1, C4,
K2, V1/V2/V4, O1-O3, S1-S5, Z0/Z1, T5, H1, F1) -- meaningful only against
that catalog's own numbering, meaningless to anyone (including future-us)
reading a docstring/comment in isolation.

2026-09-14 count via
`grep -rnoE "\b[A-Z][0-9]\b" src/ tests/ CHANGELOG.md working-docs/ docs/`:
over 500 occurrences total, heaviest in `src/` at `deps.py`,
`deps_installed.py`, `deps_license.py`, `provenance.py`, `enrich/base.py`,
`_license.py`, `project/pyproject.py`, `project/poetry.py`, and in
`tests/` across a dozen-plus modules.

## Approach

Replace every `src/`/`tests/`/`CHANGELOG.md`/`docs/` occurrence with a
stable, self-explanatory name (e.g. `field-conflict` for G2,
`enrichment-override-lineage` for E1, `ai-inferred-marker` for E2,
`unification-rationale` for A1, `artifact-metadata-preservation` for
P1 -- exact names TBD at implementation time, one per catalog entry
that's actually referenced in code). `working-docs/` may keep the
short codes as shorthand for its own planning history, since that's
internal-only and never shipped to a user.

New code from 2026-09-14 onward (the installed-dist-info-source
feature) already avoids "G2" outside `working-docs/`; this item is the
backlog to clean up every pre-existing occurrence of every code, not a
rename done in passing inside an unrelated PR.

Sizeable, mechanical-but-not-trivial (a docstring's code often carries
real meaning that must survive the rename, not just a find-replace) --
likely worth its own dedicated PR per code family (G-series, N-series,
the rest) rather than one giant diff.

## Opportunistic path

`working-docs/`'s own hygiene rule (AGENTS.md -- trim a grown roadmap
bullet out to its own file, split an oversized doc, move a completed
item to `implementation/`, retire a superseded one to `archive/`)
already means `working-docs/*.md` files get touched/rewritten
periodically for unrelated reasons -- whenever such a reorg/trim/split
touches a file that defines or uses one of these codes
(`use-case-catalog.md`, `multi-source-conflict.md`,
`role-vocabulary.md`, `annotation-provenance.md`, etc.), replace the
code with its stable name in that file as part of the same edit, then
update whichever `src/`/`tests/` occurrences that doc's own
cross-references point at. No need to wait for a dedicated cleanup PR
for the subset that a reorg was touching anyway.
