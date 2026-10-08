---
Created: 2026-09-29
Last-Modified: 2026-10-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom known limitations: detail

See also: `../SKILL.md` ("Known limitations", which holds the rule for
each case: say so plainly, do not paper over it).

Pitloom's dependency/supplier/license extraction is Python-packaging-native:
it reads `pyproject.toml`/`setup.cfg`/`setup.py`, installed
`importlib.metadata`, and the PyPI JSON API. Outside that world, coverage
drops.

## No Python packaging markers

Typical files: `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`/
`build.gradle`, `Gemfile`, `composer.json`, a `.csproj`/`.sln`. The
refusing `ERROR:` names `pyproject.toml`, `setup.cfg` and `setup.py`.

## Mixed-ecosystem repos

The SBOM inventories `[project.dependencies]` and what is importable; every
non-Python dependency leaves no element, no error and no placeholder. Look for
non-Python ecosystem files beside `pyproject.toml`.

## Non-PyPI dependencies

`git+https://...`, a local path requirement or a private-index-only
package: unless it is installed locally (its installed metadata is read),
supplier/license/hash enrichment has nothing to look up, so the copyright
lands on `NOASSERTION`, supplier and hash stay empty, and the package gets
no license relationship -- Pitloom never asserts a license it was not told
(a source that itself says `UNKNOWN`/`NOASSERTION` gives the
`NoAssertionLicense` individual).

## AI model formats

Formats, suffixes and header checks:
<https://bact.github.io/pitloom/ai-model-formats/>; what counts as a model:
<https://bact.github.io/pitloom/ai-model-scan-limits/#what-is-a-model>. A
`.bin` or `.model` file without a format's magic, and a Python
path-configuration `.pth`, are silently not models (other tools use those
suffixes).

How to tell a stub, its causes and their stderr lines: `../SKILL.md` ("AI
model caps"). Beyond that:

- A file-named entry with other properties was read: NumPy, fastText,
  CRFsuite and classic PyTorch carry no model name, nor does an ONNX file
  whose `graph.name` is an exporter default.
- A name ending `...~` and 8 hex digits was cut at 1024 characters (code
  points), the digest of the whole name keeping two long names apart: the
  model's own name, or its file name stem, whichever is shown, and its
  base model, dataset and dataset creator names. The id registry and the
  `spdxId` use the same cut name. `WARNING: FORMAT=<fmt> FILE=<path>:
  model name of <N> characters cut to 1024` (or `base model name`,
  `dataset name`, `dataset creator name`).
- A `\udXXX` in a name or value was a lone surrogate in the file (a JSON
  or YAML `"\ud800"`), which UTF-8 cannot hold: `WARNING: FORMAT=<fmt>
  FILE=<path>: lone surrogates written as \uXXXX`.
- A CRFsuite or fastText model with no `labels` but a `num_labels` (or an
  `outputs` shape) had a label over 4 KiB: then none is recorded, and a
  CRFsuite model gets no generated description. `WARNING: FORMAT=<fmt>
  FILE=<path>: a label over 4096 bytes; no label recorded`. A CRFsuite
  description shows at most 20 labels of 64 characters each, by design.
- `\u202e`, `\ufeff` and the like in a name, description, type,
  hyperparameter, `ai_informationAboutApplication`, a reference, a
  licence, or a Hugging Face base model or dataset are escaped invisible,
  bidi or control characters, a URL percent-encoded (U+202E can make
  `txt.exe` read `exe.txt`):
  `WARNING: FORMAT=<fmt> FILE=<path>: invisible or bidi control characters
  written as \uXXXX in <properties>`. The escape is not reversible on its own:
  a `\u202e` the file held as text looks the same, so check the
  `artifact-metadata` annotation's `metadata` (kept as read; not every
  field, e.g. an ONNX graph name) or the model file. Which fields are escaped:
  <https://bact.github.io/pitloom/metadata-reading-back/>.
