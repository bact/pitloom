---
Created: 2026-08-13
Last-Modified: 2026-08-13
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Draft: provenance and enrichment vocabulary reference page

**Status:** draft, parked for later review. Not shipped in the v0.14.0
release PR -- too much to review in one pass alongside that PR's other
changes. This file exists so a human or an AI agent can pick the work
back up later without re-deriving the research.

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
`"role": "role"`; `document.py:235`'s content-type-override case now
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
4. **`docs/metadata-provenance.md`'s stale `synthetic` value**: code
   emits `synthetic environment root`, the doc says `synthetic`. Small,
   independent fix, not yet applied anywhere -- could be split out and
   shipped on its own regardless of what happens to the rest of this.
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

## Full inventory (from the `Explore` agent's repo-wide research)

### 1. Provenance `method` values

All are the literal string that follows `Method:` in a
`"Source: X | Method: <value>"` provenance string (parsed by
`parse_provenance_value` in `src/pitloom/assemble/spdx3/provenance.py:74-96`,
keyed `method` in the JSON statement).

| `method` value | Meaning | Emission site(s) |
| --- | --- | --- |
| `dynamic_extraction` | Value read from a Python file at build time (e.g. `__version__`/`__about__.py`), not `pyproject.toml` directly | `src/pitloom/extract/pyproject.py:340`, `:361` |
| `licenseid_detection` | License matched against a known SPDX id via the `licenseid` library -- detected, not declared | `src/pitloom/extract/pyproject.py:301`; `src/pitloom/extract/_huggingface.py:392`, `:523`; `src/pitloom/extract/_license.py:352`, `:415` |
| `inferred_from_authors` | Copyright text derived from the `authors` list, not read verbatim | `src/pitloom/extract/setuptools.py:280`, `:427`; `src/pitloom/extract/poetry.py:169`; `src/pitloom/extract/hatchling.py:143`; `src/pitloom/extract/pyproject.py:200` |
| `file_directive` | `pyproject.toml` dynamic field pointed at a file (`{file = "..."}`) | `src/pitloom/extract/setuptools.py:495` |
| `attr_directive` | `pyproject.toml` dynamic field pointed at a Python attribute (`{attr = "..."}`) | `src/pitloom/extract/setuptools.py:514` |
| `inspect_caller` | Recorded automatically by the `pitloom.loom` SDK via stack inspection | `src/pitloom/loom.py:52`, `:57`, `:62` |
| `synthetic environment root` | The element is Pitloom's own synthesized placeholder root package for an installed environment | `src/pitloom/extract/env.py:42-43` |
| `extension_guess` | File content-type resolved by filename-extension fallback (no `magika` / no confident result) | `src/pitloom/assemble/spdx3/document.py:241` |
| `magika_content_detection` | File content-type resolved by the `magika` content-detection library; includes a `Tool: magika==<ver>` segment | `src/pitloom/assemble/spdx3/document.py:238` |
| `yaml_frontmatter` | Value read from a local README/model-card's YAML frontmatter block (the `enrich/readme.py` enricher) | `src/pitloom/enrich/readme.py:100` |

**As of 2026-08-13, `sbomAuthorSupplied` and `inference` are no longer
`method` values** -- both retired from this table; see the `role` table
in §2 below instead. Before the fix, `document.py:235` emitted
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

### 2. Provenance `role` values

Defined once, canonically, as the `ConflictCandidate.role` docstring in
`src/pitloom/assemble/spdx3/provenance.py:369-397`, and reused for
`EnrichedFieldEntry.role` (`provenance.py:443-459`) and
`EnrichedField.role` (`src/pitloom/enrich/base.py:42-48`). Fuller prose
in `working-docs/implementation/annotation-provenance.md:818-931`.

| `role` value | Meaning | Actually implemented in `src/`? |
| --- | --- | --- |
| `declared` | The subject's own stated claim, however observed | **Yes** -- `src/pitloom/assemble/spdx3/deps.py:877` |
| `detected` | Pitloom's own independent-verification procedure's determination | **Yes** -- `deps.py:883`; `src/pitloom/enrich/readme.py:114`, `:138` |
| `externalReported` | Some other party's own determination, relayed without Pitloom re-deriving it | **No** -- defined and documented (`provenance.py:376-379`) but zero `role="externalReported"` in `src/**/*.py` today |
| `inferred` | An AI agent's non-deterministic reasoning/judgment | **No** in Pitloom's own code as a literal `role=` keyword argument -- but as of 2026-08-13 it's what the `sbom-enrich` Skill's hand-authored fragments literally write (`Role: inferred`, fixed from the old `Method: inference`) |
| `sbomAuthorSupplied` | Asserted directly by the human operating Pitloom (or an agent relaying their direct statement) | **Yes**, as of 2026-08-13 -- `document.py:235` now emits `Role: sbomAuthorSupplied` (was `Method: sbomAuthorSupplied`); the `sbom-enrich` Skill's conventions fixed to match |

