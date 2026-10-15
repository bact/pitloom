---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: path keys, implementation plan (plan)

See also: [id-registry-path-keys.md](id-registry-path-keys.md)
(overview, status, decisions P1-P11),
[id-registry-path-keys-problem.md](id-registry-path-keys-problem.md)
(problem classes K1-K17),
[id-registry-path-keys-design.md](id-registry-path-keys-design.md)
(options A-C, worked example, surface matrix).

Part of the path-keys plan (see the overview for status and the section map).
Section numbers are the plan's own; D- and I-numbers refer to
[id-registry-v3.md](../implementation/id-registry-v3.md).

## 6. Risks and traps for implementers

- **Realpath on both sides, lexical first.** `registry_key_for_path` collapses
  `..` lexically before following symlinks; the fix round made
  `_resolve_id_generate_path` do the same in its fallback (`link/..` is the
  directory above the link as written). Keep the order in the new helper;
  `id generate` (`_project_relative`) realpaths the parent but not the file.
- **`built` must be an explicit flag**, not "the path is absolute": an
  included file outside the project but inside a monorepo root is absolute
  too, and `TMPDIR` may lie inside the root. Thread `ProjectFile.built`
  (CLAUDE.md, stage-scoped helpers); keep `project_relative_or_fallback` the
  only fallback.
- **sdist root:** drop exactly one leading component, the archive's single
  `name-version/` directory (normalised spelling `demo_pkg-1.0.0`); reuse the
  root detection of `_sdist_scan`, not a regex on the project name.
- **Wheel `.data/` members** (`*.data/data/...`, `scripts/`) have no project
  path: they stay distribution-path keyed. Do not let the alias rule match
  through them.
- **Alias determinism:** sort candidate keys, require one; a tie is a miss.
  Never pick by dict order (recurring pattern: unordered collections).
- **Hash objects:** never share one `spdx3.Hash` between a package and its file
  (8.1); G7 #3 copies the value into a new `Hash`.
- **NFC duplicates:** two on-disk files equal after NFC (possible on Linux)
  map to one key; `generate()` would otherwise re-mint on every run (`content
  changed` churn). Skip both with a `WARNING:`, like I5.
- **On-disk case:** obtain it by listing the parent and matching by
  `os.path.normcase` plus identity, never by `Path.resolve()` (keeps the
  caller's case on macOS); a path that does not exist keeps its spelling.
- **Windows:** keys are `/`-separated; `PureWindowsPath` drive or UNC outside
  the root is tier 2; dry-run every new path test as Windows would (CLAUDE.md
  checklist). Case-insensitive NTFS needs the same on-disk-case step.
- **Tri-state:** a lookup's recorded key is `None` (no lookup, e.g. a
  non-reader) vs a key; only the latter feeds harvest. `sha256=None` stays
  "ungated", never "empty hash".
- **Display escaping:** path keys are raw; keep the escaped retry for
  imported names, and record the raw key in the session map.
- **Re-keying is not minting:** promotion and R-keep must not touch
  `id_counters`; `Rebase.added` must not count a re-keyed id as new.
- **`replay_changes` with re-keys:** a promotion is a dropped key plus a new
  key holding the same id; the refusal loop must treat it as one change, not as
  "another run saved this id first".
- **`registry_key_for_path` calls `os.getcwd()`**, which raises when the cwd
  was deleted (open follow-up); the new helper must catch it.
- **The order-matrix invariant `_alias`** (`_order_invariants.py`) encodes
  I4's exception; update it with I4, or the harness reports false failures.

## 7. Implementation tasks (in dependency order)

Ratings: sensitivity (S: low/med/high) and the agent tier to use. Every
task: regression tests that fail on the base tree, Windows dry-run, linters.

1. **Key helper** (`id_registry/keys.py`, `resolve.py`): `artifact_key`,
   canonical path (lexical/identity/realpath, re-anchor, on-disk case, NFC,
   `getcwd` guard), the layout alias predicate replacing
   `_is_files_path_alias` and the `RegistryCopy` tail rule. Tests: parametrised
   boundaries (`..`, symlinked ancestor, outside root, other drive via
   `PureWindowsPath`, NFC/NFD, case, one vs two leading parts, tie). S high;
   Opus, high effort.
2. **`_element_key` NFC + generate ambiguity** (`_types.py`, `_format.py`,
   `_registry.generate`): NFC every key; load rejects a duplicate after NFC;
   two files with one key skipped. S high (determinism); Opus.
3. **`ProjectFile.built` flag** (`core/project.py`, `core/_models_wheel.py`,
   build-and-read): replace "absolute means built" for registry keys. S med;
   Opus or Sonnet with a precise brief.
4. **Session: alias lookup + key recording** (`_session.py`): try exact, then
   sdist strip, then layout alias (gated, unique); record id -> key for hits
   and post-miss mints (`record_key`). S high; Opus.
