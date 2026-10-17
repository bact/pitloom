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
| after B2, B1, B3, honesty fix | `9b70174` | gguf | 16 | 22 | 18 | 25 | 42.1% |
| after B2, B1, B3, honesty fix | `9b70174` | safetensors | 13 | 25 | 18 | 25 | 34.2% |
| after B2, B1, B3, honesty fix | `9b70174` | onnx | 22 | 16 | 18 | 25 | 57.9% |
| after B2, B1, B3, honesty fix | `9b70174` | hub | 27 | 29 | 0 | 25 | 48.2% |
| after B2, B1, B3, honesty fix | `9b70174` | library | 26 | 30 | 0 | 25 | 46.4% |

Coverage is present / (present + missing).

## Honesty

The table only ever records what the SBOM states. The guards that hold this:
a `present` rule rests on a real property on the right element; no property a
rule reads holds a placeholder; an edit that removes a value turns the rule
`missing`; an unreadable file fails the test rather than reading as all
`missing`. A flip that rests on a weaker form (a generic Agent, a Hub card's
claim) is said so in the log entry. What Pitloom cannot extract, tell apart or
record: [g7-honesty-and-non-recordable.md](../design/g7-honesty-and-non-recordable.md).

## Increment log

Add one paragraph per increment: the rules that flipped, what was left to the
`sbom-enrich` skill and why.

**B2, identifiers (2026-10-17).** `MDL-002` flipped to `present` in all five
scenarios and `DP-004` in `hub` and `library`. A Hub model gets
`pkg:huggingface/<owner>/<name>[@<commit>]` (the commit only when the Hub gave
a 40-digit hash); a hashed model file gets
`pkg:generic/<file>?checksum=sha256:<digest>`, derived from the digest already
computed; a dataset with an http(s) download URL gets
`pkg:generic/<name>?download_url=<url>` (the `huggingface` type covers models
only). Left absent, silently: a model with no file name and no hub id, a
dataset without an http(s) URL. A gitoid `contentIdentifier` needs a second
pass over the file and was not added. The 0.20.2 history file holds the
before; `0.20.3-dev.json` the after. The CHANGELOG entry waits for a PR number
(`tests/test_changelog.py` requires one).

**Honesty fix, model inputs (2026-10-17).** A model's `inputs`/`outputs` are
now only what its format states as a signature. Safetensors tensor keys, NumPy
arrays and PT2 parameters, buffers and constants were written as inputs and
reached `ai_informationAboutApplication`; they no longer are (details and
the readers' new behaviour: [g7-honesty-and-non-recordable.md](../design/g7-honesty-and-non-recordable.md)).
`safetensors` lost six `present` cells, MDL-006, MDL-006.4, MDL-010, MDL-010.4,
SLP-008 and SLP-008.3, so its coverage went down (50.0% to 34.2%): the earlier
figure was wrong. `onnx` keeps the same cells, which rest on its real signature
and on the checker's close-match mapping, not on any intended-use statement.

**B3, Hub revision (2026-10-17).** `MDL-003`, `MDL-004`, `SLP-004` and
`SLP-005` are `present` in `hub`. A Hub model's version is its 40-digit commit
hash and its `releaseTime` the Hub's last-modified time (the commit time of
that revision), parsed with the SBOM's other times (`parse_iso_datetime`; a
naive time is UTC, a time that is not ISO 8601 is left out with a warning).
The hash feeds the document identity, so a new revision of a Hub model is a new
document namespace. The scenario's mocked `model_info` now carries `sha` and
`last_modified`, as the real Hub's does. Model files carry no time and stay
`missing`. Not added: a Hub `created_at` (the repository's creation, not the
revision's).

**B1, dataset licence (2026-10-17).** `DP-010` is `present` in `library`.
A dataset's licence goes through the same builder as a model's
(`add_license_relationships`): declared, or concluded for a third-party record;
an SPDX expression, a URL and free text are kept as they are read. `hub` stays
`missing`: Hub dataset references carry no licence, and no reader (Croissant is
library-only) feeds one into a model SBOM yet. That reader is the next step
for `DP-010`, with the `loom` SDK (B7).

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
