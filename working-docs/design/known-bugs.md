---
Created: 2026-10-03
Last-Modified: 2026-10-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs, by priority

See also: [roadmap.md](roadmap.md),
[id-registry-v3.md](id-registry-v3.md),
[id-registry-followups.md](id-registry-followups.md),
[canonical-output-followups.md](canonical-output-followups.md) (open
canonicalisation questions behind several bugs here).

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
  summary `WARNING:` per run, one line per file at `--debug`; lands
  before registry v3, which reuses it for loom `path=`.
- [ ] **A fragment value may lose to an extracted one (S-M, own PR).**
  Unconfirmed in #294: a fragment or catalogue `description` should win
  over the one generated from a CRFsuite model's labels
  (`Method: generated_from_labels`); check the merge order treats
  extracted and generated values as weak, for every field, not only this
  one.
- [ ] **Same AI model gets different ids per surface; enrichment can hit
  the wrong model (S-M).** Found in the #292 review: `loom model` looks an
  AI model up in the registry by file stem only. `_model_generator.py`
  (single-model SBOM and `enrich_model()`) passes `model_path.stem`, while project scans
  try name, then path, then stem (`_ai_model_entity_candidates`), so an id
  imported from a model SBOM whose package carries its own name never
  hits for `loom model`. Reuse the candidates helper. Related: `loom id
  generate` derives the stem itself (`id_registry/_registry.py`, `Path.stem`)
  rather than through `AiModelMetadata.file_name_stem`; add a drift-guard
  test or share it. Reproduced end to end (#292 black-box round, same on
  `main`): `dup_named.onnx` (graph name `dup_stem`) and `dup_stem.onnx`
  (no name) in one project; `id generate` keys both by stem, the project
  scan gives `dup_named.onnx` the id of `dup_stem`, `dup_stem.onnx` gets a
  fresh id each run (never written back, so the collision warning repeats),
  and `loom enrich dup_stem.onnx` targets the package the project SBOM gave
  `dup_named.onnx` -- a merged fragment enriches the wrong model. The
  warning also labels `dup_named.onnx` by its own name `dup_stem`, so it
  reads as a file colliding with itself; name the file too.

## P1: fixed by registry v3 in 0.21.0 (decided, in its spec)

- [ ] **Wheels with no `Name` share one package id.** Two different
  wheels both become `unknown` and the second reuses the first's IRI
  (Q-C: folded into v3).
- [ ] **A registry inside the scanned tree never settles.** Each run
  hashes the registry as a project file, then rewrites it: 4 runs, 4
  different SBOMs and registries.
- [ ] **A project under any `build/` directory indexes nothing.**
  `_is_eligible_file` matches ignored directory names against the
  absolute path (`id_registry/_types.py`); `loom id generate` writes 0
  files, silently.
- [ ] **Same-stem model files share one entity.** `a/model.gguf` and
  `b/model.gguf` get one `ai_AIPackage` key (Q-A: key by project path).
- [ ] **A package key without a version gives every release one id**
  (Q-D: PEP 503 name plus PEP 440 version).
- [ ] **`normcase` does not fold case on macOS**, so a `same_path`
  helper built on it misses case variants; use `(st_dev, st_ino)`.

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

- [ ] **`loom wheel` invents a copyright text (S).** With no author name
  in `METADATA` (only `Author-email`), `document.py` writes
  `Copyright (c) <SBOM year> <package name>`: neither holder nor year comes
  from the package. Pitloom's own wheel gets `Copyright (c) 2026 pitloom`
  and no supplier, where the hook records the author. Seen on 0.19.0 too.
