---
Created: 2026-07-05
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom sbom-enrich skill: copy-paste recipe

Companion to `../SKILL.md`. This recipe is meant to be run as-is or
adapted with minimal edits. Snippets are POSIX shell; on Windows use
`python` or `py` for `python3`, and PowerShell equivalents.

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
assigns this model's `ai_AIPackage` a different id than a standalone `loom
model model.safetensors` run would. Without `--project-dir`, the fragment
would reference an id absent from `sbom.spdx3.json` and the merge in step 5
would fail (a dangling-reference `WARNING:`, then an `ERROR:` and a non-zero
exit). A `loom model` base cannot be merged into at all (`loom model`
ignores registered fragments, silently): draft, then hand the fragment over
unmerged. Pass the same `--config`, `--id-registry` and `--use-lockfile` as
the base run if it used them. `-o` is always explicit: without it the
fragment lands in the current directory under the model's own file name.

This parses only `README.md`'s YAML frontmatter (`license: apache-2.0`)
and writes a standalone fragment -- no prose reading, no reasoning, no
network. Read it to see what it filled, so step 2 below doesn't
re-propose the same field:

```bash
python3 -c "import json; print(json.load(open('model.enrich.spdx3.json'))['@graph'])"
```

(Standard library only: any Python 3 works, not only Pitloom's own.)

## 2. Draft a fragment for what prose adds

The frontmatter enrichment already covered `license`; it never runs on
prose, so the "evaluated on imagenet-val" relationship stated in the
README body is still an agent-only finding. A `Relationship` must start
from the model's real id, so first read it from the base SBOM:

```bash
python3 -c "import json,sys; print(*[o['spdxId'] for o in json.load(open(sys.argv[1]))['@graph'] if o.get('type') == 'ai_AIPackage'], sep='\n')" sbom.spdx3.json
```

Put the printed id where `<AIPackage-spdxId>` appears below.
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
      "comment": "Source: AI agent | Role: inferred -- name and role inferred from README.md's prose \"Evaluation\" section, not its YAML frontmatter (loom enrich already covered the frontmatter-only fields).",
      "dataset_datasetAvailability": "directDownload",
      "dataset_datasetType": ["image"],
      "description": "Evaluation dataset referenced in the project README's prose.",
      "name": "imagenet-val",
      "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/DatasetPackage/imagenet-val-01",
      "type": "dataset_DatasetPackage"
    },
    {
      "creationInfo": "_:creationinfo-agent",
      "comment": "Source: AI agent | Role: inferred -- README.md's prose \"Evaluation\" section states the model was evaluated on imagenet-val.",
      "from": "<AIPackage-spdxId>",
      "relationshipType": "testedOn",
      "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/Relationship/imagenet-val-tested-on-01",
      "to": [
        "https://spdx.org/spdxdocs/pitloom-agent/DatasetPackage/imagenet-val-01"
      ],
      "type": "Relationship"
    }
  ]
}
```

### Override example

If instead the README's prose contradicted the frontmatter -- say
`license: apache-2.0` in frontmatter, but the body text says "note: as of
v2 this model is actually MIT-licensed, the header above is stale" -- the
agent's fragment would override, recording both values and why rather than
silently replacing the deterministic result. A license is a
`simplelicensing_LicenseExpression` element linked to the model by a
`Relationship`, so the override is a pair of `@graph` entries, with `<AIPackage-spdxId>`
filled in as above:

```json
{
  "creationInfo": "_:creationinfo-agent",
  "comment": "Source: AI agent | Role: inferred | Overrides: apache-2.0 (from loom enrich's frontmatter parse) | Reason: README body states license changed to MIT as of v2, frontmatter header is stale.",
  "simplelicensing_licenseExpression": "MIT",
  "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/LicenseExpression/mit-01",
  "type": "simplelicensing_LicenseExpression"
},
{
  "creationInfo": "_:creationinfo-agent",
  "comment": "Source: AI agent | Role: inferred | Overrides: apache-2.0 (from loom enrich's frontmatter parse) | Reason: README body states license changed to MIT as of v2, frontmatter header is stale.",
  "from": "<AIPackage-spdxId>",
  "relationshipType": "hasConcludedLicense",
  "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/Relationship/mit-concluded-01",
  "to": ["https://spdx.org/spdxdocs/pitloom-agent/LicenseExpression/mit-01"],
  "type": "Relationship"
}
```

If the base already has an `MIT` expression, the merge keeps the base's
element (an `Annotation` records the unification), so the override note
survives on the relationship's `comment`, not the shared licence.

