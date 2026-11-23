---
Created: 2026-11-23
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 16 (wheels and embedding): steps, tests, gates, risks

See also: [message-catalogue-pr16-plan.md](message-catalogue-pr16-plan.md)
(counts, sites, probes, contradictions, design, rulings Q1 to Q20),
[message-catalogue-pr16-build.md](message-catalogue-pr16-build.md) (the
build log), [message-catalogue-pr15-build.md](message-catalogue-pr15-build.md)
(the gate commands reused here). Reference tree: `main` at 01d1a726.
Section numbers continue the plan's.

## 6. Steps and agents

Step 1, **Opus** (attacker text, ZIP semantics, the classifier). Fence:
`src/pitloom/messages/**`, `core/wheel_dist_info.py`,
`core/archive_member_names.py`, `_wheel_sbom_location.py`,
`_sbom_format.py` (the cross-check causes), `scripts/message_inventory/`
(`_scope.py`, `_relay.py` for Q9), `mkdocs.yml`,
`tests/messages/test_wheels*.py`. Entries, fields and `SAMPLES`, the
refusal constructors, `warn_archive_member`, the mismatch helper; masking
order mask, cut, escape for S7's values; `--write` the reference; measure
pages; the import-cycle test both orders.

Step 2, **three Sonnets** in parallel (common brief as PR 15's: CLAUDE.md,
British English, ASCII comments, no `%r`, messages only through `emit` or
helpers, no generated pages, no baseline, no git writes, no `sed -i`,
touched tests only, report every changed stderr text, the Windows notes).

| Agent | Fence | Work |
| - | - | - |
| A (conversions) | `_embed_wheel.py`, `embed.py`, `_embed_stale.py`, `_embed_generate.py`, `extract/wheel.py`, `extract/project/_sdist_scan.py`, `core/_models_wheel_build_and_read.py`, `cli/commands/{verify_wheel,validate_wheel,embed_wheel,_embed_wheel_batch,utils}.py`, `plugins/hatch.py`, `id_registry/_sbom_read.py` (Q12); pinned tests under `tests/assemble/test_{embed,verify,validate}_*`, `tests/core/test_{wheel_dist_info,archive_member_names}.py`, `tests/extract/test_wheel_*`, `tests/extract/project/test_{sdist,hatch_hook}_*` | sections 1 and 4.3 |
| B (docs, skills) | section 4.6 files, `CHANGELOG.md` | quotes to the regenerated text with `[code]`; P1's false claim removed; a fresh read of each changed `SKILL.md` |
| C (new tests) | `tests/messages/test_wheels_surfaces.py`, `test_wheels_hostile.py`, `tests/_message_drift.py`, `test_drift_quotes.py` | section 7 |

Step 3, **Haiku sweep** (after A; no `src/`): grep `tests/` and `scripts/`
for `wheel refused`, `SBOM/wheel`, `recommended`, `no validator`,
`identity unknown`, `-- skipped`, `recorded as`, `Multiple SBOMs`, `no SBOM
found`, `removed stale`, `floored`, `byte order mark`, `too old for PEP
770`, `ignoring case`; 37 test files hold one today (V). Update, run each,
report files over 450 lines.

Step 4, **Opus integrate**: `--write`, `--write-baseline` (expect 44),
page sizes, the stderr sweep (section 8), review rounds (a fresh-context
Opus on the diff, with the Windows notes), Gates A and B, working docs.

## 7. Tests (one per boundary)

- Every line through `template_problem`; each `SAMPLES` value renders.
- Hostile names (`test_wheels_hostile.py`): a member `a\nWARNING: x`, an ANSI
  escape, `https://u:pw@h/m.py`, a 64 KiB name, a `'` and a `"`, a NUL
  (raw-patched bytes: `ZipInfo` cuts at NUL, V), a 10 MB `METADATA` `Name`
  in S7; each prints one line, masked, quoted, no forged `[code]`
  (`trusted_message`).
