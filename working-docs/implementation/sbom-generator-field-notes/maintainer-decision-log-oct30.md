---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: maintainer decision log, 2026-10-29 and 2026-10-30

See also: [README.md](README.md) (index of these notes),
[message-catalogue-decisions.md](message-catalogue-decisions.md) (decisions A
to M, not repeated here),
[evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md),
[message-catalogue-migration-plan.md](../../design/message-catalogue-migration-plan.md)
(the 0.22.0 cut),
[roadmap.md](../../design/roadmap.md),
[process-lessons.md](process-lessons.md).

One developer decides, with agents proposing options. This is a short
table of decisions that shaped the day's work, each with the reason and
where it is recorded. It is a log, not an argument; the notes it links
hold the evidence. "Recommended" means an agent's recommendation that the
maintainer accepted in the session (*session record*: the repository holds
the result, not the exchange). PRs not merged on 2026-10-30 at 15:20 UTC
are marked.

## 1. Decisions

| Date | Decision | Why | Recorded in |
| --- | --- | --- | --- |
| 2026-10-02 | Registry v3 Q-D: key a package by name plus version, purl-shaped | one id per release | `id-registry-v3.md` (history) |
| 2026-10-29 | A safety cap bounds reading, never reporting: if a property is known by a safe route, the SBOM states it with its evidence level | a missing hash meant both "unknown" and "skipped" | `AGENTS.md` (with #387); [evidence notes](evidence-levels-and-provenance-of-absence.md) section 1 |
| 2026-10-29 | Decisions A to M of the message catalogue (causes only; `/` for a variant; the code is stable from its first release) | a rename once codes are printed is a migration | [message-catalogue-decisions.md](message-catalogue-decisions.md) |
| 2026-10-30 | The 0.22.0 cut: model-stub causes (PR 1), unreadable files and directories (PR 2), `licenseid` 0.7.0 adoption, the licence provenance mapping (#384), the licence families (PR 18, after the adoption), and a list of serious known bugs. The rest goes to 0.22.x or 0.23.0 | the plan gives no reason for the scope; it notes the message ratchet keeps new uncoded messages out meanwhile | #398; `message-catalogue-migration-plan.md` |
| 2026-10-30 | "Serious" means a crash, silently wrong data or identity, or a leak; the list: a non-UTF-8 file name, a `:` in provenance text, a direct-URL dependency looked up by name, the hook's licence database in an isolated build, a package key without a version, a raw exception in a log line | a definition fixed in the plan; no reason recorded | 9c28a825; migration plan |
| 2026-10-30 | Cap `licenseid` below 0.7 until the adoption | 0.7 renames the API Pitloom imports | #401; CHANGELOG |
| 2026-10-30 | Model-stub family (D1 to D12): six codes by cause; `library-missing` names the extra; the cause in the SBOM is parked (D12); the catalogue gets its own page (D11) | see [model-stub-causes-catalogue.md](model-stub-causes-catalogue.md) | #404; `message-catalogue-and-skills.md` |
| 2026-10-30 | A direct reference is not looked up on PyPI; the `loom env` and private-index cases, and the version taken from Pitloom's own environment, stay open; the `INFO:` waits for a catalogue PR | see [name-keyed-lookups-and-direct-references.md](name-keyed-lookups-and-direct-references.md) | #405; known-bugs |
| 2026-10-30 | Two gates per PR (A before the first push, B before handoff); `-n 4` locally; reviewers read only; the CI matrix unchanged | the full suite and review machinery had run in every loop | #406; [ci-cost-and-two-gate-policy.md](ci-cost-and-two-gate-policy.md) |
| 2026-10-30 | Registry v4, D1 to D6: a range keyed by its resolved version; no migration (a v3 file is refused, never rewritten); a project's unknown version keys bare; local and dev versions are distinct; no pruning; `name@version`, not a purl | see [registry-key-must-carry-the-release.md](registry-key-must-carry-the-release.md) | #407 (**in review**); `id-registry-v3.md` section 6.1 on that branch |
| 2026-10-30 | Remote registry entries (a Hub model, a URL dataset) are a second PR in the same release, not part of #407 | its own decision set; a later PR would need registry format 5 | planning report D7 (recommended); known-bugs on the #407 branch |
| 2026-10-30 | Unreadable-file family: PR 2 is split in 2a then 2b; `text-malformed` has the effect `weaker` | the lone surrogate is not the source's character | #408 (**in review**); `message-catalogue-and-skills.md` on that branch |
| 2026-10-30 | Licence-families catalogue PR 18 moves to a later release; the `licenseid` 0.7.0 adoption waits for its release | the release is not out (below) | *session record*; **not yet in the repository** |

## 2. Notes on three rows

- **The 0.22.0 cut changed within the day.** The repository's plan at
  `c6a7f039` still lists the licence families (PR 18) in 0.22.0 (the
  table in `message-catalogue-migration-plan.md`, "Cut" column). The
  maintainer's later decision to move them to a later release, and to wait
  for `licenseid` 0.7.0 before adopting it, is from the session and is not
  yet written in the plan: **the repository and this log disagree until
  the plan is updated.** The adoption page (`licenseid-0-7-adoption.md`)
  says the adoption waits on the release.
- **`licenseid` 0.7.0 was not on PyPI.** The maintainer's check at about
  13:05 UTC on 2026-10-30 found no 0.7.0 (session record). I looked at
  15:14 UTC the same day: the index's latest `licenseid` was 0.6.0 (the
  `releases` list ended `0.5.0`, `0.6.0`). The cap below 0.7 (#401) is
  therefore still the right pin.
- **Caps bound reading, never reporting** is already in
  [evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md);
  the row is a pointer, not a new entry.

## 3. Recommendations the maintainer accepted

The catalogue families (#404, #408) and the registry key (#407) each had a
read-only plan from one agent, with options and a recommendation per
decision (D1 to D12, D1 to D6, D7a to D7h). In the records the maintainer
"took the recommendations" for #404 and #408 (`message-catalogue-and-skills.md`
on main and on the #408 branch). For #407 the rulings are written as the
user's (`id-registry-v3.md`, section 6.1 on its branch), with D6 rejecting
three options (exact pins only, a purl, stripping local and dev labels).
Whether the recommendation matched the maintainer's first view, or the
maintainer would have chosen differently without it, is not recorded.

## 4. Open

- A log like this is written after the fact from commit messages and design
  records; the exchange (what was asked, what else was weighed) is only in
  the session. How much of it should enter the paper notes is for the
  authors to decide.
