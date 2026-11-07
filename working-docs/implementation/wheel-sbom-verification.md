---
Created: 2026-07-06
Last-Modified: 2026-11-07
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Wheel-embedded SBOM verification

See also:
[wheel-sbom-verification-history.md](wheel-sbom-verification-history.md)
(the verifications of v0.9.0 to v0.20.2).

## Why this exists

The Hatchling-hook rewiring and code-review fixes (name/dependency
canonicalisation parity, Poetry fallback, PURLs, file hashes -- see
[hatchling-build-hook.md](hatchling-build-hook.md)) had only
been checked against local dogfood builds and unit/integration tests
before this pass. This document records independent checks against
**actual published releases** on PyPI -- the real, externally-built
artefacts -- so the result is durable evidence, not just a one-off chat
answer that disappears with the session that produced it.

As of 2026-08-11 this check is part of the standard
[release checklist](release-checklist.md) (step 3, post-publish
verification) -- run it for every release, not just the ones below that
happened to prompt a closer look.

As of 2026-09-01, the location and schema checks below are automatable
via `loom verify-wheel <whl> --sbom-filename <name>` and `loom
validate-wheel <whl>` (see [roadmap.md](../design/roadmap.md)'s "PEP 770 /
embed-wheel" section) -- the manual method documented per-release below
still applies to a published PyPI wheel specifically (download + run
against the real artefact), but the same location/schema logic no longer
needs to be reasoned about by hand.

## Verification of v0.23.1 (2026-11-07)

Same method as v0.23.0 below, against
`https://pypi.org/pypi/pitloom/0.23.1/json` (wheel uploaded 2026-11-07
14:54:09 UTC, sdist 14:54:12 UTC, neither file yanked). The GitHub Release
(not a prerelease) was published at 14:52:03 UTC; the tag `v0.23.1` is
lightweight and points at `7c555774` (the merge of #456).

| File | Bytes | SHA-256 |
| - | -: | - |
| `pitloom-0.23.1-py3-none-any.whl` | 1,130,974 | `d481ec0c11b30db952b489ad0b44ac8b97e04dc25f5f8150e65d1bbcdf6a3952` |
| `pitloom-0.23.1.tar.gz` | 10,463,258 | `0fec4cfc8a742530be24fd60a7f731766a5a807c3e193a36fd5466030570a221` |
| `pitloom-0.23.1.spdx3.json` (Release asset) | 1,045,622 | `a9c0fcfbd1c1f9cc209ff771f145f0af50080f92a239180b1b1c11670dc0df01` |

### Method

- As for v0.23.0: downloads against the API digests and the six Release
  assets, `RECORD` and the wheel's payload against `git archive v0.23.1`, the
  sdist against the same archive, `verify-wheel`, `validate-wheel`, `loom
  fragment validate` and `spdx3-validate` 0.0.7 on the standalone SBOM,
  `scripts/check_sbom_license.py` at the tag, `gh attestation verify`, `python
  -m sigstore verify github` (sigstore 4.5.1, with `--sha` and `--trigger
  release`) and PyPI's integrity API.
- Installs of `pitloom==0.23.1` in fresh venvs on Python 3.10.20 and 3.14.6,
  `HOME` in a scratch directory, and a dry-run install with
  `licenseid==0.7.1`. The v0.23.0 smoke tests on fixtures from `git archive`
  of the tag, plus the two 0.23.1 fixes (#455): a project whose `LICENSE`
  is `MIT licensed.`, with and without `-v`, before and after `licenseid
  update --source packaged`, and `license = "New BSD"` with and without a
  database.
- The Action: `action.yml` and `scripts/action/pitloom-install.sh` read at the
  tag; the install script run with a stub `python -m pip`.

### Findings

- The downloads match the PyPI digests; the wheel and the sdist are
  byte-identical to the Release assets, and the standalone SBOM to the
  wheel's member. Six assets: three files, each with a `.sigstore.json`.
  The notes list #455 only; the documentation PRs #453, #454 and #456 are
  left out.
- `requires_dist` has `licenseid<0.8,>=0.7.2`; a dry run with
  `licenseid==0.7.1` fails with `ResolutionImpossible`. `provides_extra`
  unchanged; `requires_python` `>=3.10`; `License-Expression: Apache-2.0`;
  entry points `loom`, `pitloom` and the `hatch` plugin.
- Wheel: 352 members, one SBOM; `RECORD`: 352 rows, 0 bad, none missing,
  none extra; the 346 payload files equal `src/` of the tag.
- sdist: 1,422 files, the tag's 1,894 minus the 473 excluded, plus
  `PKG-INFO` (equal to `METADATA`); no byte differences. Neither the sdist
  nor the wheel has `AGENTS.md`, `CLAUDE.md` or `GEMINI.md`.
- Embedded SBOM: SPDX 3.0.1, 1,595 graph elements, `Apache-2.0` declared and
  concluded; 364 `software_File` (346 payload plus 18 directories), 0 hash
  mismatches. `Tool` `Pitloom 0.23.1`; `licenseid` 0.7.2 listed as a package,
  and licence provenance names `licenseid==0.7.2` (never 0.7.1). All
  validators pass.
- `gh attestation verify` passes for the three files (one SLSA v1
  attestation, source digest `7c555774`) and fails with `--source-ref
  refs/tags/v0.23.0`; `sigstore verify github` passes for the three, and
  fails on a wrong bundle or identity. PEP 740: publisher `bact/pitloom`,
  `pypi-publish.yml`, no environment; one attestation per file.
- Installs succeed, `pip check` is clean, `licenseid` 0.7.2 resolved.
  Smoke tests give the same results on both Pythons: the two `loom project`
  SBOMs are byte-identical; `loom model` exits 0; the version 3 registry
  gets the documented `ERROR`, exit 1, no SBOM, file unchanged; the broken
  `onnx` gives the `[library-unusable]` warning; `Apache2` reads as
  `Apache-2.0` with no database.
- The 0.23.1 fixes: `MIT licensed.` gives no `too few words` line, neither
  as `WARNING` nor with `-v` as `INFO`, and records no licence; `New BSD`
  reads as `BSD-3-Clause` with one `INFO: FIELD=project.license LICENSE='New
  BSD': read as BSD-3-Clause (alias_name)`. After the update a full `LICENSE`
  text gives `Apache-2.0` (`licenseid_detection`, `licenseid==0.7.2`).
- The Action with an empty `pitloom-version` runs `pip install
  pitloom==0.23.1`, the version `check_version_consistency.py` reads at the
  tag.

### Not run or noted

- With no licence database, the `New BSD` project, which has no `LICENSE`
  file, also prints `WARNING: licenseid database cannot be used: ...
  license text detection skipped`; the `Apache2` project does not. Fixed
  in #458: a declared name never looks the database up.
- `loom model` on the GGUF file warns `[library-missing]`: the install has
  no `gguf` extra.
- The SBOM's `created` (14:52:21 UTC) is the build's clock: the publish
  workflow sets no `SOURCE_DATE_EPOCH`, as for 0.23.0. No rebuild compared.
- No workflow run of the Action; no Merkle root recomputation.

## Verification of v0.23.0 (2026-11-06)

Same method as v0.22.1 below, against
`https://pypi.org/pypi/pitloom/0.23.0/json` (wheel uploaded 2026-11-06
00:29:28 UTC, sdist 00:29:30 UTC, neither file yanked). The GitHub Release
(not a prerelease) was published at 00:23:06 UTC; the tag `v0.23.0` is
lightweight and points at `0424016c` (the merge of #449).

| File | Bytes | SHA-256 |
| - | -: | - |
| `pitloom-0.23.0-py3-none-any.whl` | 1,130,893 | `cd765611b8c45cbc71f2746839dbc11e2ad91595f50f1f616b8f583e854da89d` |
| `pitloom-0.23.0.tar.gz` | 10,461,578 | `4ca584bac5dc15ba4a0f56db2e4913c570740705d8fa09611d0358fc846f4e4a` |
| `pitloom-0.23.0.spdx3.json` (Release asset) | 1,045,622 | `ffd7e4f5d52bf3ce015c45e2f0f0476312d69a6d7013ec65972917bcd0ee7d92` |

### Method

- As for v0.22.1: downloads against the API digests and the six Release
  assets, `RECORD` and the wheel's payload against `git archive v0.23.0`, the
  sdist against `git ls-tree -r v0.23.0`, `verify-wheel`, `validate-wheel`,
  `loom fragment validate` and `spdx3-validate` 0.0.7 on the standalone SBOM,
  `scripts/check_sbom_license.py` at the tag, `gh attestation verify`, `python
  -m sigstore verify github` (sigstore 4.5.1, with `--sha` and `--trigger
  release`) and PyPI's integrity API.
- Installs of `pitloom==0.23.0` in fresh venvs on Python 3.10.20 and 3.14.6,
  `HOME` in a scratch directory. Smoke tests on fixtures from `git archive`
  of the tag: `loom project` on `sampleproject-hatchling` twice with
  `--creation-datetime`, `loom model` on `stories260K.gguf`, a version 3
  registry, an `onnx` package on `PYTHONPATH` whose import raises `OSError`,
  `license = "Apache2"` before any licence database, then `licenseid update
  --source packaged` and a project with only a `LICENSE` file.
- The Action: `action.yml` and `scripts/action/pitloom-install.sh` read at the
  tag; the install script run with a stub `python -m pip`.

### Findings

- The downloads match the PyPI digests; the wheel and the sdist are
  byte-identical to the Release assets, and the standalone SBOM to the
  wheel's member. Six assets: three files, each with a `.sigstore.json`.
- `requires_dist` has `licenseid<0.8,>=0.7.1` and no `py-spdx-license`
  (`licenseid` 0.7.1 still pulls `py-spdx-license` 0.0.1); `provides_extra`
  unchanged; `requires_python` `>=3.10`; `License-Expression: Apache-2.0`;
  entry points `loom`, `pitloom` and the `hatch` plugin.
- Wheel: 352 members, one SBOM; `RECORD`: 352 rows, 0 bad, none missing,
  none extra; the 346 payload files equal `src/` of the tag.
- sdist: 1,422 files, the tag's 1,883 minus the 462 excluded, plus
  `PKG-INFO` (equal to `METADATA`); no byte differences. Neither the sdist
  nor the wheel has `AGENTS.md`, `CLAUDE.md` or `GEMINI.md` (#435).
- Embedded SBOM: SPDX 3.0.1, 1,595 graph elements, `Apache-2.0` declared and
  concluded; 364 `software_File` (346 payload plus 18 directories), 0 hash
  mismatches. `Tool` `Pitloom 0.23.0`; `licenseid` 0.7.1 listed as a package,
  and licence provenance names `licenseid==0.7.1`. All validators pass.
- `gh attestation verify` passes for the three files (one SLSA v1
  attestation, source digest `0424016c`) and fails with `--source-ref
  refs/tags/v0.22.1`; `sigstore verify github` passes for the three, and
  fails on a wrong bundle or identity. PEP 740: publisher `bact/pitloom`,
  `pypi-publish.yml`, no environment; one attestation per file.
- Installs succeed, `pip check` is clean, `licenseid` 0.7.1 resolved.
  Smoke tests on both Pythons: the two `loom project` SBOMs are
  byte-identical; the version 3 registry gets the documented `ERROR`, exit
  1, no SBOM, file unchanged; the broken `onnx` gives `WARNING:
  FORMAT=onnx FILE=...: required library failed to import: fake broken
  onnx; reinstall pitloom[onnx] [library-unusable]`; `Apache2` reads as
  `Apache-2.0` with no database; after the update a `LICENSE` file gives
  `Apache-2.0` (`licenseid_detection`).
- The Action with an empty `pitloom-version` runs `pip install
  pitloom==0.23.0`, the version `check_version_consistency.py` reads at the
  tag.

### Not run or noted

- `pip download --no-binary pitloom` fails ("already being built") since the
  build requires `pitloom` itself; the same holds for 0.22.1. The sdist was
  fetched by URL.
- The SBOM's `created` (00:23:29 UTC) is the build's clock: the publish
  workflow sets no `SOURCE_DATE_EPOCH`, as for 0.22.1. No rebuild compared.
- No workflow run of the Action; no Merkle root recomputation.

## Verification of v0.22.1 (2026-11-03)

Same method as v0.22.0 below, against
`https://pypi.org/pypi/pitloom/0.22.1/json` (wheel uploaded 2026-11-03
12:01:20 UTC, sdist 12:01:22 UTC, neither file yanked). The tag `v0.22.1` is
lightweight and points at `6b9fbf1f` (the merge of #431). The release gate ran
twice: its first run failed on an upstream HTTP 500 from Savannah in a
network-dependent test, and the re-run of the failed jobs passed before the
upload. This pass adds what the v0.22.0 pass left out, except a workflow run
of the GitHub Action.

| File | Bytes | SHA-256 |
| - | -: | - |
| `pitloom-0.22.1-py3-none-any.whl` | 1,111,681 | `e1008204dec9fc24576af9500fdccbea6273eef5a9a1786622736ae9d2e664fa` |
| `pitloom-0.22.1.tar.gz` | 10,410,078 | `0a1c8dd3a8cca8ae64cfe1e95fc89de2a531a3d9c4364a03a6db3ce172568602` |
| `pitloom-0.22.1.spdx3.json` (Release asset) | 1,016,627 | `0fd858380db9265bd275986c1dd109239b0848c9aa94bab5ac1fe09433ef3d06` |

### Method

- Wheel and sdist downloaded from the API's URLs into empty directories;
  `sha256sum` against the API digests. The three GitHub Release assets (wheel,
  sdist, standalone SBOM) and their Sigstore bundles downloaded and compared
  byte for byte with the PyPI files and with the wheel's SBOM member.
- `RECORD` checked by a small script run with `python -I`, as for v0.22.0.
  The wheel's files compared with `git archive v0.22.1` (`src/`), and the
  sdist's file list with `git ls-tree -r v0.22.1`, with a byte comparison of
  every file in both.
- Installs of `pitloom==0.22.1` in fresh venvs on Python 3.10.20 and 3.14.6,
  each followed by `pip check`; `loom --version`, `loom verify-wheel <whl>
  --sbom-filename pitloom-0.22.1.spdx3.json --fail-on-mismatch`, `loom
  validate-wheel <whl>`, `spdx3-validate --json` 0.0.7 on the extracted SBOM
  and `scripts/check_sbom_license.py --license Apache-2.0` on the SBOM and on
  the wheel.
- Attestations: `gh attestation verify` on the wheel, the sdist and the
  standalone SBOM, once more with `--source-ref refs/tags/v0.22.0`;
  `python -m sigstore verify github` (sigstore 4.5.1) on the same three
  files with their bundles; the PEP 740 provenance of both PyPI files from
  PyPI's integrity API.
- Smoke tests with the installed release on tiny temporary projects:
  `loom project --scan-model-usage` over a project with a `.safetensors`
  file and a script that reads it, the same without the option, `loom model`
  on a GGUF and a Safetensors file, an ID registry of version 3, `loom id
  generate -e 'foo==1.0:software_Package'`, and the deep-chain case below.
- The Action: `action.yml` and its install script read at the tag; no
  workflow was run.

### Findings

- The downloads match the PyPI digests above; `requires_dist` has
  `licenseid<0.7,>=0.6.0`; `provides_extra` is `ai`, `build`, `content-type`,
  `fasttext`, `gguf`, `hdf5`, `huggingface-hub`, `numpy`, `onnx`, `pytorch`,
  `safetensors`, `validate`; `requires_python` `>=3.10`.
- GitHub Release: the wheel and the sdist are byte-identical to the PyPI
  files, and the standalone SBOM is identical to the wheel's member.
- Wheel: 341 members, one SBOM
  `pitloom-0.22.1.dist-info/sboms/pitloom-0.22.1.spdx3.json`. `RECORD`: 341
  rows, 0 bad hashes or sizes, none missing, none extra. The 335 payload
  files equal `src/` of `git archive v0.22.1` byte for byte.
- sdist: 1,394 members, the tag's 1,847 tracked files minus the 454 that
  `pyproject.toml` excludes, plus `PKG-INFO`; no byte differences, and
  `PKG-INFO` equals the wheel's `METADATA`.
- Embedded SBOM: SPDX 3.0.1, 1,556 graph elements, `Apache-2.0` declared and
  concluded; 353 `software_File` (the 335 payload files plus 18
  directories), 0 hash mismatches. `verify-wheel` OK, `validate-wheel`
  valid, `spdx3-validate` 0.0.7 schema and SHACL pass,
  `check_sbom_license.py` passes on the SBOM and on the wheel.
- Installs on 3.10.20 and 3.14.6 succeed and `pip check` is clean; `licenseid`
  0.6.0 was resolved.
- `gh attestation verify` passes for the wheel, the sdist and the SBOM (signer
  workflow `pypi-publish.yml` at `refs/tags/v0.22.1`, source digest
  `6b9fbf1f`) and fails with `--source-ref refs/tags/v0.22.0`, as it should.
  `sigstore verify github` passes for the same three files. PyPI's PEP 740
  provenance names publisher `bact/pitloom`, workflow `pypi-publish.yml`, and
  one attestation per file whose subject digest is the file's SHA-256.
- Smoke tests: `loom project --scan-model-usage` exits 0 and records a
  `hasDataFile` relationship from the script to the model with the comment
  `read access`; without the option it prints the `INFO:` hint. `loom model`
  exits 0 on both files and the SBOMs pass `spdx3-validate`. A registry of
  version 3 is refused (exit 1, no SBOM written, registry unchanged, with
  and without `--update-id-registry`); `loom id generate -e
  'foo==1.0:software_Package'` exits 2.
- The usage scan on a 150,000-link method chain, run on Python 3.10 with
  `ulimit -s 2048` through both `python -I -m pitloom` and `loom`, exits 0
  with empty stderr and the other usage relationships intact (the crash
  #432 fixed).

### Not run or noted

- The sdist holds two dangling symlinks, `CLAUDE.md` and `GEMINI.md`, which
  point at `AGENTS.md`; the sdist excludes `AGENTS.md`. The same holds for
  0.22.0. A separate PR, not yet merged, leaves `AGENTS.md`, `CLAUDE.md` and
  `GEMINI.md` out of both the sdist and the wheel.
- A flat-layout project (no package directory named for the project) gives
  setuptools and Hatchling discovery warnings that carry no `[code]`; they
  are not yet catalogued (catalogue PR 12; see
  [Messages, catalogue and
  provenance](../design/known-bugs/messages-and-provenance.md)).
- The first release-gate run failed on an upstream Savannah HTTP 500; a re-run
  passed. Recorded in the ledger with a mitigation (see
  [Process, tooling and release
  checks](../design/known-bugs/process-tooling-and-release-checks.md)).
- Merkle root recomputation was not run; the GitHub Action was checked by
  reading `action.yml` at the tag only.

## Verification of v0.22.0 (2026-11-02)

Same method as
[v0.20.0](wheel-sbom-verification-history.md#verification-of-v0200-2026-10-05),
against `https://pypi.org/pypi/pitloom/0.22.0/json` (uploaded 2026-10-30
17:05 UTC, neither file yanked). Run on 2026-11-02 from the PyPI files only:
the GitHub Release assets, attestations and the GitHub Action check were not
part of this pass.

### Method

- Wheel and sdist downloaded with `curl` from the API's URLs into an empty
  directory; `sha256sum` against the API digests.
- `RECORD` checked by a small script run with `python -I`: every row's
  hash and size against the member's bytes, and rows against members both
  ways. The embedded SBOM's `software_File` hashes recomputed from the
  wheel's bytes and compared with the SBOM and with `RECORD`.
- Fresh Python 3.13 venv, `pip install
  "pitloom[ai,content-type,validate]==0.22.0"`; `loom --version`,
  `loom verify-wheel <whl> --sbom-filename
  pitloom-0.22.0.spdx3.json --fail-on-mismatch`, `loom validate-wheel
  <whl>`, `spdx3-validate --json` 0.0.7 on the extracted SBOM and
  `scripts/check_sbom_license.py --license Apache-2.0` on the SBOM and
  on the wheel.
- Smoke tests with the installed release on tiny temporary projects (one
  dependency, a Git LFS pointer as `LICENSE`, an ID registry of version 3);
  `licenseid update --source packaged` with `HOME` and `XDG_DATA_HOME` in a
  scratch directory.
- The sdist's file list against `git ls-tree -r v0.22.0`.

### Findings

- PyPI SHA-256: wheel `72bdadb8...14766265` (1,082,575 bytes), sdist
  `b35d1544...f9e9e55` (10,351,449 bytes); the downloads match.
  `requires_dist` has `licenseid<0.7,>=0.6.0`; `provides_extra` is `ai`,
  `build`, `content-type`, `fasttext`, `gguf`, `hdf5`, `huggingface-hub`,
  `numpy`, `onnx`, `pytorch`, `safetensors`, `validate`; `requires_python`
  `>=3.10`.
- The wheel has 331 members; the one SBOM is
  `pitloom-0.22.0.dist-info/sboms/pitloom-0.22.0.spdx3.json` (`016dd633...
  f4b40024`). `RECORD`: 331 rows, 0 bad hashes or sizes, none missing, none
  extra. `METADATA`: `Version: 0.22.0`, `License-Expression: Apache-2.0`.
- `verify-wheel` OK, `validate-wheel` valid; `spdx3-validate` schema and
  SHACL pass; `check_sbom_license.py` passes on the extracted SBOM
  (declared and concluded `Apache-2.0`).
- 343 `software_File`: the 325 payload files plus 18 directories (the 18
  without a hash); no `.dist-info` member listed. 0 hash mismatches against
  the bytes, 0 against `RECORD`.
- Main package `pkg:pypi/pitloom@0.22.0`, version `0.22.0`; spec 3.0.1;
  1,516 graph elements.
- A fresh venv reports `Pitloom 0.22.0`; `licenseid` 0.6.0 was resolved.
- `loom project` on the tiny project exits 0 and its SBOM passes
  `spdx3-validate`. A file `tiny/weights.bin` that is a Git LFS pointer
  gives one `WARNING: FILE=tiny/weights.bin: Git LFS pointer, content not
  read; run 'git lfs pull' for the content [lfs-pointer]` and is listed by
  the pointer's `oid` with the size in the hash comment. `loom generate` of
  a pointer `.gguf` gives the documented `ERROR: ... header is a Git LFS
  pointer, content not pulled (oid sha256:..., size 11357 bytes); run 'git
  lfs pull' [lfs-pointer]`.
- A registry of version 3 with `--id-registry`, with and without
  `--update-id-registry`: exit 1, `ERROR: SBOM generation failed: ID
  registry file '...': version 3, expected 4 (no migration support --
  delete it and re-run ...)`, with the two `loom id` commands named; no
  SBOM written and the registry's SHA-256 unchanged.
- `licenseid update --source packaged` works offline (SPDX list 3.29.0, 740
  licences); its one `WARNING: popularity.csv: missing` is expected without
  the ranking data. `licenseid` has no `--version` option.

### Not run or noted

- The sdist holds the 1,366 files of the tag that `pyproject.toml` does
  not exclude plus `PKG-INFO`; the 434 tag files left out are
  `working-docs/`, `.github/`, `.claude-plugin/`, large test fixtures and
  tooling dotfiles. No `.env` or key material; `docs/pitloom-etsi-2026.key`
  is a Keynote archive (a ZIP), not a private key. The sdist is 10 MB mainly
  because `docs/` ships two posters (7 MB) and that Keynote file (0.7 MB).
- A project whose `license = {file = "LICENSE"}` names a Git LFS pointer
  records a `simplelicensing_SimpleLicensingText` whose text is the
  file name `LICENSE` (an unpulled pointer); a real licence file gives its
  text. Whether a file name should stand as licence text is for the
  maintainer to decide.
- Merkle root recomputation, the GitHub Release assets, attestations and
  Sigstore bundles, and the GitHub Action check were not run.
- The `WARNING: Hatchling file discovery failed ...` line for a project
  whose name matches no package directory has no `[code]` (not catalogued).

## Conclusion

The wheel-embedded SBOMs are valid per SPDX 3.0.1 (schema + SHACL), correctly
located per PEP 770, and every field is present and correct in the actual
published artefacts -- confirmed against the real files, not just against
source or local test fixtures. Holds across releases spanning significant
internal redesigns (v0.9.0 through v0.13.3): the CLI/API rewrite, the
provenance-as-Annotation system, the native SPDX3 backfill, and the
default-SBOM-filename change (`sbom.spdx3.json` ->
`<name>-<version>.spdx3.json`, PR #130) all landed without breaking this
guarantee.
