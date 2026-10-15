---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Annotation provenance plan -- follow-ups, acceptance, hardening

See also: [`annotation-provenance.md`](annotation-provenance.md) (goal,
current state, settled design decisions, statement schema -- §1-4) and
[`annotation-provenance-implementation.md`](annotation-provenance-implementation.md)
(§5-7). This part holds §8 Out of scope / follow-ups, §9 Acceptance
criteria and §10 Security/robustness hardening; section numbers (§N) are
continuous across the parts.

## 8. Out of scope / follow-ups

- **Adopting an external AI-model / general provenance schema** as an
  additional `ProvenanceEncoder` (§4.2). The plumbing lands now; a concrete
  second encoder is a later change. Candidate schemas to evaluate when we do:
  - **W3C PROV-O** — general provenance ontology (`prov:wasDerivedFrom`,
    `prov:wasGeneratedBy`, `prov:Activity`); maps naturally to RDF/Turtle and
    would let `contentType = "application/ld+json"`.
  - **SLSA provenance / in-toto attestations** — build/supply-chain focused;
    strong for "how was this produced" attestation.
  - **Croissant** provenance fields — already partly consumed for datasets
    ([`src/pitloom/extract/dataset/croissant.py`](../../../src/pitloom/extract/dataset/croissant.py));
    natural fit for dataset subjects.
  - **Hugging Face model-card / model-index** metadata as a first-class
    encoder for AI subjects (source SHA, author, repo URL).
  When choosing, prefer one whose id maps cleanly onto Pitloom's internal
  `field -> source` map and can round-trip through the `Annotation.statement`
  string (or an `application/ld+json` body).
- Per-field granular annotations for SPARQL queryability (only if a consumer
  needs it).
- Moving `known_biases` out of `comment` into proper `ai_*` properties.
- Flipping the config default from `"both"` to `"annotation"` (separate change
  after downstream consumers updated).

---

## 9. Acceptance criteria

- [x] `provenance.py` module: parser, `ProvenanceEncoder` protocol + registry +
  `resolve_encoder`, `PitloomV1Encoder`, annotation builder — with unit tests
  ([`tests/assemble/test_annotation_provenance_core.py`](../../../tests/assemble/test_annotation_provenance_core.py)).
