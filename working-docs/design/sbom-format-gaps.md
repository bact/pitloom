---
Created: 2026-10-21
Last-Modified: 2026-10-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM format gaps: what a standard cannot record precisely

See also: [roadmap.md](roadmap.md),
[generation-gaps-extraction-and-recording.md](generation-gaps-extraction-and-recording.md)
(this ledger holds the recording gaps; the ladder of ways to record one),
[g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md) (the G7
view and the honesty rules),
[external-references-to-review.md](external-references-to-review.md),
[AGENTS.md](../../AGENTS.md) ("SPDX / Output Specifics").

The ledger of places where an SBOM format (SPDX today, CycloneDX when Pitloom
writes it) or a mapping to a standard cannot record something precisely. It is
the input to change proposals to those standards: review it, group the
entries, write the proposal, and note the outcome here.

## When to add an entry

Add one in the same change, whenever Pitloom meets a mismatch or a gap that
makes it impossible to record a fact precisely:

- the format has no property for the fact;
- a property exists but its meaning is broader, narrower or different, so
  Pitloom would have to stretch it, or does and says so;
- one property holds two meanings that a reader cannot tell apart;
- a mapping (G7, BSI, CISA, FSCT, NTIA, a checker rule) reads a different
  property than the format's own semantics call for;
- a required value has no way to say "not known" or "known to be none";
- a vocabulary term is too coarse (an enumeration, a relationship type, an
  agent type).

Not an entry: a limit of Pitloom's extraction (data the source does not
carry), a Pitloom bug, a checker bug. Those go in
[known-bugs.md](known-bugs.md) or the extractor's design doc. If unsure
whether it is a format gap, add the entry and say so.

Never work around a gap silently. The honesty rules still apply: the SBOM
records the weaker form and says so (a comment, a provenance annotation), and
the entry names that.

## Entry template

```text
### FG-<n> <short title>

- Format and version: SPDX 3.0.1 | CycloneDX 1.x | mapping <name>
- Element or property: the class and property, or the standard's element id
- Fact to record: what Pitloom knows and cannot record precisely
- Pitloom today: what it writes instead, and how the SBOM says so
- Why imprecise: no property / wrong meaning / two meanings / ...
- Proposal: the change that would fix it (new property, new enumeration
  value, a profile, a clarified definition), to which standard or mapping
- Evidence: the doc, test, rule id or example that shows it
- Status: noted | to propose | proposed (link) | accepted | declined
- Date: YYYY-MM-DD
```

Number entries in order of discovery, never reuse a number, and keep a
declined or fixed entry with its outcome.

## Entries

### FG-1 A parameter count has no property

- Format and version: SPDX 3.0.1, AI profile
- Element or property: `ai_AIPackage`; nearest is `ai_hyperparameter`
- Fact to record: a model's parameter count, and what it counts (stored tensor
  elements of a file, or a Hub total)
- Pitloom today: an `ai_hyperparameter` entry `parameters`, with a package
  comment that it is a count of elements, not a hyperparameter
- Why imprecise: a hyperparameter is a training setting; a size is not
- Proposal: a typed model-size property (count, and what is counted), or a
  clarified use of `ai_hyperparameter`
- Evidence: [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md)
- Status: noted
- Date: 2026-10-21

### FG-2 Model type and architecture share one list

- Format and version: SPDX 3.0.1 / G7 mapping (MDL-009.2)
- Element or property: `ai_typeOfModel`
- Fact to record: the model type, and separately its architecture
- Pitloom today: the architecture is appended to `ai_typeOfModel` after the
  type, as the mapping names that property
- Why imprecise: one list holds two meanings that a reader cannot tell apart
- Proposal: a separate architecture property, or a structured value
- Evidence: [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md)
- Status: noted
- Date: 2026-10-21

### FG-3 `ai_informationAboutApplication` is read as intended use, preprocessing and I/O

- Format and version: mapping (G7 MDL-006.4, MDL-010.4, SLP-008.3) to SPDX 3.0.1
- Element or property: `ai_informationAboutApplication`
- Fact to record: an input/output signature is not an intended-use statement
  or a modality
- Pitloom today: a model's signature is written there when the file states it;
  the rules read the property's presence, not its content
- Why imprecise: one free-text property carries three meanings in the mapping
- Proposal: separate properties for intended use, input description and
  output description, or a clarified mapping
- Evidence: [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md)
  ("Presence is not meaning")
- Status: noted
- Date: 2026-10-21

### FG-4 Twenty G7 elements have no SPDX 3.0.1 property

- Format and version: SPDX 3.0.1 against G7 SBOM for AI 2026
- Element or property: the mapping rows whose comment starts `GAP`
  (`g7ai2026-to-spdx30.sssom.tsv`); five more elements are catalogue-only
  (INF-001, SP-003, SP-004, KPI-001, KPI-002)
- Fact to record: what each element asks for
- Pitloom today: recorded only where the honesty doc lists a recording, else
  not recorded
- Why imprecise: no native field
- Proposal: group the rows by theme (data provenance, training, infrastructure,
  security, KPIs) and propose properties or profile extensions per theme
- Evidence: [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md),
  [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md)
- Status: to propose
- Date: 2026-10-21

### FG-5 A dataset's publisher and its originator are different roles

- Format and version: mapping (G7 DP-006.1) to SPDX 3.0.1
- Element or property: `dataset_DatasetPackage` `originatedBy`, `suppliedBy`
- Fact to record: who published a dataset, which a Hub dataset owner is
- Pitloom today: `publishedBy`; the rule reads `originatedBy`, so it stays
  missing (an owner is not shown to be the originator)
- Why imprecise: the mapping treats the two roles as one
- Proposal: decide with the mapping's owner whether `publishedBy` counts, or
  add a way to state "publisher, originator unknown"
- Evidence: [roadmap.md](roadmap.md) ("G7 dataset creator")
- Status: noted
- Date: 2026-10-21
