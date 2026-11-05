---
Created: 2026-11-02
Last-Modified: 2026-11-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs: AI model readers and metadata

See also: [known-bugs.md](../known-bugs.md) (index, severity scale,
rules for adding an entry), [roadmap.md](../roadmap.md),
[model-metadata-readers.md](../model-metadata-readers.md),
[canonical-output-followups.md](../canonical-output-followups.md),
[model-format-mapping-parity.md](../../implementation/model-format-mapping-parity.md).

AI model files (GGUF, ONNX, PyTorch PT2, Keras and HDF5, Safetensors,
fastText, CRFsuite, NumPy): what each reader records, what the SBOM shows of
it, and how metadata is escaped, capped and spelt across formats. Entries are
ranked by priority tier, then by size tag; see the severity scale in the
index. Open entries come first; fixed entries stay in the last section for
history.

## Open

### P3: after 0.20.0

- [ ] **`AiModelUsage` has no producer (M).** `limitations`,
  `safety_risk_assessment`, `known_biases`, `intended_use` and
  `unintended_use` are assembled (`_ai_package.py`) but no reader or Hugging
  Face fetch fills them. Wire a source (model card sections) or drop them.
- [ ] **ONNX loads the whole protobuf into memory (M).** `onnx.load(...,
  load_external_data=False)` still parses every graph node. fastText's full
  load is logged above; both go with the metadata-only readers in
  [model-metadata-readers.md](../model-metadata-readers.md).
- [ ] **Model provenance cites fields the SBOM never shows (S-M).** Found
  in the CRFsuite review (same for fastText and others): `framework`,
  `format_version` and `properties.*` get provenance in the package comment
  and fields annotation, but nothing in `assemble/` emits those fields, and
  a shipped model skips the artifact-metadata annotation under
  `preserve-source-metadata=auto`, so the values (e.g. CRFsuite labels
  beyond the 20 in the description) appear nowhere. Either emit them or
  drop their provenance. Repro: `loom project` (or `loom wheel`, auto mode)
  on pythainlp gives 8 `ai_AIPackage` and 0 artifact-metadata annotations,
  while each `fields` provenance still cites `properties.*`.
- [ ] **Model dtype vocabularies differ across formats (S-M).** Found in
  #294: ONNX and NumPy write NumPy names (`float32`), Safetensors its own
  (`F32`, `BF16`). Pick one vocabulary for `inputs`/`outputs` `dtype`.
- [ ] **Deep metadata text depends on call-stack depth (S).**
  `core/ai_metadata.py` `_collection_text` falls back to
  `<nested over 32 levels>` on `RecursionError`, so the CLI and the
  Hatchling hook (deeper stack) can write different bytes for a 500-950
  deep PT2 `extra/tags`. Decide from an explicit depth count.
- [ ] **Label count recorded differently (S, cross-format).** CRFsuite
  always has `properties.num_labels`; fastText only `outputs[0].shape`,
  and nothing when all labels are dropped. CRFsuite with 0 labels emits
  `labels = "[]"`, supervised fastText with none emits nothing.
- [ ] **Escape/cap hardening from the Opus review of #294 (S each).**
  (a) Hangul fillers U+115F, U+1160, U+3164, U+FFA0 render blank but are
  not in `DISPLAY_CONTROLS`; add, plus a test that every Bidi_Control is
  in the set or on a named exclusion list. (b) U+200B-U+200D are escaped
  in prose, so Thai/Persian/Indic ZWNJ/ZWJ text is mangled and warns;
  escape them only in identity fields. (c) done in #426: fastText
  caps its labels at 1,000 as CRFsuite does (over the cap it records none,
  keeps the label count and warns once). (d)
  Lone-surrogate escape runs before the name cut, which may split `\udXXX`.
  (e) Format-only stub entries skip `settle_read_text` (non-UTF-8 stem would
  raise `CanonicalizationError`); `physical_path` should stay out of the walk.
  (f) `_license_classify._replace_surrogates` uses U+FFFD, the shared
  rule `\udXXX`.
- [ ] **AI model `framework` provenance cites a value the SBOM never
  shows (S).** Found in the #292 black-box round, same on `main`: ONNX
  `producer_name`/`producer_version` land in `format_info.framework*` and
  their provenance reaches the package comment and annotation, but nothing
  in `assemble/` writes `framework` (nor `framework_version`). Either emit
  it or drop its provenance (check the other readers).
- [ ] **A model licence that is a name or URL becomes licence text (S).**
  Found in the #292 black-box round: ONNX `model_license` "Apache License
  2.0" gives a `SimpleLicensingText` holding the name, not `Apache-2.0`; a
  URL is kept as text, not a reference. The rule to apply is open: C12 and
  C18 in [canonical-output-followups.md](../canonical-output-followups.md).
