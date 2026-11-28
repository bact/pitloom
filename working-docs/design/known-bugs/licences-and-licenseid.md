---
Created: 2026-11-02
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs: licences and LicenseID

See also: [known-bugs.md](../known-bugs.md) (index, severity scale,
rules for adding an entry), [roadmap.md](../roadmap.md),
[license-pr276-followups.md](../license-pr276-followups.md),
[license-rules.md](../license-rules.md),
[license-resolution-categories.md](../license-resolution-categories.md),
[licenseid/adoption-plan.md](../../implementation/licenseid/adoption-plan.md).

Licence detection, declared and concluded licences, the LicenseID resolver
and database, licence elements and their provenance. Entries are ranked by
priority tier, then by size tag; see the severity scale in the index. Open
entries come first; fixed entries stay in the last section for history.

## Open

### P2: 0.21.0 and later

- [ ] **Two `SPDX-License-Identifier` tags, one stated, conclude only the
  stated one (S).** Found in the #287 review, same on `main`: a file
  tagged `MIT` and `Apache-2.0` with `stated="MIT"` concludes `MIT` and
  drops `Apache-2.0`.
- [ ] **A reused licence element's comment names the first source only
  (S).** A file tag that reuses the package's element records no provenance
  of its own unless it was normalised. Folded into the licence rules
  ([license-pr276-followups.md](../license-pr276-followups.md), group B).

- [ ] **A near-tie in the first licence file lets a later file decide alone
  (S).** `license_from_candidates` (`extract/_license.py`) and the Hugging
  Face loop (`_detect_license_from_hf_files`) read a `None` from detection
  as "nothing here" and move on, so a near-tie in `LICENSE` (another licence
  family within the margin) is skipped and a `COPYING` concludes alone. A
  file of several licence texts already ends the search (#554, through
  `LicenseTextReading.several_texts`); a near-tie could carry the same
  "found, undecided" signal. Same on `main` before #554.
  *Found 2026-11-26, #554 review.*

### P3: after 0.20.0

