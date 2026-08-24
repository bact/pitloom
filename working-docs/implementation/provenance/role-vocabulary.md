---
Created: 2026-08-25
Last-Modified: 2026-08-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Role vocabulary

See also [annotation-provenance.md](annotation-provenance.md) (canonical
design rationale, start here),
[annotation-mechanism.md](annotation-mechanism.md),
[use-case-catalog.md](use-case-catalog.md),
[multi-source-conflict.md](multi-source-conflict.md). The scattered
`method` (extraction-method) vocabulary is *not* covered here -- see
[working-docs/design/provenance-enrichment-vocabulary.md](../../design/provenance-enrichment-vocabulary.md)
§1 (parked, deferred).

Split out of `annotation-provenance.md`'s former G2 subsection
(2026-08-25), where it was originally written alongside G2-specific
(license-conflict) implementation detail. The `role` vocabulary itself
is general-purpose -- it is reused by G2 (multi-source disagreement),
E1/E2 (enrichment lineage), and file-header extraction alike -- so it
gets its own file. For G2's own implementation depth (schema,
normalization logic, what's built), see
[multi-source-conflict.md](multi-source-conflict.md).

## Role vocabulary

**`role` vocabulary** — an epistemic-process label (*whose* determination
this is), deliberately not "which native SPDX slot it maps to" (that
would have overloaded SPDX's own `hasConcludedLicense` meaning, "the
SBOM creator's final determination," a graph-placement outcome, not a
method category):

- `declared` — the subject's own stated claim, however observed (read
  locally, or relayed unedited by a third party).
- `detected` — Pitloom's own independent-verification *procedure*'s
  determination, whatever the input's origin (locality of the *input*
  never matters; locality of the *determination* does — Pitloom fetching a
  remote file and running its own `licenseid` match on it is still
  `detected`). "Procedure," not "algorithm ran": the license implementation
  (`detect_independent_license`) is a multi-step search — `CITATION.cff`,
  then `codemeta.json`, then license files, applying `licenseid` text
  matching only where a value isn't already a bare SPDX id — and a step
  that resolves via a direct bare-id read still counts as `detected`,
  because it was Pitloom's own independently-consulted secondary source,
  not a re-read of the subject's primary declared field. What decides the
  role is *whose search procedure* produced the value, not whether every
  individual step needed fuzzy text matching. Not named "extracted":
  `extract/` is already Pitloom's own name for the whole read-a-value
  pipeline stage, and `declared` is also extracted in that sense —
  "extracted" would have collided with `declared` instead of contrasting
  with it.
- `externalReported` — some *other* party's own determination or opinion,
  relayed without Pitloom re-deriving it, and not the subject's own claim
  either (a paper's interpretation, an unrelated org's assessment, or
  another system's own algorithmic conclusion — GitHub's own
  license-detector badge is still GitHub's determination, not Pitloom's,
  even though GitHub's detector is itself rule-based internally —
  "rule-based" was never the right test, "whose algorithm" is). No native
  slot exists for this role by nature, not because it lost a priority
  race against a local `declared` candidate.
- `inferred` — an AI agent's non-deterministic reasoning/judgment. Same
  word E2 already reserves for this.
- `sbomAuthorSupplied` — asserted directly by the human operating Pitloom
  (or an agent on their behalf), through any channel: a CLI flag,
  `[tool.pitloom]` config, or an answer typed in an interactive
  `sbom-enrich` session. Not `declared` (that's the *artifact's*
  author/vendor, not the SBOM's author); not `inferred` (nothing was
  derived — the value was simply relayed, and Pitloom can no more verify
  it than a `declared` value). Applies only when the human states the
  fact itself, not when they merely point the agent at a source ("look at
  X", "read Y", "infer it from Z") -- in that case the role is whichever
  of `declared`/`externalReported`/`inferred` matches how the agent
  actually obtained the value from that source once it looked, never
  `sbomAuthorSupplied` (the human didn't assert the fact, only named
  where to find it). Added for the `sbom-enrich` Skill's interactive mode
  (see [sbom-enrichment.md](../../design/sbom-enrichment.md)'s "Interactive
  mode" section) — that case is still Skill-only (an agent hand-authoring
  a fragment), not exercised by Pitloom's own generation code. A second,
  built case now is: a `[[tool.pitloom.content-type.override]]`
  config match (the config author is asserting a file's `contentType`
  directly) — see [file-headers.md](../file-headers.md)'s
  "Content-type overrides" section and
  `_emit_file_header_metadata` in
  [_document_files.py](../../../src/pitloom/assemble/spdx3/_document_files.py).

**Decision rule:** ask "whose determination is this," never "was the
data local or remote" and never "was a rule-based algorithm involved
somewhere" (a third-party service's own rule-based detector is still
`externalReported`, because the algorithm wasn't Pitloom's).

