---
Created: 2026-08-13
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Draft: provenance and enrichment vocabulary reference page

**Status:** draft, parked for later review.
This file exists so a human or an AI agent can pick the work
back up later without re-deriving the research.

See [working-docs/implementation/provenance/](../implementation/provenance/)
for the shipped provenance mechanism this vocabulary describes
(`annotation-provenance.md`, `metadata-provenance.md`, and siblings).
Settling the `role`/`method` taxonomy is also a prerequisite for systematic
licence rules: [license-layers.md](license-layers.md#prerequisites-conflict-resolution-provenance-and-taxonomy).
The drafted page content is in
[provenance-enrichment-vocabulary-draft-page.md](provenance-enrichment-vocabulary-draft-page.md).

**Origin:** user asked for a dedicated `docs/` (user-facing website) page
consolidating pitloom's provenance/enrichment vocabulary, since it's
grown, is now used in several places (including the Skills), and has no
single canonical reference. A full-repo inventory was run (`Explore`
agent) and a draft page was written, published to `docs/vocabulary.md`,
and cross-linked from `docs/metadata-provenance.md` and
`docs/configuration.md`. All of that was then reverted out of `docs/`
per the user's request, except one standalone, independently-correct fix
(see "Already applied" below). This file preserves the research and the
drafted page content for whenever the fuller change gets picked back up.

## Already applied (kept in docs/, not part of this deferral)

`docs/metadata-provenance.md`'s example `Annotation` `statement` showed
`"schema":"https://pitloom.dev/provenance/1"`. The shipped encoder
(`PitloomV1Encoder.schema_url`, `src/pitloom/assemble/spdx3/provenance.py:159`)
actually emits `"https://pitloom.dev/provenance/fields/1"`. This one-line
factual correction was kept (it's a bug fix independent of whether the
new vocabulary page ships) -- see the diff already in the working tree /
current PR.

**2026-08-13: the `sbomAuthorSupplied` method/role overload (Open
question 3 below) is fixed, not just documented-around.** `role` is now
a first-class key in the per-field provenance string format:
`_KEY_MAP` in `src/pitloom/assemble/spdx3/provenance.py` gained
`"role": "role"`; `_document_files.py:132`'s content-type-override case now
emits `Role: sbomAuthorSupplied` instead of `Method: sbomAuthorSupplied`
(the encoder already passed through arbitrary parsed keys generically,
so no other code changed). `tests/test_generator.py`'s
`test_build_file_content_type_config_override_is_sbom_author_supplied`
updated to match. While fixing this, found the **same pattern** in the
`sbom-enrich` Skill's own conventions -- `Method: inference` /
`Method: sbomAuthorSupplied` in `skills/sbom-enrich/SKILL.md` and
`skills/sbom-enrich/references/examples.md` had independently reinvented
a method-slot value (`inference`) for the same concept the epistemic
`role` vocabulary already names `inferred`. Fixed there too: all
instances changed to `Role: inferred` / `Role: sbomAuthorSupplied`,
retiring `inference` as a method value entirely (nothing else emitted
it). §1/§2 below and the drafted page content are updated to match.

## Open questions for whoever resumes this

1. **File name/location**: drafted as `docs/vocabulary.md`, nav label
   "Provenance and enrichment vocabulary" under `Reference`, right after
   "Metadata provenance". Reconsider if a different name reads better.
2. **How much to trim `docs/metadata-provenance.md`**: the draft removed
   its `method` table and shortened its `role` mention, pointing both at
   the new page instead, to avoid two places going stale independently.
   That's a bigger edit to review than the new page itself -- worth
   deciding whether to do the trim in the same PR as the new page, or in
   a follow-up once the new page has settled.
3. ~~**The `sbomAuthorSupplied` method/role overload**~~ -- **Resolved
   2026-08-13**, see "Already applied" above. `role` is now a real key in
   the fields-provenance format; `sbomAuthorSupplied` is a pure `role`
   value in code and in the `sbom-enrich` Skill's own conventions, no
   longer overloaded with `method`. §1/§2 below and the drafted page
   content reflect the fix.
4. ~~**`docs/metadata-provenance.md`'s stale `synthetic` value**~~ --
   **Resolved** (checked 2026-08-25): `docs/metadata-provenance.md`
   already reads `synthetic environment root`, matching
   `src/pitloom/extract/env.py`. No stale value remains.
5. **Casing is inconsistent between the `method` and `role` vocabularies**,
   and worth reconciling later:
   - `method` values are uniformly `snake_case`: `dynamic_extraction`,
     `licenseid_detection`, `inferred_from_authors`, `file_directive`,
     `attr_directive`, `inspect_caller`, `extension_guess`,
     `magika_content_detection`, `yaml_frontmatter` (plus the two-word
     `synthetic environment root`). (`sbomAuthorSupplied` and
     `inference` no longer belong on this list -- both retired as
     `method` values 2026-08-13, see "Already applied" above.)
   - `role` values (both the epistemic vocabulary in §2 and the
     dataset-relationship vocabulary in §4) are a mix of plain lowercase
     words (`declared`, `detected`, `inferred`) and `camelCase`
     (`externalReported`, `sbomAuthorSupplied`, `trainedOn`, `testedOn`,
     `finetunedOn`, `validatedOn`, `pretrainedOn`).
   - The `camelCase` `role` values read that way because they mirror
     native SPDX 3 identifiers (`RelationshipType.trainedOn`, etc.) and
     JSON-LD/schema.org convention generally uses `camelCase` for
     property-like names -- `method` has no equivalent native-SPDX
     anchor pulling it toward `camelCase`, which may be *why* it drifted
     to `snake_case` (matching plain Python identifier style) instead.
     Worth confirming that reasoning holds before picking one style, since
     unifying the two casings outright would be a breaking change to
     already-shipped provenance JSON (`comment` strings and `Annotation`
     `statement` payloads both encode literal values) -- not something to
     do casually even after this page ships.
6. **CreationInfo future enhancements** (carried over from the old
   `working-docs/design/metadata-provenance.md`, folded in here
   2026-08-14 when that file's shipped content moved to
   `working-docs/implementation/provenance/metadata-provenance.md`):
   record when third-party tools (e.g. the `enrich` skill) augmented the
   data; track validation steps and results. Neither is built.
7. ~~**Unbounded artifact-metadata-blob size**~~ -- **Resolved
   (2026-08-26):** `[tool.pitloom.provenance] max-source-metadata-bytes`
   (default `0`, unbounded) caps the serialized `Annotation.statement`
   byte length via dictionary-level, greedy-heaviest-key-first
   truncation, marked with `truncated`/`truncatedKeys`/
   `truncatedKeyCount`/`maxMetadataBytes` in the statement envelope when
   it fires. Also gained a `--max-source-metadata-bytes` CLI flag /
   `action.yml` input, a deliberate exception to this table's
   config-only precedent. See
   `working-docs/implementation/provenance/annotation-mechanism.md`'s
   "Size-bounded artifact-metadata preservation" section for the shipped
   design, and `docs/metadata-provenance.md`'s "Size-bounded
   preservation" section for the user-facing explainer.
8. **`Method` vs. `Role` as separate keys, flagged 2026-08-14 for
   dedicated human review**: the 2026-08-13 fix (see "Already applied"
   above) resolved the specific bug where `sbomAuthorSupplied` was
   wrongly emitted via the `method` slot, by making `role` a first-class
   key alongside `method`. That fixed the immediate overload, but the
   user has explicitly asked to separately review whether `Method`/`Role`
   as two distinct keys is the right split at all (naming, whether they
   should be one key, whether other values are similarly misplaced) --
   broader than item 5's casing question, and not yet started. Do this as
   part of the same deferred vocabulary-review pass, not a quick
   drive-by fix.

## Full inventory (from the `Explore` agent's repo-wide research)

### 1. Provenance `method` values

All are the literal string that follows `Method:` in a
`"Source: X | Method: <value>"` provenance string (parsed by
`parse_provenance_value` in `src/pitloom/core/provenance.py`,
keyed `method` in the JSON statement).

Paths below reflect the subpackage layout under `src/pitloom/extract/`
(`project/`, `remote/`, `lock/`, `ai_model/`, `dataset/`). Line numbers are approximate.

| `method` value | Meaning | Emission site(s) |
| --- | --- | --- |
| `dynamic_extraction` | Value read from a Python file at build time (e.g. `__version__`/`__about__.py`), not `pyproject.toml` directly | `src/pitloom/extract/project/pyproject.py:342`, `:363` |
| `licenseid_detection` | License matched against a known SPDX id via the `licenseid` library -- how it was read; own `LICENSE` stays declared unless the manifest states one | `src/pitloom/extract/remote/huggingface_fetch.py:258`, `:355`; `src/pitloom/extract/_license.py:181`, `:216`; `src/pitloom/assemble/spdx3/deps_license.py:461` (default for a library `license_concluded`) |
| `inferred_from_authors` | Copyright text derived from the `authors` list, not read verbatim | `src/pitloom/extract/project/setuptools_cfg.py:285`, `setuptools_py.py:214`; `src/pitloom/extract/project/poetry.py:169`; `src/pitloom/extract/project/hatchling.py:143`; `src/pitloom/extract/project/pyproject.py:202` |
| `parsed_author_list` | Multiple individual entities extracted by splitting a single, comma-separated author string | `src/pitloom/assemble/spdx3/deps_originator.py:347` |
| `file_directive` | `pyproject.toml` dynamic field pointed at a file (`{file = "..."}`) | `src/pitloom/extract/project/pyproject_dynamic.py` |
| `attr_directive` | `pyproject.toml` dynamic field pointed at a Python attribute (`{attr = "..."}`) | `src/pitloom/extract/project/pyproject_dynamic.py` |
| `inspect_caller` | Recorded automatically by the `pitloom.loom` SDK via stack inspection | `src/pitloom/_loom_active_run.py:62`, `:67`, `:73` |
| `synthetic environment root` | The element is Pitloom's own synthesized placeholder root package for an installed environment | `src/pitloom/extract/env.py:42-43` |
| `extension_guess` | File content-type resolved by filename-extension fallback (no `magika` / no confident result) | `src/pitloom/assemble/spdx3/_document_files.py:138` |
| `magika_content_detection` | File content-type resolved by the `magika` content-detection library; includes a `Tool: magika==<ver>` segment | `src/pitloom/assemble/spdx3/_document_files.py:135` |
| `yaml_frontmatter` | Value read from a local README/model-card's YAML frontmatter block (the `enrich/readme.py` enricher) | `src/pitloom/enrich/readme.py:100` |
| `resolved_lockfile` | `ProjectMetadata.locked_dependencies` populated from a real lock-solver output (`pylock.toml`, `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock`) via the lock/pin cascade | `src/pitloom/extract/lock/cascade.py:71-93` (the `_LOCK_SOURCES` table) |
| `pinned_requirements` | `ProjectMetadata.locked_dependencies` populated from a fully-pinned `requirements.txt` -- tagged separately from `resolved_lockfile` since it's not a lock-solver output, a weaker guarantee | `src/pitloom/extract/lock/cascade.py:94` |

**As of 2026-08-13, `sbomAuthorSupplied` and `inference` are no longer
`method` values** -- both retired from this table; see the `role` table
in §2 below instead. Before the fix, `document.py:235` (now `_document_files.py:132`) emitted
`Method: sbomAuthorSupplied` (a bug -- the surrounding docstring and
comment already called it a role); the `sbom-enrich` Skill's own
conventions independently used `Method: inference` for the exact concept
the `role` vocabulary already names `inferred`. Both fixed together --
see "Already applied" above.

**Corrections vs. `docs/metadata-provenance.md`'s current table (still
open, not yet applied to that file):**

