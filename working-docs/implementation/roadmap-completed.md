---
Created: 2026-09-30
Last-Modified: 2026-10-09
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
  [backend-file-discovery-validation.md](backend-file-discovery-validation.md)'s
  Flit-core/PDM-backend round.
- [x] **Multiple creators / tools per `CreationInfo` record** -- `Creator`/
  `Tool` dataclasses, repeatable `--creator-name`/`--creation-tool`,
  array-of-tables config. See [creation-metadata.md](../../docs/creation-metadata.md).
- [x] **SPDX license expression normalization and declared-vs-detected
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
  See [non-hatchling-file-discovery.md](../design/non-hatchling-file-discovery.md),
  [docs/allow-build.md](../../docs/allow-build.md).
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
- [x] **CLI split, test modularization, coverage** (closed 2026-08-21). See
  [cli-test-coverage-roadmap.md](../design/cli-test-coverage-roadmap.md).
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
  #286. `licenseid` alone ranked `Pixar` 0.9963 over `Apache-2.0` 0.9921 on
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