`docs/metadata-provenance.md:142-147` (current, unreverted state) covers
4 of the 5 roles and omits `sbomAuthorSupplied` from that section
entirely -- still true, that file is untouched by the 2026-08-13 fix
(the fix was in code + the Skill, not in this doc).

Unrelated to this vocabulary: `tests/test_spdx3_dataset.py:360` uses
`role="someNewRole"` to test the fallback-to-`other` behavior in
`_role_to_rel` -- a **different**, dataset-relationship role vocabulary
(see §4), easy to confuse by name only.

### 3. SPDX `Annotation` kinds and `statement` schemas

Every Annotation Pitloom builds uses `spdx3.AnnotationType.other`
(`provenance.py:237`, `provenance.py:309`). No `"review"`
`annotationType` exists anywhere in Pitloom's code.

Four distinct `statement` JSON shapes (all `contentType:
application/json`), each with a `"schema"` URL and matching `"kind"`
string (convention: `working-docs/implementation/annotation-provenance.md:691-713`):

| kind / schema URL | Builder function | Purpose | Source |
| --- | --- | --- | --- |
| `"fields"` -- `https://pitloom.dev/provenance/fields/1` | `build_provenance_annotation()` via `PitloomV1Encoder.encode()` | Per-field `{source, method, ...}` map (the default provenance Annotation) | `provenance.py:155-168`, `215-251` |
| `"unification"` -- `https://pitloom.dev/provenance/unification/1` | `build_unification_annotation()` | Why fragment elements were unified (A1: SHA-256 content-equality merge) | `provenance.py:41`, `321-356` |
| `"conflict"` -- `https://pitloom.dev/provenance/conflict/1` | `build_conflict_annotation()` | Multi-source field-value disagreement (G2), e.g. declared vs. detected license | `provenance.py:47`, `403-440` |
| `"enrichment"` -- `https://pitloom.dev/provenance/enrichment/1` | `build_enrichment_annotation()` | What an enrichment run changed (E1 override lineage / E2 inferred-vs-not marker); reuses the §2 role vocabulary in each `changes[].role` | `provenance.py:51`, `461-491` |
| `"artifact-metadata"` -- `https://pitloom.dev/provenance/artifact-metadata/1` | `build_source_metadata_annotation()` | Verbatim preserved original AI-model metadata (P1), config-gated by `preserve-source-metadata` | `provenance.py:44`, `494-531` |

`docs/metadata-provenance.md:50`'s example `schema` URL
(`.../provenance/1`, bare) doesn't match the shipped encoder
(`.../provenance/fields/1`) -- this specific fix is the one already
applied outside this deferral (see "Already applied" above). The bare
URL is still visible as stale in
`working-docs/implementation/annotation-provenance.md:169,214,332,472,498`
and `working-docs/design/metadata-provenance.md:59` -- out of scope for
a user-facing fix but worth a note if those working docs get revisited.

Distinct from the in-statement `schema` URL: the short config
`[tool.pitloom.provenance] schema` id (`"pitloom/1"`,
`DEFAULT_PROVENANCE_SCHEMA` in `src/pitloom/core/provenance.py:12`,
matching `PitloomV1Encoder.schema_id` at `provenance.py:158`) -- picks
the *encoder version*; the long URL says *which annotation kind*.

Internal design-doc taxonomy codes G1-G4 (Generation), A1/A2
(Aggregation), E1/E2 (Enrichment), P1 (Preservation), N1-N3
(native-first backfill) are working-docs shorthand
(`working-docs/implementation/annotation-provenance.md:715-1098`) for
which mechanism above serves which use case -- not literal emitted
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
(`enrich/readme.py:144`; `extract/_huggingface.py:639`, `:659`).