- The doc says `synthetic`; code emits `synthetic environment root`
  (§"Open questions" item 4 above).
- Three real, code-emitted values are missing from the doc's table:
  `extension_guess`, `magika_content_detection`, `yaml_frontmatter`.
- `Method: spdx-license-detector` appears once, only as an arbitrary
  example string in `tests/test_provenance_integration.py:67` -- not
  part of the controlled vocabulary, just test-fixture prose.
- `resolved_lockfile`/`pinned_requirements` (PR #208's lock/pin cascade,
  landed after this doc was drafted) are also missing from the doc's
  table entirely.

### 2. Provenance `role` values

Defined once, canonically, as the `ConflictCandidate.role` docstring in
`src/pitloom/assemble/spdx3/provenance.py:369-397`, and reused for
`EnrichedFieldEntry.role` (`provenance.py:443-459`) and
`EnrichedField.role` (`src/pitloom/enrich/base.py:42-48`). Fuller prose
in `working-docs/implementation/provenance/role-vocabulary.md` (split out
of `annotation-provenance.md` 2026-08-25).

| `role` value | Meaning | Actually implemented in `src/`? |
| --- | --- | --- |
| `declared` | The subject's own stated claim, however observed | **Yes** -- `src/pitloom/assemble/spdx3/deps_license.py:235` |
| `detected` | Pitloom's own independent-verification procedure's determination | **Yes** -- `deps_license.py:241`; `src/pitloom/enrich/readme.py:146` (datasets; the card's licence is `declared`, `:122`, PR #276) |
| `externalReported` | Some other party's own determination, relayed without Pitloom re-deriving it | **No** -- defined and documented (`provenance.py:376-379`) but zero `role="externalReported"` in `src/**/*.py` today |
| `inferred` | An AI agent's non-deterministic reasoning/judgment | **No** in Pitloom's own code as a literal `role=` keyword argument -- but as of 2026-08-13 it's what the `sbom-enrich` Skill's hand-authored fragments literally write (`Role: inferred`, fixed from the old `Method: inference`) |
| `sbomAuthorSupplied` | Asserted directly by the human operating Pitloom (or an agent relaying their direct statement) | **Yes**, as of 2026-08-13 -- `_document_files.py:132` now emits `Role: sbomAuthorSupplied` (was `Method: sbomAuthorSupplied`); the `sbom-enrich` Skill's conventions fixed to match |

`docs/metadata-provenance.md:142-147` (current, unreverted state) covers
4 of the 5 roles and omits `sbomAuthorSupplied` from that section
entirely -- still true, that file is untouched by the 2026-08-13 fix
(the fix was in code + the Skill, not in this doc).

Unrelated to this vocabulary: `tests/assemble/test_spdx3_dataset_relationships.py`
(originally `tests/test_spdx3_dataset.py`, since moved and split --
see `cli-test-coverage-roadmap.md`; line number not re-verified) uses
`role="someNewRole"` to test the fallback-to-`other` behavior in
`_role_to_rel` -- a **different**, dataset-relationship role vocabulary
(see §4), easy to confuse by name only.

### 3. SPDX `Annotation` kinds and `statement` schemas

Every Annotation Pitloom builds uses `spdx3.AnnotationType.other`
(`provenance.py:237`, `provenance.py:309`). No `"review"`
`annotationType` exists anywhere in Pitloom's code.

Four distinct `statement` JSON shapes (all `contentType:
application/json`), each with a `"schema"` URL and matching `"kind"`
string (convention: `working-docs/implementation/provenance/annotation-mechanism.md`, "Statement envelope convention"):

| kind / schema URL | Builder function | Purpose | Source |
| --- | --- | --- | --- |
| `"fields"` -- `https://pitloom.dev/provenance/fields/1` | `build_provenance_annotation()` via `PitloomV1Encoder.encode()` | Per-field `{source, method, ...}` map (the default provenance Annotation) | `provenance.py:155-168`, `215-251` |
| `"unification"` -- `https://pitloom.dev/provenance/unification/1` | `build_unification_annotation()` | Why fragment elements were unified (A1: SHA-256 content-equality merge) | `provenance.py:41`, `321-356` |
| `"conflict"` -- `https://pitloom.dev/provenance/conflict/1` | `build_conflict_annotation()` | Multi-source field-value disagreement (G2), e.g. declared vs. detected license | `provenance.py:47`, `403-440` |
| `"enrichment"` -- `https://pitloom.dev/provenance/enrichment/1` | `build_enrichment_annotation()` | What an enrichment run changed (E1 override lineage / E2 inferred-vs-not marker); reuses the §2 role vocabulary (also `working-docs/implementation/provenance/role-vocabulary.md`) in each `changes[].role` | `provenance.py:51`, `461-491` |
| `"artifact-metadata"` -- `https://pitloom.dev/provenance/artifact-metadata/1` | `build_source_metadata_annotation()` | Verbatim preserved original AI-model metadata (P1), config-gated by `preserve-source-metadata` | `provenance.py:44`, `494-531` |

`docs/metadata-provenance.md:50`'s example `schema` URL
(`.../provenance/1`, bare) doesn't match the shipped encoder
(`.../provenance/fields/1`) -- this specific fix is the one already
applied outside this deferral (see "Already applied" above). The bare
URL is still visible as stale in
`working-docs/implementation/provenance/annotation-provenance.md:186,231,349,489,515`
(all in §1-9, unaffected by the 2026-08-25 §10 split)
-- out of scope for a user-facing fix but worth a note if that working
doc gets revisited. (The former `working-docs/design/metadata-provenance.md:59`
occurrence was fixed when that file's shipped content moved to
`working-docs/implementation/provenance/metadata-provenance.md` on
2026-08-14.)

Distinct from the in-statement `schema` URL: the short config
`[tool.pitloom.provenance] schema` id (`"pitloom/1"`,
`DEFAULT_PROVENANCE_SCHEMA` in `src/pitloom/core/provenance.py:12`,
matching `PitloomV1Encoder.schema_id` at `provenance.py:158`) -- picks
the *encoder version*; the long URL says *which annotation kind*.

Internal design-doc taxonomy codes G1-G4 (Generation), A1/A2
(Aggregation), E1/E2 (Enrichment), P1 (Preservation), N1-N3
(native-first backfill) are working-docs shorthand -- see
`working-docs/implementation/provenance/use-case-catalog.md` (catalog +
N1-N6 checklist) and `multi-source-conflict.md` (G2 detail) for
which mechanism serves which use case -- not literal emitted
strings, not vocabulary for a user-facing page.

### 4. Enrichment vocabulary (`src/pitloom/enrich/`)

**Named enrichers:** exactly one implemented -- `ReadmeEnricher`
(`name = "readme"`, `src/pitloom/enrich/readme.py:75-83`), dispatched
from `run_enrichers()` (`src/pitloom/enrich/__init__.py:42-44`).
`EnrichmentResult.source_name` docstring names future planned sources as
examples only: `"openssf_scorecard"` (not built -- see
`src/pitloom/core/enrich_config.py:23-25` and
`working-docs/design/sbom-enrichment.md:83-89`, listing Hugging Face
Hub metadata, OpenSSF Scorecard, Parlay, PyPI/conda as "Not started").

"N3/E1/E2" are taxonomy codes, not enricher names -- don't present them
as vocabulary on a user page.

**Dataset relationship role vocabulary** -- separate from §2 despite
sharing the field name `role`. Defined in
`src/pitloom/core/dataset_metadata.py:96-109` and
`working-docs/design/sbom-enrichment.md:44-50`:

| value | meaning | maps to native SPDX 3.0.1 `RelationshipType`? |
| --- | --- | --- |
| `trainedOn` | Primary dataset used to train the model | Yes -- `spdx3.RelationshipType.trainedOn` |
| `testedOn` | Dataset(s) used to evaluate the trained model | Yes -- `spdx3.RelationshipType.testedOn` |
| `finetunedOn` | Dataset used for fine-tuning a pre-trained model | No -- falls back to `RelationshipType.other` + explanatory comment |
| `validatedOn` | Dataset used for validation during training | No -- same fallback |
| `pretrainedOn` | Dataset used to pre-train a foundation model | No -- same fallback |

Mapping logic: `_role_to_rel()` in `src/pitloom/assemble/spdx3/dataset.py:18-49`.
Only `trainedOn`/`testedOn` are actually produced today
(`enrich/readme.py:144`; `extract/remote/huggingface_field.py:248`, `:268`).

No confidence-score or evidence-type controlled vocabulary exists.
Pitloom's detector has no confidence score today (explicitly noted as a
limitation in `working-docs/implementation/provenance/role-vocabulary.md`,
"Role → native relationship mapping" section).

