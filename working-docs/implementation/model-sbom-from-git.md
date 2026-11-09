---
Created: 2026-11-09
Last-Modified: 2026-11-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# A model SBOM from a model file or folder, local and at a Git URL

See also: [remote-git-ingestion.md](remote-git-ingestion.md) (the Git fetch
this builds on), [git-lfs-pointers.md](git-lfs-pointers.md),
[model-format-mapping-parity.md](model-format-mapping-parity.md) (the Keras
mapping), [ai-model-scanning-decisions.md](ai-model-scanning-decisions.md),
[hub-model-file-range-read.md](../design/hub-model-file-range-read.md) (the
Hub follow-up that was evaluated and not built),
[known-bugs/ai-models-readers-and-metadata.md](../design/known-bugs/ai-models-readers-and-metadata.md),
the user pages `docs/git-urls.md` and `docs/ai-model-formats.md`.

What was built for 0.23.4 (PR #464), why,
what was measured first, and what was left out.

## Why

Lumina (the web checker) passes a Git URL of a model file to
`generate_git_project_sbom()`. For a model file in a repository the call
failed, and not for Keras only: every model format failed the same way,
because the Git route always ended in `read_project()`. The fix is in Pitloom
so every surface (CLI, library, Lumina) behaves alike.

## WP0: measurements on `main` (v0.23.3), before any change

The four reported failures (the first four rows) reproduced at runtime on
`main` and against the PyPI 0.23.3 release; the last three rows are read from
the code, not run:

| Input | Result before |
| :---- | :------------ |
| `…/tree/main/models` (a folder with a model file and no project) | `FileNotFoundError`: `No pyproject.toml, setup.cfg, or setup.py found in <checkout>` |
| `…/blob/main/models/m.keras` | the same: the file page was turned into its folder and the file name dropped (`GitCheckout` had no `file` field) |
| `…/raw/main/models/m.keras` | `git.clone-failed`: `raw` was no page marker, so the whole URL was cloned as a repository |
| the repository URL (a bare repository, models at its root) | the same `No pyproject.toml...` |
| `loom model <git url>` | refused, naming `loom project` |
| `loom model <dir>` | `not an AI model file` (files only) |
| `loom generate x.dat` (GGUF magic) | read as a project path and failed; `loom model x.dat` read it (suffix vs content) |

Blob filter probe (the docs claimed `--filter=blob:limit=10m` leaves out blobs
over 10 MB): a 12 MB blob in the checked-out tree was fetched and checked out
in full. The filter only leaves out blobs the checkout does not need; a file
the checkout needs is fetched whatever its size. `docs/git-urls.md` was
corrected; the `git.py` docstring still says otherwise (known-bugs, remote
sources).

Per-format reach: every one of the ten formats (crfsuite, fasttext, gguf, hdf5,
keras, numpy, onnx, pytorch, pt2, safetensors) failed identically before, for
the reasons above. Before/after corpus: `loom model` on the fixture of every
format, on `main` and on this tree: only the Keras output changed (the new
fields), as intended; the others are unchanged, HDF5 included through the
refactor of `hdf5_config.py`.

## Decisions

- **D1 Safety: native-library readers are not run on a Git download.** The
  formats of `WHEEL_GATED_FORMATS` (fastText, GGUF, HDF5, ONNX, PyTorch
  `.pt`/`.pth`) get a format-only entry (name, format, hashes) and one
  `INFO:` `reader-unsafe/remote`, a variant of the wheel gate's
  `reader-unsafe` (same `ReaderGate`, a different `Message`). Keras,
  Safetensors, NumPy, CRFsuite and PT2 are read in full: they read ZIP
  members, JSON or a bounded header in Python. Why: the hostile
  `hdf5-hang.h5` and `hdf5-segfault.h5` fixtures show a native reader can
  crash or hang the process, and a Git URL reaches Pitloom from the internet
  through Lumina. *Rejected:* run every reader (simpler; an internet file would
  hit crash-prone readers); a flag to trust a download (a URL is not a thing
  a user inspected; cloning and running on a local file is the same step with
  the user's eyes on it).
  *Revised (follow-up request): the project route is gated too.* D1 first
  covered the model route only (`read_model_file`); a Git URL read as a
  project still ran every reader on the models in the build file list. Now
  `scan_project_for_ai_models` builds the same gate
  (`scanner_project.remote_reader_gate()`, moved there from `model_target`,
  which re-exports it) from the `in_remote_clone()` ContextVar that
  `GitCheckout.reading()` sets, and reports it once after a scan that
  succeeded (after the usage pass, as a wheel scan does). One mechanism, no
  new parameter: every route into a clone (`generate_git_sbom`,
  `generate_git_project_sbom`, `generate()`, `loom project`/`loom generate
  <url>`) is gated; a local project, the Hatchling hook and `embed-wheel`
  never run inside `reading()` and stay ungated. `--trust-wheel-model` does
  not lift it (it is inert on a Git URL).
- **D2 Commands.** `generate(url)` and `loom generate <url>` choose a project
  or a model. `loom model <url>` accepts a Git URL (model only; it used to
  refuse and name `loom project`). `loom project <url>` stays project-only;
  with no project and model-like files it refuses (`git.no-project`) and hints
  `loom model <url>` / `loom generate <url>`. Library: `generate_git_sbom(url,
  *, sbom_kind="auto"|"project"|"model", ...)`; `generate_git_project_sbom` is
  its project-only wrapper. One rule, in one place
  (`extract/model_target.py`, `extract/remote/git_target.py`).
- **D3 A model file URL wins** under `auto`, even beside a project. A
  non-model file URL (`pyproject.toml`, `README.md`) reads the folder as
  before, with one `INFO:`. "Non-model" is decided by the name first
  (`has_model_suffix`, the suffix set `generate("x.gguf")` reads a file
  by): a file named as a model that is not one (an empty `e.gguf`) is
  refused under `auto` too, as it is locally; passing it over for the
  folder's project would ignore what the user named. `.zip` is not such a
  suffix (an sdist can be one).
- **D4 One model per SBOM.** A folder with several model files is an error
  (`model-ambiguous`, one `INFO:` per file, then the `ERROR:`); the user names
  one file. A multi-model document is out of scope. A folder is read
  non-recursively (the named folder; the repository root is its root files
  only), and at most 1000 files whose names could be models are sniffed: a
  folder of more is refused unread as `model-ambiguous/over-cap` (its own
  variant: no file is known to be a model, so "several AI model files"
  would overstate it).
- **D5 Neither project nor model:** `project-or-model-not-found` (library:
  `CodedValueError`; via Git: `RemoteSourceError` `git.no-project` keeping that
  code as `pitloom_code`, plus the subproject hint when the repository has
  subprojects). A named file absent from the repository is `git.path-not-found`
  when its name has a model suffix (or under `loom model`); any other name
  (`README.md`) reads the folder, as on `main` before this change.
- **D6 `config.json["metadata"]` of a Keras archive is not mapped.** The
  fixture's `description`, `author`, `model_version` and `license` there are a
  convention of that fixture's generator, not a Keras field. Mapping them would
  write a licence or version a Keras file does not state.
- **D7 `date_saved` stays a property.** It has no time zone, so it is not a
  `releaseTime` (SPDX wants UTC). Recorded as written.
- **D8 No Keras parameter count.** It needs the weights member opened with h5py
  (and inference from layer shapes); documented as a parity gap.
- **D9 `layer_count` uses the HDF5 rule** (`len(config.layers)`, an
  `InputLayer` counted), so the two Keras readers agree. The open entry
  (should an `InputLayer` count?) covers both.
- **D10 Hub range requests: documented, not built.** See
  [hub-model-file-range-read.md](../design/hub-model-file-range-read.md).
  The Hugging Face route reads repository metadata and never a model file, so
  a `.keras`-only repository gets an SBOM with no Keras-derived field, no
  format and no hash. Reading the two JSON members over HTTP Range requests
  would be a partial content fetch from a second host (the LFS/CDN storage
  host) through `huggingface_hub`'s own redirects, with no Pitloom HTTP client,
  no `check_url` per hop and no byte budget; it contradicts the documented rule
  that model files are not downloaded. The docs give the workaround: download
  the file, run `loom model <file>`.

- **D11 Confinement: nothing outside the clone is opened (revision, review
  round 1, `9ce199f`).** A Git URL's file name such as `.git%2F..%2F...` decoded
  to a path out of the clone, and a cloned project's build file list
  (`force-include` with an absolute or `../` path) listed and hashed host
  files. Four rules:
  1. *URL parser:* a decoded segment holding a slash-separated `.` or `..`, an
     empty part, a backslash or a NUL is refused (`git.url-invalid`, `Invalid
     path in URL`).
  2. *Exact spelling:* a named file must be a regular file inside the folder, spelled
     as on disk (`regular_file_inside`, `core/path_confine.py`), so a wrong-case URL is "not found" on
     every OS (a case-insensitive file system does not make it a hit).
  3. *Repository-root boundary for the build file list:*
     `drop_outside_clone` (`core/_models_wheel_clone.py`) drops entries outside
     the clone with one `file-unreadable/outside-repository` `WARNING:`, inside
     a clone only; a local project is unchanged.
  4. *FIFO refusal:* `require_model_file` refuses a FIFO or other special file
     (`model-wrong-format`) before it is opened (it hung `loom model`).
  The project-route gate (D1, revised) stays as described. *Rejected:* trusting
  the URL decoder alone (the build file list was a second vector); resolving
  with `realpath` only (a case-insensitive file system still hits the file).
- **D7 The repository's own code is not run (second review round).** Listing a
  project's wheel files ran the repository's Python (Hatchling metadata hooks,
  setuptools `cmdclass` and unresolved `attr:` versions, PDM `pdm_build.py`,
  `custom-hook`, `run-setuptools`).
  1. *Neutralise in a clone only:* the settings are dropped before discovery,
     with one `config-unsafe/build-code` `WARNING:`, inside a clone
     (`in_remote_clone()`); a local project still runs its own hooks, as a
     build would, so its file list stays that of the build. *Rejected:*
     dropping them for local projects too (changes the output for the user's
     own project), a sandbox subprocess (platform-specific).
  2. *`fetch_git_project` confines by default:* its block sets the clone mark
     (`reading_remote_clone`), so a library caller that reads `co.folder`
     itself gets the same confinement and reader gate; `reading()` stays and
     nests. *Rejected:* a note in the docs asking callers to wrap the block.
  3. *Filter before discovery:* a Hatchling `force-include` or a setuptools
     `package-dir`/`packages.find.where`/`package-data` entry outside the
     repository is dropped before the files are discovered (the host directory
     is not walked) and named as written; files found outside after discovery
     are only counted. MANIFEST.in, PDM, Poetry and Flit entries rely on the
     count-only net (known-bugs).
  4. *`.git`:* a `.git` part of a Git URL path (any case, trailing dots or
     spaces, `git~1`) is refused (`git.url-invalid`), and the clone's `.git`
     is never listed.

## Behaviour

URL form by mode (`resolve_git_target`, then `resolve_sbom_target`). A
`blob`/`raw` URL names a file; a `tree` URL or the repository names a folder.

| URL names | `generate` (auto) | `loom model` | `loom project` |
| :-------- | :---------------- | :----------- | :------------- |
| a model file | the model (even beside a project) | the model | the folder's project; no project and model-like files: `git.no-project` + hint |
| a non-model file with a name no model has (`pyproject.toml`) | `INFO:` `not an AI model file; reading its folder`, then as a folder | refused (`model-wrong-format`) | the folder's project |
| a file with a model suffix that is no model (empty `e.gguf`) | refused (`model-wrong-format`), as `loom model e.gguf` locally | the same | the folder's project |
| a file absent from the repository, or a link | model suffix: `git.path-not-found`; any other name: the folder, `INFO:` as above | `git.path-not-found` | the folder's project (the file name is ignored) |
| a model file that is an LFS pointer | `ERROR:` `lfs-pointer` (clone advice) | the same | n/a |
| a folder with a project | the project (gated formats of its build file list: format-only, D1) | its one model file, if any | the project (gated as for `generate`) |
| a folder with no project, one model | the model, `INFO:` | the model, `INFO:` | `git.no-project` + hint |
| a folder with no project, several models | `model-ambiguous` | `model-ambiguous` | `git.no-project` + hint |
| a folder with neither | `project-or-model-not-found` (`git.no-project` when subprojects exist) | `model-wrong-format` | the project read's own error, with the subproject hint |
| a folder of only LFS pointers | the first pointer as an `ERROR:`, one summary `WARNING:` | the same | n/a |

Local equivalents: `loom model <dir>` and `generate(<dir>)` read a folder with
exactly one model and no project; `generate()` and `loom generate` read a file
as a model by content as well as suffix (a GGUF named `x.dat`); a directory with
neither a project nor a model raises `project-or-model-not-found` (it was
`FileNotFoundError` `No pyproject.toml...`). Output goes to `-o` or the current
directory (`<file name>.spdx3.json` for `loom model`), never into the checkout.
`--offline` is an error with a Git URL for `loom model` too (nothing is
fetched). A folder's candidates are chosen by suffix (a model renamed
`weights.dat` is not found in a folder), then confirmed by header.

## The temp-path guarantee

The clone lives in a random temporary directory. Nothing of it may reach the
SBOM or a message: the SBOM names the file by its own name (`file_name`, the
purl and the package name), every message names it by `shown` (its path in the
repository, `models/m.keras`), and the URL is shown without credentials.
`generate_model_sbom(..., shown=)` carries that name (a new keyword; the default
is the path as given). Checked by a two-run byte-identity test across different
temporary directories (`tests/assemble/test_generate_git_model.py`) and a
stderr scan for the clone path. Link handling: inside `GitCheckout.reading()`
a symbolic link is not followed when listing a folder (`_candidate_names`), and
links leading out of the checkout were removed by the fetch.

## Where things are

`extract/model_target.py` (the rule), `extract/remote/git_target.py` (the Git
mapping of the rule), `core/project_markers.py` (what makes a folder a
project; drift test against `read_project`), `assemble/_generators_git.py`
(`generate_git_sbom`), `cli/commands/_remote.py` (`run_remote`, shared by
`project`, `model` and `generate`), `core/inert_options.py` (`GIT_MODEL`
row: options a model cannot use warn once), `messages/_sbom_target.py`
(`project-or-model-not-found`, `model-ambiguous`), `messages/_model_stub.py`
(`reader-unsafe/remote`), `messages/_lfs_pointer.py` (the clone-specific
`ERROR:` line), `extract/ai_model/keras_config.py` and
`keras_training_config.py` (the Keras v3 reader).

- **Round 4 (#464), fixed.** A clone's `.git/config` loses the URL's user
  information; setup.cfg `[global]` is not applied; `sys.path`/working
  directory code execution is closed; folder links are dropped and file
  discovery stops after 60 s (link-loop DoS); Poetry `from`, `packages`,
  `include` and `exclude` are filtered; interleaved `fetch_git_project` blocks
  keep their own confinement. Open: the time cap cannot stop a call blocked in
  C and is lost if a library swallows `BaseException`; a licence file pointing
  into `.git` now fails to read; `fetch_git_project(file:///C:/...)` is
  untested on Windows (known-bugs).

## Risks and things not checked

- **Windows:** the scrub test (no temporary path in the output) and the
  `shown` handling were read as Windows would, not run. `shown` is wrapped in
  `Path` in `refuse_not_a_model`, so one refusal prints a repository path with
  backslashes on Windows (known-bugs).
- **Enrichment reads the clone:** `--enrich` on a Git model runs the local
  enrichers, which read a README or model card beside the file in the
  temporary clone; the data is untrusted text, as it is for a local folder.
- **Registry key INFO:** the ID registry key `INFO:` line can show the clone
  path to a library log handler (the CLI and the scrubbed message path do not
  print it). Not yet checked line by line for every registry message.
- **Behaviour changes:** a directory with neither project nor model raises
  `CodedValueError` (a `ValueError`), not `FileNotFoundError`; a file with a
  model magic and no model suffix is now read as a model by `generate()` (it
  used to be an unreadable project path). Alpha, no compatibility promise.
- **Links on the project route:** closed. An earlier note here said a
  committed symlink could make the model scan read a file outside the clone.
  A review showed links that leave the clone are already removed after the
  checkout (`_drop_outside_links`); the real vector was the build backend's
  file list (`force-include` with an absolute or `..` path), which
  `drop_outside_clone` and the pre-discovery filter now close (D7).
- **Not built:** recursive model discovery; origin provenance (URL, ref,
  commit) in the package; `raw.githubusercontent.com` and Hugging Face
  `/resolve/` links (not Git page URLs); a Hub per-file hash.
- **Keras:** the date and the member list are properties in the annotation, so
  under `preserve-source-metadata=auto` a model that is in a project's file
  list does not show them (the existing rule for every format).
