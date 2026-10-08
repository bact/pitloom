---
Created: 2026-10-05
Last-Modified: 2026-10-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: review and test process

See also: [README.md](README.md) (index of these notes),
[ai-model-scan-security-lessons.md](../ai-model-scan-security-lessons.md)
section 2 (the nine review rounds of #263: measure, alternate narrow and
wide, mutation testing),
[manual-cli-checks.md](../manual-cli-checks.md) ("When to run"),
[AGENTS.md](../../../AGENTS.md) ("Testing": the test tiers).

How the work behind #276 (licence typing, ten numbered review rounds),
#282, #283 and #284 was reviewed and tested, for a paper's method
section. Reviewers and fixers were AI agents with fresh contexts; the
human maintainer made every rule and scope decision. Items already in the
lessons doc, section 2, are not repeated.

- **Review each round's fix diff, not the whole PR again.** In #276, R9
  read only R8's fixes (one agent on `src/`, one on the tests for mutants,
  vacuous passes and the Windows dry run, one on the docs); each round's
  fixes were re-checked by the next.
  Do: give a fix round's review its own narrow scope, the fix commit.
- **A functional review by feature finds what diff reviews miss.** After
  nine rounds, R10 gave each agent one feature to trace end to end
  (input, extract, assemble, SBOM bytes) on every surface, against the
  real tool where one exists: the classifier pipeline, `setup.cfg`
  `file:` directives (56 scratch projects against setuptools 84.0.0),
  declared against concluded licences, the SBOM shape, and the test
  compaction. Two of the five reported a HIGH, both introduced by #276:
  a one-line `classifiers` value declaring the licence `Python` (see
  [determinism-and-parsing.md](determinism-and-parsing.md), section 2;
  the classifier reviewer found it too, as MED), and a shared licence
  element carrying the first package's provenance for every package.
  The SBOM-shape lens found no HIGH but a MED: licences not deduplicated
  across a fragment merge, fixed in #284.
  Do: after the diff rounds converge, review by feature against the
  real tool, one lens per agent.
- **Set the merge bar to agreement, not perfection.** Near the end of
  #276 the maintainer ruled: "as long as it produce the same value across
  surfaces, it is good for now, even it is a wrong or not perfect value."
  Fixed before merge: crashes, cross-surface divergence, invalid or
  nondeterministic output, regressions, security. Everything else went
  to a follow-up note
  ([license-pr276-followups.md](../../design/license-pr276-followups.md)),
  and the rule questions to the maintainer.
  Do: write down which finding classes block a merge before the review
  rounds start, so each finding sorts itself.
- **Tier the tests by cost and moment.** While editing: the touched tests,
  ruff, mypy. Each round: the full suite, every CI linter, each new
  regression test run against the base tree, branch coverage of the
  changed files, and only the manual CLI checks of the touched area
  (`--only`). Once before merge: mutation testing, the full manual CLI
  run, the Windows dry run, one fresh-context sweep. The fail-before
  check stays in every round: it is cheap and is the only proof a
  regression test works.
  Do: map each code area to its real-process checks, so a round runs
  seconds of them, not the whole matrix.
- **Prove a test compaction with coverage and mutants, not test count.**
  The gate per compaction: line and branch coverage the same or higher,
  a mutation run on the package's source with no new survivors, and
  every boundary case still named in a test id. In #276 a separate
  reviewer mapped each removed test to a counterpart and ran 9 mutants
  on both trees: 8 killed by the merged tables, the ninth surviving on
  both, so no loss.
  Do: compare before and after trees on the same mutants; a mutant
  surviving on both is a gap to note, not a regression.
- **A narrow correctness review of the last commit still pays.** In #284,
  a review limited to the commit adding `SAME_DOCUMENT` to
  `loom fragment list` found two real bugs. A best-effort per-record key
  (the project's own document id) raised on unreadable project metadata
  and aborted the whole listing; it is now `SAME_DOCUMENT=-` with one
  `WARNING:`. The new public `project_document_id()` did not call
  `configure_logging()`, which every public entry point must (3957608f).
  Do: let one unknown field make that field unknown, never the record or
  the run; check every new public function against the entry-point rules.
- **Ask a reviewer for the siblings of a found bug, probed live.** In
  #289, round 1 found the false database warning for two input shapes (a
  long id, a long `SPDX-License-Identifier:` tag). Round 2 was asked which
  other inputs reach the same failure on a healthy database and probed
  `licenseid` 0.4.2 on a copy: three more shapes (a `License:` field, a
  URL-form tag, a JSON `"license"` field), plus the inputs that do not
  trigger it and why (quoted FTS terms, chunked `IN` lists, `=` lookups). The known-bugs entry, the
  `xfail` table and the upstream handoff were widened to match.
  Do: once a bug is confirmed, brief the next round to enumerate every
  input path to the same failure, with a live repro per path.
- **Review the stated rule against the set it describes.** An Opus review
  of #294's display-escape rule found the code sound but the wording
  ("a code point a reader cannot see") wider than the fixed list: variation
  selectors, Hangul fillers (U+3164, U+FFA0) and rarer Cf code points are
  left out. The list is fixed, not derived from Unicode properties, on
  purpose: Python 3.10 ships Unicode 13 and 3.13 ships 15.1, so a derived
  set would change output between interpreters. A zero-width joiner is
  also needed in Thai, Persian and Indic text, so escaping U+200B-200D in
  prose produces false alarms.
  Do: state a fixed list as a fixed list, name what is excluded and why,
  and test every Bidi_Control and Default_Ignorable code point is either
  in the set or on a named exclusion list.
