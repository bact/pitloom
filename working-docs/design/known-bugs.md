---
Created: 2026-10-03
Last-Modified: 2026-10-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs, by priority

See also: [roadmap.md](roadmap.md),
[id-registry-v3.md](../implementation/id-registry-v3.md),
[id-registry-followups.md](id-registry-followups.md),
[canonical-output-followups.md](canonical-output-followups.md) (open
canonicalisation questions behind several bugs here),
[known-bugs-p3.md](known-bugs-p3.md) (the P3 list, split for size).

Bugs found up to #286, each reproduced on `main` unless marked
otherwise. Features and design work stay in the roadmap. A fixed item
stays ticked, with its PR, until its release ships, then moves to
[roadmap-completed.md](../implementation/roadmap-completed.md).
Size: S under half a day, M about a day.

## P0: in 0.21.0

- [ ] **One default SBOM file name on every surface (S-M).** `loom
  project` writes `Foo.Bar-Baz-1.0+local.spdx3.json` unescaped; the
  Hatchling hook uses the raw name; embed's escaper skips `*?"<>|`.
  Decided: PEP 427 escaping everywhere, its own PR.
- [ ] **Git LFS pointers outside AI models (M, decided).** A dataset or
  any other file that is an unfetched pointer is listed with the
  pointer's SHA-256 and no warning. Decided: one shared detector, one
  summary `WARNING:` per run, one line per file at `--debug`. Registry v3
  shipped without it; loom `path=` should reuse it.
- [ ] **A fragment value may lose to an extracted one (S-M, own PR).**
  Unconfirmed in #294: a fragment or catalogue `description` should win
  over the one generated from a CRFsuite model's labels
  (`Method: generated_from_labels`); check the merge order treats
  extracted and generated values as weak, for every field, not only this
  one.
- [x] **Same AI model gets different ids per surface; enrichment can hit
  the wrong model (S-M).** Found in the #292 review (`loom model` looked a
  model up by file stem only, a project scan by name, path, then stem). Fixed
  by the path-key redesign on registry v3 (PR #305; K9, K10, K17 in
  [id-registry-path-keys.md](../implementation/id-registry-path-keys.md)): one
  model rule on every surface, a model keyed by its file's path and gated by
  its SHA-256.

## P1: registry v3 in 0.21.0 (some built, some not)

