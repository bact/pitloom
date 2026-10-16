---
Created: 2026-10-16
Last-Modified: 2026-10-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: keying an id registry by path

See also: [README.md](README.md) (index of these notes),
[id-registry-v3-lessons.md](id-registry-v3-lessons.md) (the typed,
content-gated registry this builds on),
[open-research-questions.md](open-research-questions.md) (the name-or-path
question before it was built),
[id-registry-path-keys.md](../id-registry-path-keys.md) and
[id-registry-path-keys-decisions.md](../id-registry-path-keys-decisions.md)
(the design record).

Lessons from changing a registry's keys from names to paths (Pitloom, 2026-10-16,
built on top of registry v3). Evidence is Pitloom's: an SPDX 3 AI-BOM generator
whose ids must stay the same across runs, builds and surfaces. Each item gives
the evidence and one "Do:" rule. Counts are from the built tree: full suite
13461 passed at 100% branch coverage.

## 1. Path key versus name key for an AI-BOM identity

- **What a path key keeps stable.** A model's path below the registry root
  (`models/sentimentdemo.bin`) is the same text on every surface that sees the
  file: the project scan, a built wheel, an embedded SBOM, a `loom` script that
  passes the path, `id generate`. A name key was spelt five ways for one model
  (the declared name, the file stem, the model's own internal name, a
  physical path, a distribution path), so two surfaces could mint two ids and
  two models with one stem (`a/model.npy`, `b/model.npy`) shared one.
  Do: key an artefact by something every surface can derive without asking
  the artefact what it calls itself.
- **What a path key changes.** A rename or move is a new identity (the file is
  a different place in the app; a stored alias table was rejected as state to
  garbage-collect). A retrain at the same path is the same key and, with a
  content gate, a new id: the path says which artefact, the hash says which
  version. A model with no file (a Hugging Face id) or a dependency keeps its
  name key: two tiers, not one.
  Do: state what a rename and a retrain mean before choosing the key, since
  the key and the gate split identity between them.
- **The key is not the name.** The element's `name` stays what the user
  declared (`input_datasets=` matching depends on it); only the registry key
  moved. Keeping the two apart let the change land without an API change.

## 2. One helper per cross-cutting choice

- **Every surface that spelt a key by hand drifted.** Before the change a
  file key was computed in the project scan, the wheel reader, the embed
  overlay, `id generate`, loom and the sdist reader, each with its own prefix
  handling; a model had a separate routine per surface. After: one module
  (`pitloom.id_registry.keys`) computes every key, and a drift guard runs one
  src-layout fixture through every surface (project, `--allow-build`, sdist,
  wheel, embed-wheel with and without a project directory, hook, library API,
  `model`, `enrich`, loom, `id generate`) and asserts one id per file and per
  model.
  Do: for a choice that every surface must make the same way, give the
  surfaces one function and one test that runs them all; a test per surface
  cannot see two surfaces disagreeing.
- **Explicit flags beat inference from a value.** "An absolute `physical_path`
  means a built file" is wrong when an included file outside the project is
  absolute too; the reader now sets `ProjectFile.built` and the document
  carries a `FilesOrigin` (project directory, archive, sdist).

## 3. Harvest by lookup key, not element name

- **Write what you looked up.** Harvest wrote each element under its `name`.
  A merged loom fragment's model, found by its path key, was written back
  under its name and its path key was released as stale. The session now
  records the key each lookup used and harvest writes that; an element with no
  recorded key (a merged fragment, an imported SBOM) never moves an id the
  registry holds under another key of its type.
  Do: when reading and writing a table are separate steps, carry the key
  between them instead of recomputing it from the thing it identified.
- **Re-keying is not minting.** Promotion (replace a held alias with the
  canonical key) and keep-rule moves touch no counters and do not count as a
  new id.

## 4. A loose alias rule, found three ways by an independent review

- **The rule.** A wheel names `demo/x.py` where the source tree holds
  `src/demo/x.py`. The first design matched a held key that is the lookup with
  exactly one leading part added, equal hash, unique.
- **Three failures, one review.** (a) Identity theft: `tests/foo/__init__.py`
  and `foo/__init__.py` both real, both empty, so equal in bytes: the wheel
  file took the test file's id. (b) The candidate search walked every held key:
  quadratic in the registry. (c) Every empty `__init__.py` equals every other,
  so hash equality alone binds unrelated files (the "zebra" case).
  The unit tests, written from the rule, were green.
- **The narrowing.** Only a leading `src` or `lib`; two parts must remain; not
  a wheel `.data` member; equal hash; unique; and the shorter key must not
  exist on disk, so two real files are never an alias. Candidates are built
  from the input (at most one held key per root) and looked up in the
  dictionary.
  Do: write the test where both keys exist as real files with equal content,
  and derive candidates instead of scanning for them.

## 5. A hybrid gate for datasets: pins before data exists

- **The trade-off.** A dataset package could be gated by content (a refreshed
  dataset is a new package, as a retrained model is) or left ungated. A strict
  gate fails a legitimate workflow: the user pins `data/new.txt` before the
  pipeline writes it, so the pin has no digest to hold. The built rule is
  hybrid: a pin with no hash hits any content and says so in an `INFO:`; an
  entry with a hash is gated (file SHA-256, directory Merkle root); the
  consequence that a file added to a directory dataset changes its Merkle root
  and re-mints the id is documented, not hidden.
  Do: when a gate meets an object that is created later than the pin, decide
  what an absent hash means and say it in the output.
- **One package per (key, digest) per run.** `data/t.txt`, `./data/t.txt`,
  `../data/t.txt` from a subdirectory, an absolute path, another case and NFC
  versus NFD all name one package once keyed by path.

## 6. An INFO for every deviation

- Every fallback, cap or deviation prints one `INFO:` with the registry prefix,
  once per document, element or pin, never per file in a loop (an
  alias-hit count, a name-key fallback, a gate miss, a hash-less pin, a `-e`
  stored by name). A reader of the log can reconstruct which rule decided each
  id without reading the code, and the family greps as a group.
  Do: add the message in the same change as the branch it describes; a branch
  that deviates silently is a bug even when the output is right.

## 7. An ML pipeline's order of work against the gate options

- A training pipeline downloads raw data, writes processed data, trains,
  evaluates, and only then has every file to hash. Where the registry pin
  goes relative to that order decides what a gate can mean: pin raw data
  after download (hash exists, gate works), pin it before (hybrid pin, no
  hash), and outputs written by the pipeline (processed data, the model
  itself) cannot be pinned by content before they exist; a pin made earlier
  stays hash-less until `id import` or `-e` records a digest. Declaring an output dataset before the step writes it
  gives the hash of the file it replaces (open follow-up: resolve outputs at
  run exit, as models already are).
  Do: draw the pipeline's write order next to the gate options before
  deciding which objects are gated and which pinned.

## Expected losses (stated once)

Old `-e STEM:ai_AIPackage` pins, dataset string pins that differ from the
canonical path, multi-part Hatch `sources` remaps for wheel-only lookups, raw
un-normalised archive member names; registries from the earlier unreleased v3
branch are regenerated and ids may renumber once. *Unverified:* how many
users pinned model stems.
