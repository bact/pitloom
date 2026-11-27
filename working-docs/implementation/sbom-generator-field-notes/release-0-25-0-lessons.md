---
Created: 2026-11-27
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: cutting 0.25.0 (pre-release review to publish)

See also: [README.md](README.md) (index of these notes),
[process-lessons.md](process-lessons.md) (earlier release and review
lessons), [ci-platform-subset-on-prs.md](ci-platform-subset-on-prs.md) (the
label rule the CI item below repairs),
[spdx-modelling.md](spdx-modelling.md) (licences in SPDX 3).

0.25.0 was tagged and published on 2026-11-27 (bump #564). Its theme was the
message catalogue: uncoded message sites went from 455 at v0.24.0 to none.
These items cover the last stretch, from the first pre-release review to the
PyPI page.

## 1. A pre-release review finds what per-PR reviews cannot

Every PR from #481 to #557 had its own review rounds. A first review of the
whole range v0.24.0..main (#558), one read-only agent per surface (CLI,
library, hook, Action, ID registry, skills and plugin, docs, the catalogue,
plus a "downstream" agent that read only the docs and skills), found 71
findings, 5 of them release blockers. Examples: an empty `project_dir=""` read
the current directory, `add_dataset("")` hashed it, `--creator-name ''` gave a
traceback, and a skill required a Pitloom version that never shipped. Each
sat where two changes met: a library parameter and its CLI twin, a message
code and the skill quoting it. A second "seam" check on the two combined fix
PRs (#559 and #560) found three more gaps that neither PR showed alone.

Do: before a release, review the whole release range by surface, not PR by
PR, and recheck the combined fix PRs before merging the last one.

## 2. A dependency's new answer shape can switch a rule off with every test green

#554 ruled that a licence file holding several licence texts gives no licence
and ends the licence-file search. It read the list of texts from the first
match LicenseID's `detect()` returned. LicenseID 0.9.4, released the day of
the cut, returns no match for such a file and lists the texts through a new
`texts()` call. The rule never fired again: numpy's text as `LICENSE` plus an
Apache text as `COPYING` gave `Apache-2.0`. The full suite (31,446 tests)
passed under 0.9.4 because the "ends the search" test used a text 0.9.4 still
flagged, every fixture project had only one licence file, and the test fakes
did not model `texts()`. An independent second opinion on the version bump
found it, not a test. Fix #563 asks `texts()` when nothing matched and raises
the floor to 0.9.4.

Do: on a detector upgrade, run a before/after sweep through the real library
over projects with more than one licence file, and make fakes answer every
call the code makes.

## 3. The same licence file, two detector versions, two answers

sympy's `LICENSE` holds four BSD-3-Clause texts and latex2sympy's MIT text.
LicenseID 0.9.3 reported MIT only; 0.9.4 lists all five texts. Under the #554
rule Pitloom now reports no detected licence for it, where 0.24.0 would have
said MIT. Across 388 real licence files, 7 several-texts files changed answer
and no single-licence file did. An SBOM's detected licence for such a package
depends on the detector version, which is why Pitloom records the tool and
version in each field's provenance (`Tool: licenseid==0.9.4`).

Do: treat a several-texts licence file as "no single answer" rather than
the first or the most specific match, and record the detector version with
the answer.

## 4. "Green" CI can mean the full legs never ran

On a pull request, Windows and macOS run only the `platform` tests unless the
PR has the `test-all-os` label (#467). The choice was read from the event
payload. A push and the label within a second start two runs in one
concurrency group; the newer cancels the older. When the push's run was
queued last, it cancelled the labelled run and, its payload predating the
label, ran the subset: #563 showed green with about 21,000 tests on macOS and
Windows instead of about 31,000. A later push picks up the label correctly,
and an unrelated label (`documentation`) starts a run of its own that cancels
nothing. #566 reads the PR's current labels from the API when the job runs,
failing open to every OS.

Do: read mutable state (labels) at job time, not from the event payload; and
before calling a PR merge-ready, check each OS leg's test count, not only the
tick.

## 5. Compacting a changelog changes what it says

At the cut the `[0.25.0]` section was compacted from 103 bullets to 57 by
merging bullets on one topic. An independent fidelity check of old against
new found three merges that attached a fact to the wrong subject (a refusal
that applies to `id import` only, read as also applying to `embed-wheel`; "no
warning before the error" for PyPI URLs only, read as also for Git URLs; a
documented caveat read as new behaviour) and eight user-visible facts lost.

Do: after merging changelog bullets, have someone compare old and new bullet
by bullet before publishing.

## 6. The README is the PyPI page

The README's 27 relative links (`docs/cli.md`, `./examples/`) worked on
GitHub and broke on PyPI, which renders the file as is. #565 points them at
the docs site and GitHub, written as reference-style links so the text reads
cleanly. It landed after the tag, so 0.25.0's PyPI page keeps the broken
links.

Do: check the README's links as PyPI will render them before the tag.
