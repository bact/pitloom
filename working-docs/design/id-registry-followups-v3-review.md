---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# ID registry v3: low-priority findings of the last review round

Not fixed in PR #305; each is small. Split from
[id-registry-followups.md](id-registry-followups.md) (see also there, and
[id-registry-path-keys.md](id-registry-path-keys.md) for the deferred
path-key redesign, which several items below fold into).

## Registry invariants and file I/O

- **`register()` and the loader do not enforce** "a sha only on `software_File`
  and `ai_AIPackage`" nor "two keys never share an id". Loom registers a sha
  on dataset packages; the rules hold for harvest only.
- **Parallel first runs can write a mixed-namespace file**: rebase adopts the
  other run's namespace and keeps its own ids.
- **`save_registry` after the file was deleted fails by design** (one
  `WARNING:`; tests expect it).
- **`replace_text_lf` and long names.** The temp name adds about 22 characters,
  so a 230 to 255 character registry name gives `ENAMETOOLONG`; a dangling
  symlink gives a temp-path error text; `IsADirectoryError` names the temp
  file, not the registry.
- **`resolve_registry` raises a bare `TypeError`** for a non-path argument.
- **NFC/NFD is not normalised in `RegistryCopy`.**

## Paths and walks

- **Directory-dataset pruning** of ignored names (`build`, `dist`, ...) below a
  dataset root skips subtrees silently, and `Hash.comment` does not say so.
- **`..` through a symlinked directory in `registry_key_for_path`** collapses
  lexically, but the OS opens the real parent: key and hash can describe
  different files.
- **Nearest-project-file root heuristic** for a wheel or sdist with no
  `--project-dir` misfires on a stray `setup.py` beside the registry; surfaces
  then differ in Merkle root.
- **The drop-one-leading-part rule** for a registry copy in a wheel can drop an
  unrelated member.
- **`_SKIPPED_LOOM_FILENAMES` matches the basename `loom.py`** (pre-existing).

## Loom and merge

- **Loom datasets register a sha on the dataset package** (see the invariant
  above); decide with the path-key redesign.
- **`set_model_hyperparameters` keeps stale annotation statements**
  (pre-existing).
- **Unified `rename_id_clash`**: one helper now words both the different-type
  and the conflicting-digest clash; the older name-only warning in
  `_fragments_hashes.py` (`appears with two different SHA-256 hashes`) is a
  separate wording for a different case. Align the two if they stay.
- **Unidentified wheels and sdists**: see the `unknown` item in
  [id-registry-followups.md](id-registry-followups.md#wheel-identity-and-archive-readers).
- **Non-UTF-8 byte in a directory above the project**: `_shown` /
  `_unstorable_name_error` (`id_registry/_types.py`) judge the project-relative
  name only, so a surrogate in a parent directory above the project root is
  not seen there; the absolute path then reaches log text through
  `loggable()` only. Decide whether the project root itself must be checked.
