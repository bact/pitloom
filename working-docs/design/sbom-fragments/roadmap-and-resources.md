---
Created: 2026-08-25
Last-Modified: 2026-08-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM fragments: implementation roadmap and resources

See also [README.md](README.md) (index),
[fragment-merge-design.md](fragment-merge-design.md) (start here --
Phase 1/4 items below),
[loom-sdk-and-notebooks.md](loom-sdk-and-notebooks.md) (Phase 2 items),
[extractor-integrations.md](extractor-integrations.md) (Phase 3 items).

Split from this directory's former single `sbom-fragments.md`
(2026-08-25) -- the phased roadmap ties together the sibling files'
designs by priority, plus the community-resources table and references
shared across the whole cluster.

## Implementation roadmap

The work is ordered by user-impact priority. No item depends on completing
all earlier items; each can be delivered independently.

### Phase 1: Structural improvements (high impact, low effort)

1. **`FragmentConfig` data class** -- replace `list[str]` in `PitloomConfig`.
   Loader remains backward-compatible with plain strings.
2. **`merge_fragments` rewrite** -- add pre-merge validation, duplicate-ID
   detection, link-to-main relationship emission, and merge report logging.
3. **`fragment list` CLI command** -- cheapest way to surface fragment status
   to developers; reads config and checks file existence + parse validity.
4. **SHA-256 verification in merge** -- add `fragment sign` CLI command +
   hash check on merge.

### Phase 2: SDK improvements (notebook and ML workflow ergonomics)

1. **`log_param`, `log_metric`, `log_tag` on `_ActiveRun`** -- expands the
   existing `Run` API without breaking changes.
2. **`add_dataset` builder object** -- replace the current `add_dataset(name,
   type)` with a fluent builder that supports `set_size`, `set_license`, etc.
3. **`log_evaluation` on `_ActiveRun`** -- maps to SPDX `Annotation` elements.
4. **Persistent session mode** -- `loom.start_session()` / `loom.end_session()`.
5. **IPython magic** -- `%%pitloom_record` cell magic; optional, only activated
   if `ipython` is installed.

### Phase 3: New extractors

1. **MLflow dataset input extraction** -- read `run.inputs.dataset_inputs`;
   update `MlflowExtractor.extract()`.
2. **W&B Weave extractor** -- `pitloom.extract.weave.WeaveExtractor`; add
   `loom.from_weave_model()` to public API; add `weave` optional-dependency
   group to `pyproject.toml`.
3. **DVC extractor** -- `pitloom.extract.dvc.DvcExtractor`; reads `dvc.lock`;
   emits `dataset_DatasetPackage` elements with content hashes.

### Phase 4: Compliance and interoperability

1. **CycloneDX BOM-Link emission** -- when the CycloneDX assembler is
   implemented, emit `bom-link` references for fragments instead of
   inlining all elements.
2. **`fragment validate` CLI command** -- calls `spdx3-validate`'s
   library API (`spdx3_validate.validate()`, `spdx3-validate>=0.0.7`)
   directly rather than shelling out to its CLI and parsing stdout --
   simpler, testable without spawning a subprocess, and gives access to
   the structured `ValidationResult`/`.errors` list instead of printed
   text. This makes `spdx3-validate` an actual runtime dependency of
   Pitloom (today it's only ever agent/user-installed separately, per
   `skills/sbom-validate/`); add it as a base dependency, or gate it
   behind an optional-dependency group if kept opt-in. Clear error
   messages with line numbers.
3. **Fragment completeness declaration** -- add a `completeness` field to
   `FragmentConfig` (values: `complete`, `incomplete`, `unknown`) that
   maps to CycloneDX `compositions` and is emitted as an SPDX `Annotation`
   on the fragment's `software_Sbom` element.

