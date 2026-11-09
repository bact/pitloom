---
Created: 2026-09-30
Last-Modified: 2026-11-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap -- completed items

See also: [roadmap.md](../design/roadmap.md) (open items).

Implementation detail for each item below (design decisions, function
names, PR links) lives in `working-docs/implementation/` where noted --
read the code/that doc for current state rather than this list, which
is not kept in sync with post-ship changes.

- [x] SPDX 3.0 SBOM generation (JSON-LD)
- [x] Hatchling metadata extraction (`pyproject.toml`)
- [x] Dependency tracking and SPDX relationship elements
- [x] Format-neutral internal representation
  (`DocumentModel` -- see [format-neutral-representation.md](../design/format-neutral-representation.md))
- [x] AI/ML package profiles
  (`software_Package` with AI BOM profile, `dataset_DatasetPackage`)
- [x] PEP 770 support (`.dist-info/sboms/` via `build_data["sbom_files"]`)
- [x] Hatchling build hook (`pitloom.plugins.hatch`) with fragment merging
- [x] ML tracking SDK (`pitloom.loom` -- context manager / decorator)
- [x] Metadata provenance tracking (per-field source attribution)
- [x] CLI (`loom`) with verbose mode and creator info options
- [x] Setuptools support -- initial implementation
  (`src/pitloom/extract/project/setuptools.py`; `pyproject.toml` > `setup.cfg` >
  `setup.py` conflict resolution)
- [x] Poetry support -- initial implementation
  (`src/pitloom/extract/project/poetry.py`; `read_pyproject()` falls back to
  `[tool.poetry]` when `[project]` is absent, merges both when present)
- [x] **PDM-backend and Flit-core support** -- metadata extraction and
  wheel file discovery for both backends. See
  [backend-file-discovery-validation-flit-pdm.md](backend-file-discovery-validation-flit-pdm.md)'s
  Flit-core/PDM-backend round.
- [x] **Multiple creators / tools per `CreationInfo` record** -- `Creator`/
  `Tool` dataclasses, repeatable `--creator-name`/`--creation-tool`,
  array-of-tables config. See [creation-metadata.md](../../docs/creation-metadata.md).
