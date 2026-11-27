---
Created: 2026-07-06
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Wheel-embedded SBOM verification

See also:
[wheel-sbom-verification-history.md](wheel-sbom-verification-history.md)
(the verifications of v0.9.0 to v0.22.1).

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

## Verification of v0.25.0 (2026-11-27)

A shorter pass than v0.23.3 below, the same day as the release, against
`https://pypi.org/pypi/pitloom/0.25.0/json` (wheel uploaded 2026-11-27
13:57:46 UTC, sdist 13:57:48 UTC). The GitHub Release (not a draft) was
published at 13:55:41 UTC; the tag `v0.25.0` is lightweight and points at
`1d5979d9` (the merge of #564). v0.24.0 has no entry here.

| File | Bytes | SHA-256 |
| - | -: | - |
| `pitloom-0.25.0-py3-none-any.whl` | 1,698,363 | `2a337a127c75fc841fe2091017cd6fbbdbaf89793e726fd5af763a58df634c5f` |
| `pitloom-0.25.0.tar.gz` | 11,922,581 | `1598d3b8e16871a90e618c440d052ea7b9788c52e65a10f5f47d5031a6a8cc6d` |
| `pitloom-0.25.0.spdx3.json` (Release asset) | 1,550,070 | `fa7a90dfa041a84297612b6488f5ce4e06fa82c2b142ae3ba4ab84c7b6301f9d` |

### Method

- Downloads from the JSON API's URLs; digests compared with the JSON API,
  the JSON simple index and the Release assets. `RECORD` and the embedded
  SBOM's `software_File` hashes recomputed from the wheel's bytes by a
  script run with `python -I`; the wheel payload and the sdist compared with
  `git archive v0.25.0`.
- Fresh venv on Python 3.13.12 with `pitloom[ai,content-type,validate]==0.25.0`
  and sigstore 4.6.0: `verify-wheel --fail-on-mismatch`, `validate-wheel`,
  `spdx3-validate` 0.0.7, `scripts/check_sbom_license.py --license
  Apache-2.0` at the tag, `python -m sigstore verify github` and `gh
  attestation verify` (identity and `--source-ref` of `refs/tags/v0.25.0`),
  PyPI's integrity API. A second venv on Python 3.10 with `pitloom==0.25.0`.
- Smoke tests, `HOME` in a scratch directory: a tiny Hatchling project
  (`project`, twice, `SOURCE_DATE_EPOCH` pinned), without and with a
  `licenseid update --source packaged` database; the #561 changes (a Hub id
  that does not exist, a host-only Git URL); an empty path argument.

### Findings

- Digests agree in all three sources; the wheel and the sdist are
  byte-identical to the Release assets, and the standalone SBOM to the
  wheel's member. Six assets: three files, each with a `.sigstore.json`.
- `requires_dist` has `licenseid<0.10,>=0.9.4`; `requires_python` `>=3.10`;
  `License-Expression: Apache-2.0`; 12 extras; entry points `loom`,
  `pitloom` and the `hatch` plugin. `METADATA` equals the sdist's
  `PKG-INFO`.
- Wheel: 535 members, one SBOM; `RECORD`: 535 rows, 0 bad, none missing,
  none extra; the payload equals `src/pitloom` of the tag.
- sdist: 2,035 files, all from the tag's 2,618 plus `PKG-INFO`; no byte
  differences; no `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` or `.env`.
- Embedded SBOM: SPDX 3.0.1, 2,334 graph elements; 550 `software_File` (21
  without a hash), 0 hash mismatches; `pkg:pypi/pitloom@0.25.0`,
  `hasDeclaredLicense` relationships, `Tool` `Pitloom`. All validators pass.
- Signatures: `sigstore verify github` and `gh attestation verify` exit 0
  for the three files. PEP 740: publisher `bact/pitloom`,
  `pypi-publish.yml`, no environment; one attestation for the wheel.
- Every workflow run on `1d5979d9` succeeded, `Publish to PyPI` included.
- Installs succeed, `uv pip check` is clean, `licenseid` 0.9.4 resolved.
  The tiny project's SBOM is byte-identical across two runs and between
  Python 3.10 and 3.13, valid under `spdx3-validate` and `loom fragment
  validate`; with no database the `[license-db-missing]` `INFO:` line is
  printed once.
