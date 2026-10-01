---
Created: 2026-10-01
Last-Modified: 2026-10-01
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scan limits

See also: [AI model formats](ai-model-formats.md) for what each reader
extracts, and [Configuration](configuration.md) for the one setting here
that can be changed.

Use this when you ask "why is my model missing metadata?". An AI model
file is untrusted input: what it declares (a header size, an entry count,
an array length) decides how much memory and time a parser spends. Pitloom
therefore refuses some files, or parts of them, and says so on stderr.
The caps and the wheel gate below came with PR #263.

Every line quoted below starts with `WARNING:` or `INFO:`; `<fmt>` is the
format name (`gguf`, `safetensors`, ...) and `<path>` the model's path in
the project or wheel.

## Why is my model missing metadata?

| What you see | Cause | Section |
| :----------- | :---- | :------ |
| An `ai_AIPackage` named after its format (`gguf`, `onnx`, ...) and nothing else, plus one `INFO:` | Wheel scan, format not read without `--trust-wheel-model` | [Formats gated in wheels](#formats-gated-in-wheels) |
| Same, plus `WARNING: ... scan ceiling; metadata not read` | File larger than `max-model-extract-bytes` | [Size and count caps](#size-and-count-caps) |
| Same, plus `WARNING: AI model scan: the per-wheel budget of N bytes ...` | The wheel's total budget is spent | [Size and count caps](#size-and-count-caps) |
| Same, plus another `...; metadata not read` line | A bound inside the file was exceeded | [Size and count caps](#size-and-count-caps) |
| Only the first 1000 inputs, hyperparameters, ... | Entry cap | [Size and count caps](#size-and-count-caps) |
| No `ai_AIPackage` at all, only the file entry, plus `failed to extract metadata` | The reader could not parse the file | [What cannot be recorded](#what-cannot-be-recorded) |
| A field a format cannot carry (no model name in a `.npy`) | Not a limit: the format has no such field | [What cannot be recorded](#what-cannot-be-recorded) |
| No model at all | Not a detected model, or a target that does not scan models | [What cannot be recorded](#what-cannot-be-recorded) |

The format-only entry (a "stub") has exactly this: an `ai_AIPackage` whose
`name` is the format name and which has no `ai_*` property and no `comment`
entry `Source: <model file> | Field: ...` (a read model has such entries), a
`contains` relationship to the model's `software_File`, and that file's
SHA-256 hash. The hash comes from the file list and does not depend on the
model being read. With `--enrich` (project scans) a stub can also carry a
`comment` from the README or model card, `Source: README.md | Method:
yaml_frontmatter`, plus the license and datasets it names; it is still a
stub.

## Which scans apply which limits

| Target | How the model is read | Ceiling, budget | Wheel gate | Inner and header bounds, entry cap |
| :----- | :-------------------- | :-------------- | :--------- | :--------------------------------- |
| `wheel`, `wheel --embed`, `embed-wheel` without `--project-dir`, `generate x.whl` | Copied out of the wheel to a temporary file, one at a time | Yes | Yes | Yes |
| `project`, `generate <dir>`, `embed-wheel --project-dir`, the Hatchling hook, `--allow-build` | Read in place | **No** | **No** | Yes |
| `loom model FILE`, `loom enrich FILE` | Read in place | No | No | Header and inner bounds: yes, as a failure (below). Entry cap: yes |
| `env`, sdist archive, `loom model` with a Hugging Face ID or URL | Models are not scanned | -- | -- | -- |

Scanning an untrusted checkout therefore runs the fastText, HDF5, ONNX,
GGUF and PyTorch readers on its files, in Pitloom's own process, with no
size ceiling. Only scan project directories you trust.

With `loom model FILE` or `loom enrich FILE` there is no format-only entry: a
bound that is exceeded stops the command with `ERROR: model command failed:
<reason>` (`ERROR: enrichment fragment generation failed: <reason>` for
`enrich`) and exit status 1, and nothing is written. The 1000-entry cap applies as in
the scans: the model is kept, cut, with the same one `WARNING:` naming the
fields cut.

## Size and count caps

Values are exact; "stub" is the format-only entry described above.

| Cap | Value | Applies to | Configurable | When it is hit |
| :-- | :---- | :--------- | :----------- | :------------- |
| Per-model size ceiling | 512 MiB (536870912 bytes) | Wheel scans, every format | `[tool.pitloom] max-model-extract-bytes` (positive integer; zero is an error, not "unlimited"), from `--config` or `pitloom_config=`. No CLI flag | Stub, per model. Declared size over the ceiling, checked before copying: `WARNING: FORMAT=<fmt> FILE=<path>: <N> bytes exceeds the <limit>-byte scan ceiling; metadata not read`. The copy also counts the bytes it really reads, so an archive that understates its size is stopped too: `... read more than <limit> bytes, over the <limit>-byte scan ceiling; metadata not read` |
| Per-wheel budget | 4 times the ceiling (2 GiB by default) | Wheel scans: bytes copied plus bytes read from inside models | Derived from the ceiling; no key of its own | Models in path order are read until it is spent; later ones are stubs. One `WARNING: AI model scan: the per-wheel budget of <N> bytes for copying and reading model files in <wheel> is spent; the model that would pass it and the models not yet read are listed without metadata` per wheel |
| Inner archive member | 8 MiB | Every scan. Keras v3 `metadata.json` and `config.json`; PyTorch `.pt`/`.pth` `data.pkl` (a raw pickle `.pt` is read to the same cap; its stub reads `first pickle not complete within 8388608 bytes`); PT2 `version`, `archive_version`, `METADATA.json`, `models/model.json` and `extra/` files | No | Stub: `WARNING: FORMAT=<fmt> FILE=<path>: archive member <name> larger than 8388608 bytes; metadata not read`. Read bounded, so a few KiB that inflate to gigabytes are refused |
| ZIP entries | 100,000 entries, counted by walking the central directory as Python's `zipfile` does (the counts in the end record are not trusted), and a central directory of at most 25,600,000 bytes (256 bytes per entry at the cap), both checked before the archive is opened | Keras v3, PyTorch `.pt`/`.pth`, PT2, `.npz` | No | Stub: `WARNING: FORMAT=<fmt> FILE=<path>: ZIP archive of more than 100000 entries; metadata not read` (or `ZIP central directory of <N> bytes`). If Python's internal ZIP code cannot be asked, the archive is refused too: `ZIP archive not checkable: zipfile internals changed`. A real checkpoint has a file per tensor, a few thousand at most; without the check 3 million empty entries in 16 MiB peaked at 1.8 GB |
| Pickle opcodes | 250,000; only the first pickle is read | PyTorch `.pt`/`.pth` | No | Stub: `... pickle with more than 250000 opcodes; metadata not read` |
| GGUF header budget | 1,000,000 units: tensor infos and key/value pairs weigh 4 each, array elements 1 each, at every depth | GGUF | No | Stub: `... GGUF header declares <N> tensors, over the 1000000 budget` (or `key/value pairs`, `array of <N> elements`). A count that cannot fit in the file is refused the same way: `GGUF header declares <N> tensors` (or `key/value pairs`), `GGUF array of <N> elements, more than the file holds` |
| GGUF array nesting | 4 levels | GGUF | No | Stub: `... GGUF arrays nested over 4; metadata not read` |
| GGUF string | 8 MiB per key or string | GGUF | No | Stub: `... GGUF string of <N> bytes; metadata not read`. A string that runs past the end of the file is left to the reader, which fails it |
| GGUF version | 2 and 3 are walked; a version the `gguf` package reads but the walk does not know is refused | GGUF | No | Stub: `... GGUF version <N>, not bounded; metadata not read` |
| Safetensors header | 16 MiB | Safetensors | No | Stub: `... Safetensors header of <N> bytes; metadata not read` |
| `.npy` header | 10000 bytes (NumPy's own limit) | `.npy`, and each array in an `.npz` | No | Stub: `... .npy header of <N> bytes, over 10000; metadata not read` |
| `.npz` members | Reading stops after 1001 arrays; then the entry cap below applies | `.npz` | No | See the entry cap |
| Entries per list or map | 1000, the first ones: in file order, except Safetensors `__metadata__`, which has none and keeps its first 1000 keys in sorted order. Safetensors' well-known keys (`modelspec.title`, `name`, `format`, ...) are read from the whole `__metadata__`, so they set the model's name, version and so on even when they sort past the cut | `inputs`, `outputs`, `hyperparameters`, `properties`, `raw_metadata` of every format; project and wheel scans, `loom model FILE` and `loom enrich FILE`. Not a Hugging Face model (`loom model <ID>` reads the Hub API, uncut) | No | Model kept, lists trimmed, provenance of dropped keys removed: `WARNING: FORMAT=<fmt> FILE=<path>: more than 1000 entries in <fields>; the first 1000 of each are kept` |
| Archive listing | First 20 names (`properties.archive_contents`, ending `, ... (<N> total)` when cut) | PyTorch classic, PT2 | No | No log line, since nearly every checkpoint has a file per tensor; the value itself says it is cut |
| Unparsed Keras config | First 500 characters (`properties.model_config_raw`) | HDF5, only when the config cannot be parsed | No | `WARNING: FORMAT=<fmt> FILE=<path>: Unparsed model_config of <N> characters; the first 500 are kept ...`, only when it is longer than 500 |
| fickling messages | fickling's stderr output is held back (first 4096 characters kept) and the warning quotes the first 200 | PyTorch `.pt`/`.pth` | No | `WARNING: fickling reported on stderr: <text>` |
| Usage-scan source size | 1 MiB per `.py` file | `--scan-model-usage`, project and wheel scans | No | File skipped: `WARNING: FILE=<path>: larger than the 1048576-byte usage-scan cap; skipped` |
| Usage-scan encoding | Strict UTF-8 | The same | No | File skipped: `WARNING: FILE=<path>: could not read for usage scanning; <error>` |
| Artifact-metadata size | Unlimited by default | The verbatim metadata annotation of any model | `max-source-metadata-bytes`, `--max-source-metadata-bytes` | Largest entries dropped first and marked truncated; see [Metadata provenance](metadata-provenance.md#size-bounded-preservation) |

There is no limit on the number of model files in a project or wheel. In a
wheel, the one directory not scanned is the `.dist-info` its file name names
(`my_pkg-1.0.dist-info` for `My.Pkg-1.0.0-...whl`, names and versions compared
as Python packaging does); any other `*.dist-info`, whatever it holds, is
scanned like any other directory. A path that is not a wheel file name, from
the Python API, has none skipped.
The ceiling and budget are checked against file sizes, so a gated format
(next section) is never copied and spends none of the budget.

## Settings that change the SBOM

The same input with the same settings gives a byte-identical SBOM. Changing
a setting below changes what is recorded, so two runs with different
settings are not expected to match. Each one says so on stderr when it
changes the models' entries, except where you asked for the change yourself:

| Setting | What changes | Message |
| :------ | :----------- | :------ |
| `--trust-wheel-model` | Models of the gated formats in a wheel are read, not listed as stubs | Without it, one `INFO:` naming the formats not read (each format once per run) |
| `max-model-extract-bytes` | A model over it, and every model after the per-wheel budget (4 times it) is spent, is a stub | One `WARNING:` per stubbed model; one per wheel for the budget |
| `--scan-model-usage` | `hasDataFile` edges from `.py` files to models exist or not | Without the setting given, one `INFO:` naming the flag |
| `--allow-build` | The file list comes from a real build, so the models found, and their paths, can differ from the static list | None when the build succeeds; a `WARNING:` and the static list when it fails. See [Building a project](allow-build.md) |
| The 1000-entry cap | Which entries are kept: the first 1000 in file order, or in sorted key order for Safetensors `__metadata__` | One `WARNING:` per model naming the fields cut, in a scan and in `loom model FILE` (not for a Hugging Face model) |
| A project directory, not its built wheel | Models are read in place: no ceiling, no gate | None; see [Which scans apply which limits](#which-scans-apply-which-limits) |

A cut that the output marks itself, such as the 20-name archive listing
(`... (<N> total)`) or the entries dropped from the artifact-metadata
annotation (`truncated`), has no log line.

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

Pitloom logs one line per scan, naming the gated formats it met that it has not already named. In a batch (`embed-wheel` with several wheels) each format is named once, in the first wheel that has it, and a later wheel with a different gated format gets its own line:

```text
INFO: AI models in a wheel in these formats are listed without metadata, their reader not being run on a wheel's files: gguf, onnx. Pass --trust-wheel-model for a wheel you trust.
```

To read them, for a wheel you trust:

| Surface | How |
| :------ | :-- |
| CLI | `--trust-wheel-model` on `wheel`, `wheel --embed` or `embed-wheel` without `--project-dir` |
| Python API | `trust_wheel_model=True` on `generate()` or `generate_wheel_sbom()`; `ConfigOverrides.trust_wheel_model` for `embed_wheel_sbom()` without `project_dir=` |
| GitHub Action | Input `trust-wheel-model: "true"`, with `embed-wheel` and `project-path: ""` only. With a `project-path` the models come from the project and the action logs `::warning::trust-wheel-model has no effect with project-path set`; outside `embed-wheel` it logs `::warning::trust-wheel-model has no effect without embed-wheel` |

There is no `[tool.pitloom]` key, on purpose: a config file can sit in the
untrusted tree, so it must not be able to switch the protection off. On any
other target the option warns that it has no effect. Safetensors, Keras v3,
NumPy and PT2 readers do not pass the file to a native library and are not
gated; the caps above still apply to them.

## What cannot be recorded

**Whatever the cause.** The `ai_AIPackage` carries name, version,
description, type of model (and architecture), hyperparameters (and
quantisation), and the inputs and outputs (as `informationAboutApplication`).
Properties that fit no field are kept only in the verbatim artifact-metadata
annotation. The framework name, framework version and format version a
reader finds are not written to an SPDX field of their own. The package is
named after the format when the file has no name.

**Fields a format never carries**, even when fully read:

| Format | Always absent |
| :----- | :------------ |
| NumPy | Name, description, version, hyperparameters, outputs. A `.npy` gives one input (shape, dtype); an `.npz` gives one per array |
| Safetensors | Outputs, hyperparameters, type of model. Inputs are tensor names only, with no shapes or dtypes. Name, version, description, architecture and quantisation only if the `__metadata__` header has the matching key |
| GGUF | Inputs and outputs (tensors are not listed), type of model |
| PyTorch classic | Name, version, architecture, inputs, outputs, hyperparameters. Only the class at the top of `data.pkl` (needs `fickling`; without it, no type of model) |
| PT2 / ExecuTorch | Hyperparameters. Description, licence, author and tags only in the "rich" layout |
| Keras v3 | Outputs. Hyperparameters are the scalar entries of `config` only |
| HDF5 / Keras v1-v2 | Whatever the `model_config` attribute lacks |
| ONNX | Hyperparameters. Tensors stored in external data files are not read (`load_external_data=False`) |
| fastText | Name, description, version, inputs. Labels only for supervised models |

**Not detected, or not scanned:**

- A `.bin` file without the fastText magic bytes is not detected, and no
  warning is given. Only files with a model extension are candidates; a
  model renamed to `weights.dat` is not found.
- Models inside archives other than those a reader opens itself: a model
  in a `.zip`, `.tar` or nested wheel is not found. The readers open the
  ZIP structure of Keras v3, PyTorch, PT2 and `.npz` files only.
- Sharded models: each shard is its own entry. The index file that ties
  shards together (`model.safetensors.index.json` and similar) is not read.
- Usage edges (`hasDataFile`, from a `.py` file to a model) exist only with
  `--scan-model-usage`. They come from the model's file name appearing as
  text in a `.py` file, so a name built at run time, a path from a
  variable, or a notebook is missed. Both the `.py` file and the model must
  be in the SBOM's file list.
- `env` and sdist targets do not scan for models and warn that
  `--scan-model-usage` has no effect. A model in a wheel is not enriched
  from a README or model card: no README is read from an archive.
- Remote models: `loom model` with a Hugging Face ID or URL reads the Hub
  API, not a file; see [Hugging Face Hub models](ai-model-formats.md#hugging-face-hub-models).
- A file the reader cannot parse (truncated, wrong format, corrupt) gives
  `WARNING: FORMAT=<fmt> FILE=<path>: failed to extract metadata; <error>`
  and **no** `ai_AIPackage`; the file is still listed as a `software_File`.
  A missing optional library gives a stub and
  `required library not installed`.

## Known limitations

The bounds keep a hostile file from being cheap to abuse; they do not make
it free. Figures are approximate, from measurements on one machine.

- **Memory and time of bounded input.** The largest GGUF header accepted
  costs about 1.1 GB and 6 seconds. A Safetensors header just under 16 MiB
  peaks near 0.8 GB. A pickle at the opcode cap costs about 100 MB and
  under a second in fickling. The `safetensors` library builds a model's
  whole `__metadata__` map, and the ONNX reader its whole result, before the
  entry cap trims them, so the cap bounds the SBOM, not one model's peak
  memory (about 0.6 GB for a 16 MiB `__metadata__`: 0.53 GB for one model,
  0.58 GB for a wheel of 24 of them). The trimmed maps are rebuilt and the
  memory released, so a wheel's peak is its largest model's, not the sum of
  its models'.
- **Unbounded native parsers** (fastText, HDF5, ONNX). They are not
  bounded, only gated in wheels. With `--trust-wheel-model`, or in a
  project scan, a crafted file can use gigabytes (a 16 MiB ONNX measured
  about 3 GB; a 308-byte fastText header reached 5 GB and kept climbing)
  or crash or hang libhdf5.
- **No Ctrl-C while a native parser runs.** A signal handler does not run
  inside native code, so interrupting waits for the parser; kill the
  process if it hangs.
- **Disk.** A wheel scan copies each model it reads to a temporary
  directory, up to the budget (2 GiB by default), and removes it after.
- **Planned.** Header-only readers that never pass a file to a native
  library are planned for a future release. They would let the gated
  formats be read in wheels without `--trust-wheel-model` and replace
  several of the bounds above.

## See also

- [AI model formats](ai-model-formats.md) -- formats, extensions, install
  extras.
- [Configuration](configuration.md) -- `max-model-extract-bytes`,
  `scan-model-usage`, `max-source-metadata-bytes`.
- [Command line](cli.md) -- `--trust-wheel-model`, `--scan-model-usage`.
- [Python API](python-api.md) -- `trust_wheel_model=`.
- [GitHub Action](github-action.md) -- the `trust-wheel-model` input.
