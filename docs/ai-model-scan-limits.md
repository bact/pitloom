---
Created: 2026-10-01
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scan limits

See also: [AI model formats](ai-model-formats.md) for what each reader
extracts, [Size and count caps](ai-model-scan-limits-caps.md) for every
cap and its value, [Known limitations](ai-model-scan-limits-known-limitations.md)
for what the caps leave open, and [Configuration](configuration.md) for the
one setting here that can be changed.

Use this when you ask "why is my model missing metadata?". An AI model
file is untrusted input: what it declares (a header size, an entry count,
an array length) decides how much memory and time a parser spends. Pitloom
therefore refuses some files, or parts of them, and says so on stderr.
The caps and the wheel gate below came with PR #263.

Every line quoted below starts with `WARNING:` or `INFO:`; `<fmt>` is the
format name (`gguf`, `safetensors`, ...) and `<path>` the model's path in
the project or wheel. A cap reads as every cap Pitloom applies does:
`FORMAT=<fmt> FILE=<path>: larger than the <limit>-<unit> <cap> cap; <outcome>`.

## Why is my model missing metadata?

| What you see | Cause | Section |
| :----------- | :---- | :------ |
| An `ai_AIPackage` named after its file (`weights` for `weights.gguf`) and nothing else, plus one `INFO:` | Wheel scan, format not read without `--trust-model-files` | [Formats gated in wheels](#formats-gated-in-wheels) |
| Same, plus `WARNING: ... max-model-extract-bytes cap; metadata not read` | File larger than `max-model-extract-bytes` | [Size and count caps](ai-model-scan-limits-caps.md#size-and-count-caps) |
| Same, plus `WARNING: FILE=<wheel>: larger than the N-byte per-wheel model-scan budget cap; ...` | The wheel's total budget is spent | [Size and count caps](ai-model-scan-limits-caps.md#size-and-count-caps) |
| Same, plus another `...; metadata not read` line | A bound inside the file was exceeded | [Size and count caps](ai-model-scan-limits-caps.md#size-and-count-caps) |
| A model, or a model listed in a project's build file list, from a Git URL, or a model in a wheel from a PyPI URL: an `ai_AIPackage` with name, format and hash only, plus one `INFO: ... listed without metadata ... [reader-unsafe/remote]` | fastText, GGUF, HDF5, ONNX or PyTorch reader not run on a download | [Formats gated for a download](#formats-gated-for-a-download) |
| Only the first 1000 inputs, hyperparameters, ... | Entry cap | [Size and count caps](ai-model-scan-limits-caps.md#size-and-count-caps) |
| No `parameters` hyperparameter, plus `WARNING: ... parameter count not recorded` | A tensor dimension or the count is malformed or over the parameter-count cap | [Size and count caps](ai-model-scan-limits-caps.md#size-and-count-caps) (Parameter count) |
| A format-only stub, plus `WARNING: ... failed to extract metadata; <error>` | The reader could not parse a file whose header is that of a model (truncated, corrupt) | [What cannot be recorded](#what-cannot-be-recorded) |
| A field a format cannot carry (no model name in a `.npy`) | Not a limit: the format has no such field | [What cannot be recorded](#what-cannot-be-recorded) |
| No `ai_AIPackage`, only the file entry, plus `WARNING: FORMAT=<fmt> FILE=<path>: header is not <fmt>; not listed as an AI model` | The header contradicts the model suffix, as text named `.gguf` does; a Git LFS pointer is no model under any suffix (see below) | [What is a model](#what-is-a-model) |
| No model at all | Not a detected model, or a target that does not scan models | [What cannot be recorded](#what-cannot-be-recorded) |

A file that is a model by its header gets exactly one entry on every
surface, whatever happens when it is read: a failed parse, a bound, a
missing library or the wheel gate leave a format-only entry (a "stub") and
one `WARNING:` (or the one `INFO:` for the gate), never none. So the set of
entries does not depend on the order of the files, the budget or the
installed libraries.

The format-only entry has exactly this: an `ai_AIPackage` whose
`name` is the model file's stem (`comment` entry `name: Source: Pitloom
generator | Method: file_name_stem`), no `ai_*` property and no `comment`
entry `Source: <model file> | Field: ...` (a read model has such entries),
a `contains` relationship to the model's `software_File`, and that file's
SHA-256 and SHA-512 hashes. The hash comes from the file list and does not depend on the
model being read. With `--enrich` (project scans) a stub can also carry a
`comment` from the README or model card, `Source: README.md | Method:
yaml_frontmatter`, plus the licence and datasets it names; it is still a
stub.

## Which scans apply which limits

| Target | How the model is read | Ceiling, budget | Wheel gate | Inner and header bounds, entry cap |
| :----- | :-------------------- | :-------------- | :--------- | :--------------------------------- |
| `wheel`, `wheel --embed`, `embed-wheel` without `--project-dir`, `generate x.whl` | Copied out of the wheel to a temporary file, one at a time | Yes | Yes | Yes |
| `project`, `generate <dir>`, `embed-wheel --project-dir`, the Hatchling hook, `--allow-build` | Read in place | **No** | **No** | Yes |
| `loom model FILE`, `loom enrich FILE`, `loom generate FILE`, `loom model DIR` or `loom generate DIR` for a folder with one model and no project | Read in place, as a project scan reads a file | No | No | Yes |
| `loom model URL`, `loom generate URL` for a model file or folder at a Git URL | Read in the temporary clone, one file | No | **Download gate**: the same formats, see [Formats gated for a download](#formats-gated-for-a-download) | Yes |
| `loom project URL`, `loom generate URL` for a project at a Git URL | Read in place in the temporary clone, from the build file list | No | **Download gate**: the same formats | Yes |
| `loom wheel URL`, `loom generate URL` for a PyPI URL | Copied out of the downloaded wheel, as for a local wheel | Yes | **Download gate**: the same formats | Yes |
| `env`, sdist archive (`loom project URL` for a PyPI URL too), `loom model` with a Hugging Face ID or URL | Models are not scanned | -- | -- | -- |

Scanning an untrusted local checkout therefore runs the fastText, HDF5,
ONNX, GGUF and PyTorch readers on its files, in Pitloom's own process, with
no size ceiling. Only scan project directories you trust; give an untrusted
repository's Git URL instead, which gates those formats.

`loom model FILE`, `loom enrich FILE` and `loom generate FILE` (and
`generate_model_sbom()`, `enrich_model()`) read the file by the same rule as
a scan, with the same `WARNING:` text for a bound, a missing library and a
parse failure (the wheel gate, ceiling and budget apply to wheel scans only).
The suffix filter of a scan only chooses which files to look at: a file named
explicitly is read by its content, whatever its suffix (`x.dat` with GGUF
magic is a GGUF model). A model whose read fails or exceeds a bound is written
as a stub with that one `WARNING:`, and the command exits 0 (`enrich` writes
its fragment: it reads the model too, and its enrichers read the README or
model card next to the file). A file that is not a model, an absent one or an
unreadable one fails instead: one `ERROR:` (framed by the command, `loom model`,
`loom enrich` or `loom generate`, then the path and the reason, e.g. `header is a Git LFS pointer, content not pulled
(oid sha256:<oid>, size <N> byte(s)); run 'git lfs pull'`, `header is not gguf`
or `file is empty`; an absent file has its own message) and exit status 1,
with nothing written, where a scan lists no entry. `loom model` and `loom
enrich` take a file of any suffix; `loom generate FILE` reads a file as a
model when its suffix is one of the
[suffixes scanned](ai-model-formats.md#how-a-file-is-recognised) or its header
confirms a format with a magic (a GGUF file named `x.dat`); any other file is
read as a project (an sdist archive, or a directory), and fails as one. A
script that used the exit status to detect an unreadable model must look for
the `WARNING:` instead.

A **folder** given to `loom model` or `loom generate` (a folder with no
project config, for `generate`) is read for its one model file. It is read
non-recursively, and its candidates are chosen by the suffix filter of a scan
(a model renamed to `weights.dat` is not found), then confirmed by their
header. At most 1000 files whose names could be models are looked at: a
folder of more is not read, said in one `WARNING: DIR=<dir>: larger than the
1000-entry model-candidate cap; no file read [over-cap]`, and is refused
with `more than 1000 files that could be AI models, none read; name one file`
(`model-ambiguous/over-cap`). A
folder with none is `no Python project (pyproject.toml, setup.cfg or
setup.py) and no AI model file of a supported format`
(`project-or-model-not-found`) for `generate`, and a path that is not a model
for `loom model`.

## Size and count caps

Moved to [AI model scan limits, size and count caps](ai-model-scan-limits-caps.md#size-and-count-caps).

## Settings that change the SBOM

The same input with the same settings gives a byte-identical SBOM. Changing
a setting below changes what is recorded, so two runs with different
settings are not expected to match. Each one says so on stderr when it
changes the models' entries, except where you asked for the change yourself:

| Setting | What changes | Message |
| :------ | :----------- | :------ |
| `--trust-model-files` | Models of the gated formats in a wheel or a Git URL's repository are read, not listed as stubs | Without it, one `INFO:` naming the formats not read (each format once per run) |
| `--max-model-extract-bytes` | A model over it, and every model after the per-wheel budget (4 times it) is spent, is a stub | One `WARNING:` per stubbed model; one per wheel for the budget |
| `--scan-model-usage` | `hasDataFile` edges from `.py` files to models exist or not | Without the setting given, one `INFO:` naming the flag |
| `--allow-build` | The file list comes from a real build, so the models found, and their paths, can differ from the static list | None when the build succeeds; a `WARNING:` and the static list when it fails. See [Building a project](allow-build.md) |
| `max-dataset-hash-bytes` (`loom.Run`; `loom id generate` with `-e`) | A dataset over it has no hash, and its provenance says why; a file's size is still recorded | One `WARNING:` naming the key, per dataset; see [Configuration](configuration.md) |
| The 1000-entry cap | Which entries are kept: the first 1000 in file order, or in sorted key order for Safetensors `__metadata__` | One `WARNING:` per model naming the fields cut, in a scan and in `loom model FILE` (not for a Hugging Face model) |
| A project directory, not its built wheel | Models are read in place: no ceiling, no gate | None; see [Which scans apply which limits](#which-scans-apply-which-limits) |

A cut that the output marks itself, such as the 20-name archive listing
(`archive_member_count` beside it) or the entries dropped from the
artifact-metadata annotation (`truncated`), has no log line.

## Formats gated in wheels

A model of one of these formats in a **wheel** gets a stub and is not
read, unless you trust the wheel:

- fastText (`.ftz`, `.bin` with the fastText magic)
- GGUF
- HDF5 (and HDF5-based Keras v1/v2)
- ONNX
- PyTorch classic (`.pt`, `.pth`)

Their readers run in Pitloom's own process on a copy of the file: a native
library (fastText, HDF5, ONNX), or a Python loop or pickle parser that a
crafted file can make very slow or very large (GGUF, fickling). A hostile
file can crash Pitloom, hang it, or exhaust memory, and Ctrl-C cannot stop
a native parser while it runs. A wheel is often a file you did not build.

Pitloom logs one line per scan, naming the gated formats it met that it has
not already named. In a batch (`embed-wheel` with several wheels) each format
is named once, in the first wheel that has it, and a later wheel with a
different gated format gets its own line:

```text
INFO: AI models in a wheel in these formats are listed without metadata, their reader not being run on a wheel's files: gguf, onnx; pass --trust-model-files for a wheel you trust
```

To read them, for a wheel you trust:

| Surface | How |
| :------ | :-- |
| CLI | `--trust-model-files` on `wheel`, `wheel --embed` or `embed-wheel` without `--project-dir` (and, for a Git or PyPI URL, on `project`, `model`, `wheel` or `generate`: [below](#formats-gated-for-a-download)) |
| Python API | `trust_model_files=True` on `generate()` or `generate_wheel_sbom()`; `ConfigOverrides.trust_model_files` for `embed_wheel_sbom()` without `project_dir=` |
| GitHub Action | Input `trust-model-files: "true"`, with `embed-wheel` and `project-path: ""` (or a Git URL); elsewhere Pitloom warns that it has no effect ([GitHub Action](github-action.md#configuration)) |

There is no `[tool.pitloom]` key, on purpose: a config file can sit in the
untrusted tree, so it must not be able to switch the protection off. On any
other target the option warns that it has no effect. Keras v3, NumPy, PT2
and CRFsuite readers do not pass the file to a native library, and the
Safetensors reader's Rust library is read in full on purpose: these are not
gated; the [caps](ai-model-scan-limits-caps.md#size-and-count-caps) still apply to them.

## Formats gated for a download

A model file from a Git URL, or a model file in the build file list of a
project from a Git URL, is read in a temporary clone of a repository you may
not trust, and a model in a wheel from a PyPI URL is read from a file you
downloaded, so the formats of the wheel gate are gated there too: a fastText,
GGUF, HDF5, ONNX or PyTorch (`.pt`, `.pth`) file is listed with its name,
format and hashes only, and one line per SBOM says so (the second names the
downloaded wheel):

```text
INFO: AI models from a Git URL in these formats are listed without metadata, their reader not being run on a downloaded file: gguf; pass --trust-model-files for a repository you trust
INFO: FILE=demo-1.0-py3-none-any.whl: AI models in these formats are listed without metadata, their reader not being run on a downloaded file: gguf; pass --trust-model-files for a release you trust
```

An sdist from a PyPI URL is not scanned for models, as a local sdist archive
is not, so `--trust-model-files` has no effect on `loom project` with a PyPI
URL.

To read them, for a repository or release you trust, use the same option as
for a wheel: `--trust-model-files` on `project`, `model`, `wheel` or
`generate` with the URL, `trust_model_files=True` on `generate()`,
`generate_git_sbom()`, `generate_git_project_sbom()`, `generate_pypi_sbom()`
or `generate_wheel_sbom()` with the URL, or the Action input
`trust-model-files: "true"` with a Git URL as `project-path` or `model`. It
lifts only this gate: the repository's own `[tool.pitloom]` is still ignored
and its build backend is still not run. Cloning the repository and running `loom model <file>` or `loom
project <dir>` on the copy reads them too, but also trusts the repository's
configuration and build file list. Keras v3, Safetensors, NumPy, PT2 and
CRFsuite files are read in full, with the [caps](ai-model-scan-limits-caps.md#size-and-count-caps).

## What is a model

A file is a candidate when its suffix is a model suffix, or `.bin`,
`.model` or `.zip`. It is a model when its header confirms a format:

| Format | Header that confirms it |
| :----- | :---------------------- |
| CRFsuite, fastText, GGUF, NumPy `.npy` | Its magic bytes (`lCRF` at offset 0 for CRFsuite), whatever the suffix; the suffix alone is not enough |
| Safetensors | A length of at most 100 MB, then `{`, whatever the suffix |
| Keras v3 (`.keras`), PT2, NumPy `.npz` | A ZIP header (`PK\x03\x04`, or `PK\x05\x06` for an archive with no member) |
| PyTorch (`.pt`, `.pth`) | A ZIP header or a protocol 2 to 5 pickle; a `.pth` is also a Python path-configuration text file, so a text `.pt` or `.pth` is no model and gets no warning (a Git LFS pointer does) |
| HDF5 | Its magic bytes, whatever the suffix; or, by `.h5`/`.hdf5`, any non-empty header (an HDF5 file may start with a userblock) |
| ONNX (`.onnx`) | Any non-empty header: no signature at offset 0 |
| Any | Not a model, under any candidate suffix, when the header opens with the line `version <URL>` of a Git LFS pointer spec (`https://git-lfs.github.com/spec/v1`, or an earlier one's): text in place of a file not fetched (`git lfs pull`); a scan lists it as a file only and warns once, not per file |

An empty file, an absent one or a directory is never a model, and silent. A
header that cannot be read (permission denied) is an `ERROR:` for `loom model
FILE` and its siblings. A scan normally drops such a file earlier (`could not
read ... for file scanning`, `[file-unreadable]`); `FORMAT=<fmt> FILE=<path>:
could not read header` (`[file-unreadable]` too) and no entry appear only when
it turns unreadable between the two reads. A file whose header contradicts its
model suffix is not listed, with one `WARNING: FORMAT=<fmt> FILE=<path>: header
is not <fmt>; not listed as an AI model`. A file that is a whole Git LFS
pointer, under any candidate suffix, gets no per-file warning: the SBOM has one
`WARNING: FILE=<first>: Git LFS
pointer, content not read (N files); <advice>` for all of them, where the advice
is `run 'git lfs pull' for the content` for a local directory and `clone with
git lfs, then run on the directory` for a Git URL. A pointer shipped inside a
wheel, an sdist or a build keeps the hashes of its own text and gets `WARNING:
FILE=<first>: Git LFS pointer shipped (N files); the build did not pull LFS
content`; the fix is in the build, not `git lfs pull`. A file that only opens
like a pointer (a malformed rest, or 1 KiB or more) keeps `FILE=<path>: header
looks like a Git LFS pointer but is not a valid one; not listed as an AI model`
(a `.bin`, `.model` or `.zip` one has no `FORMAT=`). A `.pt` or `.pth` that is
path-configuration text is silent.
This also catches a rare real file that fails its signature (a Safetensors
header of more than 100 MB, a ZIP with data before it). `loom id generate`
registers a model under its file's path key by the same rule (the suffix
filter, then the header), so it matches the files a scan lists.

## What cannot be recorded

**Whatever the cause.** Which field each value lands in, which fields have
no SPDX property of their own (framework, format version), and when a licence
is declared or concluded: [Where each field
goes](ai-model-formats-fields.md#where-each-field-goes). Properties that fit no field
are kept only in the verbatim artifact-metadata annotation.

**Fields a format never carries**, even when fully read: see
[What each format holds](ai-model-formats-fields.md#what-each-format-holds). Beyond
that table:

- A PT2 archive gives description, licence, author and tags only
  in the "rich" layout.
- HDF5 / Keras v1-v2 gives only what the `model_config` attribute holds.

**Not detected, or not scanned:**

- A `.bin` file without the fastText (or another format's) magic bytes, or
  a `.model` file without the CRFsuite one, is not detected, and no warning
  is given: other tools use these suffixes too. Only files with a model
  extension are candidates; a model renamed to `weights.dat` is not found.
- Models inside archives other than those a reader opens itself: a model
  in a `.zip`, `.tar` or nested wheel is not found. The readers open the
  ZIP structure of Keras v3, PyTorch, PT2 and `.npz` files only.
- Sharded models: each shard is its own entry. The index file that ties
  shards together (`model.safetensors.index.json` and similar) is not read.
  A Safetensors shard's parameter count is that of its own file; a GGUF file
  that declares `split.count` above 1 has none.
- Usage edges (`hasDataFile`, from a `.py` file to a model, with the access
  in `comment`: `read access`, `write access`, `read and write access` or
  `unknown access`) exist only with `--scan-model-usage`. They come from an
  AST walk of `.py` files whose text mentions the model's file name:
  path-shaped string literals (and single-assignment constants, `Path /`,
  `os.path.join`, f-strings, `.format()` and `%` within one file) are matched
  against the model's file name and directory suffix, then classified by the
  enclosing call or open mode. Comments, docstrings and mention-only calls
  (`print`, logging, exceptions) produce no edge, nor does a constant read
  only to build their message (`print(f"loading {MODEL}")`). A path built
  dynamically at run time, imported from another module, read from a config
  file, or inside a notebook is missed. A `.py` file that mentions a model
  name but cannot be parsed by the running Python gives `WARNING:
  FILE=<path>: could not parse as Python <x.y> for usage scanning; <failure>
  [usage-unparseable]`, one
  `INFO: FILE=<path> MODEL=<name>: model file name found; no usage
  relationship recorded [usage-unparseable/mention]` per model file name, and
  no edge.
  A file named `.PY` in capitals is not read at all: `WARNING: FILE=<path>:
  not scanned for usage; only a .py extension is read as Python
  [usage-unusable]`, once per file, when a model was found.
  Both the `.py` file and the model must be in the SBOM's file list.
- `env` and sdist targets do not scan for models and warn that
  `--scan-model-usage` has no effect. A model in a wheel is not enriched
  from a README or model card: no README is read from an archive.
- Remote models: `loom model` with a Hugging Face ID or URL reads the Hub
  API, not a file; see [Hugging Face Hub models](ai-model-formats-hugging-face.md#hugging-face-hub-models).
- A file whose header is that of a model but which the reader cannot parse
  (truncated, corrupt) gives `WARNING: FORMAT=<fmt> FILE=<path>: failed to
  extract metadata; <error>` and a stub. A missing optional library gives
  a stub and `required library not installed`; one that is installed but
  fails to import, a stub and `required library failed to import`.
- A file whose header contradicts its model suffix, or a Git LFS pointer, is
  not a model, but is still listed as a `software_File` (a pointer by its
  `oid`, as in [Git URLs](git-urls.md)); see [What is a
  model](#what-is-a-model).

## Known limitations

What the caps leave open (peak memory of a bounded file, the native parsers
that are only gated, no Ctrl-C inside one, disk use) is on
[its own page](ai-model-scan-limits-known-limitations.md).

## See also

- [AI model formats](ai-model-formats.md) -- formats, extensions, install
  extras.
- [AI model scan limits, size and count caps](ai-model-scan-limits-caps.md)
  -- every cap, its value and what happens when it is hit.
- [Reading values back](metadata-reading-back.md) -- how caps, scalar text
  and the display escape combine, and how to read a value back.
- [Configuration](configuration.md) -- `max-model-extract-bytes`,
  `scan-model-usage`, `max-source-metadata-bytes`.
- [Command line](cli.md) -- `--trust-model-files`, `--max-model-extract-bytes`,
  `--scan-model-usage`.
- [Python API](python-api.md) -- `trust_model_files=`, `max_model_extract_bytes=`.
- [GitHub Action](github-action.md) -- the `trust-model-files` input.
