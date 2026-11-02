---
Created: 2026-11-02
Last-Modified: 2026-11-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs: extraction, fragments and merge

See also: [known-bugs.md](../known-bugs.md) (index, severity scale,
rules for adding an entry), [roadmap.md](../roadmap.md),
[extras-parity.md](../../implementation/extras-parity.md#open-questions),
[non-hatchling-file-discovery.md](../non-hatchling-file-discovery.md),
[canonical-output-followups.md](../canonical-output-followups.md).

Reading project, environment, lock-file and installed-package metadata;
dependency versions and direct references; fragments and `loom merge`. Entries
are ranked by priority tier, then by size tag; see the severity scale in the
index. Open entries come first; fixed entries stay in the last section for
history.

Follow-ups from the extras and authors work (#300): see
[extras-parity.md](../../implementation/extras-parity.md#open-questions),
the one list.

## Open

### P0: in 0.21.0

- [ ] **A losing fragment's "generated" claim outlives its value (S, found
  in the 2026-10-23 review of #349).** Fragment A restates the generated
  `description` and carries its own Annotation `Method: generated_from_labels`;
  fragment B gives "curated" and wins. The output holds "curated" with A's
  Annotation (or its comment line) saying it was generated. A fragment's own provenance was never
  dropped when its value lost, but here the claim is false. A fix has to tell
  a fragment's winning entry from a losing one (a fragment whose generated
  value wins keeps its claim, which is true).

### P2: 0.21.0 and later

- [ ] **A `loom env` package installed from a URL, and a private-index
  package, are still looked up on PyPI by name (S-M).** `loom env` gets its
  packages from pipdeptree, whose JSON has no `direct_url.json`, so a URL
  install is not told apart. A private-index dependency (`[tool.uv.sources]`,
  `--index-url`) is read as a PyPI name. Same wrong licence, supplier and
  hash as the fixed project-route bug (#405).
- [ ] **A direct reference still takes its version and installed metadata
  from Pitloom's own environment by name, and keeps a `pkg:pypi` PURL
  (S).** #405 stops the PyPI lookup only. A `name @ URL` dependency can still
  get the version of a same-named package installed beside Pitloom, and a
  PURL that names a registry package it may not be. The skip is also silent:
  a coded `INFO:` ("direct reference, not looked up on PyPI") waits for a
  catalogue family PR.
- [ ] **`loom wheel` copyright year is the SBOM's (S).** With no author
  name in `METADATA` (only `Author-email`), the holder now comes from the
  `Author-email` display name or address (#300), but the year is still the
  SBOM's year, not the package's. Not re-checked since #300: the wheel
  route had no supplier where the hook records the author.

### P3: after 0.20.0

- [ ] **`loom merge` of a `loom enrich` fragment and a model SBOM writes
  invalid SPDX (M).** Found in the option D black-box round, not caused by
  it: merged elements get `creationInfo: ""` and a CreationInfo with no
  `@id`, so `loom fragment validate` fails, with or without annotations.
  Related to, but not the same as, the `_:CreationInfo0` entry above.
- [ ] **Installed-dependency `METADATA` is read unlike a wheel's (S).**
  `deps_installed.get_pkg_metadata` reads text through `importlib.metadata`
  (newlines translated, strict UTF-8): a CRLF `METADATA` gives a licence
  text without CR where the wheel reader keeps it, and a non-UTF-8 one
  raises `UnicodeDecodeError` and aborts the run. A dist-info with no
  metadata file stays silent. Use the wheel's `read_header_block` +
  `HeaderParser` (#286 review).
- [ ] **numpy licence text keeps one extra leading space per line (S).**
  meson-python folds `License:` with 9 spaces; `_unfolded` strips 8.
  Whitespace-only lines are blank on every surface since #286; the extra
  space stays (as
  0.19.0). Stripping a writer's whole fold width needs telling it from the
  text's own indent.
- [ ] **`loom fragment validate A B` fails on two `loom.run` fragments (S).**
  Both fragments name their creation info `_:CreationInfo0`, so the
  merged-graph check sees one `CreationInfo` with several `created` values
  (14 `ERROR:` lines); each fragment alone, and `--no-merge`, is valid.
  `loom merge` of the same three fragments succeeds. Not yet checked
  whether the validator or Pitloom's blank-node labels are at fault.
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

### Found in review rounds, not yet prioritised

- [ ] **The Hatchling hook does not check `requires-python` for an overlong
  number (S).** `loom project` refuses it with an `ERROR:`; in a build,
  Hatchling itself reads the value first and ends with its own `ValueError:
  Exceeds the limit (4300 digits)` traceback before the hook runs. Not
  Pitloom's to catch; noted so the difference between the surfaces is known.
  *Found 2026-10-27, combined review of #352 to #357.*
- [ ] **The PyPI prefetch resolves versions a second time (S).**
  `_document_locked_deps` calls `_resolve_version(..., warn=False)` apart from
  `_dep_groups.group_dependencies`, so the version it fetches can drift from
  the one the grouped rule states.
  *Found 2026-10-30, from #407 (registry package key).*

## Fixed

Kept for history, with the PR. A fixed entry moves to
[roadmap-completed.md](../../implementation/roadmap-completed.md) once its
release ships.

### Fixed, P0: in 0.21.0

- [x] **A fragment value may lose to an extracted one (S-M, own PR).**
  Confirmed 2026-10-23 and fixed: a fragment's value replaces one Pitloom
  generated from the file's format (`Method: generated_from_labels`,
  `derived_from_format`: the `description`, `ai_domain` and
  `ai_informationAboutApplication` of a model), with one `INFO:` and the
  provenance of that property dropped. A value read from the file still wins a
  conflict, as every other field. Built in `_fragments_generated.py`; see
  [docs/fragments.md](../../../docs/fragments.md).
- [x] **A respelt copy of a curated value warns (S, found in the 2026-10-23
  review of #349; fixed in #352).** Fragment A replaces
  a generated value; a later fragment A' was A in other JSON spacing and earned
  `WARNING: Merge: conflicting`, while a respelling of the *generated* value
  was silent. The field merge now reads two texts that are the same JSON as one
  value, for a text property merged field by field (`_fragments_equal.py`;
  list items, comments and model names still compare as text: the same JSON
  pair folds as a scalar and stays two list items).

### Fixed, P2: 0.21.0 and later

- [x] **A direct-URL dependency is looked up on PyPI by name (S-M).**
  `foo @ git+...` picked up the licence, supplier and hash of whatever
  PyPI project shares its name, possibly a different package. Fixed by
  #405: a package any declared string names by URL
  (`core.pep508.is_direct_reference`) is neither prefetched nor enriched
  from PyPI.
- [x] **`loom merge <dir>` writes no `SpdxDocument`, so no `profileConformance`
  (S).** Fixed by #284. Merging two full SBOMs that share one namespace (project
  dir + wheel) fails with a duplicate `File-2` id.
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
- [x] **Merge keeps one licence element per namespace (doc).** Fixed by
  #284: equal licences unify across a merge. Two
  `Apache-2.0 AND MIT` elements after a fragment merge are valid under the
  never-name-match policy; say so in `license-typing.md`.

### Fixed, Found in review rounds, not yet prioritised

- [x] **A fragment value loses to a generated one (S-M, fixed).** Probe: a
  Hatchling project holding a CRFsuite model, with a fragment giving the model
  another `description`; the merged SBOM kept the generated one. See the P0
  entry "A fragment value may lose to an extracted one".
  *Found 2026-10-23.*
- [x] **`_merge_dictionary_entries` dropped a differing value without a warning
  (S, found outside the set).** Fixed in #357: two fragments giving one
  `ai_hyperparameter` or `ai_metric` key different values keep the first and
  say so (`Merge: conflicting 'ai_hyperparameter' key 'k' on ...: keeping X,
  dropping Y.`); equal and same-JSON values stay quiet.
  *Found 2026-10-27, combined review of #352 to #357.*
