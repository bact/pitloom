---
Created: 2026-10-04
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence typing (PR #276): what was left open

See also: [license-rules.md](license-rules.md) (rules, rulings and open
questions), [license-layers.md](license-layers.md) (the three layers), [license-typing.md](../implementation/license-typing.md)
(what #276 built), [roadmap.md](roadmap.md#needs-systematic-rules).

PR #276 merged with one bar: every surface records the same value, even
where that value is not yet the right one. Everything below was found in
its review rounds (R1-R10) and left out. Group A will be fixed as is.
Group B waits for the licence rules (taxonomy, cascade, conflict
resolution) and may change direction there. Group C is housekeeping.

## A. To fix

- **A wheel runs no in-package licence detection.** A directory, the
  library, the Hatchling hook and (since the sdist licence-detection PR) an
  sdist read the project's `LICENSE`; `loom wheel` records the METADATA
  `License:` text only. Needs `License-File:` selection (0.21.0).
- **A licence text in `PKG-INFO` stays text.** For `license = {file =
  "LICENSE"}` (a centred Apache header, checked live with a Hatchling
  sdist) the directory and the hook declare `Apache-2.0` (`licenseid`
  identifies `license.text`); the sdist declares the `License:` text. The
  concluded value agrees now. Running `stated_license()` on `PKG-INFO`'s
  `License:` would align them, but a setuptools directory keeps a
  `setup.cfg` `license =` text as written, and an sdist cannot tell the
  backends apart: a content decision
  ([metadata-quality.md](metadata-quality.md)).
- **sdist vs directory, smaller gaps** (found with the sdist fix): with no
  `PKG-INFO`, a `license = {file = ...}` naming a file that is not a root
  licence candidate (`LICENSES/MIT.txt`) states nothing from an sdist
  (one archive pass keeps only the candidates), and an invalid
  `project.license` shape is ignored where the directory fails
  (`pyproject-metadata`); `CITATION.cff`/`codemeta.json` match their
  exact name in an archive but any case on a case-insensitive file
  system; the directory follows a symlinked `LICENSE`, the sdist skips a
  link member.
- **`embed-wheel --project-dir`** records no licence for a silent manifest
  plus a `LICENSE` file; `loom project` and the hook declare it
  (`_add_concluded_license` detects only when a licence is already
  declared). With an sdist as `--project-dir` it reads no licence files
  at all, where `loom project <sdist>` now does (plan Q7: left as is).
- **Merge:** fixed (licences unify across a merge; the four merge bugs
  found beside it), see
  [fragment-merge-unification.md](../implementation/fragment-merge-unification.md);
  what is left:
  [open-items.md](sbom-fragments/open-items.md#left-after-the-fragment-merge-fixes).
- **Fragment `customIdToUri` targets** are checked for the main namespace
  only; a dangling target in an imported fragment's namespace passes.
- **`_classifier_and` orphan texts:** it resolves term texts before
  checking whether the expression exists, and looks them up unstripped,
  so hand-typed `LicenseRef-pitloom-classifier-` input can leave text
  elements nothing references. Not reachable from real classifiers.
- **setuptools config reading** (version files, `description = file:`,
  dynamic fallbacks, `attr:` gaps, untagged setuptools output):
  [setuptools-config-followups.md](setuptools-config-followups.md).

## B. Folded into the licence rules

Each is written up with its evidence in
[license-rules.md](license-rules.md#open-questions);
user leanings are recorded there, not decisions.

- Weak manifest value (`NOASSERTION`/`UNKNOWN`) vs a real licence from a
  `LICENSE` file or a model card. Common in the wild: old setuptools wrote
  `License: UNKNOWN` into every sdist that stated no licence, so such an
  sdist declares `UNKNOWN` (concluded from its `LICENSE`) while its
  directory declares the `LICENSE` licence (`apply_in_package_license`
  takes any non-blank value as stated; `first_license` takes it as weak).
- Reconcile ranking: the project's own installed metadata vs a `LICENSE`
  detection.
- Model file licence vs model card licence: disagreement not recorded.
- `setup.cfg` `license =` beats `setup.py` `license=` (setuptools does the
  opposite); same question for other merged sources.
- Provenance: a shared licence element keeps the first package's source
  and later reusers record none; a library caller's licence with no
  provenance gets a default source label (overclaimed).
- The several-classifiers `WARNING:` fires for a value then discarded.
- Hugging Face vague values: `unknown` reads the repo `LICENSE`,
  `NOASSERTION` does not.
- Text equivalence: CRLF vs LF texts are two elements (leaning:
  normalise); a licence name keeps a trailing `\r`/spaces; a classifier
  with a leading or trailing space is a name except in `setup.cfg`.
- `license = file: LICENSE` in `setup.cfg` is recorded as the text
  `file: LICENSE` (setuptools rejects it).
- `WITH DocumentRef-x:AdditionRef-y` (layer 1, upstream).

## C. Housekeeping

- Test readability from the compaction: comment the columns of the
  `test_licence_cascade` table; split
  `test_a_named_individual_target_is_its_licence_name` back into two; the
  name `test_equivalent_spellings_share_one_canonical_value` over-promises
  for single-spelling rows; `tests/core/test_fragments_dangling_refs.py`
  imports the assemble-side `tests._license_graph`; its fragment reuses
  the base document's CreationInfo blank-node id `_:ci`.
- One surviving mutant (gap terms not deduplicated) is probably
  equivalent: confirm, then drop the redundant `set()`.
- Tests reach private names where no public seam exists
  (`_find_main_document` call count).
- Over the size limits: `tests/assemble/test_deps_enrichment_pypi_fallback.py`
  (695 lines, older than #276), `AGENTS.md` (~507), `roadmap.md` (~511).
