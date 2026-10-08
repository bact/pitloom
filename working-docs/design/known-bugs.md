---
Created: 2026-10-03
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs, by priority

See also: [roadmap.md](roadmap.md),
[id-registry-v3.md](id-registry-v3.md),
[id-registry-followups.md](id-registry-followups.md).

Bugs found up to #286, each reproduced on `main` unless marked
otherwise. Features and design work stay in the roadmap. A fixed item
stays ticked, with its PR, until its release ships, then moves to
[roadmap-completed.md](../implementation/roadmap-completed.md).
Size: S under half a day, M about a day.

## P0: in 0.20.0

All fixed; most change SBOM output.

- [x] **Every licence is emitted as an off-list licence text (M).** Fixed by
  #276. All
  licence elements came from `_get_or_create_license_element()`
  (`assemble/spdx3/deps_license.py`), which always built a
  `simplelicensing_SimpleLicensingText`, defined by SPDX 3 as a licence
  "not listed on the SPDX License List". `MIT`, `MIT AND Apache-2.0` and
  `NOASSERTION` all become custom licence texts; no
  `simplelicensing_LicenseExpression` and no
  `expandedlicensing_NoAssertionLicense` is ever emitted. The normaliser
  runs only when two licence sources conflict, so `license = "mit and
  apache-2.0"` stays verbatim with no `WARNING:`. Affects dependencies,
  wheel `License-Expression`, AI models and Hugging Face cards, and
  per-file `SPDX-License-Identifier`. Decided for 0.20.0: NOASSERTION
  becomes the `expandedlicensing_NoAssertionLicense` individual;
  normalised expressions use canonical term order, the raw value kept in
  provenance. Land before G7 #3 (dataset licences).
- [x] **sdist member order changes ids (S).** Fixed by #272. The same five files
  in reverse archive order gave PKG-INFO `File-2` in one SBOM and `File-8` in
  the other. Sort members before minting, as #266 did for wheels.
- [x] **`sbom-basename = "x.spdx3.json"` gives `x.spdx3.json.spdx3.json` (S).**
  Fixed by #273. Treat the value as a base name; strip a given `.spdx3.json`.
- [x] **Re-embedding lists the previous embedded SBOM (S).** Fixed by
  #271 (payload-only wheel SBOMs); a cross-surface regression test pins
  it.
- [x] **A negative `--max-source-metadata-bytes` is accepted (S).** Fixed by
  #280 (1-7 too). `-1` runs with exit 0; reject it with the one-line config
  error, as `max-model-extract-bytes` does.
