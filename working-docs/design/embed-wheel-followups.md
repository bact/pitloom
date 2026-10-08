---
Created: 2026-10-05
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# PEP 770 / embed-wheel: open follow-ups

See also: [roadmap.md](roadmap.md#open-follow-ups-by-area),
[sbom-package-boundary.md](sbom-package-boundary.md),
[archive-member-followups.md](archive-member-followups.md),
[wheel-verification-commands.md](../implementation/wheel-verification-commands.md).

Open items on embedding an SBOM in a wheel and on wheel scanning, moved
from the roadmap on 2026-10-05. Each was found in the PR named in it.

- [ ] **`embed-wheel`'s wheel-rewrite temp file isn't covered by the
  SIGTERM/SIGHUP/Ctrl-C guard** -- a signal during
  `_rewrite_wheel_archive()`'s ZIP write (before the `os.replace()`
  swap) leaves a `<stem>.<random>.tmp` non-wheel file in the wheel's own
  directory (the original `.whl` stays intact); a `dist/*` glob like
  `twine upload dist/*` would trip on it. Cheap fix: register the temp
  path as a cleanup on the batch's `TerminationGuard`.
- [ ] **`loom wheel --embed` has no `--sbom-basename`** -- `embed-wheel`
  takes one, so the two embed surfaces can't be pointed at the same
  arcname. Found in the manual CLI checks for PR #226.
- [ ] **Archive member follow-ups** -- name-independent `--allow-build`
  extraction (case/Unicode folding, Windows path rules), archive-level wheel
  operations on `orig_filename`, tar links in sdists. See
  [archive-member-followups.md](archive-member-followups.md).
- [ ] **Metadata-only AI model readers (after 0.20.0)** -- replace the library
  reads (fastText, ONNX, GGUF, fickling, Safetensors) with bounded
  pure-Python header readers, parity-tested against the libraries; HDF5 last.
  Later option: short GGUF arrays as values, not only `<key>.length`.
  See [model-metadata-readers.md](model-metadata-readers.md).
- [ ] **AI model outcome-parity follow-ups (#270)** -- three small items left
  by the one-entry-per-confirmed-model rule: (1) Keras v3 (`.keras`) fails
  whole on a bad `config.json` while HDF5 degrades per attribute. (2) The scan
  names an HDF5 file `FORMAT=hdf5` where the reader reports `keras` (a
  `keras_version` attribute). (3) HDF5 attribute text is unbounded into the
  SBOM (`model_config` is kept to 500 characters only when unparsed; other
  attributes, string arrays included, are not capped), on `main` as well. See
  [ai-model-scanning.md](../implementation/ai-model-scanning.md).
- [ ] **Embed takes dependency versions from Pitloom's own environment** --
  `_resolve_version` (`assemble/spdx3/deps_installed.py`) falls back to
  `importlib.metadata.version()` for a dependency with no `==` pin and no lock
  entry, so `embed-wheel`/`wheel` name versions of the machine running `loom`
  (`packaging 26.3` for `packaging>=1`); the installed-metadata enrichment
  (`_enrich_from_installed`, `deps_originator`) leaks the same way. Needs an
  explicit stage flag (false for wheel/embed), per "Explicit pin beats local
  environment".
- [ ] **Two Build SBOMs can carry different package hashes for one wheel**
  (`embed-wheel --project-dir` vs the hook, on build-added payload). See
  [sbom-package-boundary.md](sbom-package-boundary.md#open-questions).
- [ ] **What an SBOM counts as inside the package, and package-format
  independence** -- the boundary (payload vs container metadata) and file
  naming (`.data/` listed under its wheel path, not its install destination) use
  wheel knowledge today; another format would need its own rule. See
  [sbom-package-boundary.md](sbom-package-boundary.md).
- [ ] **A renamed wheel's `.dist-info` is dropped from the listing but still
  scanned for models** -- `payload_files` uses `resolve_own_dist_info` (falls
  back to the single top-level `.dist-info`), `scan_wheel_for_ai_models`
  excludes only the directory the file name names. For `demo-2.0-...whl` with
  only `demo-1.0.dist-info/` the two disagree. Make the scanner use the same
  choice.
- [ ] **`embed-wheel --sbom` embeds the SBOM verbatim** -- an SBOM from another
  tool (or from a wheel with no single own `.dist-info`) may list `.dist-info`
  files, `RECORD` among them, whose hashes go stale after the embed; Pitloom's
  own wheel SBOMs never list them. An `INFO:` when it does?
- [ ] **`embed-wheel --project-dir <sdist>` runs discovery on the
  archive path** (Hatchling fails on it with a `WARNING:`): read the
  sdist's own listing, as `loom project <sdist>` does, or reject it.
- [ ] **`embed-wheel --project-dir` rejects the project's own enrichment
  fragment** -- `loom enrich --project-dir` mints the model id under the
  directory SBOM's doc uuid, but `embed-wheel` assembles under the wheel's,
  so a registered fragment fails the merge with `ERROR: 1 dangling
  reference(s)`; `loom project` on the same directory merges it fine. Same
  with a plain model name on the pre-#253 code. Identity schemes:
  [sbom-enrichment.md](sbom-enrichment.md). Found reviewing PR #253.
- [ ] **Resolve "now" once per batch in multi-wheel `embed-wheel`** --
  two SBOMs from one command can differ by a second in `created`. See
  [canonical-output-followups.md](canonical-output-followups.md#c8-one-now-per-embed-wheel-batch).
