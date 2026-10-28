---
Created: 2026-07-05
Last-Modified: 2026-10-28
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
frontmatter (`license: apache-2.0`, `datasets: [imagenet-1k]`) plus prose
stating the model was also evaluated on "imagenet-val" -- a relationship only
the prose states, not the frontmatter. Two enrichment passes run in sequence:
the deterministic `loom enrich` command picks up the frontmatter, then an agent
reads the prose for the `imagenet-val` relationship the frontmatter never
mentioned. The base SBOM came from `loom project . -o sbom.spdx3.json`, without
`--enrich`. With `--enrich` the SBOM already holds the frontmatter's dataset and
licence, so step 1 is skipped: merging its fragment too would duplicate each
dataset and `trainedOn`.

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
fragment lands in the current directory as `<model file name>.enrich.spdx3.json`.

This parses only `README.md`'s YAML frontmatter and writes a standalone
fragment -- no prose reading, no reasoning, no network. The fragment holds the
`imagenet-1k` `dataset_DatasetPackage` with its `trainedOn` relationship, and an
`Annotation` logging every change, the `license` included (the fragment writes
no licence element: for the licence, regenerate the base with `--enrich`
instead of this step). Read it to see what it filled, so step 2 below doesn't
re-propose the same field:

```bash
python3 -c "import json; print(json.load(open('model.enrich.spdx3.json'))['@graph'])"
```

(Standard library only: any Python 3 works, not only Pitloom's own.)

## 2. Draft a fragment for what prose adds

The frontmatter enrichment already covered `datasets:` (and logged `license`); it never runs on
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
`license: apache-2.0` in frontmatter (the SBOM states it because the base run used `--enrich`), but the body text says "note: as of
v2 this model is actually MIT-licensed, the header above is stale" -- the
agent's fragment would override, recording both values and why rather than
silently replacing the deterministic result. A licence is a
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

### Model producer: a typed agent beside the generic `Agent`

Pitloom records a model's producer as a generic `Agent` (name only) in
the `ai_AIPackage`'s `originatedBy`, never as a `Person` or `Organization`
(see `minimum-elements.md`, G7 "Model producer"). When the model card says
which it is, or names a producer the file does not, add the typed agent
and restate the package with its base `spdxId` and `name`, copied exactly
(here `probe-net`):

```json
{
  "creationInfo": "_:creationinfo-agent",
  "comment": "Source: AI agent | Role: inferred -- the model card's \"Model details\" section calls Acme Labs a company.",
  "name": "Acme Labs",
  "spdxId": "https://spdx.org/spdxdocs/pitloom-agent/Organization/acme-labs-01",
  "type": "Organization"
},
{
  "creationInfo": "_:creationinfo-agent",
  "comment": "Source: AI agent | Role: inferred -- originatedBy added from the model card.",
  "name": "probe-net",
  "originatedBy": [
    "https://spdx.org/spdxdocs/pitloom-agent/Organization/acme-labs-01"
  ],
  "spdxId": "<AIPackage-spdxId>",
  "type": "ai_AIPackage"
}
```

What the merge does (checked with `loom project` on a fragment like
this):

- `originatedBy` is a union: the base's generic `Agent` named `Acme Labs`
  stays, and the `Organization` follows it. A fragment cannot remove or
  retype it. Giving the `Organization` the generic `Agent`'s `spdxId`
  does not replace it either: `WARNING: Merge: Organization 'Acme Labs'
  shares spdxId <id> with a Agent; keeping both, it gets new id <id>.`
  Give the typed agent its own id, and say in the final report that both
  are listed: the `Agent` is the name the file states, the typed one your
  reading of the card. An ONNX `model_author` such as `Doe, Jane` is two
  `Agent`s (the format's list is split on commas); add `Jane Doe` as a
  `Person` the same way and report the split.
- `name` on a restated package: the base's wins with a `WARNING: Merge:
  conflicting 'name' ...`, except on the project's own model, which takes
  the fragment's name (`INFO: Merge: 'name' on ...`). Restate the base's
  name exactly unless renaming the model is the point.
- `suppliedBy` (one value) is taken from the fragment: Pitloom sets none on
  a model it read from a file, and a Hugging Face base is never merged
  into. Set it only for a distributor the card or the user names.
- A `parameters` entry in the package's `ai_hyperparameter` (a count the
  card states) is added only where the base has none; a base entry with
  another value wins, with `WARNING: Merge: conflicting 'ai_hyperparameter'
  key 'parameters' on ai_AIPackage <id> '<name>': keeping '<base>', dropping
  '<yours>'.` (the same for any `ai_hyperparameter`/`ai_metric` key). The merge adds Pitloom's count note itself: do not type it
  into the `comment`; say in the package's own provenance `comment` that
  the entry is the card's figure, not a sum of tensor elements. A
  `comment` on a restated package is appended to the base's, after a
  semicolon.
- A restated `spdxId` the base no longer has (the source changed after the
  fragment was drafted) adds a second `ai_AIPackage`, with no warning, and
  the result still validates. Before registering the fragment, list its
  `ai_AIPackage` ids that the base lacks; an id printed means regenerate
  the base and redraft (a base may hold two models of one name, so do not
  compare names):

```bash
python3 -c "import json,sys; ids=lambda p:{o['spdxId'] for o in json.load(open(p))['@graph'] if o.get('type')=='ai_AIPackage'}; [print(i) for i in sorted(ids(sys.argv[2])-ids(sys.argv[1]))]" sbom.spdx3.json fragments/agent-enrichment.spdx3.json
```

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
is installed in; `uvx --from "pitloom>=0.21.0" python` for a `uvx` run) on
those two files. Exit 0 is a pass.

Do not run `loom fragment validate` on a fragment: it names the base
SBOM's ids without an `ExternalMap`, so it usually fails SHACL on its own, even
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
instead of being skipped with a `WARNING:`. Check the registration from the
project directory: `loom fragment list` prints one `PATH=... ROLE=...
REQUIRED=... EXISTS=... ELEMENTS=...` line per registered fragment
(`EXISTS=false` is a wrong path; none registered is `INFO: fragment list: no
fragments configured`).

## 5. Re-generate the SBOM

Re-run the exact command that produced the base SBOM (same target, `-o`
and flags):

```bash
loom project . -o sbom.spdx3.json
```

The merged output now contains the `imagenet-1k` dataset and `trainedOn`
relationship from `loom enrich`, and the `imagenet-val` `dataset_DatasetPackage`
element and `testedOn` relationship the agent inferred, alongside everything
Pitloom extracted directly. Each carries its provenance: the deterministic ones
a `pitloom.enrich.readme` tool and an enrichment `Annotation`, the agent-inferred
ones their `comment`.

## 6. Post-merge check (mandatory)

Use the `sbom-validate` skill on `sbom.spdx3.json` -- this catches
SPDX-shape/SHACL problems (e.g. a missing required property or the wrong
relationship type) that plain JSON-syntax validity would miss. Minimal fallback:
`pip install "pitloom[validate]>=0.21.0"` then
`loom fragment validate sbom.spdx3.json`.

## 7. Report back to the user

Summarise what came from which pass (e.g. "`loom enrich` added the
`imagenet-1k` training dataset from the README's frontmatter; separately, I added an `imagenet-val`
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