- [x] **sdist runs no in-package licence detection (S-M).** Fixed by #283. No G2
  concluded second opinion and no declared fallback when the manifest is silent;
  the directory has both. (Was "sdist `license_files` are not read"; that field
  went with #271.) Decided: shared detection helper for sdist and directory, 256
  KiB licence-member cap with one `WARNING:`, deterministic case pick, PKG-INFO
  cap, PKG-INFO-less sdist reads `project.license`; `License-File:` selection in
  0.21.0.
- [x] **An unknown `[tool.pitloom]` key is ignored silently (S).** Fixed by
  #280. `ofline = true` gives no warning. Decided: one `WARNING:` per key, run
  continues.
- [x] **`.WHL` (uppercase) is handled differently per surface (S).** Fixed by
  #278.
- [x] **`enrich`/`merge`/`fragment` stdout is prose, not `KEY=VALUE`
  (S).** Fixed by #281 (every subcommand).
- [x] **`lock-hash-preservation.md` says "Poetry 2.1+ writes per-package
  `files`"** -- lock-version 2.0 does too; only 1.1 uses
  `[metadata.files]` (doc only). Fixed in the 0.20.0 docs PR.

- [x] **setup.cfg `tool = X` never sets the creation tool (S).** Fixed by #280.
  `[tool:pitloom] tool = X` (and `[tool:pitloom:creation] tool = X`) is
  read, then `_clean_creation_keys` pops `creation-tool` straight after,
  so `config.tools` stays empty. Found while adding the unknown-key
  warning.
- [x] **Licence detection picks a near-variant or misses MIT (S).** Fixed by
  #286. `licenseid` alone ranked `Pixar` 0.9963 over `Apache-2.0` 0.9921 on
  requests' verbatim `LICENSE`, `Xnet` over `MIT` on PyYAML's (two notice
  lines first), `JSON` over `MIT` on wcwidth's. Now: the text is also read
  without its copyright notices, a stated licence wins a near-tie (0.01),
  an unstated near-tie with another licence family concludes none.
  Regression corpus: `tests/fixtures/license-texts/`.
- [x] **Installed dependency licence text loses its indent (S).** Fixed by
  #286. `importlib.metadata` dedents each header value, which strips the
  whole Apache `LICENSE` indent when its first line is blank; now read from
  the raw `METADATA` as the wheel and sdist readers do.
- [x] **A classifier licence has no provenance at `minimal` detail (S).**
  Fixed by #286.

## P0: in 0.20.1

Crashes, broken contracts and small mappings.

- [ ] **A very long version number crashes lock-file reading (S).**
  `packaging.Version("1." + "9" * 5000)` raises a plain `ValueError`
  (int digit limit), not `InvalidVersion`; `version_key`,
  `is_usable_version` and `is_same_version` in `extract/lock/_common.py`
  catch only the latter. #266 fixed the same class in `verify-wheel`.
  #287 adds a caller: the setuptools `version` conflict check
  (`_field_agreement.values_agree`) crashes the directory read on
  `setup(version='9' * 5000)` beside a `setup.cfg` version.
- [x] **`-o -` ends stdout with `PITLOOM_SBOM_OUTPUT_PATH=-` (S).** Fixed:
  no path line for `-`, the embed `WHEEL=` record goes to `INFO:`, and
  `embed-wheel -o -` no longer writes a file named `-`.
- [ ] **GGUF `general.license` is not mapped (S).** Classify it with
  the licence classifier #276 added.
- [ ] **`setup.cfg` `%` fails the whole run (S).** `description = 50% faster`
  gives `ERROR: SBOM generation failed: '%' must be followed by ...`. setuptools
  84's own `setup.py --description` fails the same way. Decided: keep failing,
  with one `ERROR:` naming the file, section and key and the `%%` fix.
  Precondition met (2026-10-04): pbr 7.0.3 reads `setup.cfg` with
  `configparser.ConfigParser` (interpolating; never Raw in any release checked)
  and fails on `50% faster` too; `%%` works.

- [x] **`setup.py` with no literal `name=` is dropped whole (S).** Fixed by
  #287 (`setup.py` and `setup.cfg` merged as setuptools does,
  [setuptools-support.md](../implementation/setuptools-support.md#precedence)).
  `read_setup_py` raises `ValueError` and `read_setuptools`
  (`extract/project/setuptools.py`) skips every `setup()` keyword, so a
  `setup.cfg` MIT classifier wins where the built wheel carries the
  `setup.py` BSD one: the directory and the wheel disagree. Found
  checking the paper notes (2026-10-05).

- [x] **A weak `setup.cfg` licence beats a real `setup.py` one (S).** Fixed by
  #287.
  `license = UNKNOWN` in `setup.cfg` plus `setup(license="MIT")` gives
  `NoAssertionLicense`; the built wheel says `License: MIT`.
  `merge_project_metadata` keeps any non-blank first value, where
  `first_license` would skip the weak one
  ([license-rules.md](license-rules.md#open-questions), question 2).

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
  text it can sit in an `SPDX-License-Identifier:` tag, a `License:` field or a JSON
  `"license"` field. licenseid 0.4.2 builds a SQL `LIKE` pattern from the
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

## P3: after 0.20.0

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

## Leads to verify

Seen in past sessions, not reproduced on current `main`:

- On Windows, `os.replace()` fails while another process holds the
  target open; the registry save should turn that into its existing
  "failed to save" `WARNING:`.
- Windows: `METADATA.` and `METADATA::$DATA` map onto `METADATA`; case
  variants of `.dist-info` names overwrite each other on macOS and
  Windows.