- No `ai_typeOfModel` on an ONNX model: a node uses an `ai.onnx.ml`
  operator (trees, linear models, SVMs), and the file does not say which
  kind of model that is, so it is left unset, silently. Otherwise it is
  `neural network` (the ONNX-ML opset import alone does not count).
- Reading values back from the `artifact-metadata` annotation (`/2`):
  collections (`labels`, shapes) are JSON arrays, scalars are text, and
  `valueTypes` names the type of each (`integer`, `float`, `boolean`).
  fastText `labels` is a JSON array too, so parse it, do not split on
  commas. A `truncated` or `maxEntries` key means entries were cut at the
  cap. How to decode: <https://bact.github.io/pitloom/metadata-reading-back/>.
- After the per-wheel budget is spent, later models are stubbed without a
  further line, except one over the ceiling or missing its library, which
  adds its own.
- The same input gives the same SBOM for the same settings;
  `--trust-wheel-model`, `max-model-extract-bytes`, `--scan-model-usage` and
  `--allow-build` each change what is recorded, so do not compare SBOMs made
  with different ones.

Every cap, its value and message (the single source of truth):
<https://bact.github.io/pitloom/ai-model-scan-limits/#size-and-count-caps>.

## Unsupported build backend

Hatchling, setuptools, Poetry, PDM-backend and Flit-core get accurate
file-level discovery (files, hashes, Merkle root) by default. Any other
backend (`uv_build`, or one still without its own toolchain, e.g.
`maturin`/`scikit-build-core`/`meson-python`) falls back to a
Hatchling-based heuristic. Project-level metadata (name, version,
dependencies, license, authors) is read independently and unaffected
either way. Full detail: [docs/cli.md's Generate an SBOM
section](https://bact.github.io/pitloom/cli/#generate-an-sbom).

## Wheel SBOM contents and signing

A wheel SBOM (`loom wheel`, `generate <whl>`, `embed-wheel`, `wheel --embed`)
lists the payload only: nothing under the wheel's own `.dist-info`, `licenses/`
included. `embed-wheel` and `wheel --embed` refuse a wheel with `RECORD.jws` or
`RECORD.p7s` unless `--allow-signed-wheel` (deletes the signature files, one
`INFO:` each; re-sign afterwards). Pitloom cannot see signatures or hashes over
the wheel file itself (GPG `.asc`, Sigstore, PEP 740, lock-file hash); any embed
invalidates them, so embed first, then sign, attest, upload and hash.

### Signed wheels: what to tell the user

Use when `unzip -l <wheel>` shows `RECORD.jws` or `RECORD.p7s`, or `embed-wheel`
/ `wheel --embed` refused with a signature `ERROR:`.

1. **Plain explanation.** The wheel carries a signature over its file list
   (`RECORD`). Embedding adds the SBOM and rewrites that list, so the old
   signature would no longer verify. Pitloom stops rather than leave a broken
   signature or delete one silently.
2. **The choice.** `--allow-signed-wheel` deletes the signature file(s) (one
   `INFO:` each) and embeds. Afterwards the wheel is unsigned until the user
   re-signs it. Or skip embedding, or embed before the wheel is first signed.
3. **Order of operations.** Build, embed, then sign, attest (Sigstore, PEP 740),
   upload and record hashes (lock file, `pip --hash`): anything made over the
   whole `.whl` stops matching after an embed, and Pitloom cannot detect it.
4. **Context.** For wording matching the wheel's situation (publishing, an
   internal index, verifying someone else's wheel), fetch
   <https://bact.github.io/pitloom/wheel-sbom/#signed-wheels>
   with WebFetch or `curl` and relay the relevant part; fall back to 1-3.
5. **Never** add the flag on your own. Non-interactive: report the refusal, the
   explanation and the exact re-run command with the flag.

## A licence that looks like a broken expression

Text with an operator or parenthesis and a known id (`MIT OR`, `(MIT`) is
kept as `SimpleLicensingText`, not dropped, with one stderr line per value,
e.g.:

```text
WARNING: LICENSE='MIT OR': not a valid SPDX license expression (Unexpected 'OR'); recorded as license text
```

Fix the source value to get a `LicenseExpression`.
