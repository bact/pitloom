---
Created: 2026-11-28
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: a dependency's licence, declared or concluded (#568 to #572)

See also: [README.md](README.md) (index of these notes),
[spdx-modelling.md](spdx-modelling.md) (section 3, licences: the matcher's
near-ties and #286), [open-research-questions.md](open-research-questions.md),
[../../design/provenance-taxonomy/asserter-licence.md](../../design/provenance-taxonomy/asserter-licence.md)
(the rulings and the 2026-11-28 notes on the SBOM creator),
[../licenseid/licence-families-handoff.md](../licenseid/licence-families-handoff.md)
(the family data asked of LicenseID),
[../wheel-sbom-verification.md](../wheel-sbom-verification.md) (the 0.25.0
record).

The checks of Pitloom 0.25.0's own published wheel SBOM (2026-11-27) asked
"what looks odd?". The answers led to PRs #568, #569, #571 and #572 (all
merged 2026-11-28) and to four roadmap items. Numbers come from Pitloom's
own development environment (a `.venv` of 101 to 174 installed
distributions, depending on the extras) with LicenseID 0.9.4, re-run by a
separate reviewer where marked.

## 1. Licence files when the metadata names no licence (#569)

- **The metadata often names no SPDX licence; the files usually do.** Of
  11 installed dependencies whose Core Metadata `License` was free text,
  `UNKNOWN` or absent (101-package environment), reading the licence files
  in their `.dist-info` identified 8. In Pitloom's own SBOM fickling became
  `LGPL-3.0-or-later` and safetensors `Apache-2.0`; a reviewer's sweep of
  the whole environment found 16 packages moving from text to an id.