- [ ] **Hugging Face and classifier names state no licence to detection
  (S).** `huggingface_fetch` and `stated_license()` call
  `detect_license_from_text` without `stated=`, so a repo `LICENSE` with a
  card `license: apache-2.0` near-tie gives no detection; a classifier name
  (`MIT License`) never matches an id (#286 review).
- [ ] **Licence detection reads each text twice (S).** With a notice line,
  the matcher runs on the text as written and without the notice: about
  twice the time per licence text. Skip the second reading when the first
  is decisive at a high score (#286 review).
- [ ] **File licence and README licence disagree silently (S).** Found in
  the #292 review: with `--enrich`, the README enricher only fills a
  missing licence (`enrich/readme.py`), so an ONNX file declaring
  `Apache-2.0` next to a README saying `mit` keeps `Apache-2.0` with no
  message. #292 made ONNX files carry a licence for the first time, so
  this can now happen for ONNX as for the other formats. Decide whether a
  disagreement is a `WARNING:` (see
  [license-rules.md](../license-rules.md)).

### Found in review rounds, not yet prioritised

- [ ] **Per-operand licence provenance is not built (S).** A compound with one
  respelt part (`Apache2 OR MIT`) is read as an expression (#437, #440); the
  design's per-operand results (`Resolution-n`,
  `Expansion-n`) wait for the licence provenance mapping (T14, not scheduled;
  [licence-resolution-provenance.md](../licence-resolution-provenance.md)).
  Decision Q5 (the licence list version into
  `simplelicensing_licenseListVersion`) is not built either: the version is in
  `Resolution["lists"][0]["version"]` but not yet used. The
  verbatim value and the reading's method have no SPDX property either: FG-6
  and FG-7 in [sbom-format-gaps.md](../sbom-format-gaps.md).
  *Found 2026-10-27, combined review of #352 to #357.*
- [ ] **A shared licence element keeps the first source's provenance (S).** A
  `MIT License` classifier and a file tagged `MIT` are one `LicenseExpression`;
  its notes (`Method: licenseid_resolution`) describe the first source only and
  the second source's annotation is not written. First-wins is old; the
  resolver merges more values, so it shows more often. Found in the #359
  review.
  *Found 2026-10-27, combined review of #352 to #357.*
- [ ] **A foreign warnings block overlapping a lookup takes its LicenseID
  lines (S).** Pitloom's three warning blocks share one lock
  (`pitloom.core.warning_capture`), and the relay records only its own
  thread, so nothing is left taken or dropped after both blocks. But a
  `warnings.catch_warnings(record=True)` of the host or a library, in
  another thread, entered while a lookup runs, replaces `showwarning` for
  the process (on Python 3.14 too): what LicenseID warns meanwhile goes
  into that block's list and is not said. Tested as the stated limit in
  `tests/core/test_warning_capture.py`. A fix needs a hook in LicenseID
  (a callback for its warnings) rather than `warnings`.
  *Found 2026-11-03, review of #437.*
- [ ] **A file-level SPDX tag is read by `resolve()`, not `detect()`
  (S).** `SPDX-License-Identifier: GPL-2.0` in a file header goes through
  `classify_license` (`_document_files.py` to `_license_elements.py`), so
  `resolve()` keeps `GPL-2.0` (`assumed_only`), while `detect()` on the same
  text reads `GPL-2.0-only`; the package level may differ. Pre-existing;
  decide which reader a header tag belongs to. *Found 2026-11-03, review of
  #437.*
- [ ] **LicenseID reads no id in 14 deprecated ids' List names, and gives
  no List name for an id (S, upstream).** `resolve()` answers `not found` for
  `GNU Free Documentation License v1.3` (`GFDL-1.3`), `GNU Affero General
  Public License v3.0` (`AGPL-3.0`), `wxWindows Library License` and 11 more
  (every deprecated id the List renamed); its public API has no name lookup
  (`LicenseDatabase` is an opaque handle, and a database-backed answer would
  differ with and without one). #440 keeps the 14 names in
  `extract/_license_names.py` (`same_licence`, used by `values_agree` and the
  declared vs concluded check), held to the packaged List by
  `tests/extract/test_license_names.py`. Delete the table once LicenseID
  answers. Suggested issue text: "`resolve()` reads a List name as its id
  (`MIT License` is `MIT`) but not the name of a deprecated id
  (`GNU Free Documentation License v1.3` is `not found`): read it as the
  deprecated id, category `assumed_only` with its candidates, as `GFDL-1.3`
  is; or expose the packaged List's names (`id -> name`) publicly."
  *Found 2026-11-04, review of #440.*
- [ ] **LicenseID's `trust: none` is not recorded (S, accepted).** An
  `assumed_only` answer (`GPL-3.0` kept, `-only` or `-or-later` unknown) has
  `trust: none`; the SBOM says it only through the `Deprecated-License-Id`
  note. Acceptable until the licence provenance mapping has a key for it
  ([licence-resolution-provenance.md](../licence-resolution-provenance.md)).
  *Found 2026-11-04, review of #440.*
- [ ] **`_ambiguous` can write a note with no licence (S, no trigger).**
  An operand with `candidates` but no `expression` would give
  `Deprecated-License-Id:  (A or B)`; LicenseID 0.7.0 gives candidates only
  with an expression (the review found no trigger). Skip such an operand
  if a release changes that. *Found 2026-11-04, review of #440.*
- [ ] **A lone CR inside a declared value makes it text (S, decide).**
  `MIT\rOR ISC` is more than one line (`str.splitlines`), so the multi-line
  rule keeps it as text, as for `\n`; `main` read it as an expression.
  Consistent, but a value from a CR-only file would lose its reading.
  *Found 2026-11-04, review of #440.*
- [ ] **A dependency's Apache 2.0 file with no licence stated stays
  unread (S, upstream).** The licence-file fallback for a dependency whose
  metadata names no SPDX licence (`_deps_license_files.py`) gives none for
  rfc8785 0.1.4, rfc3161-client and sigstore-rekor-types: their verbatim
  Apache 2.0 texts score `Apache-2.0` 1.0 and `Pixar` 0.995, a near-tie the
  reader refuses with nothing stated, and the `Apache Software License`
  classifier names no version to break it. 8 of the 11 installed packages
  whose metadata named no SPDX licence (a 101-package environment) were
  identified. The near-variant ranking is LicenseID's
  ([licenseid-handoff.md](../licenseid-handoff.md)); a family hint from a
  versionless classifier (`Apache-*`) is another way, not built; a licence
  the SBOM creator states is a third
  ([#570](https://github.com/bact/pitloom/issues/570), in the roadmap).
  *Found 2026-11-27, post-publish verification of 0.25.0.*
- [ ] **A dependency with no `License-File` header gets no copyright text
  (S, idea).** `_find_license_copyright` reads only the files its
  `License-File` values name, so rfc8785's root `LICENSE` is never read for
  notices. The licence reader falls back to the root licence files by name
  (`dist_license_files` with no values); the copyright reader could do the
  same, which gives more packages a copyright text and needs its own
  before/after. Not built for now (user, 2026-11-28).
  *Found 2026-11-27, review of the dependency licence-file fallback.*
- [ ] **A G2 conflict where a generic licence name narrows to its file's
  licence (S, upstream).** With #569 a dependency's stated licence text
  and its licence file's detection are both declared, the originator's
  claims, with a conflict annotation when they differ. A generic trove
  classifier name the file narrows to one member of (`BSD License` ->
  `BSD-3-Clause`, `Apache Software License` -> `Apache-2.0`) is no conflict but still gets a conflict annotation: 10 of
  14 such packages in Pitloom's own environment, 4 stated by the
  classifier, 6 by a short `License` header (`BSD`, `Apache Software
  License`, `Expat license`, `PSFL`) whose package's classifier narrows
  the same way or, for mccabe, names `MIT`. Waits on LicenseID relation API
  (narrowing): `trovenames` reads these generic names as `none` today; the
  ask is
  [licence-families-handoff.md](../../implementation/licenseid/licence-families-handoff.md).
  Narrowing then needs a Pitloom record (perhaps `Relation: narrowing` in
  provenance, not decided); widening (`-only` stated, `-or-later`
  detected) and a different family stay conflicts.
  *Found 2026-11-27, before/after sweep of the #569 G2 change.*
- [ ] **A licence with no source is concluded (S-M, to rule).**
  `is_license_concluded` (`assemble/spdx3/_provenance_encoders.py`)
  classes a licence whose provenance names no `Source:` as
  `hasConcludedLicense`; since #569 that is its only concluded case. The
  "Licence paths" table of
  [asserter-licence.md](../provenance-taxonomy/asserter-licence.md) calls
  such a value a bug at the reader, not a concluded licence. Start with an
  inventory of the readers that can leave the source empty (a library
  caller's value, a fragment, a dataset or model with no provenance), then
  decide between raising `InternalError` for a missing source and fixing
  each reader. Kept as is in #569 by the user's
  ruling (2026-11-28): a separate follow-up.
  *Found 2026-11-28, #569 dependency licences declared.*
- [ ] **An `SPDX-License-Identifier` line in a licence file is read as
  text (S).** A licence file holding only `SPDX-License-Identifier: MIT OR
  Apache-2.0` (a dependency's installed licence file, or a project's) is
  read as the whole line, recorded as a `LicenseRef-loom-text-...` custom
  text with a `license-expression-invalid` warning. Such a line should be
  read as its expression, as a source file's own tag is
  (`build_file_declared_license`). The same before #569.
  *Found 2026-11-28, review of #569.*

## Fixed

Kept for history, with the PR. A fixed entry moves to
[roadmap-completed.md](../../implementation/roadmap-completed.md) once its
release ships.

### Fixed, P2: 0.21.0 and later

- [x] **A top match that holds only part of its licence is concluded
  (S-M, needs a rule).** Found in the #287 review: a BSD-1-Clause file
  whose notice line ends "All rights reserved." concludes `BSD-2-Clause`
  (0.927, coverage 0.825): `_COPYRIGHT_NOTICE_RE` drops the whole line,
  phrase included, and `_fits_worse` checks runner-ups only. Decide a
  coverage floor for the top match and whether notice stripping keeps a
  trailing "All rights reserved" (`license-rules.md` §4).
  Fixed by #437: LicenseID 0.7.0 detects the filled BSD-1-Clause text
  (`BSD-1-Clause`, score 1.0; 0.22.1 concluded `BSD-2-Clause`). No coverage
  floor is built.
- [x] **A licence classifier becomes text, not an SPDX id (S).** Deferred
  by #276 (needs a newer LicenseID; "Known deviation" in
  `license-typing.md`).
  `License :: OSI Approved :: MIT License` (PyPI, and installed metadata
  after #276) yields the text "MIT License". Map trove classifiers to
  SPDX ids (LicenseID or a small table), keeping the raw value in
  provenance.
  Fixed by #437: the classifier path and the name are read with no
  database (`License :: OSI Approved :: MIT License` is `MIT`).
- [x] **An unknown id in an SPDX-only field is not reported (S-M).** Fixed
  in #357: the value stays text, plus one
  `WARNING:` per value naming the field (`warn_unless_expression`, called by
  each reader where the field is known). See
  [license-typing.md](../../implementation/license-typing.md#unknown-id-in-an-spdx-only-field).
  Legacy `License:` stays silent.
- [x] **A Hugging Face `license: gpl-3.0` was rewritten to `GPL-3.0-only`
  only when the LicenseID database was present (S).** Fixed in #357:
  the Hugging Face route records the card value as stated, so the deprecated
  bare id stays the id written (`GPL-3.0` after classification, never
  `GPL-3.0-only`) with or without the database. `canonicalize_license_id`
  (case fold only) was deleted in #437: it had no caller. A non-lexical
  resolver decision (alias, successor) waits for `INFO:` plus provenance, see
  [license-resolution-categories.md](../license-resolution-categories.md).
- [x] **The main package never reads `License ::` classifiers (S).** Fixed
  by #276 (`license_or_classifier`, every surface). A
  legacy wheel with `License: UNKNOWN` and an MIT classifier gets
  `NoAssertionLicense` in its own SBOM, while the same package as a
  dependency gets the classifier's licence (#276 cascade).
- [x] **A LicenseID database that breaks after the matcher is cached
  fails silently (S).** Fixed by #287: a database error from `match()`
  warns once (as an unusable database does) and drops the cached matcher;
  `InvalidInputError` (a normal input) stays at debug. Since LicenseID
  0.4.2 (#289) that error is always `DatabaseNotReadyError`, and a lookup
  no longer re-creates a deleted database as an empty file.
- [x] **A licence id over 50,000 characters ending in `+` reads as a broken
  LicenseID database (S, upstream).** Fixed in LicenseID 0.4.3; #292 raised
  the floor and made the test a plain one. Found in the #289 review: in a
  text it can sit in an `SPDX-License-Identifier:` tag, a `License:` field
  or a JSON `"license"` field. LicenseID 0.4.2 builds a SQL `LIKE` pattern from the
  id, SQLite refuses one over 50,000 bytes, and LicenseID raises
  `DatabaseNotReadyError`: one false `WARNING:`, which as `warn_once` also
  hides a later real failure. #289 skips lookups of an id over 200
  characters (`canonicalize_license_id`); a licence text holding such an id
  still warned. Fix belonged in LicenseID (an input error).
- [x] **`license = {text = "MIT License"}` plus an Apache LICENSE file
  gives declared `Apache-2.0` (S).** The `project.license.text` value goes
  through licence-file detection (seen in the #276 sweep). Fixed by #276:
  a stated text stays as written.
- [x] **Installed-dependency and local PT2 model licences are always concluded
  (S).** Decided by #276 ("Declared or concluded" in `license-typing.md`): a
  model file's own metadata is declared, a dependency's installed copy stays
  concluded (`THIRD_PARTY_SOURCES`). Reversed in #569 (2026-11-28): a dependency's
  installed copy and PyPI record are declared too, and `THIRD_PARTY_SOURCES`
  is gone.

### Fixed, Found in review rounds, not yet prioritised

- [x] **A dependency's copyright notices match `License-File` by base name
  (S-M).** `_find_license_copyright` (`assemble/spdx3/deps_originator.py`)
  compared each `License-File` value with a file's base name: a nested value
  (numpy lists nine, `numpy/_core/.../LICENSE.txt`) matched nothing, and
  `LICENSE` matched every `.dist-info` file of that name, at any depth.
  *Found 2026-11-27, review of the dependency licence-file fallback.* Fixed:
  the exact paths the licence reader uses (`dist_license_files`:
  `licenses/<value>`, else the `.dist-info` root, each file once). In
  Pitloom's environment 2 of 174 packages gain notices (h5py's
  `licenses/*.txt`, pip's vendored `src/pip/_vendor/*/LICENSE`); none loses
  one. With no header nothing is read, as before (open entry above).
- [x] **A G2 conflict on a dependency whose `License` header holds the
  licence body its file is detected as (S).** With #569 such a header
  (fickling, pyshacl, html5rdf, isodate) stayed declared beside its file's
  detection, with a conflict annotation. Fixed in #569:
  `stated_text_agrees` reads the whole stated text with LicenseID (the
  classifier's licence breaking a near-tie, so fickling's LGPLv3+ decides
  `LGPL-3.0-or-later`) and a text read as the detected id is that id: one
  declared licence, the text kept as `Normalized-From` (ruled 2026-11-28,
  with dependency licences declared); 4 of 14 annotations gone. The short names stay
  open above. *Found 2026-11-27, before/after sweep of the #569 G2 change.*

- [x] **Catalogue 18, the licence families, was later (S), fixed (#498).**
  Decided 2026-10-30: it follows the adoption; it ships in 0.25.0.
  *Found 2026-10-30, LicenseID.*
- [x] **Two spellings of one deprecated id give two expressions (S).**
  `StandardML NJ` is read as `SMLNJ` (LicenseID renames), while the listed
  `StandardML-NJ` parses locally and stays as written, so one licence has two
  records. Fixed by letting `resolve()` answer for the whole value (Q7); see
  LicenseID's expression-resolution design. Found in the #359 review.
  Fixed by #440: both spellings are `SMLNJ`.
  *Found 2026-10-27, combined review of #352 to #357.*
- [x] **The resolver's reading depends on the database (S).** Fixed by
  #437: the reading uses the list packaged with LicenseID 0.7.0, the same
  with or without a database. A comparison
  (`values_agree`, the fragment-merge key of `_license_elements`) treats
  `Apache2` and `Apache-2.0` as one licence with the LicenseID database and
  as two without it, so whether a conflict is recorded differs. Provenance of
  a value Pitloom parses itself does not (#359).
  *Found 2026-10-27, combined review of #352 to #357.*
- [x] **The Hatchling hook finds no licence database in an isolated build
  environment (S).** Pitloom 0.21.0 reads a declared licence value through
  `licenseid.resolve()`, which needs a built database. A build in an isolated
  environment never has one, so every project using the hook sees `WARNING:
  licenseid database cannot be used: ... -- license text detection and
  license id reading skipped` and its licence values stay as written
  (`Apache2` is not read as `Apache-2.0`). A project that declares an SPDX id
  is not affected. Reported by a reviewer upgrading a project to 0.21.0.
  Options: (a) `licenseid 0.7.0` makes `resolve()` work with no database from
  the packaged bundle that the PyPI wheel already ships (design:
  LicenseID `working-docs/design/expression-resolution.md`, "No database");
  (b) until then the hook builds a database from the packaged bundle
  (`licenseid update --source packaged`, offline) into a location of its own,
  not the user's cache, or keeps the single warning and says why. Today the
  same value gives different SBOM bytes with and without a database.
  Mitigated in 0.21.1 (#364): a missing database is `INFO:` when a licence is
  declared (the warning stays when none is declared or for a value that needed
  LicenseID's reading). Fixed for good when Pitloom 0.22.0 reads declared
  values through LicenseID 0.7.0 (plan: #368).
  Fixed by #437 (option (a), released as LicenseID 0.7.0).
  *Found 2026-10-28, 0.21.0 release review.*
- [x] **The 0.7.0 adoption waits for the release (S).** PyPI's latest was 0.6.0
  at 15:14 UTC on 2026-10-30. Released 2026-11-03; adopted by #437.
  *Found 2026-10-30, LicenseID.*
- [x] **A `license = {file = "LICENSE"}` that is a Git LFS pointer is recorded
  as the licence text `LICENSE` (S-M).** Fixed by #422 (CLI, library and
  hook) and #429 (a wheel, an sdist's `PKG-INFO` and an installed
  `.dist-info` whose `License` or `License-Expression` header holds a whole
  pointer: the header is absent, so the cascade goes on to the classifiers).
  The licence is now
  unstated (a pointer is no licence text, and a file name never stands as
  one); `is_pointer_text` in `core/lfs_pointer.py` decides it for every route.
  The root package's declared licence read `['LICENSE']` (the file name stood
  as text) and no `[lfs-pointer]` line was printed for that file; only a DEBUG
  line in `extract/_license_detect.py` said it. Two siblings were fixed in the
  same change: the Hatchling hook recorded the pointer's own text as the
  licence text, and an empty licence file in an sdist without `PKG-INFO`
  recorded the string `License(text='', file=None)`.
  *Found 2026-11-02, PyPI 0.22.0 verification.*