- [x] **SPDX license expression normalisation and declared-vs-detected
  conflict detection (G2)** -- via [`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license).
  See [multi-source-conflict.md](provenance/multi-source-conflict.md)
  ([PR #121](https://github.com/bact/pitloom/pull/121)).
- [x] **`[project.license-files]` support** -- PEP 639's glob-list field
  for bundling multiple license files, each getting its own
  `software_File` element and `hasDeclaredLicense` relationship (PR #207).
  Later removed: an SBOM lists nothing under the wheel's own
  `.dist-info`. See
  [license-pipeline.md](license-pipeline.md#license-files-are-not-listed-pep-639).
- [x] **Auto-sync the Loom ID registry after SBOM generation** -- `loom
  project`/`wheel`/`env` harvest newly-minted ids back into the resolved
  registry after each run. See
  [id-registry-autosync.md](id-registry-autosync.md)
  ([PR #178](https://github.com/bact/pitloom/pull/178)).
- [x] **Lock/pin formats as a resolved-dependency source** -- `poetry.lock`,
  `pylock.toml` (PEP 751), `uv.lock`, `pdm.lock`, `Pipfile.lock`, and pinned
  `requirements.txt` feed `locked_dependencies` via one shared cascade
  ([#208](https://github.com/bact/pitloom/pull/208)). See
  [lock-file-cascade.md](lock-file-cascade.md).
- [x] **Explicit Loom ID registry** (declared only, one `ERROR:`, package
  ids pinned; #234, #235). See [id-registry-autosync.md](id-registry-autosync.md).
- [x] **Agent Skills portable across clients** (#235). See
  [skills-trigger-coverage.md](skills-trigger-coverage.md).
- [x] **Release SBOM licence guard** -- `pypi-publish.yml` fails unless
  the release SBOM (wheel + standalone) declares and concludes Apache-2.0
  (`scripts/check_sbom_license.py`); `embed-wheel` now emits the concluded
  licence (#243). See [release-checklist.md](release-checklist.md).
- [x] **PR-time SBOM licence check** -- `build.yml` runs
  `scripts/check_sbom_license.py` on every push/PR and no longer ignores
  `CITATION.cff`/`codemeta.json` (#248). See
  [release-checklist.md](release-checklist.md).

- [x] **GitHub Action** (composite `action.yml`) for any Python project.
  See [github-action.md](github-action.md),
  [docs/github-action.md](../../docs/github-action.md).
- [x] **AI-agent Skills** (`sbom-generate`, `sbom-enrich`, `sbom-validate`)
  and the **Claude Code plugin** bundling them. See
  [agent-skill.md](agent-skill.md), [claude-code-plugin.md](claude-code-plugin.md),
  [docs/agent-skills.md](../../docs/agent-skills.md).
- [x] **`loom verify-wheel` / `loom validate-wheel`** (#202). See
  [wheel-verification-commands.md](wheel-verification-commands.md).
- [x] **Backend-agnostic file discovery** (2026-09-15): static rescans for
  setuptools, Poetry, PDM-backend, Flit-core; `--allow-build` for the rest.
  See [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md),
  [docs/allow-build.md](../../docs/allow-build.md); open follow-ups:
  [non-hatchling-file-discovery-followups.md](../design/non-hatchling-file-discovery-followups.md).
- [x] **Dataset-to-model relationships** (`trainedOn`/`testedOn`) and
  **Croissant dataset size**. See [ai-dataset-linking.md](ai-dataset-linking.md).
- [x] **Sort-order audit** of the assemble/id-registry path. See
  [sort-order-canonicalization.md](sort-order-canonicalization.md).

## Shipped in 0.20.0 (2026-10-05)

Grouped by area; user-facing detail in `docs/`, decisions in the linked
implementation docs, every change in `CHANGELOG.md` `[0.20.0]`.

- [x] **`--allow-build` timeout and signal-safe builds** (#226, #250, #262)
  -- `--build-timeout`, the whole build tree killed on SIGTERM/Ctrl-C,
  `ERROR: interrupted`. See [allow-build-timeout.md](allow-build-timeout.md),
  [allow-build-termination.md](allow-build-termination.md),
  [docs/allow-build.md](../../docs/allow-build.md).
- [x] **One config cascade on every surface** (#227, #228, #231, #232,
  #247, #249, #280) -- `--config` everywhere, explicit config sources, an
  sdist reads its own config, typed `setup.cfg` keys, unknown keys warn.
  See [config-sources.md](config-sources.md),
  [sdist-own-config.md](sdist-own-config.md),
  [docs/configuration.md](../../docs/configuration.md).
- [x] **Explicit ID registry, collision-free ids** (#234, #235, #255
  design) -- declared only, one `ERROR:`, `loom id`, registry format v2.
  See [id-registry-autosync.md](id-registry-autosync.md).
- [x] **`loom env` reads `pipdeptree --json`** (#236). See
  [deployed-env-pipdeptree.md](deployed-env-pipdeptree.md).
- [x] **AI model scanning: candidates, order, usage gate, wheels, bounds,
  outcome parity** (#239, #240, #252, #263, #267, #270) -- one
  `ModelCandidate`, deterministic order, `--scan-model-usage` (off by
  default), wheel scanning with `--trust-wheel-model`, bounded readers,
  one entry per confirmed model on every surface. See
  [ai-model-scanning.md](ai-model-scanning.md),
  [ai-model-scan-bounds.md](ai-model-scan-bounds.md),
  [docs/ai-model-scan-limits.md](../../docs/ai-model-scan-limits.md).
- [x] **Unreadable files and directories warn, never vanish** (#244, #257,
  #258). See [file-scan-unreadable-file.md](file-scan-unreadable-file.md),
  [file-discovery-unlistable-dir.md](file-discovery-unlistable-dir.md).
- [x] **Archive member names and wheel identity the same on every OS**
  (#251, #266, #278). See [archive-member-names.md](archive-member-names.md),
  [wheel-identity.md](wheel-identity.md).
- [x] **Valid IRIs for any name** (#253). See
  [iri-name-encoding.md](iri-name-encoding.md).
- [x] **Payload-only wheel SBOMs; embedded hashes stay valid** (#269 issue,
  #271, #277). See [wheel-embedding.md](wheel-embedding.md).
- [x] **sdist member order and `sbom-basename` extension** (#272, #273).
- [x] **Release SBOM is the build hook's, signed and attested** (#275). See
  [release-checklist.md](release-checklist.md).
- [x] **Licence element typing** (#276) -- canonical `LicenseExpression`,
  `NoAssertionLicense`/`NoneLicense` individuals, classifiers as a source,
  declared vs concluded by whose statement. See
  [license-typing.md](license-typing.md),
  [license-pipeline.md](license-pipeline.md).
- [x] **sdist licence detection** (#282, #283) -- `PKG-INFO` headers read
  bounded, one in-package rule for every reader. See
  [license-pipeline.md](license-pipeline.md).
- [x] **Fragment merge: id references, licence unification, document
  envelope** (#284). See
  [fragment-merge-unification.md](fragment-merge-unification.md),
  [docs/fragments.md](../../docs/fragments.md).
- [x] **CLI stdout is `KEY=VALUE` data only** (#281). See
  [docs/cli.md](../../docs/cli.md).
- [x] **Network-flaky tests skip with the cause; CI validation retries
  network failures** (#238, #259). See
  [recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md).
- [x] **Import cycles fixed; pylint covers test subfolders** (#260, #268).
- [x] **Windows and macOS CI** (#220), the earlier 1.0-table items 1-2;
  stale G7 gap claims in `minimum-elements.md` fixed (2026-09-20), item 4.
  See [windows-macos-ci.md](windows-macos-ci.md).
- [x] **CLI split, test modularisation, coverage** (closed 2026-08-21). See
  [cli-test-coverage-roadmap.md](cli-test-coverage-roadmap.md).
- [x] **CHANGELOG split** (2026-09-30) -- 0.19.0+ in `CHANGELOG.md`, older
  in `CHANGELOG-archive.md`.

## Bugs fixed in 0.20.0

Moved from [known-bugs.md](../design/known-bugs.md).

All fixed; most change SBOM output.

- [x] **Every licence is emitted as an off-list licence text (M).** Fixed by
  #276. All
  licence elements came from `_get_or_create_license_element()`
  (`assemble/spdx3/deps_license.py`), which always built a
  `simplelicensing_SimpleLicensingText`, defined by SPDX 3 as a licence
  "not listed on the SPDX License List". `MIT`, `MIT AND Apache-2.0` and
  `NOASSERTION` all become custom licence texts; no
  `simplelicensing_LicenseExpression` and no
  `expandedlicensing_NoAssertionLicense` is ever emitted. The normaliser
  runs only when two licence sources conflict, so `license = "mit and
  apache-2.0"` stays verbatim with no `WARNING:`. Affects dependencies,
  wheel `License-Expression`, AI models and Hugging Face cards, and
  per-file `SPDX-License-Identifier`. Decided for 0.20.0: NOASSERTION
  becomes the `expandedlicensing_NoAssertionLicense` individual;
  normalised expressions use canonical term order, the raw value kept in
  provenance. Land before G7 #3 (dataset licences).
- [x] **sdist member order changes ids (S).** Fixed by #272. The same five files
  in reverse archive order gave PKG-INFO `File-2` in one SBOM and `File-8` in
  the other. Sort members before minting, as #266 did for wheels.
- [x] **`sbom-basename = "x.spdx3.json"` gives `x.spdx3.json.spdx3.json` (S).**
  Fixed by #273. Treat the value as a base name; strip a given `.spdx3.json`.
- [x] **Re-embedding lists the previous embedded SBOM (S).** Fixed by
  #271 (payload-only wheel SBOMs); a cross-surface regression test pins
  it.
- [x] **A negative `--max-source-metadata-bytes` is accepted (S).** Fixed by
  #280 (1-7 too). `-1` runs with exit 0; reject it with the one-line config
  error, as `max-model-extract-bytes` does.
- [x] **sdist runs no in-package licence detection (S-M).** Fixed by #283. No G2
  concluded second opinion and no declared fallback when the manifest is silent;
  the directory has both. (Was "sdist `license_files` are not read"; that field
  went with #271.) Decided: shared detection helper for sdist and directory, 256
  KiB licence-member cap with one `WARNING:`, deterministic case pick, PKG-INFO
  cap, PKG-INFO-less sdist reads `project.license`; `License-File:` selection in
  0.21.0.
- [x] **An unknown `[tool.pitloom]` key is ignored silently (S).** Fixed by
  #280. `ofline = true` gives no warning. Decided: one `WARNING:` per key, run
  continues.
- [x] **`.WHL` (uppercase) is handled differently per surface (S).** Fixed by
  #278.
- [x] **`enrich`/`merge`/`fragment` stdout is prose, not `KEY=VALUE`
  (S).** Fixed by #281 (every subcommand).
- [x] **`lock-hash-preservation.md` says "Poetry 2.1+ writes per-package
  `files`"** -- lock-version 2.0 does too; only 1.1 uses
  `[metadata.files]` (doc only). Fixed in the 0.20.0 docs PR.

- [x] **setup.cfg `tool = X` never sets the creation tool (S).** Fixed by #280.
  `[tool:pitloom] tool = X` (and `[tool:pitloom:creation] tool = X`) is
  read, then `_clean_creation_keys` pops `creation-tool` straight after,
  so `config.tools` stays empty. Found while adding the unknown-key
  warning.
- [x] **Licence detection picks a near-variant or misses MIT (S).** Fixed by
  #286. LicenseID alone ranked `Pixar` 0.9963 over `Apache-2.0` 0.9921 on
  requests' verbatim `LICENSE`, `Xnet` over `MIT` on PyYAML's (two notice
  lines first), `JSON` over `MIT` on wcwidth's. Now: the text is also read
  without its copyright notices, a stated licence wins a near-tie (0.01),
  an unstated near-tie with another licence family concludes none.
  Regression corpus: `tests/fixtures/license-texts/`.
- [x] **Installed dependency licence text loses its indent (S).** Fixed by
  #286. `importlib.metadata` dedents each header value, which strips the
  whole Apache `LICENSE` indent when its first line is blank; now read from
  the raw `METADATA` as the wheel and sdist readers do.
- [x] **A classifier licence has no provenance at `minimal` detail (S).**
  Fixed by #286.

## Bugs fixed in 0.20.1

Moved from [known-bugs.md](../design/known-bugs.md).

- [x] **`-o -` ends stdout with `PITLOOM_SBOM_OUTPUT_PATH=-` (S).** Fixed:
  no path line for `-`, the embed `WHEEL=` record goes to `INFO:`, and
  `embed-wheel -o -` no longer writes a file named `-`.

- [x] **`setup.py` with no literal `name=` is dropped whole (S).** Fixed by
  #287 (`setup.py` and `setup.cfg` merged as setuptools does,
  [setuptools-support.md](../implementation/setuptools-support.md#precedence)).
  `read_setup_py` raises `ValueError` and `read_setuptools`
  (`extract/project/setuptools.py`) skips every `setup()` keyword, so a
  `setup.cfg` MIT classifier wins where the built wheel carries the
  `setup.py` BSD one: the directory and the wheel disagree. Found
  checking the paper notes (2026-10-05).

- [x] **A weak `setup.cfg` licence beats a real `setup.py` one (S).** Fixed by
  #287.
  `license = UNKNOWN` in `setup.cfg` plus `setup(license="MIT")` gives
  `NoAssertionLicense`; the built wheel says `License: MIT`.
  `merge_project_metadata` keeps any non-blank first value, where
  `first_license` would skip the weak one
  ([license-rules.md](../design/license-rules.md#open-questions), question 2).

## Release plan items, 0.20.0 to 0.20.2

Moved from [roadmap.md](../design/roadmap.md) on 2026-10-23, as they stood
there. The one item left open (CI workflow hardening) stays in the roadmap
under "Open follow-ups by area".

### 0.20.0 (released 2026-10-05)

- [x] Embed fix ([#269](https://github.com/bact/pitloom/issues/269)), licence
  element typing (#276), sdist licence detection (#283), fragment-merge
  fixes (#284), sdist member order (#272), `sbom-basename` extension (#273).
- [x] Docs PR (#285): licence rules, known bugs, test tiers, field notes.
- [x] Release PR (#286): licence detection on real licence files (notice,
  near-tie), raw installed `METADATA`. See
  [license-rules.md](../design/license-rules.md#4-declared-or-concluded).
- [x] Released 2026-10-05; published artefacts verified, see
  [wheel-sbom-verification.md](wheel-sbom-verification.md). Fuzz run after
  the release passed (2026-10-05).

### 0.20.1 (released 2026-10-07)

Shipped #287, #289, #291: setuptools precedence, licence detection on
Windows. Three planned fixes (a very long lock-file version, Safetensors
licence keys, a `%` in `setup.cfg`) did not make it; they are in
[known-bugs.md](../design/known-bugs/extraction-and-fragments.md#fixed-p2-0210-and-later)
and
[known-bugs.md](../design/known-bugs/ai-models-readers-and-metadata.md#fixed-p2-0210-and-later).
The Safetensors licence keys were fixed in 0.22.0 (#376).

### 0.20.2 (released 2026-10-09, tag v0.20.2)

AI model metadata made uniform and safer:

- [x] **One spelling for scalar text**, built in #294. See
  [scalar-text-spelling.md](scalar-text-spelling.md).
- [x] **CRFsuite models** (#294): `lCRF` magic, stdlib-only bounded reader.
  See [crfsuite-support.md](crfsuite-support.md).
- [x] **ONNX names, licence and version** (#292); **name, label and entry
  caps, display escape of bidi/invisible text, RFC 8785 embedded JSON,
  GGUF `general.license`** (#294).
- Known issue at release: a generated CRFsuite description can override a
  fragment description (roadmap 0.21.0, "A fragment value beats a value read
  from the file").

## Shipped in 0.21.0 (PRs #300-#361)

Moved from [roadmap.md](../design/roadmap.md) on 2026-10-29, as they stood
there. The release items; the ones still open are in
[roadmap.md](../design/roadmap.md#0210).

**Release status (2026-10-23):** every code PR of the release is merged
(#305-#350; the last were #347 more Git hosts, #349 fragment value replaces
generated, #350 the Spaces note). PR #346 holds the version bump, CHANGELOG,
coverage snapshots and the release review (CHANGELOG against the code, user
docs and skills, working-docs and comments). Before the tag: merge #346, tag
v0.21.0, publish to PyPI. After it: Lumina pins `pitloom==0.21.0` (it takes
LicenseID 0.6.0 through Pitloom's floor), then adds its non-GitHub examples.
See [release-checklist.md](release-checklist.md). Released 2026-10-28
(v0.21.0); v0.21.1 (#364-#366) followed the same day.

- [x] **Same AI model, same id on every surface**, and **registry path keys**
  (2026-10-16): one key helper, a model keyed by its file, content-gated
  lookups. See [id-registry-path-keys.md](id-registry-path-keys.md).
- [x] **Registry v3** (PR #305). See
  [id-registry-v3.md](id-registry-v3.md); open follow-ups in
  [id-registry-followups.md](../design/id-registry-followups.md).
- [x] **Extras, edge kind and authors on every route** (#300); open
  follow-ups in [extras-parity.md](extras-parity.md#open-questions).
- [x] **Git URL ingestion** (PR #317): `loom project <url>` and
  `loom generate <url>` for GitLab, GitHub, Gitea/Forgejo, Bitbucket and
  SourceHut; redirects followed hop by hop with a caller check; Lumina uses
  it. See [remote-git-ingestion.md](remote-git-ingestion.md),
  [docs/git-urls.md](../../docs/git-urls.md).
- [x] **More Git hosts** (#347): Bitbucket `branch`/`commits` pages (the ref
  was dropped silently), SourceHut `log`, Gitiles `/+/`, cgit `?h=`, Azure
  DevOps `?version=`; a folder page naming a file reads its folder; a clone
  rejected with HTTP 400 on the blob filter is retried without it; a Hugging
  Face Space or dataset is a Git repository, not a model. Live checks on 12
  hosts. See [docs/git-urls.md](../../docs/git-urls.md).
- [x] **A fragment value replaces one Pitloom generated** (#349): the
  `description`, `ai_domain` and input/output text a reader made from the file's
  format (`generated_from_labels`, `derived_from_format`), with one `INFO:` and
  the property's provenance dropped, in any order of fragments. See
  [docs/fragments.md](../../docs/fragments.md).
- [x] **Git URL hardening** (#339, #342-#344): `max_bytes=` clone cap in the
  library (`git.too-large`), credentials only on same-origin redirects,
  SourceHut slash branches, the process tree killed on Windows.
- [x] **One default SBOM file name** (#334): one helper for the CLI, the hook
  and `embed-wheel`. It replaces unsafe characters only, not PEP 427's
  escaping as
  [known-bugs.md](../design/known-bugs/surfaces-hook-and-wheel.md#fixed-p0-in-0210)
  decided; whether to change the rule is open.

### G7, conformance and SHA-512

The G7 and conformance work; full breakdown in
[g7-ai-sbom-coverage.md](../design/g7-ai-sbom-coverage.md).

- [x] **#3 part 1: `ai_AIPackage.verifiedUsing`** from its model file, with
  gated lookups (2026-10-16; see
  [id-registry-path-keys.md](id-registry-path-keys.md)).
- [x] **#3 part 2: dataset licence wiring** (`DatasetMetadata.license` read
  by `dataset.py`; G7 B1) and its three readers
  (Croissant via `loom.run`, a local dataset card, a Hub model's dataset
  cards): [dataset-licence-readers.md](dataset-licence-readers.md).
- [x] **Identifiers from the minimum-elements mappings** (CISA 2026, NTIA 2021,
  G7 AI 2026, BSI 2025): `software_packageUrl` on `ai_AIPackage` and dataset
  packages (G7 B2; [g7-conformance-tests.md](g7-conformance-tests.md)).
- [x] **SHA-512 beside SHA-256** (always, no flag) for every file Pitloom
  reads and describes: model files, project/wheel/sdist file elements,
  `loom` files, bundled libraries (`pitloom.core.file_hash`). The registry
  gate, a Merkle root and a lock file's dependency hash stay SHA-256; a
  dependency's SHA-512
  stays unspecified while no source states one (decided 2026-10-18;
  [build-backend-improvements.md](../design/build-backend-improvements.md)).
- [x] **Hub revision** (G7 B3): a Hub model's commit hash as its version and
  its last-modified time as `releaseTime`.
- [x] **Support tiers and demo scope** (tier 1: Safetensors, ONNX, GGUF, NumPy,
  fastText, Hugging Face Hub; demo: G7 Metadata/System/Model/Dataset, SPDX 3.0,
  Hatchling, setuptools, Poetry) and the parity ledger on
  `docs/g7-sbom-for-ai.md`; open gaps are under
  [1.0](../design/roadmap.md#10).
- [x] **G7 honesty notices** (2026-10-18): one `INFO:` per model naming a G7
  element SPDX 3.0.1 has no property for (today the architecture, in
  `ai_typeOfModel`; no reader drops a value). Always on, stderr only
  (`extract/ai_model/unrecordable.py`). See
  [g7-honesty-and-non-recordable.md](../design/g7-honesty-and-non-recordable.md).
- [x] **Conformance tests**: G7 (`g7ai`, with offline SPDX validation),
  CISA 2026 (`cisa2026`, SPDX 3.0), FSCT 2024 (`fsct3`) and BSI TR-03183-2
  v2.1 (rule-based `rules/bsi.yaml`; the hand-written `BSIChecker` is
  removed), each with an expected-outcome table and surface-parity tests;
  coverage in `g7-coverage-history/`. CISA's hash rule is checked as "an
  integrity method is present" only. BSI
  [ontology](https://bact.github.io/bom/req/bsi2025/bsi2025.ttl) and
  [mapping](https://bact.github.io/bom/mapping/bsi2025-to-spdx30.sssom.tsv).
  See [g7-conformance-tests.md](g7-conformance-tests.md).
- [x] **Same reachability for every standard** (checker `151460c`,
  2026-10-18): `trainedOn` and `testedOn` are the default `reach_via`, so
  every standard judges the datasets a reachable model uses;
  `bsi-expected.tsv` refreshed.
- [x] **CLI option choices in a stable order** (2026-10-18):
  `--content-type-method` and `--creator-type` listed a `frozenset` in hash
  order; now sorted (`tests/cli/test_cli_choices_order.py`).
- [x] **Dataset readers' edge cases** (2026-10-19): Croissant nesting cap,
  placeholder and non-URL values, card warnings without a cache path, one
  reference per dataset, a `datasets:` cap, YAML 1.1 and generated-input
  tests. See [dataset-licence-readers.md](dataset-licence-readers.md).
- [x] **One dataset, one package, one relationship per role** (PR #311, #314):
  first reference wins, later ones fill unset fields, a conflict warns once
  per field; `loom.Run` folds spellings the same way (`Org/Data` is
  `org/data`, an existing path never folded). See
  [ai-dataset-linking.md](ai-dataset-linking.md).
- [x] **A software-agent creator is the author, not the supplier** (PR #312):
  `suppliedBy` takes the first creator that is not a `software-agent`, else
  none; Lumina reports itself as the author and Pitloom as the tool.
- [x] **#6 Model producer and parameter count** from structured sources
  (PR #306): `originatedBy` Agents and the `parameters` hyperparameter
  entry. See
  [g7-model-producer-parameter-count.md](g7-model-producer-parameter-count.md).
- [x] CHANGELOG entries for the 2026-10 G7/CISA/FSCT/SHA-512 work (#309), the
  Hub model description fix (#310) and the dataset and creator fixes (#311,
  #312, #314).
- [x] The skill's G7 checklist matches the code (`hasDataFile` only with
  `--scan-model-usage`; dataset edges; SHA-512): see
  [minimum-elements.md](../../skills/sbom-enrich/references/minimum-elements.md).

## Bugs fixed in 0.21.0

Moved from [known-bugs.md](../design/known-bugs.md).

- [x] **Source and wheel SBOMs disagree on optional dependencies (M)**, and
  **extras-only dependencies are plain `dependsOn` in a wheel SBOM (S-M)**.
  Fixed by #300 (provisional): extras on every route as
  `hasOptionalDependency` with no scope, all authors as `originatedBy`. See
  [extras-parity.md](extras-parity.md). PyThaiNLP 5.4.0: 79 packages from the
  wheel route, 3 from `loom project .` before the fix.

## Shipped in 0.22.0 (PRs #374-#410)

Released 2026-10-30. Moved from [roadmap.md](../design/roadmap.md), as they
stood there. Open items:
[roadmap.md](../design/roadmap.md#0230-licenseid-07-and-message-catalogue) and
its [0.24.0](../design/roadmap.md#0240-message-catalogue-and-licence-provenance)
section.

- [x] **`embed-wheel --sbom` input check** (#374): invalid JSON, a non-object
  or a non-SPDX-3 `.spdx3.json` is refused before the wheel is written.
- [x] **Git URL messages** (#375): the temporary checkout shows as
  `<checkout>`, not a random path.
- [x] **Model licence from Safetensors and GGUF** (#376): `modelspec.license`
  and `general.license.name` (when `general.license` is blank or `other`) are
  read as the model licence.
- [x] **Git LFS pointers** (#378): one detector; a checkout pointer is listed
  by its `oid`, one `WARNING:` per SBOM. See
  [git-lfs-pointers.md](git-lfs-pointers.md); LFS fetch is open
  ([known-bugs.md](../design/known-bugs.md)).
- [x] **Flags for both size ceilings** (#381).
- [x] **Dataset size unit fix** (#382): `dataset_datasetSize` holds bytes only.
- [x] **Skill size cap** (#385).
- [x] **Evidence merge drop** (#386): `minimal` provenance keeps `Evidence:`;
  a `not_measured` entry is dropped once a merge supplies the value, with the
  comment-join fix it needs.
- [x] **Sizes under a cap** (#387): a single-file dataset's size and why its
  hash is missing. See [evidence-levels.md](../design/evidence-levels.md).
- [x] **Skills** (#392): prepare the licence database before the first run.
- [x] **Provenance segments** (#389): a `|` in a name no longer adds one.
- [x] **Message catalogue** (#390, #395, #396, #404, #408): catalogued messages
  end in a `[code]`: Git LFS pointers, size caps, why a model was not read,
  unreadable files and directories. See
  [message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md).
- [x] **LicenseID cap** (#401): `>=0.6.0,<0.7` until the 0.7 adoption.
- [x] **Serious bugs** (#402, #405, #407): a non-UTF-8 name no longer stops
  generation, a `:` in provenance text is a note, a direct-URL dependency is not
  looked up on PyPI by name.
- [x] **ID registry format 4** (#407): a package keyed by name and version;
  format 3 is refused.

## Shipped in 0.22.1 (PRs #413-#433)

Released 2026-11-03. Fixes found in the cold reviews of 2026-11-02 and the
re-run of the 0.22.0 release checks. Open items:
[roadmap.md](../design/roadmap.md#0230-licenseid-07-and-message-catalogue) and
its [0.24.0](../design/roadmap.md#0240-message-catalogue-and-licence-provenance)
section.

- [x] **`--scan-model-usage` reads ASTs** (#413): `comment` is read, write,
  read and write, or unknown access; mentions skipped; new codes
  `usage-unparseable`, `usage-unparseable/mention`, `usage-unusable` (since
  0.22.1). See [model-usage-ast-scan.md](model-usage-ast-scan.md).
- [x] **Prefetch, document module and lint** (#418): the PyPI prefetch uses
  the versions the dependency groups resolved (#429: once per package, never
  for a private one named by URL); `document.py` split under the size limit.
- [x] **Git LFS pointer as licence text** (#422, #429): `license = {file =
  ...}`, a wheel, an sdist `PKG-INFO` and an installed `.dist-info`.
- [x] **Readers** (#426, #427): Keras, PT2 and fastText (label cap), GGUF
  (non-UTF-8 strings, hyperparameter suffixes), blank GGUF, Safetensors and
  ONNX text fields (#433: a PT2 tag holding a lone surrogate is kept).
- [x] **Usage scan limits** (#432): a long expression chain no longer crashes
  Python 3.10 (the parse runs on a stack sized to the script); calls with many
  arguments, keywords or nested conditionals take linear time; a constant only
  put in a message gives no edge.
- [x] **Small fixes** (#429): `loom id generate -e` refuses a package name that
  is not a PEP 508 name; `wheel --embed -v` without `-o` logs no
  `OUTPUT_PATH`; `numpy.timedelta64` in canonical JSON; display escaping of a
  lone surrogate.
- [x] **CI and tests** (#415, #416, #421, #428): skip the push run after a
  merge that repeats a green PR tree; the manual CLI checks split under the
  complexity ceilings; loopback test servers no longer stall on a macOS runner.

## Shipped in 0.23.0 (PRs #434-#446)

Released 2026-11-05, cut early (maintainer ruling 2026-11-04). Open items:
[roadmap.md](../design/roadmap.md#0230-licenseid-07-and-message-catalogue) and
its [0.24.0](../design/roadmap.md#0240-message-catalogue-and-licence-provenance)
section.

- [x] **LicenseID 0.7 adoption** (#437 to #440, #443; floor 0.7.1, #445): a
  declared licence value is read by LicenseID alone, from its packaged SPDX
  License List, with no licence database (the Hatchling hook's isolated build
  included); `py-spdx-license` dropped; LicenseID warnings relayed as one
  line; rewrites cite `Tool: licenseid==V`. See
  [licenseid/adoption-built.md](licenseid/adoption-built.md) and the
  plan, [licenseid/adoption-plan.md](licenseid/adoption-plan.md).
- [x] **Message catalogue PR 2b** (#444): `card-malformed`, `json-malformed`,
  `text-malformed`; an unlistable card directory warns `dir-unlistable`.
- [x] **Message catalogue PRs 1b and 1c** (#446): `model-field-unreadable`,
  `model-field-conflict`, `field-not-recordable`, `library-unusable` (a
  `magika` that fails to import types files by extension). The ratchet fell
  from 498 to 469. See
  [message-catalogue-families.md](message-catalogue-families.md).
- [x] **Packaging** (#435): no `AGENTS.md`, `CLAUDE.md` or `GEMINI.md` in the
  sdist or wheel.
- [x] **Docs and tests** (#434, #436, #442): the 0.22.1 PyPI verification;
  live Git tests retry a transient 5xx answer; the catalogue plan refresh.
- [x] **Release PR** (#448): the skills require `pitloom>=0.23.0`; the action
  install self-test uses releases that cap `licenseid` below 0.7.
- [x] **Docs, skills and comments sweep** (#449, merged before the tag): the
  `loom merge`, `project` and `enrich` help text; the `pitloom` logger reset
  around every test; the action self-test fails without a licence database.

## Shipped in 0.23.1 (PRs #450-#455)

Released 2026-11-07, a patch release for LicenseID 0.7.2. Open items:
[roadmap.md](../design/roadmap.md#0240-message-catalogue-and-licence-provenance).

- [x] **LicenseID 0.7.2** (#455): its `too few words for text` notice (no
  licence in a short text) is relayed at `DEBUG`, not `WARNING:`; its
  `text_title` and `alias_name` readings (`New BSD`, `CC0 1.0 Universal`) are
  decided ids, said at `INFO:`. A test fails on a LicenseID category Pitloom
  has not decided on.
- [x] **Docs** (#450 to #454): the post-release verification of v0.23.0;
  housekeeping; field notes on the model usage scan; the licence provenance
  design refreshed for LicenseID 0.7.2; the PyPI URL targets design.
- [x] **Release PR** (#456): requires `licenseid>=0.7.2,<0.8`; the skills
  require `pitloom>=0.23.1`, since 0.23.0 relays LicenseID 0.7.2's short-text
  notice as a spurious `WARNING:`.

## Shipped in 0.23.2 (PRs #457-#459)

Released 2026-11-07, a patch release for LicenseID 0.7.3. Open items:
[roadmap.md](../design/roadmap.md#0240-message-catalogue-and-licence-provenance).

- [x] **Missing licence database** (#458): with no LicenseID database, a
  declared licence name (`New BSD`) says nothing; a declared licence text or
  a `LICENSE` file with no declared licence still warns.
- [x] **Docs** (#457): the post-release verification of v0.23.1.
- [x] **Release PR** (#459): requires `licenseid>=0.7.3,<0.8`, which reads
  Apache names with a version (`Apache, Version 2.0`, `Apache Software
  License 2.0`, `Apache License (2.0)`) as `Apache-2.0` (upstream finding
  11); the skills require `pitloom>=0.23.2`.

## Shipped in 0.23.3 (PR #461)

Released 2026-11-09, a patch release for LicenseID 0.8.1. Open items:
[roadmap.md](../design/roadmap.md#0240-message-catalogue-and-licence-provenance).

- [x] **Release PR** (#461): requires `licenseid>=0.8.1,<0.9`, which reads a
  licence URL as its ID (`https://www.apache.org/licenses/LICENSE-2.0` is
  `Apache-2.0`, category `license_url`) and drops a control or format
  character at either end of a value; a database built by LicenseID 0.7.x
  warns `build v3 outdated` until `licenseid update`. The skills require
  `pitloom>=0.23.3`. Python 3.15 is not tested: some `ai` extra wheels
  (such as `onnx`) have no 3.15 build yet.

## Shipped in 0.23.4 (PRs #462, #464, #465)

Released 2026-11-09, a patch release for LicenseID 0.8.4 and a model SBOM
from a Git URL. Open items:
[roadmap.md](../design/roadmap.md#0240-message-catalogue-and-licence-provenance).

- [x] **Release PR** (#462): requires `licenseid>=0.8.2,<0.9`. Pitloom reads
  every declared value, licence text and route as with 0.8.1: no licence
  reading, warning, category or database build changed (a database built by
  0.8.1 stays current). The skills require `pitloom>=0.23.4`.
- [x] **Floor raised** (#465, #464): `licenseid>=0.8.3,<0.9` reads a
  `licenses.nuget.org` expression URL as its expression; `>=0.8.4,<0.9` reads
  `MIT/Apache-2.0` as `Apache-2.0 OR MIT` (category `separator`). The 0.8.4
  re-run of the upstream findings is in
  [licenseid/upstream-issues.md](licenseid/upstream-issues.md).
- [x] **A model SBOM from a model file or Git URL** (#464): see
  [model-sbom-from-git.md](model-sbom-from-git.md).