No confidence-score or evidence-type controlled vocabulary exists.
Pitloom's detector has no confidence score today (explicitly noted as a
limitation at `working-docs/implementation/annotation-provenance.md:921-929`).

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
| `working-docs/implementation/annotation-provenance.md` | Canonical design rationale: full role vocabulary (§818-931), schema-envelope convention (§691-713), G1-G4/A1/A2/E1/E2/P1/N1-N3 taxonomy, statement examples |
| `working-docs/implementation/annotation-provenance-full-plan.md` | Earlier/fuller planning doc, same taxonomy, older shape (`event:` key vs. shipped `kind:` in some examples -- lines 256/263/316) |
| `working-docs/implementation/demo-provenance.md` | Worked CLI walkthrough reusing the same method strings |
| `working-docs/implementation/phase2-native-backfill-handover.md:28` | One-line pointer into `annotation-provenance.md`'s taxonomy |
| `working-docs/design/metadata-provenance.md` | Older/parallel version of `docs/metadata-provenance.md`'s content, same stale `.../provenance/1` schema URL |
| `working-docs/design/sbom-enrichment.md` | Source of truth for the dataset-relationship role table (§4), enrichment data-source table, "five-role provenance vocabulary" cross-reference |
| `working-docs/design/model-metadata-extraction.md` | No relevant content (checked, zero hits) |
| `skills/sbom-enrich/SKILL.md` | Agent-facing use of `Role: inferred` / `Role: sbomAuthorSupplied` (fixed from `Method:` 2026-08-13), the role-decision rule, minimum-elements workflow |
| `skills/sbom-enrich/references/minimum-elements.md` | The 3 standards' checklists + status-legend vocabulary (§5) |
| `skills/sbom-enrich/references/examples.md` | Worked fragment examples with literal `Role: inferred`/`Role: sbomAuthorSupplied` strings (fixed from `Method:` 2026-08-13) |
| `skills/sbom-generate/SKILL.md:125` | `--content-type-method {auto,magika,extension}` -- same "different vocabulary" caveat as `docs/configuration.md` |
| `skills/sbom-validate/SKILL.md` | No relevant content (checked) |

## Drafted page content (as published, then reverted)

The following is the full content that was published to
`docs/vocabulary.md` and then removed pending review. Kept verbatim so
resuming this doesn't require re-writing from scratch -- re-check it
against the code before re-publishing, since the code may have moved on
by the time this is picked up.

<!-- markdownlint-disable MD001 MD024 -->

### Provenance and enrichment vocabulary

> **Note:** Reference documentation for auditing or debugging a generated
> SBOM -- not needed to just generate one. This vocabulary is still in
> beta and can change without notice between releases.

Pitloom uses a small set of controlled string values to describe *how* it
determined an SBOM field's value and *what kind* of annotation it
produced. This page is the single place they're all defined -- several
of them share a field name (`role`, `method`) across otherwise unrelated
parts of the schema, which makes them easy to conflate if you've only
seen one corner of the codebase. Where a value isn't wired into Pitloom's
own code yet, that's called out explicitly.

#### Provenance method values

The `method` field in a provenance entry says *how* Pitloom arrived at a
value, not just where it read it from -- emitted inside the `fields`
provenance Annotation (see Annotation kinds below) and the legacy
`comment` string alike. A field with **no** `method` -- just a `source`
-- was read verbatim from the named file with no interpretation
involved.

