---
Created: 2026-11-02
Last-Modified: 2026-11-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs: remote sources, Git LFS and datasets

See also: [known-bugs.md](../known-bugs.md) (index, severity scale,
rules for adding an entry), [roadmap.md](../roadmap.md),
[git-lfs-pointers.md](../../implementation/git-lfs-pointers.md),
[target-resolution-and-purl.md](../target-resolution-and-purl.md).

Git and Hugging Face sources, Git LFS pointers, dataset size and hashing, and
the size ceilings and clone cap. Entries are ranked by priority tier, then by
size tag; see the severity scale in the index. Open entries come first; fixed
entries stay in the last section for history.

## Open

### Found in review rounds, not yet prioritised

- [ ] **The clone cap is missing from `generate()`, the CLI, config and the
  Action (S-M),** and its over-cap message is outside the shared wording.
  Only the library's Git entry point takes `max_bytes=` (#339).
  *Found 2026-10-29, Git LFS pointer work.*
- [ ] **`loom project .` drops a `license = {file = ...}` that is a Git LFS
  pointer with no warning (S).** `read_license_file`
  (`extract/_license_detect.py`) logs the pointer at DEBUG only and relies on
  the run's one pointer warning, which never fires because the root `LICENSE`
  is not in the scanned file set; only the sdist route warns
  (`[lfs-pointer/shipped]`). The licence is correctly left unstated (#422),
  but a source that had an opinion and failed to deliver it should be visible.
  Fix: record a declared licence file that turns out to be a pointer in
  `UnreadPointers`, or reuse the existing pointer warning. Not fixed in 0.22.1
  or 0.23.0 (the messages were fenced for #413).
  *Found 2026-11-02, cold review of the merges since 0.22.0 (#422).*
- [ ] **A wheel gives no `[lfs-pointer]` warning for a pointer
  `dist-info/licenses/LICENSE` (S).** The wheel route lists payload files
  only, so a licence file shipped as a Git LFS pointer in `dist-info/licenses/`
  is never seen, while the sdist route warns (`[lfs-pointer/shipped]`). After
  #429 the licence is left unstated, so the loss is silent. Include
  `dist-info/licenses/` in the pointer check, or reuse the sdist warning.
  *Found 2026-11-03, review of the merges #426 to #429.*
- [ ] **A loom dataset package over a pointer differs from the main
  document's (S).** Its Merkle root takes the `oid`; the hook's package root
  takes the text's digest.
  *Found 2026-10-29, Git LFS pointer work.*
- [ ] **The blob-filter docs say "10 MB"; git's `10m` is 10 MiB (S).**
  `BLOB_LIMIT` in `extract/remote/git.py`; fix `docs/git-urls.md`.
  *Found 2026-10-29, Git LFS pointer work.*
- [ ] **A dataset's identity can change from a hash to omitted after a pull
  (S).** A pointer-based dataset is hashed from the `oid`s; once pulled, stated
  sizes above the ceiling mean no hash. The SHA-256 is otherwise unchanged.
  *Found 2026-10-29, Git LFS pointer work.*
- [ ] **The hook's and `loom project`'s document ids differ for a project
  with Git LFS pointers (S, decided: kept).** The Merkle leaf of a pointer is
  the pointer text's digest in the hook (it matches `RECORD`) and the `oid` in
  `loom project`; file ids are shared (the registry holds the `oid`).
  *Found 2026-10-29, Git LFS pointer work.*
- [ ] **A dataset member that disappears mid-walk is silent and leaves no hash
  (S), decided 2026-10-30: later (not done in 0.22.x or 0.23.0).** The
  current behaviour is kept (absent is quiet, no root); skipping the member
  and hashing the rest was not chosen.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
- [ ] **A `404` from the Hub looks like a failure (S).** `_safe_load_json` in
  `extract/remote/huggingface_fetch.py` cannot tell a 404 from a failed request
  and logs DEBUG only, so no `failed` entry is possible there without the 404
  check `huggingface_dataset.py` already has.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
- [ ] **The git call's kill path may leave a child holding the output pipe
  (S).** In `test_git_hardening.py`, the `running` case of
  `test_a_call_that_writes_more_than_the_cap_is_stopped`, an unstopped
  call ran 60.2 s (the test's own `sleep 60`) once on macOS.
  Suspected: `_kill` swallows `PermissionError` from `os.killpg`, so `sh` dies
  while `sleep` keeps the pipe open. Intermittent. Smallest fix: on
  `PermissionError` also call `proc.kill()`. Not reproduced since the test was
  changed to a 120 s sleep and a < 100 s bound (#421); watch for a `[running]`
  run near 60 s.
  *Found 2026-11-02, macOS CI leg.*
- [ ] **`--allow-lfs-fetch` (idea).** Fetching LFS content contacts a second
  server the Git URL guard does not cover; reuse the clone cap if built.
  *Found 2026-10-29, Git LFS pointer work.*
- See [target-resolution-and-purl.md](../target-resolution-and-purl.md) for the
  Bitbucket and SourceHut findings of the same day.
  *Found 2026-10-23.*
- [ ] **A one-line `License: version https://git-lfs.github.com/spec/v1` in a
  wheel or sdist header is recorded as licence text (S, decision needed).**
  Only a whole pointer (version line, `oid` and `size`) counts as one
  (`is_pointer_text`, `_core_metadata.py`); a `License:` header that holds
  just the `version` line, as an unpulled file cut short might, is kept as
  the text. Decide whether a lone `version` line of the Git LFS spec also
  stands for "not pulled".
  *Found 2026-11-03, review of the 0.22.1 release.*

## Fixed

Kept for history, with the PR. A fixed entry moves to
[roadmap-completed.md](../../implementation/roadmap-completed.md) once its
release ships.

### Fixed, P0: in 0.21.0

- [x] **Git LFS pointers outside AI models (M), built for 0.22.0.** One
  detector, one summary `WARNING:` per SBOM, a checkout pointer listed by its
  `oid`, loom `path=` reuses it. See
  [git-lfs-pointers.md](../../implementation/git-lfs-pointers.md).

### Fixed, Found in review rounds, not yet prioritised

- [x] **`dataset_datasetSize` held a record count (M), fixed in #382.** A
  Croissant `totalItems` filled it, but SPDX defines it in bytes. `totalItems`
  is not Croissant, so it is no longer read; `DatasetMetadata.byte_size` (bytes,
  library callers only) replaces `dataset_size`. A count has no 3.0.1
  property: FG-12 in [sbom-format-gaps.md](../sbom-format-gaps.md).
  *Found 2026-10-29, Git LFS pointer work.*
- [x] **The two size ceilings have no flag (S-M), built in the ceilings PR.**
  `--max-model-extract-bytes` (every wheel surface, inert elsewhere; Action
  input) and `--max-dataset-hash-bytes` (`loom id generate`;
  `loom.Run(max_dataset_hash_bytes=)`; no Action input, since no Action step
  hashes a dataset); `0` stays an error.
  *Found 2026-10-29, Git LFS pointer work.*
- [x] **A Git URL's messages name the random temporary checkout (S).**
  Fixed in the next release: `core.url_masking.mask_checkout`, called by
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
  *Found 2026-10-27, combined review of #352 to #357.*
- [x] **A one-character Hub model name is a URL but not an id (S).**
  Fixed in #365: `_HF_ID_RE` takes a one-character name, as `_HF_URL_RE` does.
  `https://hf.co/o/m` logged "read as https://huggingface.co/o/m", then
  `loom model` hands `o/m` to a reader that treats it as a local file:
  `_HF_URL_RE` accepts a one-character name, `_HF_ID_RE` needs two.
  *Found 2026-10-28, 0.21.0 release review.*
- [x] **`loom id -e` ignored the project's dataset ceiling (S), fixed in the
  ceilings PR.** Flag, then the project's own key, then the default.
  *Found 2026-10-29, Git LFS pointer work.*
- [x] **The LFS-pointer `WARNING: FILE=...` line prints the path unquoted (S),
  decided: kept.** The path goes through `loggable`, as in every sibling
  `FILE=` line: a newline is escaped (one record), `|` is inert in a log
  line, and a bare space is family-wide. A quoted `FILE=` would be one PR for
  the whole family; characterised in `tests/core/test_lfs_pointer_warning.py`.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
