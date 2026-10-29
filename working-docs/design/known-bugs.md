---
Created: 2026-10-03
Last-Modified: 2026-10-29
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

- [x] **One default SBOM file name on every surface (S-M), built in #334** with
  one helper; the character rule differs from the PEP 427 escaping decided here.
  Original entry: `loom
  project` writes `Foo.Bar-Baz-1.0+local.spdx3.json` unescaped; the
  Hatchling hook uses the raw name; embed's escaper skips `*?"<>|`.
  Decided: PEP 427 escaping everywhere, its own PR.
- [x] **Git LFS pointers outside AI models (M), built for 0.22.0.** One
  detector, one summary `WARNING:` per SBOM, a checkout pointer listed by its
  `oid`, loom `path=` reuses it. See
  [git-lfs-pointers.md](../implementation/git-lfs-pointers.md).
- [x] **A fragment value may lose to an extracted one (S-M, own PR).**
  Confirmed 2026-10-23 and fixed: a fragment's value replaces one Pitloom
  generated from the file's format (`Method: generated_from_labels`,
  `derived_from_format`: the `description`, `ai_domain` and
  `ai_informationAboutApplication` of a model), with one `INFO:` and the
  provenance of that property dropped. A value read from the file still wins a
  conflict, as every other field. Built in `_fragments_generated.py`; see
  [docs/fragments.md](../../docs/fragments.md).
- [ ] **A losing fragment's "generated" claim outlives its value (S, found
  in the 2026-10-23 review of #349).** Fragment A restates the generated
  `description` and carries its own Annotation `Method: generated_from_labels`;
  fragment B gives "curated" and wins. The output holds "curated" with A's
  Annotation (or its comment line) saying it was generated. A fragment's own provenance was never
  dropped when its value lost, but here the claim is false. A fix has to tell
  a fragment's winning entry from a losing one (a fragment whose generated
  value wins keeps its claim, which is true).