**Source-recording convention, per role** — each role's `source` string
records identity appropriate to *that* answerer, using the existing
generic `"Key: Value | Key: Value"` parser (no parser change needed for
any of these):

- `declared` — unchanged: `"Source: <file> | Field: <field>"`.
- `detected` — **implemented**: gains a `Tool:` segment with the
  detection library's version (`importlib.metadata.version("licenseid")`),
  e.g. `"Source: LICENSE | Method: licenseid_detection | Tool:
  licenseid==0.3.0"` — a detection result is only as reproducible as the
  library version that produced it.
- `externalReported` (future convention, not built) — `"Source: <service
  name> | Endpoint: <API path/version> | Retrieved: <ISO 8601 date>"`.
  Fits API-style sources (HF Hub, GitHub API); a non-API external source
  (a paper, a scraped webpage) will need its own, less endpoint-centric
  shape, worked out when that source type is actually built.
- `inferred` (extended, self-identifying form not built) — the answerer
  isn't Pitloom at all; inference happens in an agent process entirely
  outside Pitloom's own Python code, so it has to be the *agent's own
  self-reported* identity: `"Source: <agent name> (<vendor>) | Role:
  inferred | Date: <ISO 8601 date>"`, e.g. `"Source: Claude Code
  (Anthropic) | Role: inferred | Date: 2026-08-10"`. Pitloom cannot
  verify this at merge time — same trust model the `sbom-enrich` skill's
  existing generic `"Source: AI agent | Role: inferred"` marker (built
  2026-08-13) already has, just more specific when the agent knows its
  own identity.
- `sbomAuthorSupplied` — `"Source: SBOM author | Role:
  sbomAuthorSupplied | Date: <ISO 8601 date>"` for the human-interactive
  case (still a Skill-level convention, future — see above); **built**
  for the content-type-override case, using the file itself as `Source:`
  rather than `"SBOM author"` since there's a concrete subject to name:
  `"Source: <file> | Role: sbomAuthorSupplied"` (no `Date:` segment —
  unlike an interactive answer, there's no distinct point-in-time
  assertion to record beyond the SBOM's own creation timestamp). Same
  unverifiable trust model as `inferred`, just a different answerer.

**Role → native relationship mapping is today's default policy, not an
inherent law.** For license (G2's concrete example, see
[multi-source-conflict.md](multi-source-conflict.md)): `declared` →
`hasDeclaredLicense`, `detected` → `hasConcludedLicense` (the only place
the word "concluded" appears — as SPDX's own relationship-type name,
applied to the `detected` candidate). This is a policy choice made
*because* Pitloom's detector has no confidence score today — its one
output is the only candidate determination available to call
"concluded," not because a detected value is inherently more
trustworthy than a declared one. A bad/spurious detection can and does
produce a wrong `hasConcludedLicense` — a pre-existing limitation of the
single detector itself, not something G2 introduces. Once multiple
detectors or confidence scoring exist, this mapping is where a smarter
policy would plug in (e.g. falling back to `declared` when `detected`
confidence is low) — future work, not built. `externalReported`,
`inferred`, and `sbomAuthorSupplied` never map to a native relationship
for license (no 3rd/4th/5th native slot exists).
