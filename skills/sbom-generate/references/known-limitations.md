---
Created: 2026-09-29
Last-Modified: 2026-10-02
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
non-Python dependency leaves no element, no error and no `NOASSERTION`
placeholder. Look for non-Python ecosystem files beside `pyproject.toml`.

## Non-PyPI dependencies

`git+https://...`, a local path requirement or a private-index-only
package: supplier/license/hash enrichment has nothing to look up, so the
fields land on `NOASSERTION` -- correct for "genuinely unknown".

## AI model formats

Recognised: GGUF, ONNX, PyTorch, PyTorch PT2/ExecuTorch, Safetensors, Keras,
HDF5, NumPy, fastText, plus Hugging Face Hub. A file is a model only when its
header does not contradict its format: magic bytes (GGUF, fastText, `.npy`,
Safetensors), a ZIP header (`.keras`, `.pt2`, `.npz`) or a ZIP or pickle
protocol 2-5 header (`.pt`/`.pth`); ONNX and HDF5 are accepted by suffix when
the file is not empty. A Python path-configuration `.pth` or an older pickle
is not a model (silent); text named `.gguf`, `.keras`, `.safetensors`... is
not either, with one `WARNING: ... header is not <fmt>; not listed as an AI
model`, and a Git LFS pointer is not one under any candidate suffix (`.onnx`,
`.h5`, `.pt`, `.bin` included), with `header is a Git LFS pointer; not listed
as an AI model`.

A recognised model can still be recorded as a stub: an `ai_AIPackage` named
after its format, with no `ai_*` property, a `contains` link to its
`software_File` and that file's SHA-256. A read model's `comment` has
`Source: <model file> | Field: ...` entries; a stub's has none. With
`--enrich` a stub can carry a `comment` from the README (`Source: README.md
| Method: yaml_frontmatter`) and is still unread. (A format-named entry with
other properties was read: NumPy, fastText and classic PyTorch carry no
model name.)
Causes, each with its own stderr line:

- Wheel gate: fastText, GGUF, HDF5, ONNX and PyTorch `.pt`/`.pth` inside a
  wheel are not read without `--trust-wheel-model` (one `INFO:` names them;
  in a batch, each format once).
- Size ceiling: a wheel member over `max-model-extract-bytes` (default
  512 MiB; set only in a config file): `WARNING: ... scan ceiling; metadata
  not read`.
- Per-wheel budget (4x the ceiling): one `WARNING: ... the per-wheel budget
  ... is spent`; after it later models are stubbed without a further line,
  except one over the ceiling or missing its library, which adds its own.
- Missing reader library: `WARNING: FORMAT=... required library not
  installed; ...` -- install `pitloom[ai]` or the format's extra.
- A bound inside the file (pickle size/opcodes/decimal number length, GGUF
  header, Safetensors header, `.npy` header, archive member size, ZIP entry
  count or central-directory size): `WARNING: ... metadata not read`.
- A file with a model's header that the reader cannot parse (truncated,
  corrupt): `WARNING: ... failed to extract metadata; <error>`.

Every one of these leaves one stub per model file, never none, so which files
are listed does not depend on file order or installed libraries. `loom model
FILE`, `loom enrich FILE` and `loom generate FILE` give the same stub and the
same `WARNING:` with exit 0 for a bound, a missing library and a parse failure
(the wheel gate, ceiling and budget apply to wheel scans only). A file that is
not a model is no entry in a scan, and an `ERROR:` (exit 1) for those
commands: empty, an unknown format, or a header that contradicts the suffix,
which includes a Git LFS pointer. A scan says `WARNING: ... header is a Git
LFS pointer; not listed as an AI model`; `loom model` and `loom enrich` (any
suffix) and `loom generate FILE` (model suffixes only, `.bin` included; a
`.zip` is read as an sdist and fails as one) say `ERROR: model command
failed:`, `enrichment fragment generation failed:` or `SBOM generation
failed:`, then `<path>: header is a Git LFS pointer`. The file was not fetched: run `git lfs
pull` and regenerate.

Inputs, outputs, hyperparameters, properties and raw metadata are cut at 1000
entries (one `WARNING:`; the first 1000 in file order, in key order for
Safetensors `__metadata__`; also for `loom model FILE` and `loom enrich FILE`,
not a Hugging Face model). Project scans, `loom model FILE` and `loom enrich
FILE` have no ceiling and no gate. The same input gives the same SBOM for the
same settings; `--trust-wheel-model`, `max-model-extract-bytes`,
`--scan-model-usage` and `--allow-build` each change what is
recorded, so do not compare SBOMs made with different ones. Full table:
<https://bact.github.io/pitloom/ai-model-scan-limits/>.

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
   <https://bact.github.io/pitloom/cli/> (section "Embed an SBOM into a wheel")
   with WebFetch or `curl` and relay the relevant part; fall back to 1-3.
5. **Never** add the flag on your own. Non-interactive: report the refusal, the
   explanation and the exact re-run command with the flag.