### 5. Minimum-elements vocabulary

`skills/sbom-enrich/references/minimum-elements.md` introduces no new
role/method vocabulary distinct from §2 -- it explicitly reuses the same
5-role vocabulary
(`working-docs/design/sbom-enrichment.md:274`: "the five-role provenance
vocabulary"). It does add a separate status-legend vocabulary for gap
analysis (`skills/sbom-enrich/references/minimum-elements.md:23-27`):

| status | meaning |
| --- | --- |
| `covered` | Pitloom emits this deterministically, nothing to do |
| `conditional` | Emitted only when a dependency resolves against PyPI/installed metadata or similar; verify per-run |
| `gap` | This workflow's actual job |
| `not automatable` | No file or answer this workflow can gather will satisfy it |

Plus the three named standards as controlled labels used for skill
triggering/routing: `NTIA 2021`, `CISA 2026` (current baseline,
supersedes NTIA), `G7 SBOM for AI 2026` (additive, only when an
`ai_AIPackage` is present) -- `skills/sbom-enrich/SKILL.md:19-26`,
`references/minimum-elements.md:9-21`.

### 6. Where this vocabulary is currently documented

| Doc | What it covers re: this vocabulary |
| --- | --- |
| `docs/metadata-provenance.md` | User-facing: `method` table (7 of 11 real values -- misses 4, has 1 stale), the 4-of-5 implemented-looking roles section, `conflict` schema example, `[tool.pitloom.provenance]` config table |
| `docs/creation-metadata.md` | CreationInfo who/what/when/how model -- background context, relevant for the N3 (enrichment CreationInfo) cross-link |
| `docs/configuration.md:53-57` | A **different, unrelated** `method` vocabulary -- `--content-type-method` (`"auto"`/`"magika"`/`"extension"`), which resolves to the `magika_content_detection`/`extension_guess` provenance `method` strings at runtime |
| `working-docs/implementation/provenance/annotation-provenance.md` | Canonical design rationale: goal, design decisions, statement schema, implementation, tests, statement examples. Start here. |
| `working-docs/implementation/provenance/role-vocabulary.md` | Full role vocabulary, decision rule, source-recording convention, role-to-native mapping. |
| `working-docs/implementation/provenance/annotation-mechanism.md` | Boundary principle, extrinsic-assertion test, schema-envelope convention. |
| `working-docs/implementation/provenance/use-case-catalog.md` | G1-G4/A1/A2/E1/E2/P1/N1-N6 taxonomy. |
| `working-docs/implementation/provenance/multi-source-conflict.md` | G2 implementation depth. |
| `working-docs/implementation/provenance/annotation-provenance-full-plan.md` | Earlier/fuller planning doc, same taxonomy, older shape (`event:` key vs. shipped `kind:` in some examples -- lines 256/263/316) |
| `working-docs/implementation/provenance/demo-provenance.md` | Worked CLI walkthrough reusing the same method strings |
| `working-docs/implementation/provenance/phase2-native-backfill-handover.md:28` | One-line pointer into `annotation-provenance-full-plan.md`'s taxonomy |
| `working-docs/implementation/provenance/metadata-provenance.md` | Implementation-register version of `docs/metadata-provenance.md`'s content (moved here 2026-08-14 from `working-docs/design/metadata-provenance.md`, which no longer exists as a separate file); schema URL already fixed |
| `working-docs/design/sbom-enrichment.md` | Source of truth for the dataset-relationship role table (§4), enrichment data-source table, "five-role provenance vocabulary" cross-reference |
| `working-docs/design/model-metadata-extraction.md` | No relevant content (checked, zero hits) |
| `skills/sbom-enrich/SKILL.md` | Agent-facing use of `Role: inferred` / `Role: sbomAuthorSupplied` (fixed from `Method:` 2026-08-13), the role-decision rule, minimum-elements workflow |
| `skills/sbom-enrich/references/minimum-elements.md` | The 3 standards' checklists + status-legend vocabulary (§5) |
| `skills/sbom-enrich/references/examples.md` | Worked fragment examples with literal `Role: inferred`/`Role: sbomAuthorSupplied` strings (fixed from `Method:` 2026-08-13) |
| `skills/sbom-generate/SKILL.md:125` | `--content-type-method {auto,magika,extension}` -- same "different vocabulary" caveat as `docs/configuration.md` |
| `skills/sbom-validate/SKILL.md` | No relevant content (checked) |

## Drafted page content (as published, then reverted)

Moved to [provenance-enrichment-vocabulary-draft-page.md](provenance-enrichment-vocabulary-draft-page.md),
kept verbatim there.