| `method` | Meaning |
| --- | --- |
| `dynamic_extraction` | Read from a Python file at build time (e.g. a `__version__` or `__about__.py` variable), not from `pyproject.toml` directly. |
| `licenseid_detection` | License text matched against a known SPDX license using the [`licenseid`](https://pypi.org/project/licenseid/) library -- detected, not author-declared. |
| `inferred_from_authors` | Derived from the `authors` list (e.g. a copyright statement), not read verbatim from any single field. |
| `file_directive` | A `pyproject.toml` dynamic field pointed at a file (`{file = "..."}`); the value was read from that file. |
| `attr_directive` | A `pyproject.toml` dynamic field pointed at a Python attribute (`{attr = "..."}`); the value was imported and read from code. |
| `inspect_caller` | Recorded automatically by the `pitloom.loom` tracking SDK via Python stack inspection -- identifies which script/function called the SDK. |
| `synthetic environment root` | The element is Pitloom's own synthesized placeholder root package for an installed environment (`loom env`), not extracted from any source file. |
| `yaml_frontmatter` | Read from a local README/model card's YAML frontmatter block during enrichment. |
| `magika_content_detection` | Per-file content type resolved by the [`magika`](https://pypi.org/project/magika/) content-detection library. |
| `extension_guess` | Per-file content type resolved by a filename-extension fallback (no `magika`, or no confident result). |

`magika_content_detection` and `extension_guess` are **not** the same
vocabulary as `[tool.pitloom.content-type] method` /
`--content-type-method` on Configuration -- that setting *chooses* the
detector; these two values are what the chosen detector *reports back*
as provenance once it runs.

`sbomAuthorSupplied` is **not** a `method` value -- it's a `role`; see
below. (An earlier draft of this page had it in both tables, matching a
code bug where it was wrongly emitted via the `method` slot; fixed
2026-08-13, see the `role` table.)

#### Provenance role values (epistemic)

`role` on a provenance candidate (e.g. in a `conflict` Annotation, an
enrichment's `changes[]` entry, or a per-field provenance entry) says
*whose* determination a value is, independent of *how* it was obtained.

| `role` | Meaning | Status |
| --- | --- | --- |
| `declared` | The subject's own stated claim, however observed. | Implemented |
| `detected` | Pitloom's own independent-verification procedure's result. | Implemented |
| `sbomAuthorSupplied` | Asserted directly by the human operating Pitloom (or an agent relaying their direct statement). | Implemented -- emitted for a per-file content type set via `[[tool.pitloom.content-type.override]]`, and by the `sbom-enrich` Skill's hand-authored fragments for a value the SBOM author stated directly in an interactive session. |
| `externalReported` | Some other party's own determination, relayed without Pitloom re-deriving it (e.g. a future linked GitHub/Hugging Face Hub API). | Reserved for future use |
| `inferred` | An AI agent's non-deterministic reasoning/judgment. | Not emitted by Pitloom's own deterministic code; emitted by the `sbom-enrich` Skill's hand-authored fragments for a value the agent derived itself, not stated by the SBOM author |

#### Dataset relationship roles

A **separate, unrelated** controlled vocabulary that happens to share the
name `role` -- this one labels *why* a dataset relates to an AI model,
not who determined a value. Set via `[tool.pitloom.enrich]`-driven
enrichment or read natively from a model source (e.g. a Hugging Face
model card).

| `role` | Meaning | Native SPDX 3 `RelationshipType`? |
| --- | --- | --- |
| `trainedOn` | Primary dataset used to train the model. | Yes -- `trainedOn` |
| `testedOn` | Dataset(s) used to evaluate the trained model. | Yes -- `testedOn` |
| `finetunedOn` | Dataset used for fine-tuning a pre-trained model. | No -- falls back to `other` plus an explanatory comment |
| `validatedOn` | Dataset used for validation during training. | No -- same fallback |
| `pretrainedOn` | Dataset used to pre-train a foundation model. | No -- same fallback |

Only `trainedOn` and `testedOn` are emitted by any extractor or enricher
today; the other three are defined vocabulary with a working fallback
path, ready for a future emitter.

#### Annotation kinds and schema envelopes

Every Annotation Pitloom builds uses SPDX 3's own `annotationType: other`
-- SPDX has no finer-grained type that fits, so the JSON `statement`
field's own `"kind"` key is what actually distinguishes one from
another. Each kind has its own schema URL, embedded in the statement:

| `kind` | Schema URL | Purpose |
| --- | --- | --- |
| `fields` | `https://pitloom.dev/provenance/fields/1` | Per-field `{source, method, ...}` map -- the default provenance Annotation described above. |
| `unification` | `https://pitloom.dev/provenance/unification/1` | Why two fragment elements were merged into one (matching SHA-256 content). |
| `conflict` | `https://pitloom.dev/provenance/conflict/1` | Multi-source field-value disagreement, e.g. declared vs. detected license. |
| `enrichment` | `https://pitloom.dev/provenance/enrichment/1` | What an enrichment run changed on an element; each entry in `changes[]` carries a `role` from the epistemic vocabulary above. |
| `artifact-metadata` | `https://pitloom.dev/provenance/artifact-metadata/1` | Verbatim preserved original AI-model metadata, gated by `[tool.pitloom.provenance] preserve-source-metadata`. |

This schema URL is a different thing from `[tool.pitloom.provenance]
schema` in `pyproject.toml` (default `"pitloom/1"`): the config value
picks the *encoder version* Pitloom writes with; the URL above says
*which kind* of Annotation a given statement is.

#### Minimum-elements gap status

The `sbom-enrich` Skill's minimum-elements workflow (NTIA 2021, CISA
2026, G7 SBOM for AI 2026) uses a small status vocabulary of its own when
reporting what's missing, distinct from the provenance vocabulary above:

| Status | Meaning |
| --- | --- |
| `covered` | Pitloom emits this deterministically; nothing to do. |
| `conditional` | Emitted only when a dependency resolves against PyPI/installed metadata or similar -- verify per run. |
| `gap` | Missing; filling it in is this workflow's actual job. |
| `not automatable` | No file or answer this workflow can gather will satisfy this element. |

The full standard-by-standard field mapping lives in the Skill's own
minimum-elements reference
(`skills/sbom-enrich/references/minimum-elements.md`).

<!-- markdownlint-enable MD001 MD024 -->
