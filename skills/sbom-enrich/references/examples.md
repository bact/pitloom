---
Created: 2026-07-05
Last-Modified: 2026-08-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom sbom-enrich skill: copy-paste recipe

Companion to `../SKILL.md`. This recipe is meant to be run as-is or
adapted with minimal edits.

The scenario: Pitloom's static extraction produced `sbom.spdx3.json` for a
project whose `model.safetensors` has an adjacent `README.md` with YAML
frontmatter (`license: apache-2.0`) plus prose stating the model was also
evaluated on "imagenet-val" -- a relationship only the prose states, not
the frontmatter. Two enrichment passes run in sequence: the deterministic
`loom enrich` command picks up the frontmatter `license`, then an agent
reads the prose for the `imagenet-val` relationship the frontmatter never
mentioned.

## 1. Run the deterministic pass

```bash
loom enrich model.safetensors --project-dir . -o model.enrich.spdx3.json
```

`--project-dir .` matters here: `sbom.spdx3.json` is a **project-level**
SBOM (from `loom project .`, step 5 below), and a project-level document
assigns this model's `ai_AIPackage` a different id than a standalone
`loom model model.safetensors` run would. Without `--project-dir`, the
fragment would reference an id absent from `sbom.spdx3.json` and the
merge in step 5 would silently produce no visible change -- omit
`--project-dir` only when merging into a `loom model`-generated base
document instead.

This parses only `README.md`'s YAML frontmatter (`license: apache-2.0`)
and writes a standalone fragment -- no prose reading, no reasoning, no
network. Read it to see what it filled, so step 2 below doesn't
re-propose the same field:

```bash
python3 -c "import json; print(json.load(open('model.enrich.spdx3.json'))['@graph'])"
```

## 2. Draft a fragment for what prose adds

The frontmatter enrichment already covered `license`; it never runs on
prose, so the "evaluated on imagenet-val" relationship stated in the
README body is still an agent-only finding.

`fragments/agent-enrichment.spdx3.json`:

```json
{
  "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
  "@graph": [
    {
      "@id": "_:creationinfo-agent",
      "created": "2026-07-05T00:00:00Z",
      "createdBy": [
        "https://spdx.org/spdxdocs/pitloom-agent/SoftwareAgent/agent-01"
      ],
      "specVersion": "3.0.1",
      "type": "CreationInfo"
    },
    {
      "creationInfo": "_:creationinfo-agent",
      "name": "AI coding agent",
      "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/SoftwareAgent/agent-01",
      "type": "SoftwareAgent"
    },
    {
      "creationInfo": "_:creationinfo-agent",
      "comment": "Source: AI agent | Method: inference -- name and role inferred from README.md's prose \"Evaluation\" section, not its YAML frontmatter (loom enrich already covered the frontmatter-only fields).",
      "dataset_datasetAvailability": "directDownload",
      "dataset_datasetType": ["image"],
      "description": "Evaluation dataset referenced in the project README's prose.",
      "name": "imagenet-val",
      "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/DatasetPackage/imagenet-val-01",
      "type": "dataset_DatasetPackage"
    }
  ]
}
```

### Override example

If instead the README's prose contradicted the frontmatter -- say
`license: apache-2.0` in frontmatter, but the body text says "note: as of
v2 this model is actually MIT-licensed, the header above is stale" -- the
agent's fragment entry would override, recording both values and why
rather than silently replacing the deterministic result:

```json
{
  "creationInfo": "_:creationinfo-agent",
  "comment": "Source: AI agent | Method: inference | Overrides: apache-2.0 (from loom enrich's frontmatter parse) | Reason: README body states license changed to MIT as of v2, frontmatter header is stale.",
  "simplelicensing_licenseExpression": "MIT"
}
```

The final report to the user (step 7 below) must call this override out
by name -- never let a silent override look identical to an ordinary
gap-fill.

### Interactive example: asking the SBOM author

Say neither frontmatter nor prose says what the model was actually
*trained* on -- only what it was evaluated on. In an interactive session,
the agent asks the SBOM author directly, and marks the answer
`sbomAuthorSupplied`, not `inference` -- the agent didn't derive this, it
was told:

```json
{
  "creationInfo": "_:creationinfo-agent",
  "comment": "Source: SBOM author | Method: sbomAuthorSupplied | Date: 2026-08-10 -- SBOM author confirmed in the enrichment session that this model was fine-tuned on an internal, unpublished dataset not described in any project file.",
  "dataset_datasetAvailability": "none",
  "dataset_datasetType": ["other"],
  "description": "Training dataset per the SBOM author, not documented in any project file.",
  "name": "internal-finetune-set",
  "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/DatasetPackage/internal-finetune-set-01",
  "type": "dataset_DatasetPackage"
}
```

Skip this kind of question entirely in a non-interactive run -- there is
no one to answer it.

Notes:

- `comment` on the inferred element carries the required provenance marker
  `Source: AI agent | Method: inference`, plus a short note on how the
  value was derived.
- Only include elements/fields the agent actually inferred -- do not
  restate what Pitloom already extracted.
- IDs (`spdxId`) must be unique; namespacing them under a distinct path
  (e.g. `.../pitloom-agent/...`) avoids collisions with the main SBOM.

## 3. Pre-merge check (mandatory)

Validate both fragments -- `model.enrich.spdx3.json` from step 1 and
`fragments/agent-enrichment.spdx3.json` from step 2 -- are syntactically
valid JSON before registering them -- `merge_fragments()` silently drops
(and only logs a warning for) a fragment it cannot parse, so catch a
malformed fragment now rather than after a wasted `loom` run:

```bash
python3 -c "import json,sys; json.load(open(sys.argv[1]))" \
  fragments/agent-enrichment.spdx3.json
```

For a stronger check, run the fragment through the same SPDX 3 JSON-LD
deserializer `merge_fragments()` itself uses. This catches the same
broken-JSON-LD cases `merge_fragments()` swallows as a warning, plus
SPDX-shape problems (e.g. an unknown property or type) that plain
JSON-syntax validity would miss:

```bash
python3 -c "
import sys
from spdx_python_model.bindings import v3_0_1 as spdx3
with open(sys.argv[1], 'rb') as f:
    spdx3.JSONLDDeserializer().read(f, spdx3.SHACLObjectSet())
" fragments/agent-enrichment.spdx3.json
```

## 4. Register both fragments

In the project's `pyproject.toml`:

```toml
[tool.pitloom.fragments]
files = [
  "model.enrich.spdx3.json",
  "fragments/agent-enrichment.spdx3.json",
]
```

## 5. Re-generate the SBOM

```bash
loom project . -o sbom.spdx3.json --pretty
```

The merged output now contains both the deterministic `license` fill and
the `dataset_DatasetPackage` element the agent inferred, alongside
everything Pitloom extracted directly -- each with its own provenance
clearly marked (the deterministic one via its N3 CreationInfo, the
agent-inferred one via its `comment`).

## 6. Post-merge check (mandatory)

Use the `sbom-validate` skill on `sbom.spdx3.json` -- this catches
SPDX-shape/SHACL problems (e.g. a missing required property or the wrong
relationship type) that plain JSON-syntax validity would miss.

## 7. Report back to the user

Summarise what came from which pass (e.g. "`loom enrich` filled `license`
from the README's frontmatter; separately, I added an `imagenet-val`
dataset reference based on the README's prose 'Evaluation' section --
please review before treating this as authoritative"). If any value was
overridden (see the override example above), name it explicitly. Never
present agent-inferred fragment content as if it were Pitloom's own
extraction.

## See also

- `../SKILL.md` -- operating instructions for this skill.
- The sibling `sbom-generate` skill -- generates the base SBOM this
  recipe enriches.
- The sibling `sbom-validate` skill -- used for the mandatory post-merge
  check above.
- `working-docs/design/sbom-enrichment.md` -- enrichment data-source table
  and the `[tool.pitloom.enrich]` enable/disable model.
- `working-docs/design/sbom-fragments.md` -- fragment system design and
  vocabulary.
- `docs/resources.md` in the Pitloom repository -- SPDX 3 spec, ontology,
  and JSON Schema links.
