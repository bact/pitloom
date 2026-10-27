---
Created: 2026-10-15
Last-Modified: 2026-10-24
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs: P3, after 0.20.0

See also: [known-bugs.md](known-bugs.md) (P0-P2 and the conventions: sizes,
ticking, where fixed items go), [roadmap.md](roadmap.md).

Follow-ups from the extras and authors work (#300): see
[extras-parity.md](../implementation/extras-parity.md#open-questions),
the one list.

- [x] **One person, two `Agent` elements (S, found in the 2026-10-23 release
  review; fixed in #353).** A model's `originatedBy` and a
  dataset's `publishedBy` naming the same person ("Alice" in the `library`
  conformance scenario) gave two `Agent` elements (`Agent-1`, `Agent-Alice-1`).
  Now one generic `Agent` per name, found through the exporter's agent index
  (`assemble/spdx3/_agents.py`, used by the model originators, the supplier and
  the dataset creator, on the assembler and `loom.run` routes). Every generic
  Agent's id carries its name (`Agent-<name>-1`; before, originators were
  `Agent-<n>`), so the id depends on neither the order the elements are built
  in (another model's dataset creator is built before this model's originators)
  nor on the Agents around it. A dataset creator is stripped, and a blank one
  names no one, as for an originator. Kept apart on purpose: the SBOM's own
  creators of type `agent` (never keyed), a main-package author and a
  dependency's author (a `Person` or `Organization`; the key includes the
  class).
- [ ] **Deep metadata text depends on call-stack depth (S).**
  `core/ai_metadata.py` `_collection_text` falls back to
  `<nested over 32 levels>` on `RecursionError`, so the CLI and the
  Hatchling hook (deeper stack) can write different bytes for a 500-950
  deep PT2 `extra/tags`. Decide from an explicit depth count.
- [ ] **Display escape can merge two JSON keys (S).** Keys `"a<U+202E>"`
  and `"a\\u202e"` in one `ai_informationAboutApplication` object spell
  the same after `escape_display_controls_in_json`; one entry is dropped.
- [ ] **PT2 tags spelt as Python repr (S, cross-format).**
  `pytorch_pt2.py` uses `source_element_text()` (scalars only) for
  non-scalar tags: `a, {'k': [1, True]}, null`. Use canonical JSON, as
  HDF5 `metrics` and `labels` do.
- [ ] **Label count recorded differently (S, cross-format).** CRFsuite
  always has `properties.num_labels`; fastText only `outputs[0].shape`,
  and nothing when all labels are dropped. CRFsuite with 0 labels emits
  `labels = "[]"`, supervised fastText with none emits nothing.
- [ ] **CRFsuite description ambiguity (low).** Labels joined by `", "`
  (a label may contain it or a newline); `backslashreplace` `\xff` looks
  like a real 4-character label.
- [ ] **fastText `getArgs()` failure drops `domain` silently (low).**
  The warning does not name `domain`.
- [ ] **`_loom_model.py` names the provenance document `declared.name or
  "model"` (low; was `_loom_active_run.py:185`).** Not in this diff; check it
  against the name cascade.

- [ ] **Escape/cap hardening from the Opus review of #294 (S each).**
  (a) Hangul fillers U+115F, U+1160, U+3164, U+FFA0 render blank but are
  not in `DISPLAY_CONTROLS`; add, plus a test that every Bidi_Control is
  in the set or on a named exclusion list. (b) U+200B-U+200D are escaped
  in prose, so Thai/Persian/Indic ZWNJ/ZWJ text is mangled and warns;
  escape them only in identity fields. (c) fastText has no label-count
  cap; share `recordable_labels` with CRFsuite. (d) Lone-surrogate escape
  runs before the name cut, which may split `\udXXX`. (e) Format-only
  stub entries skip `settle_read_text` (non-UTF-8 stem would raise
  `CanonicalizationError`); `physical_path` should stay out of the walk.
  (f) `_license_classify._replace_surrogates` uses U+FFFD, the shared
  rule `\udXXX`.

