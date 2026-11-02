---
Created: 2026-11-02
Last-Modified: 2026-11-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: a bug ledger needs a severity scale (the known-bugs split)

See also: [README.md](README.md) (index of these notes),
[known-bugs.md](../../design/known-bugs.md) (the new index and its severity
scale), [process-lessons.md](process-lessons.md) (earlier file splits, #307),
[maintainer-decision-log-oct30.md](maintainer-decision-log-oct30.md) (the
definition of "serious" used for the 0.22.0 cut),
[open-research-questions.md](open-research-questions.md).

PR #417 (merged 2026-11-02 14:20 UTC, `e93078cb`) split the project's bug
ledger. The split was driven by file size. Doing it showed that the ledger had
never had a severity scale. This note records the numbers, how the split was
shown to be loss-free, the ranking rule chosen, and what is still missing.

## 1. The problem in numbers

| Fact | Value | Source |
| --- | --- | --- |
| `known-bugs.md` before the split | 41,233 bytes | `git show b12aa4d1^:...` (measured) |
| `known-bugs-p3.md` before the split | 22,775 bytes | same |
| Project hard limit per file | about 800 lines or 30 KB | `AGENTS.md` |
| The larger file over that limit | 11,233 bytes | arithmetic |
| Both files together | 64,008 bytes, 34,008 over one file's limit | arithmetic |
| Checkbox entries in the two files | 174 (103 + 71); 124 open, 50 ticked | my recount |
| Entries in the new index table | 177 (127 open, 50 fixed) | `known-bugs.md` |
| Open entries tagged "Found" (no P level) | 48 | index table |

Two figures in the brief for these notes did not reproduce: "179 entries" (174
checkbox lines; 177 in the index table; the difference of three, all in the
open count, is *not explained*) and "38 KB over
the hard limit" (34,008 bytes over, counting both files against one file's
limit; 11,233 for the larger alone). The "about 48 open entries
unprioritised" did reproduce. Treat the brief's two as unverified.

- **Effort tags stood in for severity.** About half of the entries carry a size
  in the bold title: of 174 entries, my pattern finds a tag on 90 (71 `S`, 6
  `S-M`, 6 `doc`, 3 `M`, 2 `low`, 1 `idea`, 1 `S each`) and none on 84. The
  pattern is a heuristic; some tags may sit in another shape. The index says
  what the tag is: "effort, not harm".
- **The "priority tier" was the section an entry sat in**, and the section
  names are release-planning labels: P0 "In 0.21.0", P1 "Registry v3 in
  0.21.0", P2 "0.21.0 and later", P3 "After 0.20.0". Those say *when someone
  looked at the entry or planned it*, not how bad it is.
- **The open entries are skewed to the weakest labels.** 66 of 127 open
  entries are P3 (52 %) and 48 are "Found" (38 %); P0 has 1, P1 has 3, P2 has
  7 (index table). A ledger whose top three tiers hold 11 of 127 entries does
  not rank anything within the other 116.
- **No entry has a field for harm or likelihood.** The nearest thing in the
  project is the "serious" definition of the 0.22.0 cut (a crash, silently
  wrong data or identity, or a leak), used to choose six bugs. It was never
  applied to the whole ledger.

## 2. Showing the split lost nothing

The split moved every entry, "unchanged", into eight parts by category
(`working-docs/design/known-bugs/`, 100 to 246 lines each, 1,298 lines in all;
the index is 143 lines). The commit messages of #417 name two commits: the
move (`b12aa4d1`) and a second that fixes links and anchors (`bf1b7407`),
because the first left links to the dissolved `known-bugs-p3.md` and to three
old anchors (`#p0-in-0210`, `#p2-0210-and-later`, `#found-2026-10-29`)
pointing nowhere.

The checks I ran on 2026-11-02 against the two parents of the move:

1. **Entry-line set.** Take every line that starts a checkbox entry
   (`- [ ]` or `- [x]`), stripped. Old files: 174 lines, 174 distinct. New
   parts: 174, 174 distinct. In the old not in the new: 0. In the new not in
   the old: 0. So no entry was dropped, duplicated or retitled.
2. **All non-blank lines.** 80 old lines are absent from the new parts, by
   kind: 16 headings, 32 lines containing a Markdown link (the commit message
   says relative links "gain one `../`"), and 32 others: the old header block,
   scope notes, the "From ..." section intros and the planned-releases bullets,
   which the index replaced. The "other" 32 were read, not diffed
   mechanically; none is an entry.
3. **Links and anchors.** The maintainer's second commit exists because this
   check found breakage. I did not rerun the link check on the whole tree.

What this does not show: that an entry sits in the right part (a judgement),
or that a multi-line entry body is intact (check 1 compares the first line
only; check 2 covers the other lines, as lines present somewhere, not in
order). A reorder inside an entry would pass both.

## 3. The ranking rule that was chosen

"No entry was re-ranked when the file was split." Inside a part an entry sorts
by (1) priority tier, (2) size tag in the order `M`, `S-M`, `S`, `doc`,
`low`/`cosmetic`/`idea`, none, (3) its place in the earlier file.

- **Why not re-rank.** A split that also changes meaning is two changes; a
  reviewer cannot tell a lost entry from a re-ranked one. The split was kept
  mechanical, and the missing scale was written down as a gap, not invented.
- **An odd choice, not explained.** The size order puts the largest effort
  first (`M` before `S`). That is neither easiest-first nor worst-first. The
  index states the order and its limit ("it orders entries only within a
  tier") but gives no reason for the direction. *Reason not recorded.*
- **Rejected alternatives.** None recorded. Candidates visible from the
  material: a harm-based scale added in the same change (rejected implicitly by
  the no-re-ranking rule); one file with a table of contents (it was the
  starting point and the size problem).

## 4. What generalises

- **A file-size limit forces a classification decision.** Splitting needed a
  part for each entry; the categories (AI model readers, licences, ID registry,
  messages, remote sources, extraction, surfaces, process) were chosen by what
  a bug touches, with a rule for a bug between two parts: where its fix would
  land.
- **A ledger needs two axes before it needs a thousand entries:** harm (what
  the user loses) and cost (what the fix takes). The old ledger had one of
  them, and it was the cost.
- **A planning label drifts into a severity label** when nothing else is
  available: "P3" is read as "unimportant" by anyone who does not know it
  means "after 0.20.0". Name a tier for what it measures.

## 5. Open

- **A harm-based scale.** What would the levels be? One starting point is the
  0.22.0 "serious" definition (crash; silently wrong data or identity; leak),
  with "wrong but flagged" and "cosmetic" below it. Whether the 48 "Found"
  entries sort cleanly under it was not tried. See
  [open-research-questions.md](open-research-questions.md).
- **Does a scale change what is fixed?** The 0.22.1 scope was chosen as "small
  remaining bug fixes"; an effort-only ledger is consistent with choosing by
  size. Whether a harm scale would have chosen differently is unknown.
- **Part size.** The rule is "keep each part under about 350 lines"; the
  largest, AI model readers, is 246 lines with 43 open entries, all P3.