> `SpdxDocument.imports` population (`ExternalMap` entries for each merged
> fragment) shipped in
> [#108](https://github.com/bact/pitloom/pull/108) --
> see `_add_fragment_imports()` in
> [`fragments.py`](../../../src/pitloom/assemble/spdx3/fragments.py).
> This is **document-level** traceability (which fragment *files*
> contributed) -- it does not address **element-level** traceability
> (found by independent aggregation review, not yet fixed): when two
> elements from different fragments are unified into one survivor,
> nothing in the output records *which criterion* matched (same
> `spdxId` vs. SHA-256 content hash vs. structural Agent/Tool equality
> -- see `_merge_fragment_set()`'s priority order) or *which fragments*
> the survivor's properties were folded in from; a scalar conflict is
> resolved silently in favor of the canonical value, with only a
> `log.warning` (never written to the SBOM) recording what was dropped.
> Not planned to change without a native SPDX home for this fact (SPDX
> 3 has no "this property came from source X, that one from source Y"
> construct at the field level) -- would need a custom Annotation
> similar to E1/E2's, which hasn't been designed. Separately,
> `_deduplicate_creation_infos()` (`export/spdx3_json.py`) collapses
> `CreationInfo` nodes by content fingerprint (`specVersion`, `created`,
> `createdBy`, `createdUsing`, `comment` -- excluding the id), which is
> by design for the common "same generation event, minted twice" case,
> but as a side effect two genuinely *distinct* generation events that
> happen to share an identical timestamp/creator/tool/comment would also
> collapse into one -- a low-probability, currently-unencountered edge
> case, documented here so it isn't mistaken for new behavior later.

---

## Existing tools and community resources

The following tools and communities are directly relevant to Pitloom's
fragment work and should be monitored for alignment opportunities.

| Tool / resource | Relevance |
| :---- | :---- |
| [CycloneDX BOM-Link](https://cyclonedx.org/capabilities/bomlink/) | Cross-BOM reference standard; model Pitloom's external fragment reference on this |
| [CISA SBOM Sharing Lifecycle](https://www.cisa.gov/sites/default/files/2023-04/sbom-sharing-lifecycle-report_508.pdf) | Author/Distributor/Consumer roles; use to frame the multi-team workflow |
| [NTIA / CISA Minimum Elements 2025](https://www.cisa.gov/sites/default/files/2025-08/2025_CISA_SBOM_Minimum_Elements.pdf) | Required fields for composed SBOMs |
| [OpenChain AI SBOM Guide](https://github.com/OpenChain-Project/Reference-Material/blob/master/AI-SBOM-Compliance/en/Artificial-Intelligence-System-Bill-of-Materials-Compliance-Management-Guide.md) | AI-specific SBOM requirements; compliance checklist |
| [SPDX spdx-spec#1362](https://github.com/spdx/spdx-spec/issues/1362) | Open issue on canonical serialization; track for updates affecting fragment merging |
| [W&B Weave](https://github.com/wandb/weave) | LLM tracing and evaluation; target for Phase 3 extractor |
| [DVC](https://dvc.org) | Data/model versioning with reproducible pipelines; target for Phase 3 extractor |
| [ProvBook](https://github.com/Sheeba-Samuel/ProvBook) | Jupyter provenance via REPRODUCE-ME ontology; possible bridge to Pitloom notebook mode |
| [MLProvLab](https://github.com/fusion-jena/MLProvCodeGen) | JupyterLab ML provenance extension; inspiration for `%%pitloom_record` magic |
| [AIMMX](https://github.com/IBM/AIMMX) | AI model metadata extraction at repository level; comparable to Pitloom's AI extractor |
| [Parlay](https://github.com/snyk/parlay) | SBOM enrichment from third-party sources; inspiration for Pitloom's enrichment layer |
| [spdx3-validate](https://pypi.org/project/spdx3-validate/) | Used in `fragment validate` and pre-merge validation, via its library API (`spdx3_validate.validate()`, added in v0.0.7) rather than shelling out to its CLI |
| [STAV](https://github.com/bact/stav) | Shared vocabulary for AI SBOM tags; already used in MLflow extractor |

---

## References

- CISA. 2023. "SBOM Sharing Lifecycle Report."
  <https://www.cisa.gov/sites/default/files/2023-04/sbom-sharing-lifecycle-report_508.pdf>.
- CISA. 2025. "2025 Minimum Elements for a Software Bill of Materials (SBOM)."
  <https://www.cisa.gov/sites/default/files/2025-08/2025_CISA_SBOM_Minimum_Elements.pdf>.
- CycloneDX. 2024. "BOM-Link."
  <https://cyclonedx.org/capabilities/bomlink/>.
- Linux Foundation AI & Data. 2024.
  "SPDX AI Bill of Materials (AI BOM) with SPDX 3.0."
  <https://www.linuxfoundation.org/research/ai-bom>.
- NTIA. 2021. "The Minimum Elements for a Software Bill of Materials (SBOM)."
  <https://www.ntia.gov/files/ntia/publications/sbom_minimum_elements_report.pdf>.
- OpenChain Project. 2024. "AI SBOM Compliance Management Guide."
  <https://github.com/OpenChain-Project/Reference-Material/blob/master/AI-SBOM-Compliance/en/Artificial-Intelligence-System-Bill-of-Materials-Compliance-Management-Guide.md>.
- Samuel, Sheeba. 2022. "ProvBook: Provenance-based Notebook Analysis."
  <https://github.com/Sheeba-Samuel/ProvBook>.
- SPDX Group. 2024. "SPDX 3.0.1 Specification."
  <https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf>.
- W&B Weave. 2024. "Weave Documentation."
  <https://weave-docs.wandb.ai/>.
