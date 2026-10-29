---
Created: 2026-10-28
Last-Modified: 2026-10-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Adopting licenseid 0.7.0 (Pitloom 0.22.0)

Status: draft, built on licenseid `main` of 2026-10-28 and its plan. Revise it
when licenseid 0.7.0 is released (see "What to re-check").

See also: [license-resolution-categories.md](license-resolution-categories.md),
[roadmap.md](roadmap.md), licenseid `working-docs/design/resolver-0-7-plan.md`
(tasks T13 and T14 are this work),
[known-bugs.md](known-bugs.md) ("licenseid 0.6.0 gives Pitloom no operands").

## 1. What exists today

On licenseid `main`: `ListLookup` (`listlookup.py`) and the shared list rules
(`listrules.py`), both no-behaviour-change groundwork. Not there yet: compounds
in `resolve()`, `operands`, `components`, `reason`, the packaged-list fallback,
newer-list-wins, prose forms, trove names. Pitloom cannot adopt any of it before
those land; what can be done now is measuring, and the preparations in section 5.

## 2. Data: the parity corpus through Pitloom

licenseid's `tests/fixtures/resolver_parity.tsv` holds 139 values (real
distribution metadata, Pitloom's test projects, the plan's synthetic shapes),
Pitloom 0.21.1's answer (`pitloom_0_21_1`) and the answer the plan expects
(`expected_0_7_0`). `scripts/licence_adoption_sweep.py` classifies each value with
the installed Pitloom and relates the three. On 0.21.1 it finds no drift from the
recorded column, and:

| Result | Rows | Meaning for Pitloom |
| - | - | - |
| same | 107 | no change |
| moves: text now, read by the plan | 18 | gains: 8 `trove_name`, 4 `assumed_only`, 3 `prose_form`, 2 `version_spelling`, 1 `listed_name` |
| moves: another expression | 3 | see below |
| undecided in the plan | 11 | 10 stay text; 1 is read today |
| read now, refused by the plan | 0 | no regression in the corpus |

The three moved expressions:

- `StandardML-NJ` and `StandardML-NJ OR MIT` become `SMLNJ` / `MIT OR SMLNJ`
  (deprecated equal successor, decision Q7). Intended.
- `(MIT OR ISC) AND GPL-2.0-only WITH Classpath-exception-2.0`: 0.21.1 keeps the
  operand order of py-spdx-license (`(ISC OR MIT) AND GPL-2.0-only WITH ...`);
  the plan's own order puts `GPL-2.0-only WITH ...` first. **Any project that
  declares a nested mixed expression gets different SBOM bytes.** Accept and
  announce, or ask licenseid to keep py-spdx-license's order for it (open).

The one undecided row Pitloom reads today: `MIT WITH AdditionRef-x`.
py-spdx-license cannot parse `AdditionRef-`; Pitloom reads it with its own gap
reader. If licenseid 0.7.0 drops it, Pitloom loses the reading. Ask licenseid
to decide it explicitly (plan finding F2 and upstream issue 1).

The 10 values that stay text include `Apache Software License`, `BSD`,
`Public Domain` and `Expat license`; the plan keeps them unresolved (family
names, no id, or deferred assumed readings).

## 3. Changes in Pitloom

| Area | Change |
| - | - |
| `pyproject.toml` | `licenseid>=0.7.0,<0.8`; move `py-spdx-license` from dependencies to the test group |
| `extract/_license_classify.py` (479 lines) | `_classify` = early exits (surrogates, `NOASSERTION`, `NONE`, `UNKNOWN`, several lines, over 200 characters) then `resolve()`. Delete about 250 lines: `_strict_parse`, `_canonical_string`, `_gap_term`, `_gap_expression`, `_GAP_*`, `_successor_id`, `with_successor_ids`, `_replace_deprecated`, `_DEPRECATED_SUCCESSORS`, `_looks_like_expression`, `_parse_locally`, `_ambiguous_deprecated_ids`, the py-spdx-license imports |
| `is_listed_name`, `same_licence`, `tag_deprecated_license_ids` | use the `listed_name` category and `operands[*].candidates`, not `get_spdx_license` |
| `extract/_license_resolve.py` (151) | accept `prose_form`, `trove_name`, `assumed_only`, `deprecated_ambiguous`; drop `expression`; delete `_FOLDABLE` (licenseid refuses the dropped-character cases itself); notes from `operands`/`reason` |
| `extract/_license.py` | `resolve_declared_value` needs no matcher; cache key adds `lists[0].source` and its version; text detection still needs the database (the `INFO:` of 0.21.1 stays) |
| Provenance | `Normalizer: py-spdx-license==X` becomes `Tool: licenseid==X` plus `Tool: py-spdx-license==Y` from `components`; later (T14) one `Resolution-n` per operand and the list version |
| `fuzz/fuzz_license_expression.py` | target `resolve()` through `classify_license`; the docstring no longer blames the library |
| Docs and skills | `docs/metadata-provenance-licences.md` (Normalizer row, the database wording), skills' known-limitations and the database notes, CHANGELOG with the behaviour changes |

`py-spdx-license` stays installed as a dependency of licenseid, and in Pitloom's
test group for a drift guard: every expression Pitloom accepts must parse with
the library. Its mypy override stays for the tests.

## 4. Behaviour changes to announce in 0.22.0

`StandardML-NJ` becomes `SMLNJ`; compounds with a respelt operand resolve, in
licenseid's canonical order; prose and trove names become ids (18 of 139 corpus
values); `LGPLv3` and the `GNU ... (GPLv2)` classifier names are recorded as
`assumed_only`, as written; a declared value no longer needs a database; the
SBOM depends on the `licenseid` and list versions, not on `licenseid update`.

## 5. Preparation that can start now

1. Keep the sweep script and run it against each licenseid change that lands
   (`HOME=$(mktemp -d) licenseid update --source packaged`, then
   `python scripts/licence_adoption_sweep.py <licenseid>/tests/fixtures/resolver_parity.tsv`).
2. Write the drift-guard test (every accepted answer parses with py-spdx-license)
   against 0.21.1 behaviour, so it runs unchanged after adoption.
3. Split `test_license_classify.py` into the parts that stay (early exits,
   weak and listed-name helpers) and the parts that go with the deleted code.
4. Draft the CHANGELOG entry and the docs edits as a branch, not merged.

## 6. Open questions for licenseid

- Order of a nested mixed expression (section 2), and whether it should follow
  py-spdx-license for byte stability.
- `MIT WITH AdditionRef-x` and `DocumentRef-` forms: read or refuse?
- Are `assumed_only` answers expected to be recorded by consumers? Pitloom's
  rule has been "recorded as written, with a note".
- When both a database and the packaged list exist, the newer list version wins;
  Pitloom's cache key must carry `source` and `version`.

## 7. What to re-check at the 0.7.0 release

Result keys and category names (`operands`, `components`, `reason`, `schema: 2`,
`by`); whether `expression` is removed; the canonical order; the sweep on the
released package; Python 3.10 support; the `<0.1` pin on py-spdx-license; the
release notes' migration line.