- Surfaces: each code on each surface of 4.5 (CLI stderr and exit, library
  `pitloom_code`); `wheel` vs `embed-wheel` on P1's wheel.
- Regressions failing on base: P1 (skills), P2, P3, P4 (no generation:
  spy), P5 wording, P7.
- Determinism: `embed-wheel` twice with `SOURCE_DATE_EPOCH` gives the same
  bytes; E4 at `SOURCE_DATE_EPOCH=0` and the ZIP entry dated 1980-01-01.
- Classify each new file (`-m platform --collect-only`): paths, archives
  and encodings, so mark `platform`.

## 8. Verification

Stderr sweep, HEAD versus the tree, offline: the probe wheels of section 2
(plain, signed, `--allow-signed-wheel`, non-conforming, two `.dist-info`
renamed and wheel-named, other `.dist-info`, no `METADATA`, not a ZIP,
duplicate, backslash duplicate, raw NUL, damaged member, unsafe members,
two SBOMs, name mismatch with and without `--fail-on-mismatch`, `.json`
extension, unknown format, CycloneDX, invalid SPDX 3); `embed-wheel --sbom`
with a byte order mark, a mismatch, `--allow-mismatch`; `SOURCE_DATE_EPOCH=0`;
`--sbom-basename ../x`; `--project-dir` of another project; a cwd with
`pyproject.toml`; stale and kept SBOMs; an sdist with a shared project
path; `--allow-build` with an unsafe member; the hook with a clashing
`sbom-files` entry. Expect: identical stdout, SBOM and wheel bytes, exit
codes (except P4's timing), every changed line with `[code]` and the
ruled wording.

Gate A: PR 15's command list (absolute `PYTHONPATH`, every exit code read
directly); coverage of `messages/_wheels*`, `wheel_dist_info`,
`archive_member_names`, the embed and verify modules;
`scripts/manual_cli_checks --only '3,4a,12,13,16,17,S2,S3,S7,S8,B1,M/completeness'`
(`4b` with `--network`).

Gate B: mutation testing (refusal constructors, the `.dist-info` choice,
`warn_archive_member` kinds, the mismatch helper); the full manual run
(`-j 8`); the parity and determinism harness; the Windows dry-run below; a
fresh-context sweep; a fresh read of both changed `SKILL.md`s; PR label
`test-all-os` (paths, archives, encodings), with `Unit tests` and `Build
wheels` run on the head after it.

Windows notes for every brief: `ARCHIVE=` is the file name only (never a
`\` directory); member names come from `orig_filename` (OS-independent) and
`\` is normalised to `/`; `PureWindowsPath` for E7's name; `os.chmod`
spied, not asserted bit for bit; `write_bytes` for `METADATA` fixtures
(CRLF changes a digest); `os.replace` over an open file fails on Windows;
case-insensitive H3 and `.dist-info` collisions (known bug).

## 9. Risks (ranked)

1. **Attacker text** in member names, `METADATA` values and validator
   text: quoting and masking must happen in the writer, not at call sites;
   S7 is unbounded today. Mitigation: hostile tests, `trusted_message`.
2. **Refusal type change.** `WheelRefused` gaining `CodedValueError` must
   stay a `ValueError` (callers catch `(ValueError, OSError)`); the model
   scan catches it too. Mitigation: a test per caller.
3. **Page sizes** (`files`, `targets` near 27 KB). Mitigation: step 1
   measures; Q17's fallback.
4. **Pins outside the fences**: 37 test files, `_checks_wheel.py`.
   Mitigation: the Haiku sweep and the full suite.
5. **P4's early check** must not refuse a name `sbom_base_name` accepts
   today (`x.spdx3.json` stripped). Mitigation: one test per spelling.
6. **Inventory blind spots**: the lambda (section 0); a coded helper taking
   its entry as a parameter may read as forwarding. Mitigation: a fixture.