- [ ] **`loom model` on a 100-byte truncated `lid.176.ftz` ran to about
  20 GB RSS (S).** Native fastText reader on a hostile header, found in the
  CRFsuite review (a 400-byte cut reached about 7 GB); the metadata-only fastText reader in
  [model-metadata-readers.md](../model-metadata-readers.md) closes it.
- [ ] **Bidi controls in annotation keys are not escaped (S).** Found in
  #294: a model key with U+202E stays raw as a key of a provenance
  annotation's `fields` object (`hyperparameters.<key>`) and in an
  enrichment annotation's `changes[].field`/`after` (`datasets:<name>`,
  uncut too). Both are JSON statements, not display properties; escaping
  them needs the dict key kept raw for lookups and the display form only at
  the statement, through `escape_display_controls_in_json`. Documented in
  `metadata-reading-back.md`. The artifact-metadata annotation stays as
  read by design.
- [ ] **ONNX graph and input names are not in the artifact-metadata
  annotation (S).** Found in #294: the docs say the annotation keeps the
  text the display escape changed, but ONNX `raw_metadata` holds only
  opsets and `metadata_props`, so an escaped graph or input name has no
  original in the SBOM. Add them, or narrow the claim per format.
- [ ] **A base model URL is unbounded (S, needs a decision).** Found in
  #294: the base model name is cut at 1024 characters, but its `externalRef`
  locator (`https://huggingface.co/<id>`) keeps the whole id read (a 1 MiB id
  gives a 1 MiB locator, `_ai_package.py`). Decide: drop the `externalRef`
  when the id is over `MAX_MODEL_NAME_CHARS` (with an over-cap `WARNING:`
  such as "base model URL dropped"), or cut the locator as the name is cut.
- [ ] **Over-cap CRFsuite model keeps only its name (S).** A model with more
  than 1,000 labels (or a hostile `num_labels`) gets the stub entry, though
  the header counts are cheap to read. Same stub rule as every format;
  revisit with the metadata-only readers.
- [ ] **Licence provenance can cite a property key the entry cap
  dropped (S).** Found in the #292 black-box round: with 1,500
  `metadata_props` and `model_license` last, the licence is still read
  (correct) and cites `Field: metadata_props.model_license`, a key no
  longer in the capped `properties`. Harmless (the field name is a pointer
  into the file, not the SBOM); decide whether the cap keeps keys that
  other fields cite.
- [ ] **Keras v3 does not read `compile_config` (S).** The HDF5/Keras v1-v2
  reader takes optimizer, loss and metrics from `training_config`; the v3
  reader (`keras.py`) reads `config` and `build_config` only.
- [ ] **PT2 / ExecuTorch reader never sets `type_of_model` (S).** No
  `ai_typeOfModel` for a `.pt2`, though `framework="executorch"` is set.
