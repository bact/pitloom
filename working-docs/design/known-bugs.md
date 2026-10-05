---
Created: 2026-10-03
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs, by priority

See also: [roadmap.md](roadmap.md),
[id-registry-v3.md](id-registry-v3.md),
[id-registry-followups.md](id-registry-followups.md).

Bugs found up to #284, each reproduced on `main` unless marked
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

## P0: in 0.20.1

Crashes, broken contracts and small mappings.

- [ ] **A very long version number crashes lock-file reading (S).**
  `packaging.Version("1." + "9" * 5000)` raises a plain `ValueError`
  (int digit limit), not `InvalidVersion`; `version_key`,
  `is_usable_version` and `is_same_version` in `extract/lock/_common.py`
  catch only the latter. #266 fixed the same class in `verify-wheel`.
- [ ] **`-o -` ends stdout with `PITLOOM_SBOM_OUTPUT_PATH=-` (S).** The
  path line belongs on stderr, or nowhere, when the SBOM itself goes to
  stdout.
- [ ] **GGUF `general.license` is not mapped (S).** Classify it with
  the licence classifier #276 added.
- [ ] **`setup.cfg` `%` fails the whole run (S).** `description = 50% faster`
  gives `ERROR: SBOM generation failed: '%' must be followed by ...`. setuptools
  84's own `setup.py --description` fails the same way. Decided: keep failing,
  with one `ERROR:` naming the file, section and key and the `%%` fix.
  Precondition met (2026-10-04): pbr 7.0.3 reads `setup.cfg` with
  `configparser.ConfigParser` (interpolating; never Raw in any release checked)
  and fails on `50% faster` too; `%%` works.

- [ ] **`setup.py` with no literal `name=` is dropped whole (S).**
  `read_setup_py` raises `ValueError` and `read_setuptools`
  (`extract/project/setuptools.py`) skips every `setup()` keyword, so a
  `setup.cfg` MIT classifier wins where the built wheel carries the
  `setup.py` BSD one: the directory and the wheel disagree. Found
  checking the paper notes (2026-10-05).

- [ ] **A weak `setup.cfg` licence beats a real `setup.py` one (S).**
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

## P3: after 0.20.0

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

## Leads to verify

Seen in past sessions, not reproduced on current `main`:

- `loom env`: a requirement pipdeptree reports as `installed_version:
  "?"` loses its `dependsOn` edge silently (see also the roadmap's
  unmet-requirement item).
- On Windows, `os.replace()` fails while another process holds the
  target open; the registry save should turn that into its existing
  "failed to save" `WARNING:`.
- Windows: `METADATA.` and `METADATA::$DATA` map onto `METADATA`; case
  variants of `.dist-info` names overwrite each other on macOS and
  Windows.
