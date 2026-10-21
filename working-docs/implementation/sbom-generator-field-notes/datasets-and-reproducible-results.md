---
Created: 2026-10-21
Last-Modified: 2026-10-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: datasets, who made the SBOM, and results that depend on the machine

See also: [README.md](README.md) (index of these notes),
[messages-and-surfaces.md](messages-and-surfaces.md) (surfaces that drift
apart), [process-lessons.md](process-lessons.md) (how the review rounds ran),
[../ai-dataset-linking.md](../ai-dataset-linking.md) (what was built),
[../recurring-bug-patterns-review-rounds.md](../recurring-bug-patterns-review-rounds.md)
(the war stories, PR #311 to #315).

Observations from 2026-10-18 to 2026-10-21 (PR #311 to #315 and the Lumina
demo). One developer, one session: each item says what was seen and where the
evidence is; none is a measured rate.

## 1. One dataset, several names, several capture routes

- **A dataset arrives under several names, and the capture routes disagreed
  on whether they were one.** A model card's `datasets:` list, a Croissant
  file and a Hub dataset card can all name the same dataset, in different
  spellings. Before #311 each reference became its own package; after it,
  one package per dataset and one relationship per role (`trainedOn`,
  `testedOn`). Before #314 the Python SDK (`loom.Run`) still keyed a dataset
  that is no file by its exact string, so `Org/Data` and `org/data` were two
  packages from the SDK and one from every other route. Same dataset, a
  different component count, depending only on how the SBOM was captured.
  Do: put the identity rule of an entity in one function and make every
  capture route call it; add a test that compares the routes' counts on one
  list of spellings (`tests/core/test_loom_dataset_dedup.py`).
- **A repository id is case-insensitive; a free-text name is not.** A Hugging
  Face repository id folds by case, so folding it is a fact about the Hub.
  The same fold on a free-text dataset name ("Not An Id") would merge things
  nobody said were one. The rule (`core/dataset_names.dataset_key`) lower-cases
  only a string that matches the Hub id grammar and collapses whitespace runs
  in all names.
  Do: fold a name only under a rule the naming scheme itself states.
- **"Not a file" is not "has no digest".** The first version of the SDK rule
  folded anything the hasher returned no digest for. That also covers an
  empty directory, a file over the hash ceiling and an unreadable file: all
  exist. A dangling symlink was a path for the registry (`lexists`) and not
  for the hasher. A review found it by running those cases.
  Do: test existence with the call that asks about existence, not with a
  value that is sometimes absent for another reason.
- **A fold is a decision the reader of the SBOM cannot see.** Keeping the
  first spelling hides the other. Each route that folds now says so in one
  `INFO:`; the SDK adds a `WARNING:` when the ID registry pins a different id
  under the later spelling, because only the first spelling is looked up.
  Declaration order then decides the name and the id; the messages say so.
  Do: when a merge is order-dependent, make the order visible in a message
  rather than hiding it in a tie-break.

## 2. Who made the SBOM is not who supplies the component

- **The generator's own identity leaked into the scanned package's
  supplier.** Lumina calls Pitloom and reported its own name as the SBOM's
  tool. The cause was `Tool(name="Lumina")` plus a rule that made the first
  creator the main package's `suppliedBy`: an automated agent that merely ran
  the scan became the supplier of the thing it scanned (PR #312).
  SPDX 3 has two relations here (`createdBy`, an Agent; `createdUsing`, a
  Tool) and `suppliedBy` is a third, about the component. A generator that
  collapses them states a false supplier.
  Do: keep three questions apart: who authored the document, with what tool,
  and who supplies the component; never infer the third from the first.
- **The checker counts a property, not its meaning.** A conformance result of
  `present` says the property exists, not that its value is right. Lumina's
  About page and README say so, and a smoke test pins the sentence.

## 3. A conformance count depends on the machine that produced it

- **Licence detection and licence-id canonicalisation need a database fetched
  from the network.** In a sandbox that could not download it, the licence
  tests fail (73 tests in 7 files, all with the same cause: "licenseid
  database cannot be used: database: empty") and an SBOM's licence fields
  come out different. The Lumina demo counts ("25 of 38 present", and so on)
  were first measured without the database and before #311, so the numbers in
  the demo guide are marked as unconfirmed until they are re-run on a machine
  that has it. Same input, same code, a different conformance result.
  Do: record the environment (database present or not, versions pinned by
  commit) next to every published count, and re-measure on the machine that
  will show it.
- **Compare a failing set, not a failing count.** With a constant 73
  environment failures, "73 failed" proves nothing about a change. The check
  that held was the set difference against a baseline run of the unchanged
  tree (stash, run, compare the sorted test ids): zero new ids.

## 4. A platform matrix finds what a green local run cannot

Each of these passed locally and failed on one CI leg (PR #311, #314, #315):

- **Windows (Python 3.11): `repr(path)` is not `str(path)`.** `repr` of a
  `WindowsPath` writes forward slashes and `repr` of a string doubles each
  backslash, so a message built with `{source!r}` never contained the path as
  the OS writes it. Four fuzz tests asserted `str(path) in message` and passed
  on Linux and macOS. One quoting helper fixed all routes; a control character
  in a name must still be escaped, or a file name with a newline splits an
  error over two lines.
- **macOS: a case-insensitive file system.** A test that made `Org/Data` and
  `org/data` failed with `FileExistsError` before its own skip could run,
  because the skip tested after the second `mkdir`. Probe the file system
  first, then create case-variant paths.
- **A dependency that changes its types.** `numpy.lib.format` was untyped up
  to 2.3 and typed from 2.5: a `# type: ignore` was unused (an error) on one
  and necessary on the other, so no ignore comment could pass both. An `Any`
  view with a `cast` passes both; checked with a second environment on the
  project's lowest numpy (`mypy --python-executable`).
- **A linter's score hides its messages.** A CI log showed "rated at
  10.00/10" and a `too-many-instance-attributes` error in the same run.
  Do: read the messages and the exit code, not the score, and run the CI
  command (directories, not single files) before pushing.

## 5. Review rounds on the same change

- **Each round of fixes added code that the next round found faults in.** On
  #314 the second review found two real defects (existing paths folded when
  unhashed; a registry pin silently ignored). The third review, of the fixes,
  found five more; two were in the code the second round had added: an
  unescaped value in the new `WARNING:` (a name with a newline could forge a
  second line starting `WARNING:`) and a path test that disagreed with the
  registry's own. The card route also said the same fold once per repeat, up
  to a thousand lines for a card repeating one name.
  Do: review the fix of a review, with the same questions about output
  channels (is every untrusted value escaped, is each message said once).
- **Merge mechanics matter when ids are pinned by commit.** Lumina pins
  Pitloom and the checker by commit SHA, so every PR was merged with a merge
  commit (a squash would change the SHA). Eight Pitloom branches were
  stacked inside one (`dataset-dedupe-assembler`), so merging the top merged
  all; two PRs that each append a CHANGELOG line after the same entry
  (#314, #315) conflict whichever merges second, and the resolution is to
  keep both in PR order. A date target (the parity ledger, 2026-10-19) passed
  with items open; the roadmap records the miss instead of dropping the item.
