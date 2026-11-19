---
Created: 2026-11-20
Last-Modified: 2026-11-20
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 14 (Hub and build): rulings Q1 to Q19

See also: [message-catalogue-pr14-plan.md](message-catalogue-pr14-plan.md)
(counts, sites, contradictions, design; section 4 of the same plan),
[message-catalogue-pr14-build.md](message-catalogue-pr14-build.md),
[message-catalogue-pr12-18-plan.md](message-catalogue-pr12-18-plan.md),
[message-frames-forward.md](message-frames-forward.md).

Status (2026-11-20): the user accepted Q2, Q11 (timeout fix PR first,
redirect checking on the roadmap), Q15 and Q19 (three PRs); every other Qn is
the planner's recommendation, not yet vetoed. Reference tree: `main` at
4c4f55c7.

## 4. Rulings (Qn: recommendation, then the alternative)

- **Q1. Frames for each prefix of the temp-directory line.** [Six frames, one per spelling today (3.1); the printed prefixes stay.] Alternative: drop the prefix on `temp-dir-left-behind` only (rule 1: the `DIR=` name already says the route, `pitloom-git-` and so on). But `plb-` and `pitloom-build-and-read-` would not say "build", and `BUILD_FRAME`/`SCAN_FRAME` are needed anyway.
- **Q2. `option-no-effect`'s two templates.** [Keep both templates as rule-2 literals, both built from `BUILD_PREFIX`/`OPTIONS_PREFIX`. `BUILD_FRAME` does not admit `option-no-effect`. A test asserts `BUILD_NO_EFFECT_LINE.template.startswith(BUILD_FRAME.template)`. No `OPTIONS_FRAME`.] Exact-code frames make the collapse over-trust: `Build: Options: FINGERPRINT=...` and `Options: Options: ...` would be read as genuine (C2). Alternative: collapse to one unprefixed template plus `OPTIONS_FRAME` and `BUILD_FRAME` (the migration plan's forward requirement), accepting that trust, or with Q4.
- **Q3. Hub/PyPI prefixes.** [`HF_FRAME` and `PYPI_FRAME` hold only `temp-dir-left-behind`.] Alternative: remove `Hugging Face source: ` and `PyPI source: ` and say the line unframed (two fewer frames; a decided wording change).
- **Q4. Per-line frame restriction.** [No: accept that `BUILD_FRAME` also trusts `library-missing`'s `FORMAT=` WARNING line. Document it, and pin it in a test as known.] Alternative: `Frame.lines`, a set of `(code, template)` pairs. Exact, but a mechanism change in `_lines._text_re` and the reference generator.
- **Q5. Build failures.** [One family, `build-failed`, with five lines, plus a separate `build-timeout` (its own condition word).] Alternative: one code per cause (`build-interpreter-missing` and so on; PR 13 Q5's `git-missing` precedent). Clearer codes, but five families on one page and the same advice repeated five times.
- **Q6. Temp directory condition and code.** [`temp-dir-left-behind`, condition `unwritable`, on the `build` page.] Alternative: the variant `temp-dir-unusable/left-behind` on `files` (26,059 B, about 27.3 KB after): a sibling of a different condition and effect.
- **Q7. Leftover processes.** [`build-processes-left`, condition `unsafe`: third-party processes outliving the build, INFO when killed, WARNING when unconfirmed.] Alternative: fold both into `build-failed`/`build-timeout`. Wrong, because the build succeeded.
- **Q8. `interrupted`.** [New family with the two signal lines. Also fold Ctrl-C (`__main__.py:85`, `print_error("interrupted")`, row 4's leftover) in as its ERROR line, ratchet -1.] Alternative: signal lines only, and leave the Ctrl-C line to a final sweep.
- **Q9. PR-C1.** [Rename only: `REASON_CODES` uses the message codes and `PENDING` empties. Update `docs/metadata-provenance.md:154`. No SBOM writer (none exists; a writer is an evidence-plan item).] Alternative: write `Evidence: not_measured | Reason: download-*` for a Hub file left out. An SBOM change that needs its own determinism and before/after sweep.
- **Q10. Unpinned revision.** [`hub-revision-unpinned`, WARNING, once per model, said where the revision is decided. The advice drops `hub_info['sha']`: the user cannot pass it.] Alternative: reuse `release-unpinned` with a Hub line (wrong subject, `PYPI=`, C4), or INFO (R1 decision, effect none). But the files may differ between runs, so effect weaker means WARNING.
- **Q11. Hub API timeout and redirects (C12).** [Before 14b, a separate small PR passes `timeout=` (a constant beside `METADATA_DEADLINE_SECONDS`) to `model_info`, `dataset_info` and `list_repo_files`, and makes the timeout line reachable. Redirect checking goes on the roadmap: replace the three calls with `fetch_json` through `HubFiles`, so the policy, caps and coded errors apply, and read the file list from `model_info`'s `siblings`.] Alternative: inside 14b. That mixes a behaviour fix with messages and goes against the PR 13 lesson to stage the work.
- **Q12. HF URL rewrite (H1).** [`target-ambiguous/hf-url`: Pitloom chose what a URL names by its rule, as `/git-page` does. `targets` 25,757 B grows to about 26.6 KB.] Alternative: `url-moved/hf-url` on `network` (no redirect happens, so "moved" misstates it).
- **Q13. The `Field(s) affected (skipped)` suffix.** [Drop it on the Hub lines. Say the loss in `outcome`, as `HubFiles.read` lines already do (`kind.outcome`), so one line shape serves files and API calls.] Alternative: keep the suffix with the `fields` field, as `model-field-unreadable` does. That needs `MODEL_FIELD` (`_field_tables.py:57`) widened to allow `-`: `model-index` fails today (V, run), and so does a joined list holding it.
- **Q14. H4 and H8 (the broad `except` around `read_card`).** [Remove it. Add a probe test that `read_card` never raises on: an unreadable file, a directory, non-UTF-8 text, a BOM, a file over the cap with the frontmatter unclosed, invalid YAML, a date of 2024-02-30, nesting deeper than the recursion limit.] Alternative: keep it and code the leftover cases as a `card-malformed` "could not be read" line, which states a condition that never happens.
- **Q15. `pypi_url._refuse`'s WARNING (P1).** [Drop it, as ruling 5 did for Git/PyPI. Every route lets the `CodedValueError` reach the ERROR line (`pypi.py:190,447`; to be tested per surface). Remove the `docs/pypi-urls.md:296` row.] Alternative: WARNING twins of all 8 `pypi-url-invalid` lines plus `relay_extra`. That keeps "a rejected input is logged as well as raised" for library callers but doubles the entry.
- **Q16. `build_and_read.py:110`.** [PR 16, with the archive-member family.] Alternative: code it in 14a as the first `archive-member-unsafe` line, which forces PR 16's family name early.
- **Q17. Hook lines.** [14c: K1 to K3 as `hook-no-effect` (condition no-effect, actor none, effect none; INFO lines for disabled, target not a wheel and editable variant, said with `HOOK_STEP_FRAME`). K4 as a Summary (R1: a count). hatch.py:86, 97 and 512 (Hatchling too old or unknown, SBOM name clash) go to PR 16 (PEP 770 embedding). Split `plugins/hatch.py` (538 lines) first.] Alternative: all 7 in 14c (ratchet 106).
- **Q18. `RELAY_FRAME` at ERROR.** [Drop `ERROR` from its levels (C10), with a test that no reader logs at ERROR.] Alternative: leave it as harmless.
- **Q19. Split.** [Three PRs in order: **14a** (frames, temp directories, signals, build, the option constant; Opus-heavy), **14b** (Hub, PyPI relay, PR-C1; after the Q11 fix), **14c** (hook). Each is reviewable alone, and each keeps the ratchet monotone.] Alternative: one PR 14 (about 60 files, 3 pages regenerated, a larger stderr sweep). PR 13 showed that one Opus round per concern finds more.