- [ ] **sdist placeholder names.** An sdist with no `Name` is `unknown` and is
  still looked up and harvested; two sdists whose PKG-INFO lacks `Name` share one
  doc uuid and reuse a pinned `unknown` id. (Wheels: fixed in PR #305 with
  `identity_known` and a file-name uuid seed.) See
  [id-registry-followups.md](id-registry-followups.md#wheel-identity-and-archive-readers).
- [x] **A registry inside the scanned tree never settles.** Fixed by
  registry v3 (PR #305, D7): the declared registry is left out of the file
  set, with one `WARNING:` per run. (Was: each run hashed the registry as a
  project file, then rewrote it: 4 runs, 4 different SBOMs and registries.)
- [x] **A project under any `build/` directory indexes nothing.** Fixed
  by registry v3 (PR #305): the walk prunes ignored directory names below
  the scan root and `_skipped_name_in` checks an explicit PATH's
  project-relative parts. (Was: a check on the absolute path, so
  `loom id generate` wrote 0 files, silently.)
- [x] **Same-stem model files share one entity.** `a/model.gguf` and
  `b/model.gguf` got one `ai_AIPackage` key (Q-A: key by project path). Fixed
  by the path-key redesign (PR #305; K9 in
  [id-registry-path-keys.md](../implementation/id-registry-path-keys.md)): a
  model is keyed by its file's path, two models with one stem have two ids.
- [ ] **A package key without a version gives every release one id**
  (Q-D: PEP 503 name plus PEP 440 version). Not built in v3.
- [x] **`normcase` does not fold case on macOS**, so a `same_path`
  helper built on it misses case variants. Fixed by registry v3 (PR #305):
  `core/walk_rules.same_path` falls back to `(st_dev, st_ino)`.

## P2: in 0.21.0

- [ ] **An unknown id in an SPDX-only field is not reported (S-M).** After
  licence typing, `license = "Apache2"` (PEP 639) or `License-Expression: BSD`
  becomes licence text silently; warn only for fields that must hold an SPDX
  expression, which needs the source field passed through the six readers.
  Legacy `License:` stays silent.
- [ ] **A licence classifier becomes text, not an SPDX id (S).** Deferred
  by #276 (needs a newer `licenseid`; "Known deviation" in
  `license-typing.md`).
  `License :: OSI Approved :: MIT License` (PyPI, and installed metadata
  after #276) yields the text "MIT License". Map trove classifiers to
  SPDX ids (licenseid or a small table), keeping the raw value in
  provenance.
- [x] **The main package never reads `License ::` classifiers (S).** Fixed
  by #276 (`license_or_classifier`, every surface). A
  legacy wheel with `License: UNKNOWN` and an MIT classifier gets
  `NoAssertionLicense` in its own SBOM, while the same package as a
  dependency gets the classifier's licence (#276 cascade).
- [ ] **A top match that holds only part of its licence is concluded
  (S-M, needs a rule).** Found in the #287 review: a BSD-1-Clause file
  whose notice line ends "All rights reserved." concludes `BSD-2-Clause`
  (0.927, coverage 0.825): `_COPYRIGHT_NOTICE_RE` drops the whole line,
  phrase included, and `_fits_worse` checks runner-ups only. Decide a
  coverage floor for the top match and whether notice stripping keeps a
  trailing "All rights reserved" (`license-rules.md` §4).
- [x] **A licenseid database that breaks after the matcher is cached
  fails silently (S).** Fixed by #287: a database error from `match()`
  warns once (as an unusable database does) and drops the cached matcher;
  `InvalidInputError` (a normal input) stays at debug. Since licenseid
  0.4.2 (#289) that error is always `DatabaseNotReadyError`, and a lookup
  no longer re-creates a deleted database as an empty file.
- [x] **A licence id over 50,000 characters ending in `+` reads as a broken
  licenseid database (S, upstream).** Fixed in licenseid 0.4.3; #292 raised
  the floor and made the test a plain one. Found in the #289 review: in a
  text it can sit in an `SPDX-License-Identifier:` tag, a `License:` field
  or a JSON `"license"` field. licenseid 0.4.2 builds a SQL `LIKE` pattern from the
  id, SQLite refuses one over 50,000 bytes, and licenseid raises
  `DatabaseNotReadyError`: one false `WARNING:`, which as `warn_once` also
  hides a later real failure. #289 skips lookups of an id over 200
  characters (`canonicalize_license_id`); a licence text holding such an id
  still warned. Fix belonged in licenseid (an input error).
- [ ] **Two `SPDX-License-Identifier` tags, one stated, conclude only the
  stated one (S).** Found in the #287 review, same on `main`: a file
  tagged `MIT` and `Apache-2.0` with `stated="MIT"` concludes `MIT` and
  drops `Apache-2.0`.
- [ ] **A direct-URL dependency is looked up on PyPI by name (S-M).**
  `foo @ git+...` or a private-index package picks up the licence and
  supplier of whatever PyPI project shares its name, possibly a
  different package.
- [x] **`license = {text = "MIT License"}` plus an Apache LICENSE file
  gives declared `Apache-2.0` (S).** The `project.license.text` value goes
  through licence-file detection (seen in the #276 sweep). Fixed by #276:
  a stated text stays as written.
- [x] **Installed-dependency and local PT2 model licences are always concluded
  (S).** Decided by #276 ("Declared or concluded" in `license-typing.md`): a
  model file's own metadata is declared, a dependency's installed copy stays
  concluded (`THIRD_PARTY_SOURCES`).
- [x] **`loom merge <dir>` writes no `SpdxDocument`, so no `profileConformance`
  (S).** Fixed by #284. Merging two full SBOMs that share one namespace (project
  dir + wheel) fails with a duplicate `File-2` id.
- [ ] **A reused licence element's comment names the first source only
  (S).** A file tag that reuses the package's element records no provenance
  of its own unless it was normalised. Folded into the licence rules
  ([license-pr276-followups.md](license-pr276-followups.md), group B).
- [x] **Merge keeps one licence element per namespace (doc).** Fixed by
  #284: equal licences unify across a merge. Two
  `Apache-2.0 AND MIT` elements after a fragment merge are valid under the
  never-name-match policy; say so in `license-typing.md`.
- [x] **`test_member_order_does_not_change_the_sbom` is flaky (S).** Fixed by
  #279. It runs `generate_project_sbom` three times without `SOURCE_DATE_EPOCH`,
  so a second boundary between runs changes `created` (failed once locally under
  load, 2026-10-04). Pin the epoch in the test.

- [ ] **`loom wheel` copyright year is the SBOM's (S).** With no author
  name in `METADATA` (only `Author-email`), the holder now comes from the
  `Author-email` display name or address (#300), but the year is still the
  SBOM's year, not the package's. Not re-checked since #300: the wheel
  route had no supplier where the hook records the author.

- [ ] **A very long version number crashes lock-file reading (S).**
  `packaging.Version("1." + "9" * 5000)` raises a plain `ValueError`
  (int digit limit), not `InvalidVersion`; `version_key`,
  `is_usable_version` and `is_same_version` in `extract/lock/common.py`
  catch only the latter. #266 fixed the same class in `verify-wheel`.
  #287 adds a caller: the setuptools `version` conflict check
  (`_field_agreement.values_agree`) crashes the directory read on
  `setup(version='9' * 5000)` beside a `setup.cfg` version.

- [ ] **Safetensors licence keys are not mapped (S).** They stay in the
  verbatim annotation only; classify them like GGUF `general.license` (mapped
  in #294). GGUF `general.license.name`/`.link` are also unread.

- [ ] **`setup.cfg` `%` fails the whole run (S).** `description = 50% faster`
  gives `ERROR: SBOM generation failed: '%' must be followed by ...`. setuptools
  84's own `setup.py --description` fails the same way. Decided: keep failing,
  with one `ERROR:` naming the file, section and key and the `%%` fix.
  Precondition met (2026-10-04): pbr 7.0.3 reads `setup.cfg` with
  `configparser.ConfigParser` (interpolating; never Raw in any release checked)
  and fails on `50% faster` too; `%%` works.

## P3: after 0.20.0

Moved to [known-bugs-p3.md](known-bugs-p3.md) for size.

## Leads to verify

Seen in past sessions, not reproduced on current `main`:

- On Windows, `os.replace()` fails while another process holds the
  target open; the registry save should turn that into its existing
  "failed to save" `WARNING:`.
- Windows: `METADATA.` and `METADATA::$DATA` map onto `METADATA`; case
  variants of `.dist-info` names overwrite each other on macOS and
  Windows.
