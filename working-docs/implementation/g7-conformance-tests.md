---
Created: 2026-10-17
Last-Modified: 2026-10-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# G7 conformance tests

See also: [g7-ai-sbom-coverage.md](../design/g7-ai-sbom-coverage.md) (what G7
needs and the order of work), [roadmap.md](../design/roadmap.md).

Pitloom's SBOMs are checked against the G7 SBOM for AI minimum elements by
`ntia-conformance-checker` (`-c g7ai`, SPDX 3.0 only), in the test suite. The
tests turn each G7 field Pitloom adds into a table cell that cannot slip back.

## What runs

- `tests/conformance/` builds one SBOM per scenario (`gguf`, `safetensors`,
  `onnx` from the fixture models; `hub`, a mocked Hugging Face model with a
  dataset; `library`, a model with a licensed dataset built through the
  assembler, since no reader feeds a dataset licence into a model SBOM yet), validates it offline, and runs the checker in-process.
- `tests/fixtures/conformance/g7ai-expected.tsv` holds the expected outcome of
  all 81 rules per scenario. The test fails on any changed cell: a `present` that is no longer
  `present` is reported as a regression, a cell that became `present` as an
  improvement (update the table in the same commit). `--write-expected`
  refuses to rewrite the table when a `present` cell would be lost, unless
  `--allow-regression` is given.
- Drift guards: the table lists exactly the checker's rules and provisions; the
  `out-of-scope` rows are the checker's `catalogue-only` rules; every `present`
  rule rests on a property in the SBOM; no property a rule reads holds a
  placeholder (`NOASSERTION`, empty).
- Adversarial cases edit a generated SBOM (drop the hash or producer, blank the
  name, unlink the dataset, empty the root) and expect the rule to turn
  `missing`. A truncated file fails the test instead of reading as "all
  missing" (the checker only logs a parse failure).
- `test_g7ai_sssom_gaps.py` pins the elements the checker does not check
  although Pitloom writes the property the G7 -> SPDX mapping assigns to them
  (`EMITTED_BUT_UNCHECKED`). Property level only.

## Offline validation

`tests/_spdx3_validate.py` calls `spdx3_validate.validate(model_dir=...)`
against `tests/fixtures/spdx-model/v3.0.1/` (SPDX 3.0.1 context, SHACL model
and JSON schema, Community-Spec-1.0). The socket block in `tests/conftest.py`
then proves no download happens, so those tests carry no `network` marker. The
release gate keeps two network tests: the default (downloading) validator
path, and `test_network_spdx_model_snapshot.py`, which fails when spdx.org
differs from the snapshot (`scripts/refresh_spdx_model_snapshot.py` refreshes
it).

The `conformance` dependency group pins the checker (not on PyPI with `g7ai`)
and the `spdx3-validate` build with `model_dir` (PR JPEWdev/spdx3-validate#13)
by commit. The `spdx3-validate` build still reports 0.0.7, a version on PyPI, so pip
keeps an old install; `test_conformance_pins.py` compares the installed
commits with the pins. The checker commit is also pinned in `lumina`
(`backend/requirements.txt`); keep the two equal.

## Coverage history

`python scripts/g7_coverage_report.py` prints the counts per scenario and G7
cluster, and `--compare PREVIOUS CURRENT` lists the rules that flipped and warns
when the checker or the mapping changed (a series break). Each increment adds
`g7-coverage-history/<pitloom version>.json`. The figure is "meets the checker's
reading of G7", not "G7 compliant"; unchecked rules are not counted as missing.

| Pitloom | Checker | Scenario | Present | Missing | Not applicable | Unchecked | Coverage |
|---|---|---|---|---|---|---|---|
| 0.20.2 (baseline) | `9b70174` | gguf | 15 | 23 | 18 | 25 | 39.5% |
| 0.20.2 (baseline) | `9b70174` | safetensors | 18 | 20 | 18 | 25 | 47.4% |
| 0.20.2 (baseline) | `9b70174` | onnx | 21 | 17 | 18 | 25 | 55.3% |
| 0.20.2 (baseline) | `9b70174` | hub | 21 | 35 | 0 | 25 | 37.5% |
| 0.20.2 (baseline) | `9b70174` | library | 23 | 33 | 0 | 25 | 41.1% |

Coverage is present / (present + missing).

## Increment log

Add one paragraph per increment: the rules that flipped, what was left to the
`sbom-enrich` skill and why.

## Database-less builds

`licenseid` canonicalises licence IDs when its database exists (CI builds it)
and changes the SBOM text. The scenarios build as if it were absent
(`g7ai_shared._without_licence_database`), so the table is the same on a
laptop and in CI.

## Rejected

- Running the checker as a subprocess: untyped, not counted by coverage, and a
  subprocess bypasses the socket block.
- Keeping `network` on every validation test: it hid the offline guarantee and
  made the release gate download the schema for each test.