- **A verbatim Apache 2.0 file is not decisive.** rfc8785 0.1.4,
  rfc3161-client and sigstore-rekor-types score `Apache-2.0` 1.0 and
  `Pixar` 0.995. With nothing stated and a versionless
  `Apache Software License` classifier, no rule may pick one, so the three
  stay unresolved (the same family of near-tie as #286's requests file).
- **A dual licence must not be narrowed by its file.** python-dateutil
  states `License: Dual License` with the `BSD License` and
  `Apache Software License` classifiers; its `LICENSE` holds the Apache
  notice and the BSD-3-Clause text, and was read as `Apache-2.0` alone. A
  review caught it; the file read is now skipped when the classifiers name
  more than one licence.
- Do: read the files the package itself lists (PEP 639 `License-File`)
  before guessing, and never let a second source narrow a first that names
  several licences.

## 2. A generic name against a specific file: "narrowing"

- **Trove classifiers name families, not licences.** LicenseID 0.9.4's
  `trovenames` table has 89 classifier names: 49 read as stated ids, 5 as
  assumed, 35 as none. `BSD License`, `Apache Software License` and
  `Python Software Foundation License` are none; `licenseid.resolve()`
  calls them, and the header spellings `BSD`, `Expat license` and `PSFL`,
  `unresolved`.
- **Of 14 dependencies with stated text beside an identified file** (one
  more, python-dateutil, is skipped as dual): 4 state the licence body in
  their `License` header and read as the same id (html5rdf MIT, isodate
  BSD-3-Clause, pyshacl Apache-2.0, fickling LGPL-3.0-or-later with its
  `LGPLv3+` classifier breaking the `-only`/`-or-later` tie); 9 state a
  generic name the file narrows (jinja2, colorama, safetensors,
  trove-classifiers by classifier; ghp-import, mpmath, nodeenv,
  semantic-version, defusedxml by a short header whose own classifier
  narrows); mccabe's `Expat license` header has an `MIT License`
  classifier, so it is the same. No case widened (the file granting more)
  or disagreed.
- **Four relations, not two.** Same, narrowing, widening
  (`LGPL-3.0-only` stated, `-or-later` detected) and disagree. Only the
  last two are conflicts. "Narrowing" needs family data: which ids a
  classifier covers.
- Do: keep family data in the licence-identification library, not in each
  SBOM tool (two copies drift); Pitloom records the 9 as two declared
  licences and a conflict until LicenseID answers.

## 3. Declared or concluded: whose statement it is (#569, item 8)

- **SPDX 3.0.1's definition decides it.** `hasDeclaredLicense` is a
  licence the artefact "was discovered to actually contain", for example
  "as detected by use of automated tooling". A dependency's metadata, its
  PyPI record and its licence files are the originator's statements, so
  declared. Pitloom had typed the installed copy and the PyPI record as
  third-party, concluded.
- **The switch, measured.** Pitloom's own project SBOM: 25 dependencies
  change; licence relationships go from 26 concluded and 1 declared to 1
  concluded (the main package's own detection) and 27 declared; conflicts
  0 to 1 (safetensors). The `loom env` SBOM: declared 174 to 184,
  conflicts 0 to 10 (the narrowing cases of section 2), 4 header bodies
  collapse to one declared id. The main package's output was
  byte-identical across five fixtures.
- **A type must not depend on a second source.** The intermediate design
  made a stated text concluded when its file could not be read and
  declared when it could; a reviewer showed one metadata value with two
  types. Declared for both fixed it.
- **Two declared licences on one package are valid.** Two
  `hasDeclaredLicense` relationships from one package (stated text and a
  differing file) pass `spdx3-validate` (schema and SHACL); the conflict
  annotation names both as `declared` candidates.
- **The stated text survives a collapse.** When a header body reads as the
  file's id, one declared id is kept with the text as `Normalized-From`.
  A review found the note lost when the id's element already existed (a
  project licensed MIT, a dependency stating the MIT body): a dedup helper
  compared provenance strings and saw no change. Fixed before merge.
- Do: decide declared versus concluded by who stated the value, not by
  where Pitloom read it.

## 4. Concluded needs someone who concludes

- **A detector's match is a reading, not a conclusion.** With every
  originator value declared, Pitloom writes `hasConcludedLicense` for no
  dependency. The SBOM's creator may conclude (the library's
  `license_concluded=`; a creator-supplied value, issue #570); Pitloom
  alone does not.
- **One person can be originator and SBOM author.** An owner building
  their own project's SBOM may conclude its licence as well as declare
  it; both relationships are valid, to one element when equal. The tool
  cannot infer it: the same command builds a stranger's project from a Git
  URL, and running the tool states nothing.
- **Standards count different relationships.** As mapped in Pitloom's
  skill references, FSCT 2024 COMP-007 counts `hasConcludedLicense` only and
  CISA 2026 COMP-006 `hasDeclaredLicense` only. Declaring dependency
  licences raised CISA coverage and made FSCT report every dependency
  licence missing; the maintainer accepted the trade-off and logged the
  mapping question (FG-17 in the format-gaps ledger).
- Do: when a semantic fix moves a field between relationship types, rerun
  every minimum-elements mapping and say which framework loses coverage.

## 5. Copyright notices by exact `License-File` path (#572)

- **A `License-File` value is a path, not a name.** The copyright reader
  compared values with file basenames: nested values (h5py's
  `licenses/hdf5.txt`, pip's 22 values including vendored
  `src/pip/_vendor/*/LICENSE`) matched nothing, and `LICENSE` matched every
  `.dist-info` file of that name. Exact paths (`licenses/<value>`, else
  the `.dist-info` root) gave 2 of 174 packages more notices and none
  fewer.
- **A package with no header gets none.** numpy 2.2.6 in this environment
  lists no `License-File`; the root-file fallback the licence reader uses
  was left out of the copyright reader for now (an open option).
- Do: resolve a path a format defines by that format's rule, the same
  helper for every reader of the same files.

## 6. Other oddities in a release's own SBOM (0.25.0)

- **The SBOM creator and a dependency author were two `Person` elements**
  with the same name and email (#568): the creator was registered after
  the agents, under no shared key. The `loom env` route needed the same
  fix, found by a review.
- **Organisations typed as `Person`.** Ruled 2026-11-27 (#170): an exact
  known list of organisation names and addresses gives `Organization`; an
  author no rule types is `Agent`, not `Person`. Not built.
- **Environment markers dropped.** `tomli` (`python_version < "3.11"`) and
  `auditwheel` (Linux only) are recorded as plain runtime `dependsOn`.
- **Release and facts disagree for an uninstalled extra.** An optional
  dependency not installed at build time gets version `unknown`, but its
  licence and authors come from the latest PyPI release.
- Do: read a release's own SBOM as a user would, asking "what is odd?";
  four of the six answers were real defects.