- [x] **A respelt copy of a curated value warns (S, found in the 2026-10-23
  review of #349; fixed in #352).** Fragment A replaces
  a generated value; a later fragment A' was A in other JSON spacing and earned
  `WARNING: Merge: conflicting`, while a respelling of the *generated* value
  was silent. The field merge now reads two texts that are the same JSON as one
  value, for a text property merged field by field (`_fragments_equal.py`;
  list items, comments and model names still compare as text: the same JSON
  pair folds as a scalar and stays two list items).
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

## P2: 0.21.0 and later

- [x] **An unknown id in an SPDX-only field is not reported (S-M).** Fixed
  in #357: the value stays text, plus one
  `WARNING:` per value naming the field (`warn_unless_expression`, called by
  each reader where the field is known). See
  [license-typing.md](../implementation/license-typing.md#unknown-id-in-an-spdx-only-field).
  Legacy `License:` stays silent.
- [x] **A Hugging Face `license: gpl-3.0` was rewritten to `GPL-3.0-only`
  only when the `licenseid` database was present (S).** Fixed in #357:
  the Hugging Face route records the card value as stated, so the deprecated
  bare id stays the id written (`GPL-3.0` after classification, never
  `GPL-3.0-only`) with or without the database. `canonicalize_license_id`
  (case fold only) has no caller in `src/`. A non-lexical
  resolver decision (alias, successor) waits for `INFO:` plus provenance, see
  [license-resolution-categories.md](license-resolution-categories.md).
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

- [x] **A very long version number crashes lock-file reading (S).**
  Fixed in #354: `pitloom.core.pep440` refuses a
  version number over 640 digits before `int()` (any interpreter limit,
  `packaging` 25 and 26) for every version, specifier and requirement
  parse; a lock entry, pin or requirement holding one is unusable as any
  invalid one, the project's own `version`/`requires-python` an `ERROR:`.
  `packaging` 25 also failed building a specifier set, 26 printing one of
  several clauses. Was:
  `packaging.Version("1." + "9" * 5000)` raises a plain `ValueError`
  (int digit limit), not `InvalidVersion`; `version_key`,
  `is_usable_version` and `is_same_version` in `extract/lock/common.py`
  catch only the latter. #266 fixed the same class in `verify-wheel`.
  #287 adds a caller: the setuptools `version` conflict check
  (`_field_agreement.values_agree`) crashes the directory read on
  `setup(version='9' * 5000)` beside a `setup.cfg` version.
  Open: the cap is not applied to a `setup.cfg` `version`, a Poetry
  `version` and a wheel `METADATA` `Version`: none is checked for an
  over-long number (not probed).

- [x] **Safetensors licence keys are not mapped (S).** Fixed in the next
  release: `modelspec.license` (the only licence key in 9 real headers read on
  2026-10-28) is the model licence, as written; GGUF `general.license.name`
  stands in when `general.license` is blank or a placeholder (`other`...).
  `general.license.link` stays unread: `AiModelMetadata` has no licence-URL
  field, though SPDX 3.0.1 has `ExternalRefType` `license` for it (a Pitloom
  gap, not a format gap). Safetensors files
  with `license`/`license_name` keys were not seen; add them if one turns up.

- [x] **`setup.cfg` `%` fails the whole run (S).** `description = 50% faster`
  gives `ERROR: SBOM generation failed: '%' must be followed by ...`. setuptools
  84's own `setup.py --description` fails the same way. Decided: keep failing,
  with one `ERROR:` naming the file, section and key and the `%%` fix.
  Precondition met (2026-10-04): pbr 7.0.3 reads `setup.cfg` with
  `configparser.ConfigParser` (interpolating; never Raw in any release checked)
  and fails on `50% faster` too; `%%` works. Fixed in #355
  (`setup_cfg_interpolation.py`): `... setup.cfg:
  '<path>' [metadata] description: '%' must be followed by ...; setuptools
  fails on it too; write a literal '%' as '%%'`. An undefined `%(key)s` and a
  reference loop fail the same way (setuptools 84.0.0 fails on both); a
  `[DEFAULT]` value is named under `[DEFAULT]`; `$` is not special. A test
  asks setuptools' own `read_configuration` for the same verdict and value.
  Open: setuptools also fails on a `%` in any section Pitloom does not
  read (`[flake8]`, `[tool:pytest]`); Pitloom's own read passes it, file
  discovery warns and the SBOM has no file list. A `pyproject.toml`
  `dynamic` field filled from such a `setup.cfg` is a `WARNING:`, not an
  error, though the build fails.

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

## Found 2026-10-23

- [x] **A fragment value loses to a generated one (S-M, fixed).** Probe: a
  Hatchling project holding a CRFsuite model, with a fragment giving the model
  another `description`; the merged SBOM kept the generated one. See the P0
  entry "A fragment value may lose to an extracted one".
- [x] **Untagged setuptools lines on stderr (S).** Cloning
  `zzzeek/sqlalchemy` with `loom project <url>` printed
  `warning: no files found matching '*.js' under directory 'doc'` and
  `no previously-included files found matching …` with no level tag (CLI
  output rule). Not a build child: setuptools' in-process manifest step
  (`include_package_data` in static file discovery) logs through
  `distutils.log`, the root logger, which with no handler falls to
  `logging.lastResort` on stderr; `distutils.text_file` writes there itself.
  A local checkout, `--allow-build`, `embed-wheel --project-dir` and the
  library did the same; the Hatchling hook never runs setuptools discovery.
  Fixed (#356): discovery captures this thread's
  stderr and relays each line as one `DEBUG:` record (`WARNING:` for an
  `error:` line), beside #300's banners. See
  [backend-file-discovery-validation-flit-pdm.md](../implementation/backend-file-discovery-validation-flit-pdm.md).
- See [target-resolution-and-purl.md](target-resolution-and-purl.md) for the
  Bitbucket and SourceHut findings of the same day.

## Found 2026-10-27

From the combined review of #352 to #357. Open:

- [x] **A Git URL's messages name the random temporary checkout (S).**
  Fixed in the next release: `logging_config.mask_checkout`, called by
  `escape_controls` (so by `quote_source`, the stderr formatter and
  `print_error`), writes it `<checkout>` in every message; a path below it
  keeps its tail (`<checkout>/setup.cfg`). Only a directory of `tempfile`'s
  form (`pitloom-git-` and eight characters of `[a-z0-9_]`) is masked, never an
  address (`https://`, `git@host:`), and never stdout `KEY=VALUE` data (the Action reads
  `PITLOOM_SBOM_OUTPUT_PATH`); a local directory keeps its path.
  Known limit: a Windows path with a space before the temporary directory
  (`C:\Users\Jane Doe\...`) keeps the part before the space. Was:
  `Could not parse setup.cfg: '/tmp/pitloom-git-v6mrrlyz/setup.cfg' [metadata]
  ...` and `DEBUG: '/tmp/pitloom-git-82p252s_': setuptools stderr: ...` carry a
  different path each run. Git's own output is masked as `<checkout>`
  (`_git_run.py`), these messages are not. Show a checkout-relative path or
  the URL, through one helper.
- [x] **A failed setuptools file discovery is followed by a second, wrong
  warning (S).** Fixed in 0.21.1 (#365): a per-thread flag set by every
  discoverer that logs a failure (`warn_discovery_failed`,
  `mark_discovery_failed`) makes the fallback line say the discovery failed.
  Was: after `Setuptools file discovery failed for ...` (any cause,
  e.g. a bad `%` in `[flake8]`), `_models_wheel_dispatch` also says `No static
  setuptools config resolvable ... (packages only resolvable via an
  imperative setup.py build)`, as if the config were absent. Found in the
  #357 review; `discover()` returns `None` for both.
- [ ] **The Hatchling hook does not check `requires-python` for an overlong
  number (S).** `loom project` refuses it with an `ERROR:`; in a build,
  Hatchling itself reads the value first and ends with its own `ValueError:
  Exceeds the limit (4300 digits)` traceback before the hook runs. Not
  Pitloom's to catch; noted so the difference between the surfaces is known.
- [ ] **`licenseid` 0.6.0 gives Pitloom no operands (S).** `resolve()`
  answers for a whole value, so a compound with one respelt part (`Apache2 OR
  MIT`) is `expression` with no expression and stays text; the design asked
  for per-operand results (`Resolution-n`, `Expansion-n`). Decision Q5 (the
  licence list version into `simplelicensing_licenseListVersion`) is not built:
  the version is in `Resolution["lists"][0]["version"]` but not yet used. The
  verbatim value and the reading's method have no SPDX property either: FG-6
  and FG-7 in [sbom-format-gaps.md](sbom-format-gaps.md).
- [ ] **A shared licence element keeps the first source's provenance (S).** A
  `MIT License` classifier and a file tagged `MIT` are one `LicenseExpression`;
  its notes (`Method: licenseid_resolution`) describe the first source only and
  the second source's annotation is not written. First-wins is old; the
  resolver merges more values, so it shows more often. Found in the #359
  review.
- [ ] **Two spellings of one deprecated id give two expressions (S).**
  `StandardML NJ` is read as `SMLNJ` (`licenseid` renames), while the listed
  `StandardML-NJ` parses locally and stays as written, so one licence has two
  records. Fixed by letting `resolve()` answer for the whole value (Q7); see
  `licenseid`'s expression-resolution design. Found in the #359 review.
- [ ] **The resolver's reading depends on the database (S).** A comparison
  (`values_agree`, the fragment-merge key of `_license_elements`) treats
  `Apache2` and `Apache-2.0` as one licence with the `licenseid` database and
  as two without it, so whether a conflict is recorded differs. Provenance of
  a value Pitloom parses itself does not (#359).
- [x] **`_merge_dictionary_entries` dropped a differing value without a warning
  (S, found outside the set).** Fixed in #357: two fragments giving one
  `ai_hyperparameter` or `ai_metric` key different values keep the first and
  say so (`Merge: conflicting 'ai_hyperparameter' key 'k' on ...: keeping X,
  dropping Y.`); equal and same-JSON values stay quiet.

## Found 2026-10-28

From the 0.21.0 release review. Open:

- [x] **`embed-wheel --sbom FILE` embeds a file it cannot parse or read as SPDX 3
  (S).** Fixed in the next release: `pitloom._sbom_format.refuse_unusable_given_sbom`
  refuses invalid JSON, a non-object and a `.spdx3.json` that is not SPDX 3
  before the wheel is written. Malformed JSON named `x.spdx3.json` was embedded with a skip
  `WARNING:` (exit 0), where `fragment validate` says `ERROR: Invalid JSON`; a
  CycloneDX file named `.spdx3.json` is now refused too. Parse failure of a
  file the user named should be an error before the wheel is written.
- [ ] **`embed-wheel --sbom FILE` stores another format under a `.spdx3.json`
  name (S).** A valid CycloneDX `bom.cdx.json` is embedded as
  `<basename>.spdx3.json` (with the cross-check `WARNING:`):
  `_derive_wheel_sbom_filename` and `sbom_file_name` always add the SPDX 3
  extension. Decide: refuse a format Pitloom cannot name, or store it under its
  recommended extension (`.cdx.json`, PEP 770 allows any name).
- [x] **A one-character Hub model name is a URL but not an id (S).**
  Fixed in #365: `_HF_ID_RE` takes a one-character name, as `_HF_URL_RE` does.
  `https://hf.co/o/m` logged "read as https://huggingface.co/o/m", then
  `loom model` hands `o/m` to a reader that treats it as a local file:
  `_HF_URL_RE` accepts a one-character name, `_HF_ID_RE` needs two.
- [ ] **The Hatchling hook finds no licence database in an isolated build
  environment (S).** Pitloom 0.21.0 reads a declared licence value through
  `licenseid.resolve()`, which needs a built database. A build in an isolated
  environment never has one, so every project using the hook sees `WARNING:
  licenseid database cannot be used: ... -- license text detection and
  license id reading skipped` and its licence values stay as written
  (`Apache2` is not read as `Apache-2.0`). A project that declares an SPDX id
  is not affected. Reported by a reviewer upgrading a project to 0.21.0.
  Options: (a) `licenseid 0.7.0` makes `resolve()` work with no database from
  the packaged bundle that the PyPI wheel already ships (design:
  `licenseid` `working-docs/design/expression-resolution.md`, "No database");
  (b) until then the hook builds a database from the packaged bundle
  (`licenseid update --source packaged`, offline) into a location of its own,
  not the user's cache, or keeps the single warning and says why. Today the
  same value gives different SBOM bytes with and without a database.
  Mitigated in 0.21.1 (#364): a missing database is `INFO:` when a licence is
  declared (the warning stays when none is declared or for a value that needed
  licenseid's reading). Fixed for good when Pitloom 0.22.0 reads declared
  values through `licenseid` 0.7.0 (plan: #368).

## Found 2026-10-29

From the Git LFS pointer work. Open:

- [x] **`dataset_datasetSize` held a record count (M), fixed in #382.** A
  Croissant `totalItems` filled it, but SPDX defines it in bytes. `totalItems`
  is not Croissant, so it is no longer read; `DatasetMetadata.byte_size` (bytes,
  library callers only) replaces `dataset_size`. A count has no 3.0.1
  property: FG-12 in [sbom-format-gaps.md](sbom-format-gaps.md).
- [x] **A pointer's registry entry flipped between routes (M), fixed in
  #378.** Each harvest wrote its SBOM's hash, the `oid` (checkout) or the
  pointer text's digest (wheel, sdist, `--allow-build`), so alternating runs
  rewrote the entry and `id generate` after a wheel run minted. Now the
  registry holds the `oid` on every route and every lookup uses it.
- [ ] **`id import` of a wheel or sdist SBOM holds the text's digest (S,
  decided: kept).** `id import` records what an SBOM states; the next run
  misses once for each pointer (a new id), then holds.
- [ ] **A loom fragment's pointer does not unify with the hook's or an
  `--allow-build` run's (S-M).** The fragment's element states the `oid`,
  the archive's the text's digest: the merge keeps two `software_File`
  elements for one path. Harvest no longer loses the id over it (#378: the
  fragment's element is the pointer's twin, never written; before, the key
  was ambiguous, nothing was recorded, and the next checkout minted).
  Long-term fix: fold the two in the merge by the registry hash
  (`_MergeIndex` indexing a document file under its `registry_hashes`
  entry). Not done: it changes SBOM output, and the survivor's hash list
  must not take the `oid`, which is not the digest of the shipped bytes
  (`RECORD`), nor drop the fragment's provenance.
- [ ] **A loom dataset package over a pointer differs from the main
  document's (S).** Its Merkle root takes the `oid`; the hook's package root
  takes the text's digest.
- [ ] **The `Tool`/`SoftwareAgent` "Pitloom" registry entries churn (S).**
  Their id's document-uuid part flips on each project-then-wheel
  alternation, so the registry is rewritten each run (not pointer-specific;
  tracked in
  [id-registry-followups.md](id-registry-followups.md#harvest-rewrites-per-document-entities-env-root-is-never-looked-up),
  allow-listed in the order checks).
- [x] **The two size ceilings have no flag (S-M), built in the ceilings PR.**
  `--max-model-extract-bytes` (every wheel surface, inert elsewhere; Action
  input) and `--max-dataset-hash-bytes` (`loom id generate`;
  `loom.Run(max_dataset_hash_bytes=)`; no Action input, since no Action step
  hashes a dataset); `0` stays an error.
- [ ] **The clone cap is missing from `generate()`, the CLI, config and the
  Action (S-M),** and its over-cap message is outside the shared wording.
  Only the library's Git entry point takes `max_bytes=` (#339).
- [x] **`loom id -e` ignored the project's dataset ceiling (S), fixed in the
  ceilings PR.** Flag, then the project's own key, then the default.
- [ ] **The blob-filter docs say "10 MB"; git's `10m` is 10 MiB (S).**
  `BLOB_LIMIT` in `extract/remote/git.py`; fix `docs/git-urls.md`.
- [ ] **A dataset's identity can change from a hash to omitted after a pull
  (S).** A pointer-based dataset is hashed from the `oid`s; once pulled, stated
  sizes above the ceiling mean no hash. The SHA-256 is otherwise unchanged.
- [ ] **The hook's and `loom project`'s document ids differ for a project
  with Git LFS pointers (S, decided: kept).** The Merkle leaf of a pointer is
  the pointer text's digest in the hook (it matches `RECORD`) and the `oid` in
  `loom project`; file ids are shared (the registry holds the `oid`).
- [ ] **`--allow-lfs-fetch` (idea).** Fetching LFS content contacts a second
  server the Git URL guard does not cover; reuse the clone cap if built.
- [ ] **A loom fragment's document namespace is a random `uuid4` per run (S).**
  `_ActiveRun` sets `doc_uuid = str(uuid4())` (`_loom_active_run.py`), so the
  same script gives different `spdxId`s each run unless an ID registry pins
  them; the idempotence rule (no random UUIDs) holds only with a registry.
  Found while testing the dataset-size fix: the determinism test sits on
  `build_model`, not on `loom.run`.

## Found 2026-10-29 (evidence-levels review)

From an Opus review of the provenance code against `evidence-levels.md`:

- [x] **After a comment merge the second `Metadata provenance:` block is not
  found by the drop helpers (S), fixed (#386).** `_merge_comment`
  joined comments with `"; "` (`_fragments_props.py`);
  `provenance_comment_parts` strips the prefix only at the start of a line. A
  provenance line now starts a line of its own on either side of the join, and
  a `not_measured` entry goes when the merged element gains the value
  (`_fragments_evidence.py`).
- [ ] **An unreadable project file is logged with the raw exception (S).** The
  skip in `core/_models_wheel.py` logs `exc`, not `one_line`/`loggable`, and an
  `OSError` text can hold an absolute path.
- [ ] **A `404` from the Hub looks like a failure (S).** `_safe_load_json` in
  `extract/remote/huggingface_fetch.py` cannot tell a 404 from a failed request
  and logs DEBUG only, so no `failed` entry is possible there without the 404
  check `huggingface_dataset.py` already has.
- [x] **Provenance `Source:` strings built from a file or label name outside
  `assemble/spdx3` were not sanitised (S), fixed (#389).** A `|` in the name
  added a segment (a forged `Evidence:` or `Method:`). Every provenance
  string is now built by `provenance_source`/`provenance_segment`
  (`core/provenance.py`): the setup.cfg/pyproject directives, the installed
  dist-info label, licence and copyright file and archive names, the dataset
  labels (Croissant, card, licence), the lock-file cascade, the merged
  setuptools and optional-dependency sources, `Normalized-From` and the
  `Resolution-1`/`Expansion-1` steps, a dependency marker in
  `declared_constraint` (a real forge: `os_name == "x | Evidence: ..."`),
  the loom caller and the AI-model readers. The pdm, Poetry, setuptools,
  Hugging Face and README-card sites interpolated constants only (defence in
  depth). `tests/test_provenance_builders_lint.py` keeps it so.
- [x] **The LFS-pointer `WARNING: FILE=...` line prints the path unquoted (S),
  decided: kept.** The path goes through `loggable`, as in every sibling
  `FILE=` line: a newline is escaped (one record), `|` is inert in a log
  line, and a bare space is family-wide. A quoted `FILE=` would be one PR for
  the whole family; characterised in `tests/core/test_lfs_pointer_warning.py`.
- [ ] **A project file whose name is not valid UTF-8 crashes generation (S).**
  For `src/demo/\xff.py` the provenance Annotation now passes (the
  sanitiser escapes the lone surrogate), but
  `export/spdx3_json.py::_graph_sort_key` raises an `rfc8785` error on the
  element's own `name`. Needs its own fix and an end-to-end regression test.
- [ ] **A plain-text provenance value with a `:` reads as a key (S).**
  `declared_constraint` holds requirement text, but `emit_provenance` parses
  every value as `Key: value`: `pkg @ https://x/p.whl` gives the key
  `pkg @ https`, and a marker holding a `:` gives one too. Such a value should
  be written as a `note`.
- [ ] **A base element holding both a value and a `not_measured` entry loses the
  entry when a fragment folds into it for an unrelated field (S).** Needs a
  forged entry, which sanitising now blocks; ruling it out means tracking which
  side of each fold supplied the entry.