- [ ] **GGUF licence `other` and comma lists (S, needs a decision).**
  Questions, moved to
  [canonical-output-followups.md](../canonical-output-followups.md#6-licence-identifiers-expressions-and-texts)
  (C15, C16).
- [ ] **GGUF `general.license` with a zero-width character (S).** A
  question, moved to
  [canonical-output-followups.md](../canonical-output-followups.md#c17-invisible-characters-at-the-edges-of-a-licence-value)
  (C17).
- [ ] **PT2 lists lifted parameters as inputs; framework `executorch` (S).**
  Inputs fixed 2026-10-17: only `signature.input_specs` `user_input` entries
  are read. Open: the framework. (Original report:) `example-model.pt2` (`archive_format` `pt2`: a `torch.export` archive, not
  an ExecuTorch `.pte`) gives inputs `p_line_weight`, `p_line_bias`, `x`;
  `signature.input_specs` marks only `x` as `user_input`. Read user inputs
  only, framework `pytorch` with `torch_version` (`2.11.0`, unread). The
  fixture's `details/pytorch-pt2.md` claims `inputs` = `[x]`. Malformed
  `model.json` shapes: see the fixed PT2 entry under Fixed, P3.
- [ ] **Safetensors name and framework (S).** `ss_base_model_version` (the
  base model, not this one) is a name candidate; prefer `ss_output_name`.
  Framework is the raw `format` value `pt`, not `pytorch`.
- [ ] **Keras `layer_count` counts `InputLayer` (S, needs a decision).**
  `len(layers)` in `hdf5_config.py`; a Sequential with an `InputLayer` and one
  `Dense` gives 2. Keras 3 and a Sequential's `model.layers` leave the
  `InputLayer` out, but a Keras 2 functional model counts it. Pick the rule;
  `test_hdf5_hostile_attrs.py` pins the current count and must flip.
- [ ] **Type of model holds a class or training mode (S).** PyTorch
  `OrderedDict` (a state dict) and fastText `supervised`/`cbow`/`skipgram`
  reach `ai_typeOfModel`; neither is a model type. Map or drop.
- [ ] **`software_primaryPurpose` never set on `ai_AIPackage` (S).**
  Documented as fragment-only; decide whether a model gets `model` by default.
- [ ] **Quantised fastText (`.ftz`) leaves `quantization` empty (S).**
  `args.qout`/the quantised state is never read.
- [ ] **CRFsuite description ambiguous; hash-table offset 0 (S).** Empty,
  comma or backslash labels read ambiguously in `CRFsuite model with N
  labels: a, b` (quote them). `_check_hash_tables` skips a table with offset
  0 even when its count is non-zero.
- [ ] **Unreadable model handling differs by case (S).** A truncated
  `.crfsuite` or `.onnx` exits 0 with a `WARNING:`; an empty `.model`
  exits 1 with `ERROR: ... not an AI model file`. The ONNX warning repeats
  itself: `failed to extract metadata; Failed to load ONNX model from <path>`.
- [ ] **Keras v3 `config.json` is parsed apart from Keras v1/v2 (S).** Found
  in the #294 review. A non-string `class_name` or `config.name` is fixed by
  #426 (the field is skipped with one `WARNING:`). Open: `keras.py` has its
  own `_parse_model_config`; share `hdf5_config.parse_model_config` between
  Keras v1/v2 and v3, since v3 also omits `InputLayer` `batch_shape` inputs,
  `layer_count` and the `model_name` fallback, and drops `dtype` from
  hyperparameters, unlike HDF5. Add a drift-guard test over one model in both
  formats.
- [ ] **Model metadata spellings differ across readers (S).** Found in the
  #294 review: counts are `num_labels`/`num_features` in CRFsuite and
  fastText but `GGUF.tensor_count`, `layer_count` and
  `archive_member_count` elsewhere; `type_of_model` mixes class names,
  training modes and families (see the type-of-model entry above); a
  non-string Keras v3 `date_saved` lands in properties as an integer.
- [ ] **CRFsuite description ambiguity (low).** Labels joined by `", "`
  (a label may contain it or a newline); `backslashreplace` `\xff` looks
  like a real 4-character label.
- [ ] **fastText `getArgs()` failure drops `domain` silently (low).**
  The warning does not name `domain`.
- [ ] **Empty `x.crfsuite` and empty `x.model` give different messages from
  `loom model` (cosmetic).** `file is empty` vs `not an AI model file of a
  supported format`; the shared-suffix rule explains it.
- [ ] **`_loom_model.py` names the provenance document `declared.name or
  "model"` (low; was `_loom_active_run.py:185`).** Not in this diff; check it
  against the name cascade.

### Found in review rounds, not yet prioritised

- [ ] **Safetensors `framework` treats a blank value as present (S).**
  `format` and `modelspec.implementation` are chosen with `or`, which skips
  an empty string but not a white-space-only value (`" "`): that still counts
  as present, while every other blank text field gives way (#427). Use the
  shared stated-text helper.
  *Found 2026-11-03, review of the merges #426 to #429.*
- [ ] **A lone surrogate is escaped only on the scanner path (S, test-helper
  trap).** `cap_and_warn` escapes it, so `read_model_candidate` returns safe
  text; `read_ai_model` called directly returns the raw surrogate, and a
  failing assertion on it crashes pytest's repr under xdist. Tests go through
  `read_model_candidate`; decide whether the readers should return escaped
  text.
  *Found 2026-11-03, review of the merges #426 to #429.*
- [ ] **A Keras `training_config` with a lone surrogate fails the whole read
  (S).** A lone surrogate (`"\ud800"`, which `json.loads` accepts) in a nested
  list, an object, an object key or a top-level list of `training_config`
  makes RFC 8785 raise `ValueError`; `_record_json_value`
  (`extract/ai_model/hdf5_config.py`) catches only `RecursionError`, so the
  read ends as `model-unreadable` and the model's other fields are lost. Same
  on 0.22.0. Fix as #433 did for PT2 `extra/tags`: on `ValueError`, retry on a
  copy escaped with `escape_lone_surrogates_in`.
  *Found 2026-11-03, review of the 0.22.1 release.*
- [ ] **A PT2 tag nested about 330 levels or more that holds a lone surrogate
  fails the read (S).** `_tag_text` (`extract/ai_model/pytorch_pt2.py`, new in
  #433) escapes the surrogate on `copy.deepcopy(tag)` with the recursive
  `escape_lone_surrogates_in`; past the recursion limit that raises
  `RecursionError`, which nothing catches, so the model is unreadable.
  Hostile input only. A loop-based escape (an explicit stack) would fix it and
  could serve the Keras entry above too.
  *Found 2026-11-03, review of the 0.22.1 release.*
- [ ] **A collection nested over 32 levels that holds a lone surrogate shows
  as `<nested over 32 levels>` (low).** `_collection_text`
  (`core/ai_metadata.py`) catches the `ValueError` of RFC 8785 together with
  `RecursionError`, so the text is the placeholder, not the collection with the
  surrogate escaped. Display text only; the same fallback as "Deep metadata
  text depends on call-stack depth" above.
  *Found 2026-11-03, review of the 0.22.1 release.*

## Fixed

Kept for history, with the PR. A fixed entry moves to
[roadmap-completed.md](../../implementation/roadmap-completed.md) once its
release ships.

### Fixed, P2: 0.21.0 and later

- [x] **Safetensors licence keys are not mapped (S).** Fixed in the next
  release: `modelspec.license` (the only licence key in 9 real headers read on
  2026-10-28) is the model licence, as written; GGUF `general.license.name`
  stands in when `general.license` is blank or a placeholder (`other`...).
  `general.license.link` stays unread: `AiModelMetadata` has no licence-URL
  field, though SPDX 3.0.1 has `ExternalRefType` `license` for it (a Pitloom
  gap, not a format gap). Safetensors files
  with `license`/`license_name` keys were not seen; add them if one turns up.

### Fixed, P3: after 0.20.0

- [x] **Safetensors tensor names are recorded as `inputs` (S).** Fixed
  2026-10-17 (G7 honesty fix): Safetensors writes no inputs, NumPy keeps its
  arrays as file `properties`, PT2 reads only the signature's user inputs and
  outputs; see [g7-honesty-and-non-recordable.md](../g7-honesty-and-non-recordable.md).
  (Original report:) the reader called it a "lightweight inventory";
  `ai_informationAboutApplication` inputs mean model inputs. ONNX initializers
  were fixed in #294.
- [x] **PT2 tags spelt as Python repr (S, cross-format).** Fixed by #426:
  `pytorch_pt2.py` writes an array or object tag as canonical JSON, as HDF5
  `metrics` and `labels` do. (Was: `source_element_text()` (scalars only)
  gave `a, {'k': [1, True]}, null`.)
- [x] **PT2 root-level `version` file is read as the model version (S).**
  Fixed by #426: it is the export schema version (PyTorch v2.5.0
  `torch/export/__init__.py`, `SCHEMA_VERSION = (7, 3)`), so it becomes
  `format_version` (provenance `Field: version`) only when no
  `archive_version` was read, and never sets `version`. (Was: `_read_pt2_zip`
  took it as `version`, overridden by `extra/model_version`; a legacy
  `torch.export.save` file got a wrong `software_packageVersion`.)
- [x] **PT2: a malformed `model.json` drops all PT2 metadata (S).** Fixed by
  #426: a `model.json`, `graph_module` or `signature` of the wrong shape (a
  non-object) warns instead of crashing, and the rest of the PT2 fields stay;
  `inputs`/`outputs` entries were guarded already, and a non-string tensor
  name is kept as read. (Was: a list raised `AttributeError` in
  `_read_pt2_graph_io`, re-checked 2026-10-18.)
- [x] **One invalid UTF-8 GGUF string fails the whole file (S).** Fixed by
  #427: `_field_value` reads the string with `surrogateescape`, so the
  lone-surrogate warning applies and the file still reads. (Was: the strict
  decode's `UnicodeDecodeError` became "Failed to read GGUF file".)
- [x] **Blank text fields are kept by some readers (S).** Fixed by #427: GGUF,
  Safetensors and ONNX read an empty or white-space-only name, description,
  version, architecture, quantisation or `doc_string` as absent through one
  shared helper, and a blank Safetensors key gives way to the next candidate
  key. (Was: a blank or padded value (`"  "`) kept with its provenance.) The
  Safetensors `framework` choice is still open above.
- [x] **GGUF hyperparameter suffixes incomplete (S).** Fixed by #427:
  `.attention.layer_norm_epsilon`, `.expert_count`, `.expert_used_count` and
  `.rope.scaling.{type,factor,original_context_length}` are hyperparameters.
  (Was: they landed in properties.)
- [x] **`numpy.timedelta64` makes `canonical_json` raise (S).** Fixed by #429:
  a duration is no scalar, so `canonical_json` and `value_text` write its
  `str()` (`5 seconds`), as they do a `datetime64`. (Was: it is a
  `numbers.Integral`, so `json_safe` called `int()` and raised `TypeError`;
  no reader yielded one.)
- [x] **`escape_display_controls_in_json` edge cases (S).** Fixed by #429 for
  the surrogate: a decoded `\ud800` next to a control is escaped as text,
  where it raised `CanonicalizationError`. Two keys that escape to the same
  text keep the later one; the docstring says so and a test pins it, by
  decision, not changed. (Found in the #294 review; reachable with keys
  `"a<U+202E>"` and `"a\\u202e"` in one `ai_informationAboutApplication`
  object.)