- #561: an unknown Hub id gives `ERROR: ... [input-not-found/hub]`, exit 1,
  no SBOM; `loom project ''` gives `[input-not-found]`, exit 1.
- `loom model https://github.com/` is read as repository
  `https://github.com` (`[target-ambiguous/git-page]`) and cloned; `git`
  refuses it (`[git-repository-unusable]`, exit 1, no SBOM). A host with no
  repository path is not refused before the network. Known-bugs
  ledger entry added the same day
  ([remote-sources-lfs-and-datasets.md](../design/known-bugs/remote-sources-lfs-and-datasets.md)).

### Not run or noted

- No workflow run of the Action (the `Action self-test (install)` run on
  the merge commit passed); no Merkle root recomputation; no sdist rebuild.
- The SBOM's `created` (13:56:04 UTC) is the build's clock, as for 0.23.3.
- The local `v0.24.0` tag (`cbf44b05`, merge of #475) differs from the
  remote one (`fd063903`, merge of #476): `git fetch --tags` refused to
  clobber it. The remote is authoritative; the local tag was reset to
  `fd063903` the same day.

## Verification of v0.23.3 (2026-11-08)

Same method as v0.23.1 below, against
`https://pypi.org/pypi/pitloom/0.23.3/json` (wheel uploaded 2026-11-08
19:47:42 UTC, sdist 19:47:44 UTC, neither file yanked). The GitHub Release
(not a prerelease) was published at 19:45:43 UTC; the tag `v0.23.3` is
lightweight and points at `3b993e16` (the merge of #461). v0.23.2 (#460,
published 06:56 UTC the same day) has no entry here.

| File | Bytes | SHA-256 |
| - | -: | - |
| `pitloom-0.23.3-py3-none-any.whl` | 1,131,583 | `681ba5b74cf65bf0396fd01801a07b76856ec20e5432a9670487b12e5b1f369b` |
| `pitloom-0.23.3.tar.gz` | 10,467,363 | `d9d002dd8c8d8f8bcbc3c2b0415e5fb687e521baa728b6881e985dd8bb5ec81a` |
| `pitloom-0.23.3.spdx3.json` (Release asset) | 1,045,622 | `8d19acd0fccf0df06f6f5da2121c7d9f3da7c707a5764f427b73a9f2ce5e14b5` |

### Method

- As for v0.23.1: downloads against the API digests and the six Release
  assets, `RECORD` and the wheel's payload against `git archive v0.23.3`, the
  sdist against the same archive, `verify-wheel`, `validate-wheel`, `loom
  fragment validate` and `spdx3-validate` 0.0.7 on the standalone SBOM,
  `scripts/check_sbom_license.py` at the tag, `gh attestation verify`, `python
  -m sigstore verify github` (sigstore 4.5.1, with `--sha` and `--trigger
  release`) and PyPI's integrity API.
- Installs of `pitloom==0.23.3` in fresh venvs on Python 3.10.20 and 3.14.6,
  `HOME` in a scratch directory, and dry-run installs with `licenseid==0.8.0`
  and `0.9.0`. The v0.23.1 smoke tests, plus the 0.23.3 changes (#461):
  `license = "https://www.apache.org/licenses/LICENSE-2.0"`, `license =
  "MIT\u200b"` (a trailing zero-width space), a directory dataset with a card
  (`loom.add_dataset`) holding `license: other`, `license_name: apache-2.0`
  and the Apache link, and the same card without the name. Then each
  project, plus one with only a `LICENSE` file and one with `license =
  "MIT"`, against a database built by `licenseid update --source packaged` of
  LicenseID 0.7.3 (build v3), a fresh copy per run.
- The Action: `action.yml` and `scripts/action/pitloom-install.sh` read at the
  tag; the install script run with a stub `python -m pip`.

### Findings

- The downloads match the PyPI digests; the wheel and the sdist are
  byte-identical to the Release assets, and the standalone SBOM to the
  wheel's member. Six assets: three files, each with a `.sigstore.json`.
  The notes list #461 only, which is the only PR since v0.23.2.
- `requires_dist` has `licenseid<0.9,>=0.8.1`; the dry runs fail with
  `ResolutionImpossible` (0.8.0) and no matching distribution (0.9.0).
  `provides_extra` unchanged; `requires_python` `>=3.10`;
  `License-Expression: Apache-2.0`; entry points `loom`, `pitloom` and the
  `hatch` plugin.
- Wheel: 352 members, one SBOM; `RECORD`: 352 rows, 0 bad, none missing,
  none extra; the 346 payload files equal `src/` of the tag.
- sdist: 1,423 files, the tag's 1,904 minus the 482 excluded, plus
  `PKG-INFO` (equal to `METADATA`); no byte differences. Neither the sdist
  nor the wheel has `AGENTS.md`, `CLAUDE.md` or `GEMINI.md`.
- Embedded SBOM: SPDX 3.0.1, 1,595 graph elements, `Apache-2.0` declared and
  concluded; 364 `software_File` (346 payload plus 18 directories), 0 hash
  mismatches. `Tool` `Pitloom` (`pkg:pypi/pitloom@0.23.3`); `licenseid`
  0.8.1 listed as a package, and licence provenance names `licenseid==0.8.1`
  only. All validators pass.
- `gh attestation verify` passes for the three files (one SLSA v1
  attestation, source digest `3b993e16`) and fails with `--source-ref
  refs/tags/v0.23.1`; `sigstore verify github` passes for the three, and
  fails on a wrong bundle or identity. PEP 740: publisher `bact/pitloom`,
  `pypi-publish.yml`, no environment; one attestation per file.
- Installs succeed, `pip check` is clean, `licenseid` 0.8.1 resolved.
  Smoke tests give the same results on both Pythons, and the SBOMs compared
  across them are byte-identical: `sampleproject-hatchling` twice, the
  version 3 registry (`ERROR`, exit 1, no SBOM, file unchanged), the broken
  `onnx` (`[library-unusable]`), `Apache2` read as `Apache-2.0`.
- The 0.23.1 fixes hold: `MIT licensed.` prints no `too few words` line
  (with or without `-v`, with or without a 0.8.1 database) and records no
  licence; `New BSD` reads as `BSD-3-Clause` (`alias_name`), and with no
  database no longer prints the `cannot be used` warning (#458).
- The 0.23.3 changes: the URL gives `Apache-2.0` with `INFO:
  FIELD=project.license LICENSE='https://www.apache.org/licenses/LICENSE-2.0':
  read as Apache-2.0 (license_url)`; the zero-width space gives `MIT` with
  `INFO: ... LICENSE='MIT\u200b': read as MIT (trim)`; the card gives
  `Apache-2.0` as a licence expression, and the card with only the link
  gives `Apache-2.0` too (`license_url`).
- With the LicenseID 0.7.3 database, only the `LICENSE`-only project prints
  `WARNING: licenseid: database: build v3 outdated: current v4; run
  'licenseid update'`, and still records `Apache-2.0`
  (`licenseid_detection`); the URL, zero-width space and `MIT` projects
  print no warning. The database file is left unchanged. After `licenseid
  update` of 0.8.1 the warning is gone and the SBOM is byte-identical.
- The Action with an empty `pitloom-version` runs `pip install
  pitloom==0.23.3`, the version `check_version_consistency.py` reads at the
  tag; a bare version and a specifier pass through as before.

### Not run or noted

- The release was published while the `Unit tests` run on the merge commit
  was still going (it passed at 19:51 UTC); the publish workflow's own
  network-dependent test job passed before the upload.
- `loom model` on the GGUF file warns `[library-missing]`: the install has
  no `gguf` extra.
- The SBOM's `created` (19:46:03 UTC) is the build's clock: the publish
  workflow sets no `SOURCE_DATE_EPOCH`, as for 0.23.1. No rebuild compared.
- No workflow run of the Action; no Merkle root recomputation.

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

Same method as [v0.22.1](wheel-sbom-verification-history.md#verification-of-v0221-2026-11-03), against
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