5. **Harvest by recorded key, R-keep, promotion; drop I4 exception**
   (`_harvest.py`, `_generators_shared._sync_registry`, `_persist.py`
   counting). Tests: merged loom fragment keeps the path key; `id import` of a
   merged SBOM keeps it; promotion of `demo/x.py` to `src/demo/x.py`;
   `replay_changes` with a promotion. S high; Opus, high effort.
6. **File surfaces** (`_document_files.py`, sdist, wheel, embed, hook):
   re-anchored physical key, sdist strip, alias for wheel/built. Drift guard:
   one fixture, `project`/`wheel`/`project <sdist>`/hook/library API all give
   each file the same id. S high; Opus.
7. **G7 #3** (`_ai_package.py`, `ai.py`, `_model_generator.py`, embed):
   `ai_AIPackage.verifiedUsing` copied (new `Hash`) from the model
   `software_File`; every model lookup gated (section 8). S high; Opus.
8. **Model keys to tier 1** (`_ai_package._ai_model_entity_candidates`,
   `_model_generator` `model`/`enrich`, `_loom_model._spdx_id`/`_record`,
   `IdRegistry.generate` registering model paths, not stems; shared-stem
   `INFO:` removed). Drift guard: one model file gets one id from loom
   (`set_model`/`use_model`), `model`, `enrich`, `project`, `wheel`, hook,
   `id generate`. S high; Opus.
9. **Dataset keys to tier 1, resolved at exit** (`_loom_dataset.py`,
   `_loom_active_run.py`): package key from the path when it exists; output
   datasets hashed and keyed at `finalize()`; per-run cache keyed by the
   canonical key. S high; Opus.
10. **`id generate -e` canonicalisation (P9)** (`cli/id.py`). S med; Sonnet.
11. **Manual checks and order matrix** (`scripts/manual_cli_checks`): a
    monorepo profile, an sdist reader op, a "run loom from a subdirectory"
    op, NFD file and upper-case spelling ops; `_alias` invariant updated;
    `_known.py` entries removed for fixed items. S med; Sonnet, then an Opus
    review of the invariants.
12. **Docs and skills** (`docs/id-registry.md` "What a registry pins",
    `docs/python-api.md`, `skills/sbom-generate/references/id-registry.md`,
    sentimentdemo README and regenerated registry, CHANGELOG one bullet,
    follow-ups/roadmap trimmed, implementation doc). S low; Haiku/Sonnet for
    the sweep, a fresh-eyes read of each changed `SKILL.md`.

Review points: after 1-2 (key shape frozen), after 5 (harvest semantics),
after 8 (cross-surface drift guards green), before merge (fresh-context
sweep of the whole range).

**Verification.** Mutation targets: the tie-break in the alias predicate,
the one-leading-part bound, the sdist strip count, NFC in `_element_key`,
R-keep, promotion, recorded-key preference in harvest, the gate on each model
lookup, the re-anchor relpath, the on-disk case step. Reversal probe corpus
(run HEAD and the branch; list every input that hit before and misses now):
flat project `generate -> project -> wheel`; src layout in all four orders of
`id generate` and `project`/`wheel`/`sdist`; monorepo root above project;
`--allow-build` src layout; `force-include` from outside the project;
`models/{a,b}/model.npy`; a GGUF/ONNX model whose own name differs from its
stem; two copies of one model at two paths; loom datasets as `data/t.txt`,
`./data/t.txt`, `../data/t.txt` from `scripts/`, an absolute path,
`DATA/T.TXT`, NFC vs an NFD file, `imdb`, `stanfordnlp/imdb`, a URL, an output
dataset declared before it is written, a directory dataset; a renamed file
with the same bytes; an edited file at the same path; a symlinked directory;
a file name with a control character via `id import`; `loom model user/repo`;
the sentimentdemo pipeline end to end (determinism: two runs, same bytes).
Expected losses to list and accept: old `-e` stem pins for pathful models
(P2a), dataset strings for datasets now found by path.

## 8. G7 #3

G7 #3 (roadmap "#3 Mechanical wiring": `ai_AIPackage.verifiedUsing` from its
model `software_File`) must land in this PR or before it, per the G7
blockers in [id-registry-followups.md](id-registry-followups.md). With path
keys it slots in as task 7, after the session alias lookup (4) and before the
model key switch (8): once every surface hashes the model, its lookup is
gated, so a retrained file at the same path misses and gets a new id (D3), and
harvest writes the recorded path key, so blocker 1 (a retrain laundered into
an old id) and blocker 2 (harvest keys `.name`, `id generate` keys the stem)
both close. Revisit the `id import` content-gate drop ruling then: an imported
project SBOM will carry the model's own hash.

## 9. Out of scope

- Same-type id coincidences and later-fragment collisions in a merge; the
  merge hash-survivor policy (follow-ups).
- Content-addressed model identity (one id for one model's bytes at any
  path): two copies at two paths stay two ids.
- `env` file-level keys, its root package, the `unknown` wheel sentinel, the
  per-document `SoftwareAgent`/`Tool` churn.
- Directory keys (P8a), wheel `.data/` members, hatch `sources` remapping
  other than one leading part, renames (P6a).
- Registry file locking, Windows `os.replace` retries, the loom
  claim-before-write race.
