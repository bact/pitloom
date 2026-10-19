---
Created: 2026-10-17
Last-Modified: 2026-10-18
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
The same scenarios are checked against CISA 2026 (`cisa2026`) and FSCT 2024
(`fsct3`, the checker's id), each with a table of its own.

## What runs

- `tests/conformance/` builds one SBOM per scenario (`gguf`, `safetensors`,
  `onnx`, `numpy`, `fasttext` from the fixture models; `hub`, a mocked Hugging Face model with a
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
- `test_standard_outcomes.py` holds `cisa2026-expected.tsv`,
  `fsct3-expected.tsv` and `bsi-expected.tsv` the same way: every rule listed
  with its provision, `out-of-scope` only for the `catalogue-only` rules, any
  changed cell fails. Every standard judges the datasets and
  models a component reaches by `trainedOn` and `testedOn` (since checker
  `151460c`; before, only CISA 2026, FSCT 2024 and G7).
- `test_g7ai_surfaces.py` runs one input through the library, `loom model`,
  `loom generate`, `loom project`, `loom wheel` and the Hatchling hook, and
  requires the same outcome for every rule of all four standards, the same
  element types and property names, and the same names, versions, package
  URLs and hash values. The hook may add `builtTime`.

Three project scenarios (`proj-hatchling`, `proj-setuptools`, `proj-poetry`)
build the same small project, with one Safetensors model, on each build
backend; a test requires the same G7 outcomes from all three. Setuptools ships
a data file only when `package-data` says so, so its project declares it; a
test shows that without it the model is not described (nothing is claimed that
the distribution would not ship). A project that ships a model has
a root of its own, so the checker reads its System-level properties (`SLP`)
from that root: only an SBOM whose one root is a single model is judged by the
model (`systemJudgedByModel`, in the report as the model's name; narrowed on
2026-10-18, after first judging a project by the model it ships). The model of a bare Safetensors file has
no producer, version or time, so those cells stay `missing` even though the
project names an author: Pitloom does not copy the project's author onto the
model, and the checker does not either.

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

`python scripts/g7_coverage_report.py [--standard g7ai|cisa2026|fsct3]` prints
the counts per scenario and cluster, and `--compare PREVIOUS CURRENT` lists the
rules that flipped and warns when the standard, the checker, the mapping or the
rule count changed (a series break). Each increment adds
`g7-coverage-history/<pitloom version>.json` (G7) or
`<standard>-<pitloom version>.json`. The figure is "meets the checker's
reading", not "compliant"; unchecked rules are not counted as missing.

| Pitloom | Checker | Scenario | Present | Missing | Not applicable | Unchecked | Coverage |
|---|---|---|---|---|---|---|---|
| 0.20.2 (baseline) | `9b70174` | gguf | 15 | 23 | 18 | 25 | 39.5% |
| 0.20.2 (baseline) | `9b70174` | safetensors | 18 | 20 | 18 | 25 | 47.4% |
| 0.20.2 (baseline) | `9b70174` | onnx | 21 | 17 | 18 | 25 | 55.3% |
| 0.20.2 (baseline) | `9b70174` | hub | 21 | 35 | 0 | 25 | 37.5% |
| 0.20.2 (baseline) | `9b70174` | library | 23 | 33 | 0 | 25 | 41.1% |
| 0.20.3-dev | `151460c` | gguf | 16 | 22 | 18 | 25 | 42.1% |
| 0.20.3-dev | `151460c` | safetensors | 13 | 25 | 18 | 25 | 34.2% |
| 0.20.3-dev | `151460c` | onnx | 22 | 16 | 18 | 25 | 57.9% |
| 0.20.3-dev | `151460c` | numpy | 15 | 23 | 18 | 25 | 39.5% |
| 0.20.3-dev | `151460c` | fasttext | 23 | 15 | 18 | 25 | 60.5% |
| 0.20.3-dev | `151460c` | hub | 28 | 28 | 0 | 25 | 50.0% |
| 0.20.3-dev | `151460c` | library | 26 | 30 | 0 | 25 | 46.4% |
| 0.20.3-dev | `151460c` | proj-hatchling | 15 | 23 | 18 | 25 | 39.5% |
| 0.20.3-dev | `151460c` | proj-setuptools | 15 | 23 | 18 | 25 | 39.5% |
| 0.20.3-dev | `151460c` | proj-poetry | 15 | 23 | 18 | 25 | 39.5% |

Coverage is present / (present + missing).

CISA 2026 (23 rules, 9 unchecked) at `151460c`: 71.4% for each model file
scenario, `hub` and `library`, 78.6% for each project. FSCT 2024 (13 rules,
3 unchecked): 50.0% for each model file scenario, 60.0% for `hub`, `library`
and each project. G7 `hub` at `151460c` after reader 3: 28 present, 28
missing, 50.0%.

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

**Demo scenarios (2026-10-18).** `numpy` and `fasttext` (tier 1) and the three
project scenarios were added; the System cells of the projects are judged by
the model (checker `b7785f4`; narrowed the same day, below). A fastText model's `ai_domain` is derived from
the format, not stated in the file; its provenance now says so
(`Method: derived_from_format`).

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

**Judge-by-model narrowed (2026-10-18).** Only an SBOM whose one root is a
single AI model is judged by that model (`systemJudgedByModel`). A project
that ships a model has its own root, so the projects' System cells are read
from the project's package and most are `missing` (SLP 22%).

**CISA 2026 and FSCT 2024 (2026-10-18).** The same scenarios are checked with
`cisa2026` and `fsct3`; tables `cisa2026-expected.tsv` and `fsct3-expected.tsv`,
reports `cisa2026-0.20.3-dev.json` and `fsct3-0.20.3-dev.json`. The component
rules of both reach the datasets and models linked by `trainedOn` and
`testedOn`, so a training dataset with no hash or version is reported. The
CISA identifier rule needs a real identifier (`software_packageUrl`,
`externalIdentifier` or `software_contentIdentifier`), not the `spdxId`;
every package in every scenario carries a package URL.

**BSI TR-03183-2 v2.1 (2026-10-18).** Checked with `bsi` (rule-based, 20
elements, 16 checked); table `bsi-expected.tsv`, report
`bsi-0.20.3-dev.json`. Checker `a877b4c` did not follow
`trainedOn`/`testedOn` for BSI; `151460c` follows them for every standard, so
the `hub` and `library` datasets are judged: version `missing` for `hub`,
SHA-512 `missing` for `library`, and the dataset's download location makes
COMP-012 apply and pass. The SHA-512 hash is `present` for model files,
`missing` for a Hugging Face model, the library-built model and every project
(a SHA-256 Merkle root; no SHA-512 source for dependencies or datasets); the creator rules
are `missing` everywhere because Pitloom's creator is a software agent.

**SHA-512 (2026-10-18).** Every file Pitloom reads and describes gets its
SHA-512 beside its SHA-256, from one read (`pitloom.core.file_hash`): model
files, project, wheel and sdist file elements, `loom` model, dataset and
script files, and bundled (phantom) libraries. A dependency's hash stays the
SHA-256 its lock file gives, and a Merkle root stays SHA-256 only.

**Reader 3, Hub dataset cards (2026-10-18).** Each dataset a Hub model card
lists is filled from its own Hub repository (licence, description, keywords,
version, owner; `extract/remote/huggingface_dataset.py`). The `hub` scenario's
mocked `c4` dataset card states `ODC-By-1.0` and its repository a commit
hash. Flipped to `present` in `hub`: G7 `DP-010` (dataset licence), CISA 2026
`COMP-006` (licence: `hasDeclaredLicense`, which this checker accepts) and
`COMP-008` (version), FSCT `COMP-002` (version), BSI `COMP-003` (version);
the version is the dataset revision's commit hash, as for a Hub model, a
weaker form than a release version. Nothing else moved. A second dataset
without a licence was tried in the scenario: every component rule then stays
`missing` (each dataset must have the property), so it was left out; the
tests cover that case. All four history files were regenerated; their headers
now name checker `151460c`.

## Database-less builds

`licenseid` canonicalises licence IDs when its database exists (CI builds it)
and changes the SBOM text. The scenarios build as if it were absent
(`g7ai_shared.without_licence_database`), so the table is the same on a
laptop and in CI.

## Rejected

- Running the checker as a subprocess: untyped, not counted by coverage, and a
  subprocess bypasses the socket block.
- Keeping `network` on every validation test: it hid the offline guarantee and
  made the release gate download the schema for each test.

## History files and the checker commit

Each history file's header names the checker commit it was made with: the
0.20.2 baseline `9b701748`; the four `0.20.3-dev` files `151460c`, the pinned
commit, since reader 3. A history file named
`0.20.3-dev` records `pitloom 0.20.2`, the installed version when it was made.
