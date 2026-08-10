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
project whose README states the model was trained on the "tiny-imagenet"
dataset and evaluated on "imagenet-val" -- information no model file format
encodes, so Pitloom's own extractors cannot see it. An agent reads the
README and contributes that relationship back as a fragment.

## 1. Draft a minimal fragment

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
      "comment": "Source: AI agent | Method: inference -- name and role inferred from README.md \"Training data\" section.",
      "dataset_datasetAvailability": "directDownload",
      "dataset_datasetType": ["image"],
      "description": "Training dataset referenced in the project README.",
      "name": "tiny-imagenet",
      "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/DatasetPackage/tiny-imagenet-01",
      "type": "dataset_DatasetPackage"
    }
  ]
}
```

Notes:

- `comment` on the inferred element carries the required provenance marker
  `Source: AI agent | Method: inference`, plus a short note on how the
  value was derived.
- Only include elements/fields the agent actually inferred -- do not
  restate what Pitloom already extracted.
- IDs (`spdxId`) must be unique; namespacing them under a distinct path
  (e.g. `.../pitloom-agent/...`) avoids collisions with the main SBOM.

## 2. Pre-merge check (mandatory)

Validate the drafted fragment is syntactically valid JSON before
registering it -- `merge_fragments()` silently drops (and only logs a
warning for) a fragment it cannot parse, so catch a malformed fragment now
rather than after a wasted `loom` run:

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

## 3. Register the fragment

In the project's `pyproject.toml`:

```toml
[tool.pitloom.fragments]
files = ["fragments/agent-enrichment.spdx3.json"]
```

## 4. Re-generate the SBOM

```bash
loom project . -o sbom.spdx3.json --pretty
```

The merged output now contains the `dataset_DatasetPackage` element from
the fragment alongside everything Pitloom extracted directly, with the
inferred element's provenance clearly marked in its `comment`.

## 5. Post-merge check (mandatory)

Use the `sbom-validate` skill on `sbom.spdx3.json` -- this catches
SPDX-shape/SHACL problems (e.g. a missing required property or the wrong
relationship type) that plain JSON-syntax validity would miss.

## 6. Report back to the user

Summarise what was inferred and from where (e.g. "Added a
`tiny-imagenet` dataset reference based on the README's 'Training data'
section; please review before treating this as authoritative"). Never
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
