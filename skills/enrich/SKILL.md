---
name: enrich
description: >-
  Use this skill when asked to enrich, augment, or add inferred detail to
  a Pitloom-generated SBOM or AIBOM -- for example inferring an unstated
  license, classifying a dependency's purpose, or deriving
  trainedOn/testedOn dataset relationships from a README or model card
  that no file format encodes explicitly. Trigger phrasings include
  "enrich this SBOM", "add more detail to the SBOM", "infer the dataset
  used to train this model", "fill in missing SBOM information from the
  README/model card". Requires a Pitloom-generated SBOM to already exist --
  generate one first with the `sbom` skill if it does not.
license: Apache-2.0
---

<!-- Created: 2026-07-05 -->
<!-- Last-Modified: 2026-07-08 -->
<!-- SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul -->
<!-- SPDX-FileType: SOURCE -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Enrich a Pitloom-generated SBOM

Static extraction cannot read prose. An agent can go further than Pitloom
alone: read the project's README or the model's model card, infer a
plausible license or a dependency's purpose, or work out
`trainedOn`/`testedOn` dataset relationships that no file format encodes
explicitly. Do this only **after** a base SBOM exists (use the `sbom`
skill first if it does not), and only when it adds real information -- do
not fabricate detail for its own sake.

See `references/examples.md` for a full worked example.

## Contribute enrichment as a fragment, never by hand-editing

Do not edit the generated SBOM JSON directly. Pitloom has a purpose-built
mechanism for exactly this: **fragments**. Write the inferred facts as a
small, standalone SPDX 3 JSON file and let Pitloom merge it on the next
generation run. See `references/examples.md` for a full worked example.

Every inferred field's `comment` (or the fragment's
`CreationInfo.comment`) must carry a provenance marker in this exact form,
so it is never confused with authoritative, extracted metadata:

```text
Source: AI agent | Method: inference
```

Steps:

1. Generate a base SBOM first, if not already done (use the `sbom`
   skill).
2. Read the project's `README.md` / model card and any other local docs.
3. Draft a fragment (`*.spdx3.json`) containing only the elements or
   relationships you can infer (e.g. a `dataset_DatasetPackage` plus a
   `trainedOn` relationship, or a `comment` refining a license guess).
   Mark every inferred value with the provenance string above.
4. **Pre-merge check (mandatory):** validate the drafted fragment is
   syntactically valid JSON before registering it -- a fragment with
   broken JSON is silently dropped by `merge_fragments()`'s catch-and-warn
   behaviour, so catch it now rather than after a wasted `loom` run:

   ```bash
   python3 -c "import json,sys; json.load(open(sys.argv[1]))" \
     fragments/agent-enrichment.spdx3.json
   ```

5. Register the fragment so Pitloom merges it on the next run:

   ```toml
   [tool.pitloom.fragments]
   files = ["fragments/agent-enrichment.spdx3.json"]
   ```

6. Re-run `loom <path>` (generate again) so the merged, enriched SBOM is
   written.
7. **Post-merge check (mandatory):** validate the merged output is still
   a conformant SPDX 3 JSON document -- a syntactically valid fragment can
   still be missing a required property or use the wrong relationship
   type, which only shape/SHACL validation catches:

   ```bash
   pip install spdx3-validate  # if not already installed
   spdx3-validate --json <merged-sbom-file>
   ```

8. Tell the user what was inferred and why, so they can review it -- this
   is provenance-tracked, agent-derived data, not ground truth.

For the full enrichment data-source table, the `[tool.pitloom.enrich]`
enable/disable model, and the dataset-relationship field map, see
`working-docs/design/sbom-enrichment.md` in the Pitloom repository.