- [x] `exporter.add_annotation` and inclusion in graph/SBOM output.
- [x] `[tool.pitloom.provenance] format` (default `"both"`, validated at
  config-load time) and `schema` (default `"pitloom/1"`, validated at first
  SBOM generation — see §5.4's "as implemented" note) config.
- [x] All six call sites (§2.2) migrated behind the toggle.
- [x] Emitted annotations pass SPDX 3 compliance tests
  ([`tests/assemble/test_spdx3_compliance_shacl.py::test_spdx3_provenance_annotations_are_compliant`](../../../tests/assemble/test_spdx3_compliance_shacl.py)).
- [x] Output is byte-stable across two generations (determinism preserved) —
  verified cross-process with a fixed `creation_datetime`, both for
  `generate_project_sbom()` and the `pitloom.loom` SDK path.
- [x] Existing `test_provenance.py` extraction assertions still pass.
- [x] A second (stub) encoder can be registered without editing call sites —
  demonstrated by
  [`test_swapping_encoder_changes_output_without_changing_wiring`](../../../tests/assemble/test_annotation_provenance_core.py)
  and [`test_build_provenance_annotation_uses_given_encoder`](../../../tests/assemble/test_annotation_provenance_core.py).

### Found and fixed during implementation review

- `emit_provenance` originally matched neither `if` branch for an
  unrecognized `provenance_format`, silently dropping the provenance with no
  comment, no Annotation, and no error — contradicting its own docstring's
  claim of a `"both"` fallback. Fixed to raise `ValueError` (matching
  `resolve_encoder`'s fail-fast pattern); regression test:
  `test_emit_provenance_unknown_format_raises`. The `pyproject.toml`-driven
  path was never affected (`core/config.py` already validated `format`
  eagerly) — this only mattered for direct API/library callers.
- [`metadata-provenance.md`](metadata-provenance.md)
  described only the pre-Annotation `comment`-based mechanism; updated to
  document Annotation as the primary mechanism with `comment` as the
  back-compat path.

### Deliberately out of scope (not attempted)

- CLI flags (`--provenance-format` / `--provenance-schema` / `--provenance-detail`
  / `--provenance-preserve-source-metadata`) mirroring
  `--describe-relationship`'s per-command precedence/diagnostics table in
  `__main__.py`. None of the four `[tool.pitloom.provenance]` keys has a CLI
  flag; all are reachable only via `pyproject.toml` or explicit keyword
  arguments to the library API. Not required by these acceptance criteria; the
  `pyproject.toml` config path is fully wired end to end (CLI, Hatchling
  build hook, and library API all honor `[tool.pitloom.provenance]` or
  explicit keyword arguments).
- `pitloom.loom` always uses `provenance_format = "both"` (hardcoded, not
  config-driven) — it is a standalone SDK invoked from ad hoc scripts, not
  through a `pyproject.toml`-based config; see the comment at
  `src/pitloom/_loom_active_run.py`'s `_LOOM_PROVENANCE_CONFIG`.
- Demo/example SBOM fixtures under `examples/sentimentdemo-aibom/` were not
  regenerated (no test depends on their exact content; they now simply show
  the pre-Annotation output format).
- §8 follow-ups (external schema encoders, per-field granular annotations,
  moving `known_biases` out of `comment`, flipping the default format) —
  unchanged, still future work.

---

## (Former §10) Boundary refinement, role vocabulary, use-case catalog, and G2 -- moved 2026-08-25

This section originally covered non-native/high-signal Annotation
boundaries, the `role` vocabulary, the G1-G4/A1-A2/E1-E2/P1 use-case
catalog, and the Phase 2 native-first backfill checklist -- it grew past
this file's own 800-line size cap and was split into four sibling files
in this directory:

- [`annotation-mechanism.md`](annotation-mechanism.md) -- when/how to use
  the Annotation mechanism at all (boundary principle, extrinsic-assertion
  test, high-signal test, config, statement-envelope convention).
- [`role-vocabulary.md`](role-vocabulary.md) -- the `role` vocabulary
  (`declared`/`detected`/`externalReported`/`inferred`/`sbomAuthorSupplied`),
  decision rule, source-recording convention, role-to-native mapping.
- [`use-case-catalog.md`](use-case-catalog.md) -- the G1-G4/A1-A2/E1-E2/P1
  catalog and the Phase 2 N1-N6 backfill checklist.
- [`multi-source-conflict.md`](multi-source-conflict.md) -- G2's own
  implementation depth (license-conflict schema, normalization logic,
  what's built, real-world validation, future candidate sources).

## 10. Security/robustness hardening (2026-07-21)

Agent-driven adversarial review of the provenance-string construction and
JSON-serialization paths (`record_dict_field_provenance`, `_sanitize_for_json`)
found and fixed two real gaps:

- **Provenance-string delimiter injection.** Both a dict key from an
  untrusted binary artifact (a GGUF kv key, a safetensors `__metadata__`
  key, ...) *and* the model's filename (`f"Source: {model_path.name}"`,
  built independently in all nine AI-model extractors) flow unescaped into a
  `"Source: X | Field: Y"` provenance string. A crafted value containing
  `"| Source: pyproject.toml"` would inject a fake segment that
  `parse_provenance_value` re-parses as if the field came from a transparent
  manifest -- misattributing the source and, in the default minimal-detail
  mode, silently dropping the entry entirely. Fixed with a shared
  `sanitize_provenance_text()` (`_extract_utils.py`) that escapes `|`,
  applied both inside `record_dict_field_provenance` (the key) and at every
  `source = f"Source: {model_path.name}"` construction site (the filename) --
  the first fix (key-only) was caught as incomplete by a follow-up
  adversarial audit before this file was updated.
  **Scope boundary, not fixed:** `dataset/croissant.py`/`project/pyproject.py`/
  `project/setuptools.py`/`_license.py` build `"Source: {path}"` strings with the
  identical unescaped pattern, but never call `record_dict_field_provenance`
  and were outside the audited AI-extractor scope; their inputs (project-local
  paths, PEP 621 field values) are a different, generally lower trust
  boundary than an arbitrary downloaded binary model file. Worth revisiting
  with the same `sanitize_provenance_text()` if that trust assumption changes.
- **Non-deterministic/invalid JSON in the P1 preservation blob.**
  `json.dumps`'s `default=` hook is never called for a `float`, so a
  malformed model's NaN/Infinity metadata value round-tripped into the
  non-standard `NaN`/`Infinity` JSON tokens (RFC 8259 forbids them); a `set`
  value fell back to `str()`, whose iteration order is
  `PYTHONHASHSEED`-dependent. Fixed with `_sanitize_for_json()`, a recursive
  pre-pass that converts NaN/±Infinity to string tokens and orders set
  elements by their *canonical JSON form* rather than Python's native `<` --
  ordering by `<` was tried first and rejected: `sorted()` can silently
  succeed without raising `TypeError` for types whose `<` isn't a total order
  (e.g. `frozenset`, where `<` means "is a proper subset of"), so a
  set-of-frozensets stayed input-order-dependent even after the first
  attempt.
  **Known-dormant, not fixed:** extractors are expected to normalize
  numpy/library-native scalars (via `.tolist()`/`.item()`) before they reach
  `raw_metadata` -- confirmed true of every current extractor against real
  fixtures -- so `_sanitize_for_json` doesn't special-case numpy types. A
  future extractor that skips that normalization would silently mis-serialize
  (e.g. a `numpy.int64` becoming a JSON string via the generic `default=str`
  fallback); noted in the function's docstring as an assumption, not guarded
  against, since guarding it well requires a numpy dependency this module
  doesn't otherwise need.

Also documented (`use-case-catalog.md`, P1 Preservation bullet): the P1 blob has no size cap, so a
production-scale model's large arrays (e.g. a 32K+ entry GGUF vocab table)
could produce a multi-megabyte `Annotation.statement`. Not a spec violation
(`statement` is unbounded `xsd:string`), not exercised by the small test
fixtures, and deliberately not truncated (silently cutting array data would
make "verbatim preservation" dishonest) -- `preserve-source-metadata = "never"`
is the escape hatch for large models today.
