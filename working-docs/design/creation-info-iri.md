---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Content-derived `CreationInfo` IRIs (design note, not built)

Status: prototyped and reverted 2026-10-08; kept out of #294 to stop scope
growth. Fixes the `_:CreationInfo0` merge collision.

See also: [canonical-output-followups.md](canonical-output-followups.md)
(C10: RDFC-1.0 and blank nodes), [known-bugs.md](known-bugs.md),
[id-registry-followups.md](id-registry-followups.md).

## Problem (reproduced)

- The SPDX Python model labels a `CreationInfo` without an id as a blank
  node `_:CreationInfo{n}`, counting from 0 in each document.
- `spdx3-validate`'s merged-graph check (`loom fragment validate A B`)
  reads all documents into one graph; equal labels collapse into one node:
  two `created` values and a SHACL error. Each document alone, or with
  `--no-merge`, is valid. Reproduced with two `loom.run` fragments given
  different `creation_datetime`. `loom merge` of the same fragments works.
- A validator behaviour as much as a Pitloom one: the hand-written
  `tests/fixtures/fragments/ai-model-fragment.spdx3.json` and
  `dataset-fragment.spdx3.json` (both `_:creationinfo`) fail together too. A
  correct RDF merge keeps blank nodes apart per document; third-party input
  needs its own fix (relabel each document before the merged check, or
  report upstream).
- Separate defect: sentimentdemo fragments 01 and 03 share `File-1` with
  different `comment` values.

## What SPDX 3.0.1 and the bindings allow

- SHACL model: `CreationInfo` is `sh:BlankNodeOrIRI`. JSON schema 3.0.1:
  `CreationInfo.@id` is `BlankNodeOrIRI` (an IRI matches `^(?!_:).+:.+`);
  the key is `@id`, not `spdxId` (`CreationInfo` is not an `Element`).
- The spec pages say nothing about blank nodes versus IRIs or graph order.
- `spdx_python_model` v3_0_1: `CreationInfo.NODE_KIND = BlankNodeOrIRI`;
  `_id`/`set_id()` accept an IRI and the object is then a top-level node.
  Without an id the serialiser relabels, and may write a creation info that
  is referenced once and not in the object set inline, with no `@id`.

## One choke point

Every surface serialises through `Spdx3JsonExporter.to_json()`, which
already post-processes `@graph` once (`_deduplicate_creation_infos`,
`_deduplicate_named_elements`, sort). CLI `project`/`generate`, `wheel`,
`env`, `merge`, `model`, `enrich`, `embed-wheel`, the Hatchling hook,
`loom.run` fragments, the library API and the GitHub Action all reach it;
`fragment validate`, `validate-wheel`, `verify-wheel` and enrich reading a
base SBOM only read. Replace `_deduplicate_creation_infos` and
`_creation_info_fingerprint` there. The fragment merge skips `creationInfo`
and rewrites agent and tool ids, which changes content; renaming at export
time handles that. No src code special-cases `_:CreationInfo0`.

## Scheme

- Form: `https://spdx.org/spdxdocs/CreationInfo-<UUIDv5>`, built as
  `doc_namespace("CreationInfo", uuid5(PITLOOM_NS, canonical_json(content)))`;
  `content` is the node without `@id`, each array sorted by its items'
  canonical form (`createdBy`, `createdUsing` are unordered).
- Content only, not the document namespace: `loom.run` fragments have no
  `SpdxDocument` and a merged graph makes "which document" ambiguous.
  Equal content gives one IRI everywhere; any field change gives a new one.
  UUIDv5 (122 bits) over 12 hex digits for a shared namespace. Alternative:
  `urn:uuid:<uuid5>` (registered, but does not say what the node is). User
  decision.
- Post-process the serialised JSON in the existing pass: lift inline
  `creationInfo` dicts to top-level nodes; compute each IRI; map old `@id`
  to IRI (raise if one old id has two contents); rewrite every
  `creationInfo` string; keep one node per IRI. Stay in tier 0 of
  `_graph_sort_key`, sorted by IRI.
- Move `PITLOOM_NS` into `core/iri.py` (re-export from `core.models`) to
  avoid an `export -> core.models -> ... -> core.config` import cycle.

## Evidence from the prototype

Two `loom.run` fragments got distinct IRIs and `fragment validate A B`
passed; the new test failed on the base tree. `spdx3-validate` passed on a
project SBOM, an ONNX model SBOM, a merge of two runs, an enrich fragment
merged with a model SBOM, and `fragment validate` of four documents. Bytes
were identical under `PYTHONHASHSEED` 0, 1 and 12345. Full suite 10527
passed, 100% coverage, linters clean. `loom merge` keeps three nodes (two
runs plus the merged document's own); their IRIs change as agents unify.

## Risks and decisions

- Every SBOM's bytes change (every document has a creation info): CHANGELOG
  entry.
- `spdx.org/spdxdocs/` IRIs match the document-namespace practice; an SPDX
  expert may prefer `urn:uuid:`.
- A creation info holding an inline element whose own `creationInfo` is a
  blank label would feed that label into the hash; Pitloom always adds
  agents and tools to the object set, so it does not occur today.
- The RDFC-1.0 route (C10 note) gives deterministic blank-node labels but
  not merge safety; both may be wanted.

## Plan (about 0.5 to 1 day)

1. Helper module, wire into the exporter, move `PITLOOM_NS`.
2. About six compact tests: IRI shape; content parametrised over `created`,
   `createdBy`, `createdUsing`, `specVersion`, `comment`; rename, dedup and
   inline lift; the ambiguous-label error; one node per content in pretty
   and compact output; a network-marked CLI regression (two `loom.run`
   fragments, merge, `fragment validate`). Update
   `test_spdx3_compliance_structure.py` (asserts the `_:CreationInfo`
   prefix) and replace the `_deduplicate_creation_infos` tests in
   `test_spdx3_compliance_shacl.py`.
3. Manual check 7: no blank creation-info ids; every `creationInfo`
   reference resolves.
4. Docs: `docs/fragments.md` paragraph; the `spdx-modelling.md` field note
   ("Pitloom emits `_:CreationInfo0`"); remove the known-bugs entry; roadmap;
   C10 status line.
