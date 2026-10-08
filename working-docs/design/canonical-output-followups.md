---
Created: 2026-09-20
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Canonical output: open questions

See also: [roadmap.md](roadmap.md) (the "Canonical output" bullet),
[known-bugs.md](known-bugs.md) (reproduced bugs of the same theme),
[id-registry-followups.md](id-registry-followups.md) (id scheme), "SBOM
output" in [CLAUDE.md](../../CLAUDE.md) (bit-for-bit determinism, RFC 8785,
UTC).

The one home for open questions and undecided policy on canonicalisation,
normalisation and the stability of strings, keys and order in SBOM output:
anything that can change the bytes or an identifier for the same real-world
input. Decided and built rules stay in their implementation records, listed
under [Decided, where recorded](#decided-where-recorded).

**Guiding principle: cross-format consistency.** The same kind of value has
the same shape, the same spelling and the same destination in every AI
model format and on every surface (CLI, library API, Hatchling hook,
GitHub Action, Skills). The same input gives the same bytes, and the same
real-world thing gets the same identifier, whatever the format or surface.
Each rule is a policy first, then one shared helper, then a test that runs
every format and surface through it.

**Scope.** Not here: how `spdxId`s are minted and kept stable (registry
keys, namespaces, id length). Those are in
[id-registry-followups.md](id-registry-followups.md) and
[id-registry-v3.md](id-registry-v3.md). Where the two meet (name comparison
for registry keys, a capped name inside an id), each side links the other.
Reproduced bugs stay in [known-bugs.md](known-bugs.md); see
[Related bugs](#related-bugs-in-known-bugsmd).

Each question gives: the question, why it matters (which bytes or ids
change), options, current behaviour, recommendation if any, and owner.
Changing any pinned behaviour changes SBOM bytes for the same input, so it is
announced under CHANGELOG `### Changed`, not treated as an internal detail.

## Decided, where recorded

- **Sorted dict keys, UTC `Z` datetimes, LF and UTF-8 through one writer**
  (step 6.5):
  [sdist-own-config.md](../implementation/sdist-own-config.md#canonical-output-folded-in).
- **`@graph` element order** (type tier, then `spdxId`/`@id`, then the
  element's RFC 8785 form): built in `export/spdx3_json._graph_sort_key()`;
  rationale in
  [architecture-overview.md](architecture-overview.md#json-ld-graph-element-ordering).
- **Which `sorted()` calls are canonical** (fragment merge survivor,
  annotation statement arrays, file summary):
  [sort-order-canonicalization.md](../implementation/sort-order-canonicalization.md).
  Set elements in annotation values are ordered by their canonical JSON
  form:
  [annotation-provenance.md](../implementation/provenance/annotation-provenance.md).
- **sdist members sorted by `distribution_path` before minting** (#272):
  [sdist-own-config.md](../implementation/sdist-own-config.md).
- **Names in ids are percent-encoded, losslessly, not NFC-normalised, not
  cut** (#253): [iri-name-encoding.md](../implementation/iri-name-encoding.md).
- **Pinned by #294**: one display-escape set (`DISPLAY_CONTROLS`, lowercase
  `\uXXXX`), the 1024-character name cap and its cut layout (first 1012
  characters, `...~`, 8 hex digits of the SHA-256 of the full name), the
  4096-byte label cap, lone surrogates as `\udXXX`, scalar spelling
  (`scalar_text`, `-0.0` as `0`, float32 shortest decimal) and every
  embedded JSON text as RFC 8785 (`core/canonical_json`). Each has a drift
  test; growing the escape set also changes the `spdxId` of any name holding
  the new code points. See
  [annotation-mechanism.md](../implementation/provenance/annotation-mechanism.md#untrusted-model-text-annotation-as-read-display-escaped-2026-10-08),
  [scalar-text-spelling.md](../implementation/scalar-text-spelling.md).
- **Collections are arrays, scalars are text, in every format** (#294):
  [annotation-mechanism.md](../implementation/provenance/annotation-mechanism.md#value-types-in-artifact-metadata-metadata-2026-10-08).
- **The Hatchling hook always writes compact RFC 8785 output**, ignoring
  `pretty` (PEP 770):
  [hatchling-build-hook.md](../implementation/hatchling-build-hook.md).
- **Licence expressions in canonical term order; licence tie-breaks**:
  [license-rules.md](license-rules.md#8-determinism-and-tie-breaks).
- **Package names compare under PEP 503, versions under PEP 440** ("Recurring
  bug patterns" in CLAUDE.md); the registry key applies PEP 503 to
  `software_Package` only (`_element_key`, see
  [id-registry-v3.md](id-registry-v3.md)).
- **SHA-256 hex compared lowercase** (planned, step 1 of
  [id-registry-v3-rollout.md](id-registry-v3-rollout.md)); `sha256_hash()`
  already lowercases what it emits.

## 1. Identifiers and name comparison

### C1. Name comparison across element types

- **Question:** do AI model, dataset and fragment names compare with case
  or Unicode folding, as package names do under PEP 503, or as raw strings?
- **Why it matters:** registry keys, lineage lookup by `name` and enrich
  identity decide whether two runs reuse one `spdxId` or mint two, and
  whether a fragment folds into the right element.
- **Options:** raw string (state it); NFC only; NFC plus case fold; a
  per-type rule.
- **Current behaviour:** package names under PEP 503; every other name as a
  raw string.
- **Recommendation:** decide together with C2, as a matching rule separate
  from id encoding (which stays lossless, see
  [iri-name-encoding.md](../implementation/iri-name-encoding.md)).
- **Owner:** roadmap "Canonical output"; the registry side is
  `_element_key` in [id-registry-v3.md](id-registry-v3.md).

### C2. Unicode normalisation of names and labels

- **Question:** normalise read names and labels to NFC (or state that none
  is applied)?
- **Why it matters:** a name or label in NFC and the same text in NFD give
  different bytes and different ids.
- **Options:** NFC at the read choke point (`settle_read_text()`, where the
  cap applies); no normalisation, stated in the docs.
- **Current behaviour:** none. The id encoding decided against NFC *inside*
  the encoder, to stay lossless
  ([iri-name-encoding.md](../implementation/iri-name-encoding.md)); this
  question is about the name before it reaches the encoder, so the two do
  not conflict, but an NFC choice would change ids of NFD names.
- **Recommendation (from #294):** decide once, with C1, and apply it in the
  same place as the cap so identity and display agree.
- **Owner:** roadmap "Canonical output".

### Kept in the id-scheme docs

- `pitloom.loom` run namespaces (several `doc_name`s, a random document
  uuid per run):
  [id-registry-followups.md](id-registry-followups.md#pitloomloom-run-namespaces).
- `loom model` looks a model up by file stem, other surfaces by name:
  [known-bugs.md](known-bugs.md#p0-in-0210) ("Same AI model gets different
  ids per surface").
- Id length for long names (slug plus digest):
  [id-registry-followups.md](id-registry-followups.md#bounded-spdxid-minting-for-long-or-hostile-names).
- Case-insensitive and Windows-aliased wheel member names (one
  portable-name rule):
  [id-registry-followups.md](id-registry-followups.md#wheel-identity-and-archive-readers),
  [archive-member-followups.md](archive-member-followups.md).

## 2. Key and collection order

### C3. Key-order audit of project-metadata sources

- **Question:** does any dict or set from `pyproject.toml`, `setup.cfg`, lock
  files or installed metadata reach the SBOM in source order?
- **Why it matters:** two sources with the same content in another order
  would give different bytes.
- **Current behaviour:** not audited. AI model metadata is sorted at the
  choke points (step 6.5); `@graph` and object keys are sorted at
  serialisation, which does not reorder arrays.
- **Owner:** roadmap "Canonical output".

### C4. Which list orders are semantic

- **Question:** for each list-valued field, is the source order meaningful
  (keep) or incidental (sort)?
- **Why it matters:** RFC 8785 keeps array order, so an incidental order
  leaks into the bytes; sorting a meaningful one loses information.
- **Current behaviour:** `inputs`/`outputs` (tensor or I/O names) keep the
  source order, which can be meaningful (ONNX I/O).
- **Recommendation:** decide per field before sorting it; record the list.
- **Owner:** roadmap "Canonical output".

### C5. Key order for non-BMP keys

- **Decided (user, 2026-10-08):** switch the remaining `sort_keys=True`
  writers to RFC 8785 order. Not built yet; see the owner line.
- **Question:** move the remaining `sort_keys=True` writers to RFC 8785
  order (`core/canonical_json`)?
- **Why it matters:** RFC 8785 sorts by UTF-16 code unit, Python
  `sort_keys` by code point; they differ only where a non-BMP key meets
  U+E000 to U+FFFF.
- **Current behaviour** (grep of `src/`, 2026-10-08): embedded JSON and
  compact output follow RFC 8785. Two writers keep `sort_keys`: the pretty
  SBOM (`export/spdx3_json.py`, see C9) and the ID registry file
  (`id_registry/_registry.py`, not SBOM text).
- **Owner:** roadmap "Canonical output".

## 3. String normalisation and escape

### C6. Text sources outside AI models

- **Question:** apply the lone-surrogate rule and the display-escape set to
  every text source, not only AI model text?
- **Why it matters:** the same control character gives escaped bytes from a
  model file and raw bytes from project metadata.
- **Current behaviour:** applied to AI model text (and the README enricher's
  front matter); `Pipfile.lock`, project metadata and wheel member names are
  not audited.
- **Owner:** roadmap "Canonical output".

### C7. Inner line endings in text values

- **Question:** normalise inner CRLF/CR to LF in text values (licence
  texts, descriptions, model card text), or keep them as written?
- **Why it matters:** CRLF and LF copies of one text are two licence
  elements; surfaces disagree today, so one dependency gives different
  bytes per surface.
- **Options:** normalise to LF (line endings are encoding, not content);
  keep as written everywhere.
- **Current behaviour:** kept as written, except where a reader translates
  newlines: installed `METADATA` read through `importlib.metadata` loses the
  CR a wheel's `METADATA` keeps ([known-bugs.md](known-bugs.md#p3-after-0200)).
- **Recommendation:** none decided. The licence rules lean to normalising
  inner CRLF/CR to LF and keeping everything else as written
  ([license-rules.md](license-rules.md#open-questions), question 10, which
  keeps the licence-only parts: case, inner spacing, trailing `\r` in a
  name).
- **Owner:** license-rules question 10 for licence text; roadmap "Canonical
  output" for the rest.

## 4. Number, date and time spelling

### C8. One "now" per `embed-wheel` batch

Moved from [embed-wheel-followups.md](embed-wheel-followups.md).

- **Question:** read `now` once per multi-wheel `embed-wheel` batch? And
  should `_embed_wheel.py`'s ZIP entry timestamp, which also calls `now()`,
  share the batch's value?
- **Why it matters:** two SBOMs from one command can differ by a second in
  `created`.
- **Current behaviour:** the CLI resolves `CreationMetadata` once per batch
  but leaves `creation_datetime` unset, so each wheel calls `now()` for its
  own `created`.
- **Recommendation (leaning):** read `now` once, only when neither
  `creation-datetime` nor `SOURCE_DATE_EPOCH` is set, on both the CLI and
  the library `file_cache=` path. The ZIP timestamp is still open.
- **Owner:** embed follow-ups; found de-flaking PR #230.

## 5. Serialisation layers

### C9. Whole-document pretty mode

- **Question:** what does `pretty` promise: a reading copy only, or the
  canonical document plus whitespace?
- **Why it matters:** a pretty SBOM is not RFC 8785, so its bytes and any
  hash over them differ from the canonical one; with C5, its key order can
  differ too.
- **Options:** state "reading copy, not canonical"; make it RFC 8785 order
  with indentation.
- **Current behaviour:** indented, `sort_keys` order. The docs'
  pretty-printed examples show canonical key order for that reason. The
  Hatchling hook ignores `pretty`; that is stated only in its docstring
  ([config-cascade-parity.md](config-cascade-parity.md)).
- **Owner:** roadmap "Canonical output".

### C10. What "JSON-LD: follow RDF canonicalisation" means here

Found while consolidating this doc: CLAUDE.md asks JSON-LD to follow RDF
canonicalisation, and no working doc records how.

- **Question:** does Pitloom apply RDF canonicalisation (RDFC-1.0) at all,
  for example for blank-node labels or for comparing documents, or is
  RFC 8785 plus the `@graph` order the whole rule?
- **Why it matters:** blank-node labels (`_:CreationInfo0`) are serialiser
  output, not content; two fragments that each use `_:CreationInfo0` fail
  `loom fragment validate A B`
  ([known-bugs.md](known-bugs.md#p3-after-0200)). The SPDX canonical
  serialisation is silent on graph order
  ([spdx-spec#1362](https://github.com/spdx/spdx-spec/issues/1362), open).
- **Options:** RFC 8785 plus `@graph` order only (reword CLAUDE.md);
  RDFC-1.0 blank-node labels; RDFC-1.0 only to compare graphs.
- **Current behaviour:** RFC 8785 plus `_graph_sort_key()`; blank-node
  labels as the serialiser gives them.
- **Intent (user, 2026-10-08):** Pitloom should follow RDF
  canonicalisation (RDFC-1.0) as CLAUDE.md says, but it does not yet; the
  design needs thought first (scope: labels, comparison, or both; cost of a
  JSON-LD processor; interaction with `@graph` order).
- **Owner:** none yet.

## Related bugs in known-bugs.md

Reproduced bugs of this theme stay in [known-bugs.md](known-bugs.md):

- P0 in 0.21.0: one default SBOM file name (PEP 427 escaping) on every
  surface; the same AI model gets different ids per surface.
- P3: bidi controls in annotation keys are not escaped; ONNX graph and
  input names are not in the artifact-metadata annotation; a base model URL
  is unbounded; model provenance cites fields the SBOM never shows;
  installed `METADATA` is read unlike a wheel's (C7); two `loom.run`
  fragments share `_:CreationInfo0` (C10); the signed release wheel and SBOM
  are not reproducible (no `SOURCE_DATE_EPOCH`).

Other domain docs that hold related open questions:

- [license-rules.md](license-rules.md#open-questions): licence text
  equivalence (10), tie-breaks as written rules (16), licence URL folding
  (17); `LicenseRef-` case in
  [metadata-quality.md](metadata-quality.md).
- [archive-member-followups.md](archive-member-followups.md): `--allow-build`
  extraction folds case and NFC/NFD names on macOS and Windows, so the
  Source SBOM differs by OS.
- [sbom-package-boundary.md](sbom-package-boundary.md): a Merkle-root
  recompute recipe has to say how member names are normalised.