- [ ] **Extras-only dependencies are plain `dependsOn` in a wheel SBOM
  (S-M).** `loom wheel` lists every `Requires-Dist`, `extra == ...` ones
  included (Pitloom's wheel: 27 packages, 11 extras-only), with no marker
  or scope; the hook and `loom project` list 16. Seen on 0.19.0 too.

- [ ] **A very long version number crashes lock-file reading (S).**
  `packaging.Version("1." + "9" * 5000)` raises a plain `ValueError`
  (int digit limit), not `InvalidVersion`; `version_key`,
  `is_usable_version` and `is_same_version` in `extract/lock/_common.py`
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

- [ ] **Deep metadata text depends on call-stack depth (S).**
  `core/ai_metadata.py:162` `_collection_text` falls back to
  `<nested over 32 levels>` on `RecursionError`, so the CLI and the
  Hatchling hook (deeper stack) can write different bytes for a 500-950
  deep PT2 `extra/tags`. Decide from an explicit depth count.
- [ ] **Display escape can merge two JSON keys (S).** Keys `"a<U+202E>"`
  and `"a\\u202e"` in one `ai_informationAboutApplication` object spell
  the same after `escape_display_controls_in_json`; one entry is dropped.
- [ ] **PT2 tags spelt as Python repr (S, cross-format).**
  `pytorch_pt2.py:233` uses `source_element_text()` (scalars only) for
  non-scalar tags: `a, {'k': [1, True]}, null`. Use canonical JSON, as
  HDF5 `metrics` and `labels` do.
- [ ] **Label count recorded differently (S, cross-format).** CRFsuite
  always has `properties.num_labels`; fastText only `outputs[0].shape`,
  and nothing when all labels are dropped. CRFsuite with 0 labels emits
  `labels = "[]"`, supervised fastText with none emits nothing.
- [ ] **CRFsuite description ambiguity (low).** Labels joined by `", "`
  (a label may contain it or a newline); `backslashreplace` `\xff` looks
  like a real 4-character label.
- [ ] **fastText `getArgs()` failure drops `domain` silently (low).**
  The warning does not name `domain`.
- [ ] **`_loom_active_run.py:185` names the document `self.model.name or
  "model"` (low).** Not in this diff; check it against the name cascade.

- [ ] **Escape/cap hardening from the Opus review of #294 (S each).**
  (a) Hangul fillers U+115F, U+1160, U+3164, U+FFA0 render blank but are
  not in `DISPLAY_CONTROLS`; add, plus a test that every Bidi_Control is
  in the set or on a named exclusion list. (b) U+200B-U+200D are escaped
  in prose, so Thai/Persian/Indic ZWNJ/ZWJ text is mangled and warns;
  escape them only in identity fields. (c) fastText has no label-count
  cap; share `recordable_labels` with CRFsuite. (d) Lone-surrogate escape
  runs before the name cut, which may split `\udXXX`. (e) Format-only
  stub entries skip `settle_read_text` (non-UTF-8 stem would raise
  `CanonicalizationError`); `physical_path` should stay out of the walk.
  (f) `_license_classify._replace_surrogates` uses U+FFFD, the shared
  rule `\udXXX`.

- [ ] **`-v` logs `OUTPUT_PATH=-` for both "no copy" and "copy to stdout"
  (S).** `wheel --embed -v` (no `-o`) and `wheel --embed -v -o -` print the
  same line (`cli/commands/wheel.py`, `docs/cli.md` "Verbose output"). Omit
  the key when nothing is written (#288 review).
- [ ] **Action `output: "-"` sets `sbom-path=-` (S).** The upload step then
  fails on a path named `-`. Refuse `-` in `action.yml`, or write the SBOM
  to a file (#288 review).
- [ ] **Library docs never say `output_path="-"` means stdout (S).**
  `write_sbom_output` gives every generator and `embed_wheel_sbom()` that
  meaning; neither the docstrings nor `docs/python-api.md` state it, and no
  library-level test pins it (#288 review).
- [ ] **`--help` choice order changes per run (S).** `choices=` takes a
  frozenset (`VALID_CONTENT_TYPE_METHODS`, `VALID_CREATOR_TYPES`), so
  `{auto,extension,magika}` prints in hash order. Pass a sorted tuple.
- [ ] **Installed-dependency `METADATA` is read unlike a wheel's (S).**
  `deps_installed.get_pkg_metadata` reads text through `importlib.metadata`
  (newlines translated, strict UTF-8): a CRLF `METADATA` gives a licence
  text without CR where the wheel reader keeps it, and a non-UTF-8 one
  raises `UnicodeDecodeError` and aborts the run. A dist-info with no
  metadata file stays silent. Use the wheel's `read_header_block` +
  `HeaderParser` (#286 review).
- [ ] **Hugging Face and classifier names state no licence to detection
  (S).** `huggingface_fetch` and `stated_license()` call
  `detect_license_from_text` without `stated=`, so a repo `LICENSE` with a
  card `license: apache-2.0` near-tie gives no detection; a classifier name
  (`MIT License`) never matches an id (#286 review).
- [ ] **Licence detection reads each text twice (S).** With a notice line,
  the matcher runs on the text as written and without the notice: about
  twice the time per licence text. Skip the second reading when the first
  is decisive at a high score (#286 review).
- [ ] **numpy licence text keeps one extra leading space per line (S).**
  meson-python folds `License:` with 9 spaces; `_unfolded` strips 8.
  Whitespace-only lines are blank on every surface since #286; the extra
  space stays (as
  0.19.0). Stripping a writer's whole fold width needs telling it from the
  text's own indent.
- [ ] **GitHub Action drops invalid boolean inputs silently.** Any
  non-empty value other than exactly `true`/`false` (`maybe`, `True`) on
  the tri-state `enrich`, `extract-file-header`, `update-id-registry`,
  `content-type`, `offline`, `use-lockfile`, and on the two-state
  `pretty`, `allow-build`, `no-build-isolation` (case-sensitive
  `= "true"`, so `allow-build: True` skips the build) passes no flag and
  prints no warning; `use-lockfile` in model/embed-wheel mode is dropped
  silently too.
- [ ] **Non-directory targets ignore configured fragments.** `loom model`
  (and `generate` on a model file), Hugging Face, `wheel`, `env` and sdist
  runs never call `merge_fragments()`, so fragments in `--config` or
  project config are dropped with no `WARNING:` and exit 0. The
  `sbom-enrich` skill says so.
- [ ] **`loom env` loses an unmet requirement.** A dependency pipdeptree
  reports as not installed (`installed_version: "?"`) loses its
  `dependsOn` edge with no trace (#236 review).
- [ ] **`loom env`: two installs sharing one pipdeptree `key` collide.**
  `build_deployed` keys its id map by `key`, so an editable copy next to
  a site-packages copy overwrites the first; all edges go to one element.
  Not seen from pipdeptree yet (#236 review).
- [ ] **setuptools discovery: absolute `physical_path` for a project dir
  named in another letter case.** On macOS and Windows, `loom project
  stproj` for on-disk `StProj`: the discoverer's `chdir()` +
  `os.getcwd()` gives the on-disk case, which no longer matches
  `project_dir` textually. Other backends are unaffected (#257 review).
- [ ] Case-insensitive member-name collisions in wheels; `--allow-build`
  extraction keeps the last duplicate with a warning.
- [ ] A scan in a worker thread registers its temp-dir cleanup with its
  own guard, so the dir can outlive SIGTERM to the main thread.
- [ ] `embed-wheel` temp file on SIGTERM (P4): `BaseException` cleanup is
  in place; signals are still uncovered.
- [ ] Pin one CI leg to an unpatched `zipfile` (pre CVE-2025-8291).
- [ ] The signed release wheel and SBOM are not reproducible: `created`
  and `builtTime` come from the clock. Set `SOURCE_DATE_EPOCH` (last
  commit time) in `pypi-publish.yml`'s build job so anyone can rebuild and
  compare against the signed bytes.
- [ ] Windows `--build-timeout`: when a process in the build tree exits on
  its own during `taskkill /F /T`, taskkill reports failure, so the
  `WARNING:` says "could not confirm the build process tree terminated"
  although it did. A Job Object would confirm it (0.21.0).
- [ ] **The registry harvest `INFO:` can print a negative count (S).**
  `_sync_registry()` (`assemble/_generators_shared.py`) logs `added %d
  new file(s), %d new entit(y/ies)` from the net counts of `harvest()`.
  Two library calls on the example project in a row printed `added 0 new
  file(s), -1 new entit(y/ies)`: a stale key released in the same pass
  makes the net count negative. Log gross additions, or the "updated stale
  entries" line when any count is not positive. Found while checking doc
  examples.
- [ ] **`loom.run` never calls `configure_logging()` (S).** `loom.py` and
  `_loom*.py` have no call, so a script using the decorator or context
  manager prints its registry messages (`_loom_caller.py`,
  `_loom_active_run.py`) bare, with no `WARNING:` tag. Those messages also
  say `loom: ...` where every sibling `pitloom.id_registry` message says
  `ID registry: ...`. Seen running `examples/sentimentdemo-aibom`'s
  `train.py` on current `main`. The same example's committed
  `loom-id-registry.json` is stale against its scripts' hashes, so running `train` and
  `evaluate` straight from a checkout (the pipeline script refreshes the
  registry between stages) logs the "SHA-256 no longer matches" message.
- [ ] **`loom fragment validate A B` fails on two `loom.run` fragments (S).**
  Both fragments name their creation info `_:CreationInfo0`, so the
  merged-graph check sees one `CreationInfo` with several `created` values
  (14 `ERROR:` lines); each fragment alone, and `--no-merge`, is valid.
  `loom merge` of the same three fragments succeeds. Not yet checked
  whether the validator or Pitloom's blank-node labels are at fault.
- [ ] **AI model `framework` provenance cites a value the SBOM never
  shows (S).** Found in the #292 black-box round, same on `main`: ONNX
  `producer_name`/`producer_version` land in `format_info.framework*` and
  their provenance reaches the package comment and annotation, but nothing
  in `assemble/` writes `framework` (nor `framework_version`). Either emit
  it or drop its provenance (check the other readers).
- [ ] **A model licence that is a name or URL becomes licence text (S).**
  Found in the #292 black-box round: ONNX `model_license` "Apache License
  2.0" gives a `SimpleLicensingText` holding the name, not `Apache-2.0`; a
  URL is kept as text, not a reference. The rule to apply is open: C12 and
  C18 in [canonical-output-followups.md](canonical-output-followups.md).
- [ ] **Model provenance cites fields the SBOM never shows (S-M).** Found
  in the CRFsuite review (same for fastText and others): `framework`,
  `format_version` and `properties.*` get provenance in the package comment
  and fields annotation, but nothing in `assemble/` emits those fields, and
  a shipped model skips the artifact-metadata annotation under
  `preserve-source-metadata=auto`, so the values (e.g. CRFsuite labels
  beyond the 20 in the description) appear nowhere. Either emit them or
  drop their provenance. Repro: `loom project` (or `loom wheel`, auto mode)
  on pythainlp gives 8 `ai_AIPackage` and 0 artifact-metadata annotations,
  while each `fields` provenance still cites `properties.*`.
- [ ] **`loom model` on a 100-byte truncated `lid.176.ftz` ran to about
  20 GB RSS (S).** Native fastText reader on a hostile header, found in the
  CRFsuite review (a 400-byte cut reached about 7 GB); the metadata-only fastText reader in
  [model-metadata-readers.md](model-metadata-readers.md) closes it.
- [ ] **`loom merge` of a `loom enrich` fragment and a model SBOM writes
  invalid SPDX (M).** Found in the option D black-box round, not caused by
  it: merged elements get `creationInfo: ""` and a CreationInfo with no
  `@id`, so `loom fragment validate` fails, with or without annotations.
  Related to, but not the same as, the `_:CreationInfo0` entry above.
- [ ] **Bidi controls in annotation keys are not escaped (S).** Found in
  #294: a model key with U+202E stays raw as a key of a provenance
  annotation's `fields` object (`hyperparameters.<key>`) and in an
  enrichment annotation's `changes[].field`/`after` (`datasets:<name>`,
  uncut too). Both are JSON statements, not display properties; escaping
  them needs the dict key kept raw for lookups and the display form only at
  the statement, through `escape_display_controls_in_json`. Documented in
  `metadata-reading-back.md`. The artifact-metadata annotation stays as
  read by design.
- [ ] **ONNX graph and input names are not in the artifact-metadata
  annotation (S).** Found in #294: the docs say the annotation keeps the
  text the display escape changed, but ONNX `raw_metadata` holds only
  opsets and `metadata_props`, so an escaped graph or input name has no
  original in the SBOM. Add them, or narrow the claim per format.
- [ ] **A base model URL is unbounded (S).** Found in #294: the base model
  name is cut at 1024 characters, but its `externalRef` locator
  (`https://huggingface.co/<id>`) keeps the whole id read (a 1 MiB id gives
  a 1 MiB locator). Bound or drop an over-long locator.
- [ ] **Over-cap CRFsuite model keeps only its name (S).** A model with more
  than 1,000 labels (or a hostile `num_labels`) gets the stub entry, though
  the header counts are cheap to read. Same stub rule as every format;
  revisit with the metadata-only readers.
- [ ] **Empty `x.crfsuite` and empty `x.model` give different messages from
  `loom model` (cosmetic).** `file is empty` vs `not an AI model file of a
  supported format`; the shared-suffix rule explains it.
- [ ] **Licence provenance can cite a property key the entry cap
  dropped (S).** Found in the #292 black-box round: with 1,500
  `metadata_props` and `model_license` last, the licence is still read
  (correct) and cites `Field: metadata_props.model_license`, a key no
  longer in the capped `properties`. Harmless (the field name is a pointer
  into the file, not the SBOM); decide whether the cap keeps keys that
  other fields cite.
- [ ] **`Source: Pitloom generator | Method: ...` is hand-written at 7
  sites (S).** Found in the #292 review: `core/ai_metadata.py`,
  `extract/env.py` and four `inferred_from_authors` sites (pyproject,
  poetry, setuptools options, hatchling). Add one helper in
  `core/provenance.py` (e.g. `generator_provenance(method)`) and use it at
  each.
- [ ] **File licence and README licence disagree silently (S).** Found in
  the #292 review: with `--enrich`, the README enricher only fills a
  missing licence (`enrich/readme.py`), so an ONNX file declaring
  `Apache-2.0` next to a README saying `mit` keeps `Apache-2.0` with no
  message. #292 made ONNX files carry a licence for the first time, so
  this can now happen for ONNX as for the other formats. Decide whether a
  disagreement is a `WARNING:` (see
  [license-rules.md](license-rules.md)).

- [ ] **Keras v3 does not read `compile_config` (S).** The HDF5/Keras v1-v2
  reader takes optimizer, loss and metrics from `training_config`; the v3
  reader (`keras.py`) reads `config` and `build_config` only.
- [ ] **PT2 / ExecuTorch reader never sets `type_of_model` (S).** No
  `ai_typeOfModel` for a `.pt2`, though `framework="executorch"` is set.
- [ ] **PT2 root-level `version` file is read as the model version (S).**
  `_read_pt2_zip` (`pytorch_pt2.py`) takes it as `version`, overridden by
  `extra/model_version`. Unverified (no `torch` here): a real
  `torch.export` / `torch.save` zip is believed to hold a serialization
  format number there, which would be a format version, not a model version.
  Check against a real archive.
- [ ] **`AiModelUsage` has no producer (M).** `limitations`,
  `safety_risk_assessment`, `known_biases`, `intended_use` and
  `unintended_use` are assembled (`_ai_package.py`) but no reader or Hugging
  Face fetch fills them. Wire a source (model card sections) or drop them.
- [ ] **Safetensors tensor names are recorded as `inputs` (S).** The reader
  calls it a "lightweight inventory"; `ai_informationAboutApplication`
  inputs mean model inputs. Check this is intended (the PT2 `model.json`
  graph names are the same kind of stand-in). Same class: PT2 lists lifted
  parameters as inputs (below); ONNX initializers were fixed in #294.
- [ ] **ONNX loads the whole protobuf into memory (M).** `onnx.load(...,
  load_external_data=False)` still parses every graph node. fastText's full
  load is logged above; both go with the metadata-only readers in
  [model-metadata-readers.md](model-metadata-readers.md).

- [ ] **Model dtype vocabularies differ across formats (S-M).** Found in
  #294: ONNX and NumPy write NumPy names (`float32`), Safetensors its own
  (`F32`, `BF16`). Pick one vocabulary for `inputs`/`outputs` `dtype`.
- [ ] **GGUF licence `other` and comma lists (S, needs a decision).**
  Questions, moved to
  [canonical-output-followups.md](canonical-output-followups.md#6-licence-identifiers-expressions-and-texts)
  (C15, C16).
- [ ] **GGUF hyperparameter suffixes incomplete (S).** Not matched:
  `.attention.layer_norm_epsilon`, `.expert_count`, `.expert_used_count`,
  `.rope.scaling.*`; they land in properties.
- [ ] **One invalid UTF-8 GGUF string fails the whole file (S).**
  `_field_value` decodes strictly; the `UnicodeDecodeError` (a `ValueError`)
  becomes "Failed to read GGUF file". Decode with replacement, one `WARNING:`.
- [ ] **GGUF `general.license` with a zero-width character (S).** A
  question, moved to
  [canonical-output-followups.md](canonical-output-followups.md#c17-invisible-characters-at-the-edges-of-a-licence-value)
  (C17).
- [ ] **PT2 lists lifted parameters as inputs; framework `executorch` (S).**
  `example-model.pt2` (`archive_format` `pt2`: a `torch.export` archive, not
  an ExecuTorch `.pte`) gives inputs `p_line_weight`, `p_line_bias`, `x`;
  `signature.input_specs` marks only `x` as `user_input`. Read user inputs
  only, framework `pytorch` with `torch_version` (`2.11.0`, unread). The
  fixture's `details/pytorch-pt2.md` claims `inputs` = `[x]`. Malformed
  `model.json` shapes: see the PT2 entry at the end of this section.
- [ ] **Safetensors name and framework (S).** `ss_base_model_version` (the
  base model, not this one) is a name candidate; prefer `ss_output_name`.
  Framework is the raw `format` value `pt`, not `pytorch`.
- [ ] **Keras `layer_count` counts `InputLayer` (S).** `len(layers)` in
  `hdf5_config.py`; Keras's own summary does not count it.
- [ ] **Type of model holds a class or training mode (S).** PyTorch
  `OrderedDict` (a state dict) and fastText `supervised`/`cbow`/`skipgram`
  reach `ai_typeOfModel`; neither is a model type. Map or drop.
- [ ] **`software_primaryPurpose` never set on `ai_AIPackage` (S).**
  Documented as fragment-only; decide whether a model gets `model` by default.
- [ ] **Quantised fastText (`.ftz`) leaves `quantization` empty (S).**
  `args.qout`/the quantised state is never read.
- [ ] **CRFsuite description ambiguous; hash-table offset 0 (S).** Empty,
  comma or backslash labels read ambiguously in `CRFsuite model with N
  labels: a, b` (quote them). `_check_hash_tables` skips a table with offset
  0 even when its count is non-zero.
- [ ] **AI model usage hint names CLI flags in library messages (S).**
  `_USAGE_HINT` (`extract/scanner.py`) says `pass --scan-model-usage` from
  `generate_project_sbom()` and the hook too; the setting text differs per
  producer. Word it per surface through one helper.
- [ ] **Unreadable model handling differs by case (S).** A truncated
  `.crfsuite` or `.onnx` exits 0 with a `WARNING:`; an empty `.model`
  exits 1 with `ERROR: ... not an AI model file`. The ONNX warning repeats
  itself: `failed to extract metadata; Failed to load ONNX model from <path>`.

- [ ] **Keras v3 `config.json` values are not type-checked (S).** Found in
  the #294 review: `extract/ai_model/keras.py:83-98` takes `class_name` and
  `config.name` as they are, so `"class_name": {"a": 1}` or a non-string
  name aborts the whole run (`loom project` exits non-zero). Share
  `hdf5_config.parse_model_config` between Keras v1/v2 and v3: v3 also
  omits `InputLayer` `batch_shape` inputs, `layer_count` and the
  `model_name` fallback, and drops `dtype` from hyperparameters, unlike
  HDF5. Add a drift-guard test over one model in both formats.
- [ ] **PT2: a malformed `model.json` drops all PT2 metadata (S).** Found
  in the #294 review: `models/model.json` as a list, `graph_module` as a
  list, `"inputs": null` or a non-string tensor name each lose every PT2
  field (`pytorch_pt2.py:265-278`), not just the bad one.
- [ ] **Blank text fields are kept by some readers (S).** Found in the #294
  review: Safetensors and ONNX `doc_string` and GGUF `general.description`
  keep a blank or padded value (`"  "`) with its provenance, while PT2,
  GGUF `general.version` and ONNX `model_license` strip it and drop a blank
  one. One shared stated-text helper for every reader.
- [ ] **fastText labels have no cap (S).** Found in the #294 review: a
  trained model records all its labels (1,200 in one), with no cap or
  `WARNING:`, while CRFsuite stops at 1,000; the docs describe only
  CRFsuite's cap.
- [ ] **`numpy.timedelta64` makes `canonical_json` raise (S).** Found in
  the #294 review: it is a `numbers.Integral`, so `json_safe` takes it as
  an integer and raises `TypeError`. No reader yields one today.
- [ ] **`escape_display_controls_in_json` edge cases (S).** Found in the
  #294 review, no reachable path: two keys can escape to the same text
  (the later stays, silently), and a decoded `\ud800` next to a control
  raises `CanonicalizationError`.
- [ ] **Model metadata spellings differ across readers (S).** Found in the
  #294 review: counts are `num_labels`/`num_features` in CRFsuite and
  fastText but `GGUF.tensor_count`, `layer_count` and
  `archive_member_count` elsewhere; `type_of_model` mixes class names,
  training modes and families (see the type-of-model entry above); a
  non-string Keras v3 `date_saved` lands in properties as an integer.

## Leads to verify

Seen in past sessions, not reproduced on current `main`:

- On Windows, `os.replace()` fails while another process holds the
  target open; the registry save should turn that into its existing
  "failed to save" `WARNING:`.
- Windows: `METADATA.` and `METADATA::$DATA` map onto `METADATA`; case
  variants of `.dist-info` names overwrite each other on macOS and
  Windows.
