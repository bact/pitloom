---
Created: 2026-11-04
Last-Modified: 2026-11-07
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# LicenseID 0.7.0 adoption: what was built (0.23.0)

See also: [adoption-plan.md](adoption-plan.md)
(the plan, its rulings and measurements),
[roadmap-completed.md](../roadmap-completed.md#shipped-in-0230-prs-434-446),
[license-pipeline.md](../license-pipeline.md),
[licences-and-licenseid.md](../../design/known-bugs/licences-and-licenseid.md)
(open entries).

Pitloom requires `licenseid>=0.7.2,<0.8` (0.23.1; 0.23.0 required
`licenseid>=0.7.1,<0.8`; 0.7.0: 2026-11-03). A declared
licence value is read by `licenseid.resolve(value, source="packaged")`, on
the SPDX License List the `licenseid` wheel ships, with no database; only
licence-text detection (`LicenseDetector().detect()`) needs one. Pitloom no
longer imports `py-spdx-license` (LicenseID still requires it).

## Stages

| PR | Stage | What it did |
| - | - | - |
| #437 | A | Pin; `resolve(..., source="packaged")` with no database gate; `detect()` for texts; `relay_licenseid_warnings()` says each `LicenseIdWarning` once as `WARNING: licenseid: ...` (`INFO:` for `variant not stated`); `canonicalize_license_id` deleted; CI builds the database with `licenseid update --source packaged` |
| #438 | B | Licence-text detection split out of `_license.py` into `_license_text_match.py` (moves only) |
| #439 | D | Docs and skills: preflight `licenseid update --source packaged`, detection only; new `WARNING: licenseid:` lines |
| #440 | C | LicenseID is the only reader of a declared value: Pitloom's own parser is gone, `assumed_only` and the other categories are accepted, rewrites cite `Tool: licenseid==V` (`+` also `Expansion-1`), not `Normalizer`; the 14 deprecated List names kept in `extract/_license_names.py` |
| #443 | E | Final gate (this record) and the ledger ticks |

## Final gate on `main` 54f79c57

- Full manual CLI checks: 551 pass, 0 fail, 22 known, 37 skipped.
- Wheel and sdist built with Hatchling (`--no-isolation`): no `AGENTS.md`,
  `CLAUDE.md` or `GEMINI.md`; `Requires-Dist: licenseid<0.8,>=0.7.0`, no
  `py-spdx-license`. In a fresh venv: `pip check` clean, `loom --version`,
  `verify-wheel` ok, `validate-wheel` valid, `spdx3-validate` exit 0.
- With `import py_spdx_license` blocked for Pitloom's modules (a
  `sitecustomize` shim; LicenseID may still import it): 21 fixture
  projects, 20 generate (the 21st is the invalid-version fixture, which fails
  the same way without the shim); the SBOMs are byte-identical with and
  without a licence database.
- Self-SBOM: byte-identical across three builds (`PYTHONHASHSEED` unset, 0
  and 4242); `licenseid` 0.7.0 is a runtime `dependsOn`; no
  `py-spdx-license` package.
- Surfaces: an isolated Hatchling build (offline wheelhouse holding this
  wheel, no database) reads `license = {text = "Apache2"}` as `Apache-2.0`;
  the Action install script installs the wheel; the library and the CLI give
  the documented `INFO:`/`WARNING:` lines for a missing database and the
  relayed `build v2 outdated` for a database built by 0.6.0. The real output
  of `licenseid update --source packaged` (fresh, current, 0.6-built) matches
  the skills' text.

## Sweep: 0.22.1 against 0.23.0

Before: tag v0.22.1 with LicenseID 0.6.0 and a 0.6-built database. After:
`main` 54f79c57 with 0.7.0 (answers identical with and without a database).
Inputs: 671 distinct values (the curated 366 and the 462 PyPI values of
LicenseID's `pypi_values_2026-10.tsv`, overlapping; "projects" counts the
PyPI projects that declare the value). Each value was classified with
warnings on (the `License` path) and checked as an SPDX-only field
(`License-Expression`).

| Difference class | Values | Projects | Examples |
| - | -: | -: | - |
| Value gained (text to id) | 83 | 390 | `"MIT"` to `MIT`; `GPLv3` to `GPL-3.0` |
| Value lost (id to text) | 8 | 0 | `-MIT`; `GPLv3 +` |
| Same terms, new order | 4 | 0 | `MirOS OR MIT`; `LicenseRef-pitloom-gap-000 OR Apache-2.0+` |
| Deprecated id renamed | 2 | 0 | `StandardML-NJ` to `SMLNJ`; with `OR MIT` |
| Provenance `Normalizer` removed | 125 | 1,763 | `(mit and mit)`; `GPL-2.0+` |
| Provenance `Tool: licenseid` added | 77 | 84 | `(mit and mit)`; `(MIT AND ISC) OR (ISC AND MIT)` |
| Provenance `Tool` version 0.6.0 to 0.7.0 | 48 | 1,679 | `APACHE 2.0`; `AGPLv3+` |
| Provenance `Expansion-1` added | 7 | 6 | `GPL-2.0+`; `GPL-2.0+ OR MIT` |
| Text reason reworded (in the `WARNING:` lines: 298 SPDX-only, 37 others) | 299 | 1,491 | `Unknown Expression 'Foo'` to `not found: Foo`; `""` to `empty` |
| `INFO: ... read as` new | 75 | 389 | `GPL v3`; `ISC License (ISCL)` |
| `INFO: ... read as` gone | 8 | 0 | the 8 lost values |
| `WARNING:` (not an expression) gone | 15 | 20 | `"MIT" or "Apache-2.0"`; `Apache2 OR MIT` |
| `WARNING:` (SPDX-only field) gone, new | 83, 8 | 390, 0 | the gained and lost values |

- Read silently (no `INFO:`, provenance only): 10 of the 83 gains, a quote,
  bracket or case change only (`"MIT"`, `[MIT]`, `licenseref-foo`), as the
  form-only rule of #440 says.
- Not in the corpus, probed apart: `AGPL-3.0+`, `GFDL-1.1+` to `GFDL-1.3+`
  and their `WITH` forms become `-or-later`; `MIT WITH AdditionRef-x WITH
  Classpath-exception-2.0` becomes text; `MIT or later` is `MIT+`.
- SBOM level (`loom project` on 21 fixture projects and 20 real-world
  sdists): the same classes (`MIT License (MIT)` and `Mozilla Public
  License 2.0 (MPL 2.0)` now ids, `Tool`, `Normalizer`). Eight concluded
  licences of dependencies differ only because the two virtual environments
  held different packages.
- Every class is in the 0.23.0 CHANGELOG entries of #437 and #440.

## Left open

- Ledger: the two-tags entry (both versions conclude nothing for two tags),
  the no-operands entry (operands are built; Q5,
  `simplelicensing_licenseListVersion`, is not), the warning-block overlap,
  the header-tag reader, `trust: none`, the lone CR and the 14 List names
  ([licences-and-licenseid.md](../../design/known-bugs/licences-and-licenseid.md)).
- Upstream: a short word detected as a licence, `\v`/`\r`/U+2028 read as
  space, `coverage` above 1, a library message naming `--db` and the network
  `licenseid update`, the undocumented once-per-process warning rule,
  deprecated List names, `trust` ergonomics, `components` filled for
  compounds only, the database's undocumented methods. An issue text is
  drafted for the maintainer.
