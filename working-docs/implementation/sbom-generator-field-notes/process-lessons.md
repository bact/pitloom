---
Created: 2026-10-05
Last-Modified: 2026-10-16
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
- **Review the release diff once more, with fresh eyes, after the PR
  review rounds.** Eight review rounds of #294 left an exponential-time
  walk in the README enricher (see determinism-and-parsing.md, YAML
  aliases) that two fresh-context reviewers of `v0.20.1..HEAD` found in
  minutes, along with three cross-format spelling gaps. The cause was a
  late fix (the lone-surrogate walk) that broadened what code touched.
  Do: after the last PR round, review the whole release range by area
  with fresh agents; a fix added in a late round is the likeliest place.
- **A release verification is its own artefact.** For 0.20.2: byte
  comparison of PyPI vs release assets, `verify-wheel`, `validate-wheel`,
  `spdx3-validate`, a Merkle root recomputed by an independent script
  (223 payload files, `.dist-info` excluded), `gh attestation verify`
  (silent when not on a TTY: use the exit code) and `sigstore verify
  github` on the release copies. 240 `software_File` = 223 payload + 17
  directories.
  Do: record the evidence in the repo the day of the release.
- **A bugs list needs a re-homing step at release time.** Moving a
  released section to the completed list would have archived three
  unfixed bugs that sat under "in 0.20.1". Move only ticked items; the
  open ones go to the next release's section.

## Extras, authors and copyright on every route (#300, 2026-10-09 to 14)

One PR, about 15 delegated rounds, 140 files changed, 21 numbered open
questions left. Numbers for a method section; the maintainer made every
ruling, agents did the reading, building and reviewing.

- **Split the agents by file ownership, and run the gate only when all land.**
  Up to four agents ran at once, each told which files it owned and which not
  to touch. A full-suite run on the shared tree is red while another agent is
  mid-edit (80 failures once, all in the author code), so the gate (tests,
  coverage, linters, manual CLI checks) ran after the last agent reported.
  Do: name the files each agent owns; trust a shared-tree red run only after
  every agent has stopped.
- **A fresh read-only review after every batch found regressions the
  previous batch introduced.** The "never split `Author`" ruling lost people
  that HEAD recorded; the next review reproduced six findings against both HEAD
  and the tree, then mutation-tested the new branches (24 mutants, 23 killed).
  Do: give each review the HEAD copy (`git archive`) to run alongside the tree.
- **Ask the maintainer when a request overrides an earlier ruling.** "Never
  split structured authors" met "split `Author-email` alike"; one question
  with three options (each with its cost) settled it in one answer and kept
  the rule from flipping a third time.
- **Measure the producers before designing the reader.** Hatchling 1.32.3,
  setuptools 84, flit_core 4.0.2, pdm-backend 2.4.9, poetry-core 2.4.1 and uv
  0.10.4 were run on probe projects; the matrix (what each writes for authors,
  extras, self-references, markers) replaced three assumptions, one of them
  the premise of a planned feature (uv and pip write no PEP 751 extras keys).
- **Verify a supplied list before using it.** A list of ten "projects that use
  `pylock.toml`" was wrong in six places (a lock only on `main`, an issue about
  something else, a scanner fixture that is not valid PEP 751, a project with
  no lock). Each entry was checked for producer, file, version, size and
  licence, and the report lists what was excluded and why.
- **Keep working notes committed.** An uncommitted edit to the open-question
  list was discarded by accident and regenerated from the conversation;
  commit `working-docs/` in small steps, as the code is.
- **State the evidence behind a counter.** "62 packages" in a fixture README
  was a count of `[[packages]]` entries (including the project itself and two
  `click` entries); the test now says entries.
- **Decide quickly what is out of scope.** The stopping rule was: the
  in-flight change lands, one delta review finds nothing Medium or higher, the
  rest is recorded as numbered open questions. It held; 21 items moved to
  follow-ups.

- **Disjoint file ownership per agent, and rerun before blaming.** Six
  agents fixed one PR in parallel, each owning named files. Intermittent
  failures (four permission tests, a mypy count, an `E501`) appeared in
  combined runs while another agent was mid-edit, and vanished when run alone
  or after the agents stopped. Do: gate once after all agents land; a failure
  in a file nobody owns is first a concurrency artefact.
- **A reviewer who ran a repro beats the test suite.** After 12,452 passing
  tests, 100% branch coverage and a clean linter set, three read-only
  reviewers found one wrong-output merge bug, a reused-id hole, a regression
  against HEAD and a placeholder-as-key bug. What they had that the author did
  not: a `git archive HEAD` copy to diff against, instructions to report only
  reproduced defects, and no stake in the change. Do: brief each with the
  intent, the diff command and "run it", and verify a finding yourself before
  fixing.
- **Defer a big redesign with its plan intact, then build it.** The path-key
  redesign was drafted by a planning agent in one pass (three options, a
  surface-by-member matrix, ten decisions) and deferred by the maintainer as
  too big for the PR (2026-10-15); built the next day with the plan as the
  checklist, then folded into a record of what was built
  ([path-keys-lessons.md](path-keys-lessons.md)).

- **Review the fix round too.** The second review found three defects that the
  first round's fixes had introduced or left: a skipped element's id not
  reserved, an error scoped to explicit input also hitting the implicit
  roots, a conflict branch that skipped the content-hash fold. A third,
  focused one on the last change (the unknown-wheel work) found a missing call
  site. Do: review the delta of every fix round with a HEAD copy to diff
  against, and keep each review to one area.
- **Say which numbers a claim rests on.** "100% coverage" was true on three
  of four CI legs and false on the one that is uploaded. Report coverage per
  leg that is reported, not per machine that ran it.

## Producer and parameter count (#306, 2026-10-15)

One PR: a planned item built by mixed agents (about ten work packages),
three review rounds before the first commit (61 files), then a CI failure and
two short delta rounds. 12,958 tests, 100 % branch coverage at the end.

- **A reversed decision is worth writing down as reversed.** A merge rule
  was changed to spare a rare case, found to remove the note from the main
  route (a fragment's count from a model card), and put back the same day. The
  decision doc says "tried, then reverted, because", so the next change does
  not retry it. Do: list every writer of a derived field before narrowing its
  rule.
- **A user's catch beats three reviewers on the principle.** The plan was
  approved by two agents and one maintainer pass; the maintainer then asked
  that the package say its `ai_hyperparameter` stands in for a missing field,
  which none had raised. The constant note came out of that. Do: put the
  mapping's weakest point to the owner while the plan is still cheap.
- **Two independent reviews of the same diff, different focus, find
  different things.** One focused on mapping consistency, one on correctness:
  the first found a provenance-key convention clash and a Hub count whose
  provenance vanished in `minimal` mode; the second found a silent bound and
  a warning flood. Later rounds on narrower areas found one real bug in the
  last delta (free-text `7B` given the note) and several stale or over-broad
  statements in docs and skills.
- **A skill is code nobody tests, so give it a reader who has not seen the
  change.** The agent that edited the skills checked its own work; an
  independent fresh-eyes read ran the recipe end to end and found a
  false-positive check that would loop an agent. Do: run each recipe a skill
  gives, on an input where it should do nothing.
- **Keep the gate separate from the editors, and read the CI log.** The
  failing job was one of four (the rest were cancelled by fail-fast); the log
  held the diff of two SBOMs, and the differing bytes were one file hash,
  not the UUID that appeared first.
