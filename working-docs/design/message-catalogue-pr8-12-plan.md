---
Created: 2026-11-17
Last-Modified: 2026-11-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue PRs 8 to 12: config, lock files, project metadata

See also: [message-catalogue-migration-plan.md](message-catalogue-migration-plan.md)
(rows 8 to 12, R1 to R7), [message-catalogue-pr6-pr7-plan.md](message-catalogue-pr6-pr7-plan.md)
(how a past plan was built and where it needed rework),
[message-catalogue-pr8-9-config-plan.md](message-catalogue-pr8-9-config-plan.md),
[message-catalogue-pr10-11-lock-plan.md](message-catalogue-pr10-11-lock-plan.md),
[message-catalogue-review-rounds.md](../implementation/message-catalogue-review-rounds.md).

Status: planned 2026-11-17 on `main` 654d734e (#495 merged, 316 uncoded
sites). Config (8 and 9) and lock files (10 and 11) are built first, as two
PRs in two worktrees. Project metadata (12) is planned again with licence (18)
from the `main` that has them.

## 1. Order and structure

1. Lock files (10 and 11) merge first (smaller); config (8 and 9) second.
   The second PR merges `main` in (no rebase), reruns the generator and
   `--write-baseline`, and never hand-merges a generated file, the baseline
   or the tails of `_topics.py`.
2. Family 12 gets a contract (section 4), not a per-site plan: its sites are
   re-listed after 8 to 11 merge.
3. Orphans (32 sites outside a row) are assigned to an owning row in each
   planning pass; a final sweep PR takes what is left.

## 2. Rulings (maintainer, 2026-11-17)

1. **"Kept X over Y": a naming rule, not one code.** No generic
   `source-conflict`. Decision D: split a code only when the advice differs.
   The condition word is `conflict`; each code is `<subject>-conflict`,
   one per concept (the shipped `model-field-conflict`, `registry-conflict`
   and `registry-hash-conflict` are the precedent). Concepts found at the
   sites: a package pinned twice in one lock file (11, advice: regenerate);
   two sources where a fixed order picks one (12); fragment against fragment
   by merge order (15); a fragment overriding a generated value by design
   (15, an INFO decision, actor none); identity, where both are kept or names
   are unified (15, 17). Every conflict line names what it kept and what it
   dropped in its outcome clause, in lower case (`kept X, dropped Y`), not as
   `KEPT=` and `DROPPED=` keys (amended 2026-11-17: it matches the shipped
   `model-field-conflict` line, and a key would repeat the value in the
   subject); the advice reads "the SBOM states <kept>; <dropped> is not
   recorded" unless a concept needs other advice. The grid (one code per
   concept, field names, sentence shape) is in
   [message-catalogue-pr10-11-lock-plan.md](message-catalogue-pr10-11-lock-plan.md);
   each family applies it.
2. **Relaying a coded exception.** R6 is general: a site that catches a coded
   exception and prints its text forwards the code (`relay_extra`, `code_of`
   in `messages/_emit.py`), and a test per site checks `[code]` is present.
   Covers `_models_wheel_build_and_read.py` (14, 16) and `fragments.py` (15)
   as well as the PR 4 sites.
3. **R1 is forward only.** A family merged before R1 is not reopened inside a
   new PR; a deviation found is logged in `message-catalogue-review-rounds.md`.
4. **Owners of the overlapping modules.** 11 owns every requirement line and
   lock pin: `core/requirements.py`, `_poetry_requirements.py`. 12 owns file
   discovery and metadata: `_requirements_files.py`, `deps_installed.py`.

## 3. What every plan below contains (for weaker agents)

- A per-site table made by the AST (`python -m scripts.message_inventory
  --jsonl`, `_scope.in_scope`, `coded` false): file:line, level, current text,
  condition, code and variant, fields, owner row, agent tier.
- Known traps with a counter-example for each, sensitive areas, and the
  canary tests (a prefix stacked twice, a newline, `\x1b` and a lone
  surrogate in a value, a Windows path through `PureWindowsPath`, a repeated
  input said once, a line number in a CRLF file, fail-on-base with
  `PYTHONPATH` pinned, one test per surface: CLI, hook, library, Action).
- Forbidden shortcuts: a ratchet exemption by text; a new condition word
  without a ruling; a level change in a coding PR; `%r`; a helper that adds a
  prefix; dropping a said-once memo; editing a generated file or the baseline
  by hand; a block `pylint: disable`.
- An escalation list: every judgement call goes back to Opus.
- Agent tiers: Sonnet for sites and tests, Opus for entries, fields, helpers
  and review, Haiku only for mechanical checks.

## 4. Contract for family 12 (project metadata)

Written now so 8 to 11 do not move under it:

- 12 reuses the config-file code (`sdist.py:275`), the malformed against
  `file-unreadable` split rule set by 9 and 10, `requirement-invalid` from
  11, and the conflict grid of ruling 1.
- 12 owns `_requirements_files.py`, `deps_installed.py`, file discovery,
  `core/project.py:394` and `extract/_extract_utils.py:261`.
- None of the names above is renamed during review of 8 to 11.

## 5. Shared files and the order they are touched

Conflict-prone, from the review of PRs 6 and 7: `tests/fixtures/message-inventory/uncoded.txt`
(the `total` line), the tails of `src/pitloom/messages/_topics.py`,
`docs/message-codes.md`, `mkdocs.yml`, both skills' `messages.md` indexes,
`CHANGELOG.md`, `_fields.py`. The `files` topic page is near its 30 KB limit
(about 25 KB): each plan states its budget on it. Both PRs carry the
`test-all-os` label; `since` is 0.25.0 unless a tag is cut between them.

## 6. Open questions: accepted (maintainer, 2026-11-17)

All recommendations in both plans are accepted: config Q1 to Q9 and lock files Q1 to Q10, with the conflict grid fields in lower case (ruling 1). Q7 of the config plan changes an exit code (a bad `--creation-datetime` exits 2, not 1); Q7 of the lock plan fixes the uv said-once bug in the lock PR. Q9 and Q10 of the lock plan (`loom fragment list` reading lock files, ignored `--generate-hashes` requirements files) go in the roadmap as out of scope.