### Interactive example: asking the SBOM author

Say neither frontmatter nor prose says what the model was actually
*trained* on -- only what it was evaluated on. In an interactive session,
the agent asks the SBOM author directly, and marks the answer
`sbomAuthorSupplied`, not `inferred` -- the agent didn't derive this, it
was told. Two more `@graph` entries (a dataset and the `trainedOn`
relationship to it):

```json
{
  "creationInfo": "_:creationinfo-agent",
  "comment": "Source: SBOM author | Role: sbomAuthorSupplied | Date: 2026-08-10 -- SBOM author confirmed in the enrichment session that this model was fine-tuned on an internal, unpublished dataset not described in any project file.",
  "dataset_datasetType": ["other"],
  "description": "Training dataset per the SBOM author, not documented in any project file.",
  "name": "internal-finetune-set",
  "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/DatasetPackage/internal-finetune-set-01",
  "type": "dataset_DatasetPackage"
},
{
  "creationInfo": "_:creationinfo-agent",
  "comment": "Source: SBOM author | Role: sbomAuthorSupplied | Date: 2026-08-10 -- same enrichment-session answer.",
  "from": "<AIPackage-spdxId>",
  "relationshipType": "trainedOn",
  "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/Relationship/internal-finetune-set-trained-on-01",
  "to": [
    "https://spdx.org/spdxdocs/pitloom-agent/DatasetPackage/internal-finetune-set-01"
  ],
  "type": "Relationship"
}
```

Skip this kind of question entirely in a non-interactive run -- there is
no one to answer it.

Notes:

- `comment` on the inferred element carries the required provenance marker
  `Source: AI agent | Role: inferred`, plus a short note on how the
  value was derived.
- Only include elements/fields the agent actually inferred -- do not
  restate what Pitloom already extracted.
- IDs (`spdxId`) must be unique; namespacing them under a distinct path
  (e.g. `.../pitloom-agent/...`) avoids collisions with the main SBOM.

## 3. Pre-merge check (mandatory)

Read both fragments -- `model.enrich.spdx3.json` from step 1 and
`fragments/agent-enrichment.spdx3.json` from step 2 -- with the SPDX 3
JSON-LD deserialiser `merge_fragments()` itself uses, as `../SKILL.md`'s
step 7 describes: run its one-line snippet (with the interpreter Pitloom
is installed in; `uvx --from "pitloom>=0.20.2" python` for a `uvx` run) on
those two files. Exit 0 is a pass.

Do not run `loom fragment validate` on a fragment: it names the base
SBOM's ids without an `ExternalMap`, so it fails SHACL on its own even
when correct. The merged SBOM is validated in step 6.

## 4. Register both fragments

In the project's `pyproject.toml`:

```toml
[tool.pitloom.fragment]
files = [
  { path = "model.enrich.spdx3.json", required = true },
  { path = "fragments/agent-enrichment.spdx3.json", required = true },
]
```

`required = true` makes a missing or unparsable fragment fail the run
instead of being skipped with a `WARNING:`.

## 5. Re-generate the SBOM

Re-run the exact command that produced the base SBOM (same target, `-o`
and flags):

```bash
loom project . -o sbom.spdx3.json --pretty
```

The merged output now contains both the deterministic `license` fill and
the `dataset_DatasetPackage` element and `testedOn` relationship the
agent inferred, alongside everything Pitloom extracted directly -- each
with its own provenance clearly marked (the deterministic one via its N3
CreationInfo, the agent-inferred one via its `comment`).

## 6. Post-merge check (mandatory)

Use the `sbom-validate` skill on `sbom.spdx3.json` -- this catches
SPDX-shape/SHACL problems (e.g. a missing required property or the wrong
relationship type) that plain JSON-syntax validity would miss. Minimal fallback:
`pip install "pitloom[validate]>=0.20.2"` then
`loom fragment validate sbom.spdx3.json`.

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
  <https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/SKILL.md>
- The sibling `sbom-generate` skill -- generates the base SBOM this
  recipe enriches.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/SKILL.md>
- The sibling `sbom-validate` skill -- used for the mandatory post-merge
  check above.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
- <https://bact.github.io/pitloom/cli/#enrich-an-sbom> and
  <https://bact.github.io/pitloom/configuration/> -- `loom enrich`, and the
  `enrich` and `[tool.pitloom.fragment]` settings.
- `docs/resources.md` -- SPDX 3 spec, ontology, and JSON Schema links.
  <https://bact.github.io/pitloom/resources/>