- [ ] **`-v` logs `OUTPUT_PATH=-` for both "no copy" and "copy to stdout"
  (S).** `wheel --embed -v` (no `-o`) and `wheel --embed -v -o -` print the
  same line (`cli/commands/wheel.py`, `docs/cli.md` "Verbose output"). Omit
  the key when nothing is written (#288 review).
- [ ] **Action `output: "-"` sets `sbom-path=-` (S).** The upload step then
  fails on a path named `-`. Refuse `-` in `action.yml`, or write the SBOM
  to a file (#288 review).
- [ ] **Library docs never say `output_path="-"` means stdout (S).**
  `write_sbom_output` gives every generator and `embed_wheel_sbom()` that
  meaning; neither the docstrings nor `docs/python-api.md` state it, and no
  library-level test pins it (#288 review).
- [x] **`--help` choice order changes per run (S).** Fixed (06d7cc45): `cli/parser.py`
  passes `choices=sorted(VALID_CONTENT_TYPE_METHODS)` and
  `sorted(VALID_CREATOR_TYPES)`. (Was: a frozenset in hash order.)
- [ ] **Installed-dependency `METADATA` is read unlike a wheel's (S).**
  `deps_installed.get_pkg_metadata` reads text through `importlib.metadata`
  (newlines translated, strict UTF-8): a CRLF `METADATA` gives a licence
  text without CR where the wheel reader keeps it, and a non-UTF-8 one
  raises `UnicodeDecodeError` and aborts the run. A dist-info with no
  metadata file stays silent. Use the wheel's `read_header_block` +
  `HeaderParser` (#286 review).
- [ ] **Hugging Face and classifier names state no licence to detection
  (S).** `huggingface_fetch` and `stated_license()` call
  `detect_license_from_text` without `stated=`, so a repo `LICENSE` with a
  card `license: apache-2.0` near-tie gives no detection; a classifier name
  (`MIT License`) never matches an id (#286 review).
- [ ] **Licence detection reads each text twice (S).** With a notice line,
  the matcher runs on the text as written and without the notice: about
  twice the time per licence text. Skip the second reading when the first
  is decisive at a high score (#286 review).
- [ ] **numpy licence text keeps one extra leading space per line (S).**
  meson-python folds `License:` with 9 spaces; `_unfolded` strips 8.
  Whitespace-only lines are blank on every surface since #286; the extra
  space stays (as
  0.19.0). Stripping a writer's whole fold width needs telling it from the
  text's own indent.
- [ ] **GitHub Action drops invalid boolean inputs silently.** Any
  non-empty value other than exactly `true`/`false` (`maybe`, `True`) on
  the tri-state `enrich`, `extract-file-header`, `update-id-registry`,
  `content-type`, `offline`, `use-lockfile`, and on the two-state
  `pretty`, `allow-build`, `no-build-isolation` (case-sensitive
  `= "true"`, so `allow-build: True` skips the build) passes no flag and
  prints no warning; `use-lockfile` in model/embed-wheel mode is dropped
  silently too.
- [ ] **Non-directory targets ignore configured fragments.** `loom model`
  (and `generate` on a model file), Hugging Face, `wheel`, `env` and sdist
  runs never call `merge_fragments()`, so fragments in `--config` or
  project config are dropped with no `WARNING:` and exit 0. The
  `sbom-enrich` skill says so.
- [ ] **`loom env` loses an unmet requirement.** A dependency pipdeptree
  reports as not installed (`installed_version: "?"`) loses its
  `dependsOn` edge with no trace (#236 review).
- [ ] **`loom env`: two installs sharing one pipdeptree `key` collide.**
  `build_deployed` keys its id map by `key`, so an editable copy next to
  a site-packages copy overwrites the first; all edges go to one element.
  Not seen from pipdeptree yet (#236 review).
- [ ] **setuptools discovery: absolute `physical_path` for a project dir
  named in another letter case.** On macOS and Windows, `loom project
  stproj` for on-disk `StProj`: the discoverer's `chdir()` +
  `os.getcwd()` gives the on-disk case, which no longer matches
  `project_dir` textually. Other backends are unaffected (#257 review).
- [ ] Case-insensitive member-name collisions in wheels; `--allow-build`
  extraction keeps the last duplicate with a warning.
- [ ] A scan in a worker thread registers its temp-dir cleanup with its
  own guard, so the dir can outlive SIGTERM to the main thread.
- [ ] `embed-wheel` temp file on SIGTERM (P4): `BaseException` cleanup is
  in place; signals are still uncovered.
- [ ] Pin one CI leg to an unpatched `zipfile` (pre CVE-2025-8291).
- [ ] The signed release wheel and SBOM are not reproducible: `created`
  and `builtTime` come from the clock. Set `SOURCE_DATE_EPOCH` (last
  commit time) in `pypi-publish.yml`'s build job so anyone can rebuild and
  compare against the signed bytes.
- [ ] Windows `--build-timeout`: when a process in the build tree exits on
  its own during `taskkill /F /T`, taskkill reports failure, so the
  `WARNING:` says "could not confirm the build process tree terminated"
  although it did. A Job Object would confirm it (0.21.0).
- [x] **The registry harvest `INFO:` can print a negative count (S).** Fixed
  by registry v3 (PR #305): `added N new id(s)` counts distinct new ids.
  (Original report:)
  `_sync_registry()` (`assemble/_generators_shared.py`) logs `added %d
  new file(s), %d new entit(y/ies)` from the net counts of `harvest()`.
  Two library calls on the example project in a row printed `added 0 new
  file(s), -1 new entit(y/ies)`: a stale key released in the same pass
  makes the net count negative. Log gross additions, or the "updated stale
  entries" line when any count is not positive. Found while checking doc
  examples.
- [x] **`loom.run` never calls `configure_logging()` (S).** Fixed by
  registry v3 (PR #305): `loom.Run` configures logging first, so its messages
  carry their `WARNING:`/`INFO:` tag. The `loom: ...` sub-prefix (against
  `ID registry: ...` elsewhere) is kept on purpose, and the example's
  committed registry is regenerated by its pipeline script.
- [ ] **`loom fragment validate A B` fails on two `loom.run` fragments (S).**
  Both fragments name their creation info `_:CreationInfo0`, so the
  merged-graph check sees one `CreationInfo` with several `created` values
  (14 `ERROR:` lines); each fragment alone, and `--no-merge`, is valid.
  `loom merge` of the same three fragments succeeds. Not yet checked
  whether the validator or Pitloom's blank-node labels are at fault.
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
  C18 in [canonical-output-followups.md](canonical-output-followups.md).
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
- [ ] **`loom model` on a 100-byte truncated `lid.176.ftz` ran to about
  20 GB RSS (S).** Native fastText reader on a hostile header, found in the
  CRFsuite review (a 400-byte cut reached about 7 GB); the metadata-only fastText reader in
  [model-metadata-readers.md](model-metadata-readers.md) closes it.
- [ ] **`loom merge` of a `loom enrich` fragment and a model SBOM writes
  invalid SPDX (M).** Found in the option D black-box round, not caused by
  it: merged elements get `creationInfo: ""` and a CreationInfo with no
  `@id`, so `loom fragment validate` fails, with or without annotations.
  Related to, but not the same as, the `_:CreationInfo0` entry above.
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
- [ ] **A base model URL is unbounded (S).** Found in #294: the base model
  name is cut at 1024 characters, but its `externalRef` locator
  (`https://huggingface.co/<id>`) keeps the whole id read (a 1 MiB id gives
  a 1 MiB locator). Bound or drop an over-long locator.
- [ ] **Over-cap CRFsuite model keeps only its name (S).** A model with more
  than 1,000 labels (or a hostile `num_labels`) gets the stub entry, though
  the header counts are cheap to read. Same stub rule as every format;
  revisit with the metadata-only readers.
- [ ] **Empty `x.crfsuite` and empty `x.model` give different messages from
  `loom model` (cosmetic).** `file is empty` vs `not an AI model file of a
  supported format`; the shared-suffix rule explains it.
- [ ] **Licence provenance can cite a property key the entry cap
  dropped (S).** Found in the #292 black-box round: with 1,500
  `metadata_props` and `model_license` last, the licence is still read
  (correct) and cites `Field: metadata_props.model_license`, a key no
  longer in the capped `properties`. Harmless (the field name is a pointer
  into the file, not the SBOM); decide whether the cap keeps keys that
  other fields cite.
- [ ] **`Source: Pitloom generator | Method: ...` is hand-written at 3
  sites (S).** Found in the #292 review (then 7 sites): `core/ai_metadata.py`
  (`FILE_NAME_STEM_PROVENANCE`) and two in `extract/env.py`. Add one helper in
  `core/provenance.py` (e.g. `generator_provenance(method)`) and use it at
  each; `generator_provenance` does not exist yet.
- [ ] **File licence and README licence disagree silently (S).** Found in
  the #292 review: with `--enrich`, the README enricher only fills a
  missing licence (`enrich/readme.py`), so an ONNX file declaring
  `Apache-2.0` next to a README saying `mit` keeps `Apache-2.0` with no
  message. #292 made ONNX files carry a licence for the first time, so
  this can now happen for ONNX as for the other formats. Decide whether a
  disagreement is a `WARNING:` (see
  [license-rules.md](license-rules.md)).

- [ ] **Keras v3 does not read `compile_config` (S).** The HDF5/Keras v1-v2
  reader takes optimizer, loss and metrics from `training_config`; the v3
  reader (`keras.py`) reads `config` and `build_config` only.
- [ ] **PT2 / ExecuTorch reader never sets `type_of_model` (S).** No
  `ai_typeOfModel` for a `.pt2`, though `framework="executorch"` is set.
- [ ] **PT2 root-level `version` file is read as the model version (S).**
  `_read_pt2_zip` (`pytorch_pt2.py`) takes it as `version`, overridden by
  `extra/model_version`. Unverified (no `torch` here): a real
  `torch.export` / `torch.save` zip is believed to hold a serialization
  format number there, which would be a format version, not a model version.
  Check against a real archive.
- [ ] **`AiModelUsage` has no producer (M).** `limitations`,
  `safety_risk_assessment`, `known_biases`, `intended_use` and
  `unintended_use` are assembled (`_ai_package.py`) but no reader or Hugging
  Face fetch fills them. Wire a source (model card sections) or drop them.
- [x] **Safetensors tensor names are recorded as `inputs` (S).** Fixed
  2026-10-17 (G7 honesty fix): Safetensors writes no inputs, NumPy keeps its
  arrays as file `properties`, PT2 reads only the signature's user inputs and
  outputs; see [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md).
  (Original report:) the reader called it a "lightweight inventory";
  `ai_informationAboutApplication` inputs mean model inputs. ONNX initializers
  were fixed in #294.
- [ ] **ONNX loads the whole protobuf into memory (M).** `onnx.load(...,
  load_external_data=False)` still parses every graph node. fastText's full
  load is logged above; both go with the metadata-only readers in
  [model-metadata-readers.md](model-metadata-readers.md).

- [ ] **Model dtype vocabularies differ across formats (S-M).** Found in
  #294: ONNX and NumPy write NumPy names (`float32`), Safetensors its own
  (`F32`, `BF16`). Pick one vocabulary for `inputs`/`outputs` `dtype`.
- [ ] **GGUF licence `other` and comma lists (S, needs a decision).**
  Questions, moved to
  [canonical-output-followups.md](canonical-output-followups.md#6-licence-identifiers-expressions-and-texts)
  (C15, C16).
- [ ] **GGUF hyperparameter suffixes incomplete (S).** Not matched:
  `.attention.layer_norm_epsilon`, `.expert_count`, `.expert_used_count`,
  `.rope.scaling.*`; they land in properties.
- [ ] **One invalid UTF-8 GGUF string fails the whole file (S).**
  `_field_value` decodes strictly; the `UnicodeDecodeError` (a `ValueError`)
  becomes "Failed to read GGUF file". Decode with replacement, one `WARNING:`.
- [ ] **GGUF `general.license` with a zero-width character (S).** A
  question, moved to
  [canonical-output-followups.md](canonical-output-followups.md#c17-invisible-characters-at-the-edges-of-a-licence-value)
  (C17).
- [ ] **PT2 lists lifted parameters as inputs; framework `executorch` (S).**
  Inputs fixed 2026-10-17: only `signature.input_specs` `user_input` entries
  are read. Open: the framework. (Original report:) `example-model.pt2` (`archive_format` `pt2`: a `torch.export` archive, not
  an ExecuTorch `.pte`) gives inputs `p_line_weight`, `p_line_bias`, `x`;
  `signature.input_specs` marks only `x` as `user_input`. Read user inputs
  only, framework `pytorch` with `torch_version` (`2.11.0`, unread). The
  fixture's `details/pytorch-pt2.md` claims `inputs` = `[x]`. Malformed
  `model.json` shapes: see the PT2 entry at the end of this section.
- [ ] **Safetensors name and framework (S).** `ss_base_model_version` (the
  base model, not this one) is a name candidate; prefer `ss_output_name`.
  Framework is the raw `format` value `pt`, not `pytorch`.
- [ ] **Keras `layer_count` counts `InputLayer` (S).** `len(layers)` in
  `hdf5_config.py`; Keras's own summary does not count it.
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
- [ ] **AI model usage hint names CLI flags in library messages (S).**
  `_USAGE_HINT` (`extract/scanner.py`) says `pass --scan-model-usage` from
  `generate_project_sbom()` and the hook too; the setting text differs per
  producer. Word it per surface through one helper.
- [ ] **Unreadable model handling differs by case (S).** A truncated
  `.crfsuite` or `.onnx` exits 0 with a `WARNING:`; an empty `.model`
  exits 1 with `ERROR: ... not an AI model file`. The ONNX warning repeats
  itself: `failed to extract metadata; Failed to load ONNX model from <path>`.

- [ ] **Keras v3 `config.json` values are not type-checked (S).** Found in
  the #294 review: `extract/ai_model/keras.py:83-98` takes `class_name` and
  `config.name` as they are, so `"class_name": {"a": 1}` or a non-string
  name aborts the whole run (`loom project` exits non-zero). Share
  `hdf5_config.parse_model_config` between Keras v1/v2 and v3: v3 also
  omits `InputLayer` `batch_shape` inputs, `layer_count` and the
  `model_name` fallback, and drops `dtype` from hyperparameters, unlike
  HDF5. Add a drift-guard test over one model in both formats.
- [ ] **PT2: a malformed `model.json` drops all PT2 metadata (S).** Found
  in the #294 review: `models/model.json` or `graph_module` as a list raises
  `AttributeError` in `_read_pt2_graph_io` and loses every PT2 field, not just
  the bad one (re-checked 2026-10-18). A non-string tensor name is now kept as
  read.
- [ ] **Blank text fields are kept by some readers (S).** Found in the #294
  review: Safetensors and ONNX `doc_string` and GGUF `general.description`
  keep a blank or padded value (`"  "`) with its provenance, while PT2,
  GGUF `general.version` and ONNX `model_license` strip it and drop a blank
  one. One shared stated-text helper for every reader.
- [ ] **fastText labels have no cap (S).** Found in the #294 review: a
  trained model records all its labels (1,200 in one), with no cap or
  `WARNING:`, while CRFsuite stops at 1,000; the docs describe only
  CRFsuite's cap.
- [ ] **`numpy.timedelta64` makes `canonical_json` raise (S).** Found in
  the #294 review: it is a `numbers.Integral`, so `json_safe` takes it as
  an integer and raises `TypeError`. No reader yields one today.
- [ ] **`escape_display_controls_in_json` edge cases (S).** Found in the
  #294 review, no reachable path: two keys can escape to the same text
  (the later stays, silently), and a decoded `\ud800` next to a control
  raises `CanonicalizationError`.
- [ ] **Model metadata spellings differ across readers (S).** Found in the
  #294 review: counts are `num_labels`/`num_features` in CRFsuite and
  fastText but `GGUF.tensor_count`, `layer_count` and
  `archive_member_count` elsewhere; `type_of_model` mixes class names,
  training modes and families (see the type-of-model entry above); a
  non-string Keras v3 `date_saved` lands in properties as an integer.

