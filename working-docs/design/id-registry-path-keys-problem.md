---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: path keys, problem classes (plan)

See also: [id-registry-path-keys.md](id-registry-path-keys.md)
(overview, status, decisions P1-P11),
[id-registry-path-keys-design.md](id-registry-path-keys-design.md)
(options A-C, worked example, surface matrix),
[id-registry-path-keys-implementation.md](id-registry-path-keys-implementation.md)
(risks, tasks, G7 #3, out of scope).

Part of the path-keys plan (see the overview for status and the section map).
Section numbers are the plan's own; D- and I-numbers refer to
[id-registry-v3.md](../implementation/id-registry-v3.md).

## 1. Problem: every collision and miss class today

Probes were run on 2026-10-15 against the working tree (registry-v3 branch
plus the v3 fix round of PR #305) in a scratch src-layout project
(`src/demo/x.py`, `models/{a,b}/model.npy`, `models/solo.npy`, `data/t.txt`),
a monorepo copy, and loom scripts. "Probed" marks a reproduced result.

Surfaces: `project` (directory, `--allow-build`, sdist target), `wheel`,
`embed-wheel`, `env`, `generate` (auto-detect, delegates), `model`, `enrich`,
the Hatchling hook, the library API (`generate_project_sbom()` and siblings),
`loom.Run` (datasets, files, script, models), `id generate`, `id import`,
merge/fragment harvest, the GitHub Action (wraps the CLI) and the skills
(`skills/sbom-generate/references/id-registry.md` and friends).

| # | Class | Surfaces | Where in the code |
| --- | --- | --- | --- |
| K1 | **src-layout split**: `id generate` keys `src/demo/x.py`; a wheel looks up `demo/x.py` (physical = `orig_filename`, distribution = normalised name). Misses unless a `project` harvest first wrote the alias key. Probed: an `id generate`-only registry gave every wheel file a document id, and the harvest then added `demo/x.py` under that **new** id, so one file has two ids in one registry. | wheel, embed-wheel, `--allow-build` | `_resolve_file_and_directory_hits` (`assemble/spdx3/_document_files.py`); `_hash_wheel_entry` (`extract/wheel.py`) |
| K2 | **Two keys, one id** (the intended alias): a `project` run writes `demo/x.py` beside `src/demo/x.py` with the same id (probed). Kept by I4's exception (`_is_alias`, `_is_files_path_alias` in `_harvest.py`); a second alias rule lives in `walk_rules.RegistryCopy`/`_DeclaredRegistry`. Reverse order (`id generate` after a wheel harvest) splits ids (order matrix `O1/src/fresh-cli`). | project, hook, wheel, id generate | `_release_stale_keys_for_id`, `_is_alias` |
| K3 | **sdist prefix**: members are `demo_pkg-1.0.0/src/demo/x.py`; nothing in the registry has that prefix. Probed: every file missed and the harvest added 21 prefixed keys. | project `<sdist>` | `_sdist_scan` (`physical_path=raw, distribution_path=name`) |
| K4 | **Registry root above the project** (monorepo): `id generate --project-dir .` keys `pkgs/demo/src/demo/x.py`; `project pkgs/demo` looks up `src/demo/x.py`. Probed: every file missed. Project-side keys are project-relative, never registry-root-relative. | project, hook, wheel, library API | `project_relative_or_fallback` callers; only loom uses `registry_key_for_path` |
| K5 | **Dataset package keyed by the caller's string** (ruling 2026-10-15): from `scripts/`, `../data/t.txt` and `./../data/t.txt` each miss the `data/t.txt` pin and mint (two `untracked entity` WARNINGs), while the `software_File` hits (probed). An absolute path string misses too. | loom | `LoomElements._package` (`_loom_dataset.py`) |
| K6 | **Same dataset, two spellings, one run**: two `dataset_DatasetPackage`s both `contains` one `software_File` (probed). The fix round's per-run cache (`LoomElements._packages`, keyed `(caller string, digest)`) merges only identical strings. | loom | `LoomElements.dataset` |
| K7 | **Case on a case-insensitive file system**: `DATA/T.TXT` on macOS keys the file `DATA/T.TXT`; both the package and the file miss (probed). `registry_key_for_path` keeps the tail as spelt. | loom (and any path a user types: `model`, `enrich`) | `registry_key_for_path` (`id_registry/resolve.py`) |
| K8 | **Unicode normalisation**: a file created NFD (`café.txt`) is keyed NFD by `id generate` (`os.walk` gives the on-disk form); a script passing NFC misses both package and file (probed on APFS). No key is normalised anywhere. | loom, id generate, wheel (member names are whatever the zip holds) | `_element_key` (`_types.py`) |
| K9 | **Shared-stem models**: `models/a/model.npy` and `models/b/model.npy` register one sha-less `ai_AIPackage model` (probed, `INFO: 2 model files share the name model`). In one document the second claimant gets the collision WARNING; across fragments (`loom model models/a/...`, `loom model models/b/...`) both get the **same** id, and a merge folds two models into one (no `verifiedUsing` before G7 #3, so the fix round's `hash_conflict` cannot keep them apart). | id generate, project, wheel, model, enrich, merge | `IdRegistry.generate`; `_model_generator` (`model_path.stem`) |
| K10 | **Model name vs stem**: `id generate` keys the stem; harvest keys `.name` (`AiModelMetadata.resolve_name()`: own name else stem); loom keys the declared `name=`; `project` tries own name, physical path, stem (`_ai_model_entity_candidates`); `model`/`enrich` try the stem only. Five candidate lists for one artifact (G7 blocker 2). | all model surfaces | listed functions |
| K11 | **PEP 503 only for packages**: `_element_key` canonicalises `software_Package` names; a model or dataset named `My_Model` vs `my-model` are two keys. Harmless for packages; for artifacts with a path the path is the better identity. | id generate `-e`, loom | `_element_key` |
| K12 | **Ambiguous-name harvest skip** (I5): two elements of one type and name in one document are not harvested. With path keys this stays for packages (two versions behind markers) and for wheel members that normalise to one name (#251). | harvest, id import | `_ambiguous_keys` (`_ambiguous.py`) |
| K13 | **Display-escaped retry**: `IdRegistrySession.lookup_id` also tries `escape_display_controls(name)`, because `id import` stores names as the SBOM shows them. A path computed from disk is raw; harvest from the SBOM is escaped: two spellings of one key. | id import, every lookup | `IdRegistrySession.lookup_id` |
| K14 | **Directory keys**: directories are looked up by distribution directory (`demo`), never by `src/demo`; `id generate` never registers one; a harvest writes them with document-namespace ids (probed). | project, wheel, sdist | `_resolve_directory_hits_for_file` |
| K15 | **`--allow-build`**: `physical_path` is absolute into a temp directory, so `project_relative_or_fallback` falls back to the distribution path: K1 again. An included file outside the project dir (`force-include ../shared/x`) is absolute too, and indistinguishable from a built one by the path alone. | project `--allow-build`, hook | `_physical_path` (`core/_models_wheel.py`) |
| K16 | **Same id, two contents in a merge**: fixed in PR #305 (`hash_conflict` in `_fragments_hashes.py`, `rename_id_clash` in `_fragments_ids.py`). Not a key problem; listed so this plan does not redo it. | merge | `_find_survivor` |
| K17 | **Harvest re-keys by `.name`**: a merged loom fragment's model or dataset carries the registry id it got by its loom key; harvest writes it under the element name and `_release_stale_keys_for_id` drops the other key (G7 blocker 2's mechanism). | project, wheel (merged fragments), id import | `_import_sbom_element` |

Not key problems, kept out (section 7): same-type id coincidences in a merge,
the `unknown` wheel name sentinel, `env`'s root package, the
per-document `SoftwareAgent`/`Tool` churn.

**Correction to the preliminary answer.** "Same dataset declared twice needs
a per-run package cache": the fix round already caches by `(caller string,
digest)`; what remains is K6 (two spellings), which path keys fix. "Merge
keeping two hashes on one id": the fix round's `hash_conflict`. "One artifact,
several paths": true, but the src-layout and sdist cases are derivable by rule
from one canonical path (section 2), so no stored alias table is needed for
them; only a rename needs one, and that stays a new identity (decision P6).
A further class the answer missed: K4, the registry root is not the project
root for any surface but loom.
