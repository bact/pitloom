---
Created: 2026-09-30
Last-Modified: 2026-11-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap -- completed items

See also: [roadmap.md](../design/roadmap.md) (open items).

What was built and how, with the design choices that are worth not
re-deciding. Not listed: release preparation, post-release verification, CI
and housekeeping; `CHANGELOG.md` has every change. Detail for an item is in
the implementation doc it links to; read the code for current state, as this
list is not kept in sync with later changes.

## Before 0.20.0

- [x] **SPDX 3.0 SBOM** (JSON-LD) from a format-neutral `DocumentModel`
  ([format-neutral-representation.md](../design/format-neutral-representation.md)),
  with AI/ML package profiles (`software_Package` with the AI BOM profile,
  `dataset_DatasetPackage`).
- [x] **Metadata sources**: Hatchling (`pyproject.toml`), setuptools
  (`pyproject.toml` > `setup.cfg` > `setup.py` conflict resolution), Poetry
  (`[tool.poetry]` when `[project]` is absent, merged when both exist),
  PDM-backend and Flit-core
  ([backend-file-discovery-validation-flit-pdm.md](backend-file-discovery-validation-flit-pdm.md)).
- [x] **Surfaces**: CLI (`loom`), Hatchling build hook with fragment merging,
  PEP 770 (`.dist-info/sboms/` via `build_data["sbom_files"]`), `pitloom.loom`
  tracking SDK, GitHub Action ([github-action.md](github-action.md)), Agent
  Skills (`sbom-generate`, `sbom-enrich`, `sbom-validate`) and the Claude
  Code plugin ([agent-skill.md](agent-skill.md)),
  `loom verify-wheel` / `validate-wheel` (#202)
  ([wheel-verification-commands.md](wheel-verification-commands.md)).
- [x] **Provenance**: per-field source attribution; several creators and
  tools per `CreationInfo` ([creation-metadata.md](../../docs/creation-metadata.md)).
- [x] **Licences**: expression normalisation and declared-vs-detected
  conflict detection through `py-spdx-license` (#121,
  [multi-source-conflict.md](provenance/multi-source-conflict.md));
  `[project.license-files]` (#207), later changed so an SBOM lists nothing
  under the wheel's own `.dist-info`
  ([license-pipeline.md](license-pipeline.md#license-files-are-not-listed-pep-639)).
- [x] **Dependencies**: one shared cascade for lock and pin formats
  (`poetry.lock`, `pylock.toml`, `uv.lock`, `pdm.lock`, `Pipfile.lock`, pinned
  `requirements.txt`) as the resolved-dependency source (#208,
  [lock-file-cascade.md](lock-file-cascade.md)).
- [x] **Loom ID registry**: harvests newly minted ids back after each run
  (#178, [id-registry-autosync.md](id-registry-autosync.md)); the explicit,
  declared-only registry came in 0.20.0.
- [x] **Backend-agnostic file discovery** (2026-09-15): static rescans for
  setuptools, Poetry, PDM-backend and Flit-core; `--allow-build` for the rest
  ([non-hatchling-file-discovery.md](non-hatchling-file-discovery.md),
  [docs/allow-build.md](../../docs/allow-build.md)).
- [x] **Dataset-to-model relationships** (`trainedOn`, `testedOn`) and
  Croissant dataset size ([ai-dataset-linking.md](ai-dataset-linking.md)).
- [x] **Release SBOM is checked for Apache-2.0** by
  `scripts/check_sbom_license.py` (#243, #248); `embed-wheel` emits the
  concluded licence.

## Shipped in 0.20.0 (2026-10-05)

- [x] **`--allow-build` timeout and signal-safe builds** (#226, #250, #262):
  `--build-timeout`; the whole build tree is killed on SIGTERM or Ctrl-C
  ([allow-build-timeout.md](allow-build-timeout.md),
  [allow-build-termination.md](allow-build-termination.md)).
- [x] **One config cascade on every surface** (#227, #228, #231, #232, #247,
  #249, #280): `--config` everywhere, explicit config sources, an sdist reads
  its own config, typed `setup.cfg` keys. Decided: an unknown `[tool.pitloom]`
  key gives one `WARNING:` per key and the run continues
  ([config-sources.md](config-sources.md),
  [sdist-own-config.md](sdist-own-config.md)).
- [x] **Explicit ID registry, collision-free ids** (#234, #235, #255): ids
  come from a declared registry only, one `ERROR:` otherwise; `loom id`;
  registry format v2.
- [x] **`loom env` reads `pipdeptree --json`** (#236,
  [deployed-env-pipdeptree.md](deployed-env-pipdeptree.md)).
- [x] **AI model scanning** (#239, #240, #252, #263, #267, #270): one
  `ModelCandidate`, deterministic order, `--scan-model-usage` (off by default),
  wheel scanning gated by `--trust-wheel-model`, bounded readers, one entry
  per confirmed model on every surface
  ([ai-model-scanning.md](ai-model-scanning.md),
  [ai-model-scan-bounds.md](ai-model-scan-bounds.md)).
- [x] **Unreadable files and directories warn, never vanish** (#244, #257,
  #258).
- [x] **Same names on every OS** (#251, #266, #278): archive member names,
  wheel identity ([archive-member-names.md](archive-member-names.md),
  [wheel-identity.md](wheel-identity.md)); valid IRIs for any name (#253).
- [x] **Payload-only wheel SBOMs** (#269, #271, #277): a wheel SBOM lists the
  payload, not an earlier embedded SBOM, so embedded hashes stay valid
  ([wheel-embedding.md](wheel-embedding.md)). The release SBOM is the build
  hook's, signed and attested (#275).
- [x] **Licence element typing** (#276): canonical `LicenseExpression`,
  `NoAssertionLicense` and `NoneLicense` individuals, classifiers as a source,
  declared vs concluded by whose statement. Decided: normalised expressions
  use canonical term order and keep the raw value in provenance
  ([license-typing.md](license-typing.md),
  [license-pipeline.md](license-pipeline.md)).
- [x] **sdist licence detection** (#282, #283): `PKG-INFO` headers read with a
  bound, one in-package rule for every reader. Decided: one detection helper
  for sdist and directory, a 256 KiB licence-member cap with one `WARNING:`, a
  deterministic case pick, a PKG-INFO-less sdist reads `project.license`;
  `License-File:` selection deferred.
- [x] **Fragment merge** (#284): id references, licence unification, document
  envelope ([fragment-merge-unification.md](fragment-merge-unification.md)).
- [x] **CLI stdout is `KEY=VALUE` data only** (#281), for every subcommand.
- [x] **sdist member order and `sbom-basename`** (#272, #273): members are
  sorted before ids are minted; the value is a base name, a given
  `.spdx3.json` is stripped.

## Bugs fixed in 0.20.0

All fixed; most change SBOM output.

- [x] **Every licence was an off-list licence text** (#276). One helper always
  built `simplelicensing_SimpleLicensingText`, so `MIT` and `NOASSERTION` were
  custom texts. Now typed as above.
- [x] **Licence detection picked a near-variant or missed MIT** (#286).
  LicenseID alone ranked `Pixar` over `Apache-2.0` on requests' `LICENSE`.
  Now the text is also read without its copyright notices, a stated licence
  wins a near-tie (0.01), and an unstated near-tie with another licence
  family concludes none. Regression corpus: `tests/fixtures/license-texts/`.
- [x] **Installed dependency licence text lost its indent** (#286):
  `importlib.metadata` dedents header values; read from the raw `METADATA`
  as the wheel and sdist readers do.
- [x] Smaller: a negative `--max-source-metadata-bytes` is rejected; `setup.cfg`
  `tool = X` sets the creation tool; `.WHL` is handled alike on every surface
  (#278, #280); a classifier licence has provenance at `minimal` detail
  (#286).

## Bugs fixed in 0.20.1

- [x] **`setup.py` with no literal `name=` was dropped whole**, and **a weak
  `setup.cfg` licence beat a real `setup.py` one** (#287). `setup.py` and
  `setup.cfg` are merged as setuptools does, and a placeholder
  (`license = UNKNOWN`) yields to a real value
  ([setuptools-support.md](setuptools-support.md#precedence),
  [license-rules.md](../design/license-rules.md#open-questions)).
- [x] **`-o -` ended stdout with `PITLOOM_SBOM_OUTPUT_PATH=-`**: no path line
  for `-`; `embed-wheel -o -` writes no file named `-`.

## 0.20.1 and 0.20.2

0.20.1 (2026-10-07, #287, #289, #291) shipped the setuptools precedence and
licence detection on Windows. 0.20.2 (2026-10-09, #292, #294) made AI model
metadata uniform and safer: one spelling for scalar text
([scalar-text-spelling.md](scalar-text-spelling.md)); CRFsuite models (`lCRF`
magic, stdlib-only bounded reader,
[crfsuite-support.md](crfsuite-support.md)); ONNX names, licence and version;
caps on names, labels and entries; display escaping of bidi and invisible
text; RFC 8785 embedded JSON; GGUF `general.license`.

## Shipped in 0.21.0 (PRs #300-#361)

- [x] **Same AI model, same id on every surface**, with registry path keys
  (2026-10-16): one key helper, a model keyed by its file, content-gated
  lookups ([id-registry-path-keys.md](id-registry-path-keys.md)). **Registry v3**
  (#305, [id-registry-v3.md](id-registry-v3.md)).
- [x] **Extras, edge kind and authors on every route** (#300): extras are
  `hasOptionalDependency` with no scope and all authors `originatedBy`, on
  source and wheel routes alike. Provisional; open questions in
  [extras-parity.md](extras-parity.md#open-questions).
- [x] **Git URL ingestion** (#317, #347): `loom project <url>` and
  `loom generate <url>` for GitLab, GitHub, Gitea/Forgejo, Bitbucket,
  SourceHut, Gitiles, cgit and Azure DevOps pages; redirects followed hop by
  hop with a caller check; a folder page naming a file reads its folder; a
  Hugging Face Space or dataset is a Git repository, not a model
  ([remote-git-ingestion.md](remote-git-ingestion.md),
  [docs/git-urls.md](../../docs/git-urls.md)). Hardening (#339, #342-#344):
  a `max_bytes=` clone cap in the library (`git.too-large`), credentials only
  on same-origin redirects, the process tree killed on Windows.
- [x] **A fragment value replaces one Pitloom generated** (#349): the
  `description`, `ai_domain` and input/output text a reader made from the
  file's format, with one `INFO:` and the property's provenance dropped, in
  any order of fragments ([docs/fragments.md](../../docs/fragments.md)).
- [x] **One default SBOM file name** (#334): one helper for the CLI, the hook
  and `embed-wheel`. It replaces unsafe characters only, not PEP 427's
  escaping; whether to change that rule is open
  ([known-bugs](../design/known-bugs/surfaces-hook-and-wheel.md#fixed-p0-in-0210)).

### G7, conformance and SHA-512

Breakdown in [g7-ai-sbom-coverage.md](../design/g7-ai-sbom-coverage.md).

- [x] **#3 Dataset licences and model hash**: `ai_AIPackage.verifiedUsing`
  from the model file with gated lookups; `DatasetMetadata.license` read by
  three readers (Croissant via `loom.run`, a local dataset card, a Hub model's
  dataset cards, [dataset-licence-readers.md](dataset-licence-readers.md)).
- [x] **Identifiers and Hub revision** (G7 B2, B3): `software_packageUrl` on
  `ai_AIPackage` and dataset packages
  ([g7-conformance-tests.md](g7-conformance-tests.md)); a Hub model's commit
  hash is its version and its last-modified time its `releaseTime`.
- [x] **SHA-512 beside SHA-256**, always, for every file Pitloom reads and
  describes (`pitloom.core.file_hash`). Decided (2026-10-18): the registry
  gate, a Merkle root and a lock file's dependency hash stay SHA-256; a
  dependency's SHA-512 stays unspecified while no source states one
  ([build-backend-improvements.md](../design/build-backend-improvements.md)).
- [x] **#6 Model producer and parameter count** from structured sources
  (#306): `originatedBy` Agents and the `parameters` hyperparameter entry
  ([g7-model-producer-parameter-count.md](g7-model-producer-parameter-count.md)).
- [x] **G7 honesty notices** (2026-10-18): one `INFO:` per model naming a G7
  element SPDX 3.0.1 has no property for (today the architecture, in
  `ai_typeOfModel`); no reader drops a value
  ([g7-honesty-and-non-recordable.md](../design/g7-honesty-and-non-recordable.md)).
- [x] **Conformance tests** for G7 (`g7ai`, with offline SPDX validation),
  CISA 2026, FSCT 2024 and BSI TR-03183-2 v2.1 (rule-based `rules/bsi.yaml`),
  each with an expected-outcome table and surface-parity tests; coverage
  snapshots in `g7-coverage-history/`. Decided: CISA's hash rule is checked as
  "an integrity method is present" only; `trainedOn` and `testedOn` are the
  default `reach_via`, so every standard judges the datasets a reachable model
  uses.
- [x] **Datasets**: one dataset, one package, one relationship per role (#311,
  #314): the first reference wins, later ones fill unset fields, a conflict
  warns once per field; `loom.Run` folds spellings alike (`Org/Data` is
  `org/data`, an existing path never folded). Reader edge cases: nesting cap,
  placeholders, a `datasets:` cap. A software-agent creator is the author,
  never the supplier (#312): `suppliedBy` takes the first creator that is not
  a `software-agent`.
- [x] **Stable CLI choice order**: `--content-type-method` and
  `--creator-type` are sorted, not in set-hash order.

## Bugs fixed in 0.21.0

- [x] **Source and wheel SBOMs disagreed on optional dependencies** (#300):
  PyThaiNLP 5.4.0 gave 79 packages from the wheel route and 3 from
  `loom project .`; fixed with the extras parity above.

## Shipped in 0.22.0 (PRs #374-#410)

- [x] **Model licence from Safetensors and GGUF** (#376): `modelspec.license`,
  and `general.license.name` when `general.license` is blank or `other`.
- [x] **Git LFS pointers** (#378): one detector; a checkout pointer is listed
  by its `oid` with one `WARNING:` per SBOM. LFS fetch is open
  ([git-lfs-pointers.md](git-lfs-pointers.md)).
- [x] **Evidence levels** (#386, #387): `minimal` provenance keeps
  `Evidence:`; a `not_measured` entry is dropped once a merge supplies the
  value; a capped single-file dataset records its size and why its hash is
  missing ([evidence-levels.md](../design/evidence-levels.md)).
- [x] **Message catalogue** (#390, #395, #396, #404, #408): catalogued messages
  end in a `[code]` (Git LFS pointers, size caps, why a model was not read,
  unreadable files and directories)
  ([message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md)).
- [x] **Smaller changes**: `embed-wheel --sbom` refuses invalid JSON or a
  non-SPDX-3 document before writing (#374); the Git checkout shows as
  `<checkout>` (#375); flags for both size ceilings (#381);
  `dataset_datasetSize` holds bytes only (#382); a `|` in a name adds no
  provenance segment (#389); a non-UTF-8 name no longer stops generation, a
  direct-URL dependency is not looked up on PyPI by name (#402, #405, #407).
- [x] **ID registry format 4** (#407): a package keyed by name and version;
  format 3 is refused.

## Shipped in 0.22.1 (PRs #413-#433)

- [x] **`--scan-model-usage` reads ASTs** (#413): the edge `comment` is read,
  write, read and write, or unknown access; mentions are skipped; codes
  `usage-unparseable`, `usage-unparseable/mention`, `usage-unusable`. Limits
  (#432): a long expression chain no longer crashes Python 3.10 (the parse
  runs on a stack sized to the script), many arguments, keywords or nested
  conditionals take linear time, a constant only put in a message gives no
  edge ([model-usage-ast-scan.md](model-usage-ast-scan.md)).
- [x] **PyPI prefetch** (#418, #429): uses the versions the dependency groups
  resolved, once per package, never for a private one named by URL.
- [x] **Git LFS pointer as licence text** (#422, #429): `license = {file =
  ...}`, a wheel, an sdist `PKG-INFO` and an installed `.dist-info`.
- [x] **Readers** (#426, #427, #433): Keras, PT2 and fastText (label cap),
  GGUF (non-UTF-8 strings, hyperparameter suffixes), blank GGUF, Safetensors
  and ONNX text fields; a PT2 tag holding a lone surrogate is kept.

## Shipped in 0.23.0 (PRs #434-#446)

Cut early (maintainer ruling 2026-11-04).

- [x] **LicenseID 0.7 adoption** (#437 to #440, #443, #445): a declared
  licence value is read by LicenseID alone, from its packaged SPDX License
  List, with no licence database (the Hatchling hook's isolated build
  included); `py-spdx-license` dropped; LicenseID warnings relayed as one
  line; rewrites cite `Tool: licenseid==V`
  ([licenseid/adoption-built.md](licenseid/adoption-built.md),
  [licenseid/adoption-plan.md](licenseid/adoption-plan.md)).
- [x] **Message catalogue 1b, 1c, 2b** (#444, #446): `card-malformed`,
  `json-malformed`, `text-malformed`, `dir-unlistable`,
  `model-field-unreadable`, `model-field-conflict`, `field-not-recordable`,
  `library-unusable` (a `magika` that fails to import types files by
  extension) ([message-catalogue-families.md](message-catalogue-families.md)).
- [x] **Packaging** (#435): no `AGENTS.md`, `CLAUDE.md` or `GEMINI.md` in the
  sdist or wheel.

## Shipped in 0.23.1 (PRs #450-#455)

- [x] **LicenseID 0.7.2** (#455): its `too few words for text` notice (no
  licence in a short text) is relayed at `DEBUG`, not `WARNING:`; its
  `text_title` and `alias_name` readings (`New BSD`, `CC0 1.0 Universal`) are
  decided ids, said at `INFO:`. A test fails on a LicenseID category Pitloom
  has not decided on.

## Shipped in 0.23.2 (PRs #457-#459)

- [x] **Missing licence database** (#458): with no LicenseID database, a
  declared licence name (`New BSD`) says nothing; a declared licence text or a
  `LICENSE` file with no declared licence still warns.
- [x] **LicenseID 0.7.3** (#459): reads Apache names with a version
  (`Apache, Version 2.0`, `Apache License (2.0)`) as `Apache-2.0`.

## Shipped in 0.23.3 (PR #461)

- [x] **LicenseID 0.8.1**: reads a licence URL as its id
  (`https://www.apache.org/licenses/LICENSE-2.0` is `Apache-2.0`, category
  `license_url`) and drops a control or format character at either end of a
  value; a database built by LicenseID 0.7.x warns `build v3 outdated` until
  `licenseid update`. Python 3.15 is not tested: some `ai` extra wheels (such
  as `onnx`) have no 3.15 build yet.

## Shipped in 0.23.4 (PRs #462, #464, #465)

- [x] **LicenseID 0.8.4** (#462, #465, #464): 0.8.2 changed no Pitloom
  reading; 0.8.3 reads a `licenses.nuget.org` expression URL as its
  expression; 0.8.4 reads `MIT/Apache-2.0` as `Apache-2.0 OR MIT` (category
  `separator`). The upstream findings re-run on 0.8.4 are in
  [licenseid/upstream-issues.md](licenseid/upstream-issues.md).
- [x] **A model SBOM from a model file, folder or Git URL** (#464): one shared
  resolver for `loom model`, `loom generate`, `generate()` and the Git route,
  for all ten model formats; a file is a model by content, not suffix.
  Decided: a file URL beats a project beside it; a folder with several models
  is an error naming them; in a Git clone the native-library readers (fastText,
  GGUF, HDF5, ONNX, PyTorch) are not run and the model is listed by name,
  format and hash; a clone runs none of the repository's own build code and
  keeps no URL credentials, outside links or folder links. The Keras v3 reader
  adds layer count, optimiser, loss, metrics and archive members; one member
  that does not parse is one `WARNING:` and the other is still read. Not
  built: a Hub model file read by HTTP range requests
  ([hub-model-file-range-read.md](../design/hub-model-file-range-read.md)),
  recursive model discovery, the commit and URL in the SBOM. See
  [model-sbom-from-git.md](model-sbom-from-git.md).

## Shipped in 0.24.0 (PRs #468, #469, #471)

- [x] **PyPI URL targets and one remote-fetch policy** (#468): `loom wheel`,
  `loom project` and `loom generate` read a PyPI project or release URL (the
  wheel that fits the running Python and platform, or the sdist);
  `--max-download-bytes` caps every download (`max_clone_bytes` renamed;
  a Git URL defaults to 512 MiB); `RemoteFetchPolicy` replaces
  `check_url=`, `offline=` and `max_bytes=` on `fetch_git_project()`. Git,
  PyPI and Hugging Face share the `offline-unusable`, `download-network-failed`,
  `download-timeout` and `over-cap` codes; a Hub file read is capped and sent
  to the Hub or `cdn.hf.co` only. See
  [pypi-url-targets.md](pypi-url-targets.md) and
  [remote-fetch-policy.md](remote-fetch-policy.md).
- [x] **`--trust-model-files`** (#469): renamed from `--trust-wheel-model`
  (`trust_model_files`, Action input `trust-model-files`); also lifts the
  reader gate of a Git URL's model files.
- [x] **A licence text through a `LicenseExpression`** (#471): the declared and
  concluded licence relationships accept only `AnyLicenseInfo`, so a free-text
  licence is a `LicenseExpression` of one `LicenseRef-loom-text-<hash>` mapped
  to its text; classifier refs are `LicenseRef-loom-classifier-`; a merge fails
  on a licence relationship with wrong end types
  (`license-relationship-invalid`). See
  [license-free-text-wrapper.md](license-free-text-wrapper.md).

