---
Created: 2026-09-29
Last-Modified: 2026-10-01
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
HDF5, NumPy, fastText, plus Hugging Face Hub.

A recognised model can still be recorded as a stub: an `ai_AIPackage` named
after its format, a `contains` link to its `software_File` and that file's
SHA-256, nothing else. Causes, each with its own stderr line:

- Wheel gate: fastText, GGUF, HDF5, ONNX and PyTorch `.pt`/`.pth` inside a
  wheel are not read without `--trust-wheel-model` (one `INFO:` names them).
- Size ceiling: a wheel member over `max-model-extract-bytes` (default
  512 MiB; set only in a config file) or past the per-wheel budget (4x the
  ceiling): `WARNING: ... metadata not read`.
- A bound inside the file (pickle size/opcodes, GGUF header, Safetensors
  header, `.npy` header, archive member size): `WARNING: ... metadata not
  read`.

A file the reader cannot parse at all gets no `ai_AIPackage`, only its
file entry and a `failed to extract metadata` warning. Inputs, outputs,
hyperparameters and properties are cut at 1000 entries (one `WARNING:`; the
first 1000 in file order, in key order for Safetensors `__metadata__`). Project
scans have no ceiling and no gate. The same input gives the same SBOM for the
same settings; `--trust-wheel-model`, `max-model-extract-bytes`,
`--scan-model-usage`, `--allow-build` and the cap each change what is
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
