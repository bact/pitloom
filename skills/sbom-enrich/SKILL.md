---
# Created: 2026-07-05
# Last-Modified: 2026-09-29
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

name: sbom-enrich
description: >-
  Enrich an existing Pitloom-generated SBOM or AIBOM through a merged
  fragment: an unstated license, a dependency's purpose, trainedOn/testedOn
  datasets read from README or model-card prose. Triggers: "enrich (this)
  SBOM", "improve this SBOM", "add more detail to the SBOM", "fill in
  missing SBOM information", "infer the dataset used to train this model".
  Also completing or checking minimum elements for NTIA 2021, CISA 2026 or
  G7 SBOM for AI 2026: "make this SBOM meet NTIA standard", "is this SBOM
  CISA 2026 compliant", "what's missing for CISA/NTIA compliance",
  "complete the minimum elements", "help filling minimum elements", "check
  this SBOM against NTIA/CISA minimum elements". That is a completeness
  question, not schema validity (sbom-validate). If no SBOM exists yet, or
  generation plus enrichment or a standard is asked in one breath
  ("generate SBOM and enrich it", "give me a complete SBOM", "SBOM with CISA
  2026 minimum elements"), sbom-generate triggers and hands off here.
license: Apache-2.0
argument-hint: "[sbom-file]"
---

# Enrich a Pitloom-generated SBOM

Two enrichment sources feed the same SBOM. `loom enrich` is Pitloom's own
**deterministic** mechanical enrichment (parses only YAML frontmatter in a
README/model card -- no reasoning, no network by default); when a local AI
model file is in scope, run it first, as it is fast and free. An agent
goes further: it can read **prose**, infer a plausible license from
ambiguous wording, classify a dependency's purpose, or work out
`trainedOn`/`testedOn` dataset relationships that no structured field
encodes. Do this only **after** a base SBOM exists (use the
`sbom-generate` skill first if it does not), and only when it adds real
information -- do not fabricate detail for its own sake. If generating
that base SBOM needs `--allow-build` and the user asked for it, always
pass an explicit `--build-timeout` (see `sbom-generate`'s "Choosing
`--build-timeout`").

**Limitation inherited from the base SBOM:** enrichment can only add
evidence to elements the base SBOM already contains. If the project mixes
Python with another ecosystem (a JS frontend, a Rust extension, etc.), the
non-Python dependencies never got an element in the first place -- there
is nothing here to attach a fragment to, and no amount of reading prose
will surface them. See `sbom-generate`'s "Known limitations" section; say
so rather than implying enrichment closes that gap.

Triggers automatically on natural-language requests (see the trigger
phrasings above), or invoke it explicitly with `/sbom-enrich [sbom-file]`
(`/pitloom:sbom-enrich [sbom-file]` when installed via the Claude Code
plugin). `sbom-file` is optional -- point it at a specific
already-generated SBOM when a project has more than one; omit it to let
the agent find the one to enrich.

See `references/examples.md` for a full worked example.

## Requirements

Python >= 3.10, the `loom`/`pitloom` entry point (`pip install
pitloom`); an AI model file needs `pip install "pitloom[ai]"`; the
mandatory post-merge check needs `pip install "pitloom[validate]"`.

## Contribute enrichment as a fragment, never by hand-editing

Do not edit the generated SBOM JSON directly. Pitloom has a purpose-built
mechanism for exactly this: **fragments**. Write the inferred facts as a
small, standalone SPDX 3 JSON file and let Pitloom merge it on the next
generation run.

Every inferred field's `comment` (or the fragment's
`CreationInfo.comment`) must carry a provenance marker, so it is never
confused with authoritative, extracted metadata. When you know your own
agent name, vendor, and today's date, include them -- Pitloom cannot
verify this, but it makes the record more useful to a reviewer than a
generic placeholder:

```text
Source: <your agent name> (<vendor>) | Role: inferred | Date: <ISO 8601 date>
```

For example: `Source: Claude Code (Anthropic) | Role: inferred | Date:
2026-08-10`. If you don't know your own name/vendor, fall back to the
generic form rather than guessing:

```text
Source: AI agent | Role: inferred
```

**In an interactive session** (a human present to answer), a field the
SBOM author directly tells you is not an inference -- mark it
`sbomAuthorSupplied`, not `inferred`:

```text
Source: SBOM author | Role: sbomAuthorSupplied | Date: <ISO 8601 date>
```

The `Role:` vocabulary an agent uses:

- `inferred` -- your own reasoning or judgement from prose.
- `declared` -- the subject's own stated claim, read from where it states
  it (a file's own license field, say).
- `externalReported` -- another party's determination or opinion, relayed
  as they gave it rather than re-derived by you (a paper's, a hub's).
- `sbomAuthorSupplied` -- the SBOM author stated the fact themselves.

**Where a fragment can be merged.** Registered fragments are merged only
into an SBOM that Pitloom generates from a project directory: `loom
project <dir>`, `loom generate <dir>`, the Hatchling build hook, or `loom
embed-wheel --project-dir <dir>`. Any other base -- `loom model`, a Hugging
Face model, a wheel, `loom env`, an sdist, or a third-party SBOM -- never
merges them, **silently** (exit 0, no `WARNING:`). For such a base, do
steps 1-7, then stop: report the gaps, hand the drafted fragment(s) over
unmerged, and tell the user they were not merged into the SBOM.

Steps:

1. Generate a base SBOM first, if not already done (use the
   `sbom-generate` skill), and **record the exact command that produced
   it** -- target, `-o`, `--config`, `--id-registry`,
   `--use-lockfile`/`--no-use-lockfile`, `--enrich`, `--allow-build` with
   its `--build-timeout`. Step 9 reuses it whole, and step 2 needs its
   `--config`, `--id-registry` and `--use-lockfile` parts: element ids are
   content-addressed, so a difference in any of them can make the
   fragment's references miss the base SBOM (see "Troubleshooting:
   dangling references"). If a base SBOM already exists and Pitloom was
   upgraded since it was generated, regenerate it
   before merging any fragment against it when the upgrade could have
   changed file discovery for this project's build backend (check the
   CHANGELOG for the installed version range).
2. **Run the deterministic pass first**, when a local AI model file is in
   scope: `loom enrich <model-file>`. Skip this step when there is none (a
   plain Python project, or a Hugging Face model, for which `loom enrich`
   fails with an `ERROR:`). It parses only YAML frontmatter (no prose, no
   reasoning) and writes a standalone fragment -- fast, free, and always
   safe to run before anything else. Read the fragment to see exactly
   which fields (`license`, `datasets:...`) it filled.

   **Always pass `-o <project-dir>/model.enrich.spdx3.json`.** Without
   `-o` the fragment is named `<model-file-name>.enrich.spdx3.json` and
   written to the *current directory*, not the project directory, while
   step 8 registers a project-relative path.

   **Only a project-directory base can be merged into** (see "Where a
   fragment can be merged" above). Add `--project-dir <dir>` (the same
   directory passed to `loom project`/`loom generate`). A project-level
   and a single-model SBOM assign a model's `ai_AIPackage` *different*
   ids, so without `--project-dir` the fragment misses the base (a
   `WARNING:` per dangling reference, then an `ERROR:` and a non-zero
   exit). Also pass the base run's own `--config`, `--id-registry` and
   `--use-lockfile`/`--no-use-lockfile` when it used them:
   `--project-dir` re-derives the base document's identity and registry
   from them. Omit them to auto-match the project's own config. With
   `--project-dir`, `loom enrich` picks up the project's own declared
   `id-registry` and never writes to it (see `sbom-generate`'s "Pinning
   element ids"). For a `loom model` base (never merged into) omit
   `--project-dir`: its ids are the model document's, not a project's.

   The fragment can attach only if the base SBOM has an `ai_AIPackage`
   for that model, i.e. the model file is among the files the project's
   build includes. If it is not, say so instead of merging.

   **If the base SBOM was generated with `--allow-build`**, `loom enrich`
   cannot reproduce its identity: it has no such flag and computes the
   identity from static file discovery, so the ids match only when the
   real build's file list equals the static one. Where they differ the
   merge fails; say so, and do not merge.
3. Read the project's `README.md` / model card **prose** and any other
   local docs. Only propose fields for gaps step 2 left untouched --
   `loom enrich` already found everything it could from frontmatter, so
   do not re-derive or restate those same fields.
4. **Interactive session only -- ask the SBOM author about remaining
   gaps they're plausibly positioned to know:** intended use, training-data
   provenance/consent, deployment restrictions -- not facts derivable from
   files (those belong in steps 2-3, not here). Ask targeted questions for
   *specific* remaining gaps only, not an open-ended interview. **Skip
   this step entirely in a non-interactive run** (CI, batch, no human to
   answer) -- do not block waiting for input.

   **The answer decides the role -- is it the fact, or a pointer to the
   fact?**
   - The SBOM author states the fact itself ("it's MIT", "yes, trained on
     our internal support-ticket corpus"): mark it `Source: SBOM author |
     Role: sbomAuthorSupplied | Date: <ISO 8601 date>` -- never `Role:
     inferred`; you didn't derive it, you relayed what you were told.
   - The SBOM author points at a source instead ("look at
     CONTRIBUTING.md", "read the wiki page", "try the HF card", "infer it
     from the changelog"): go look. The role is *never*
     `sbomAuthorSupplied` here -- it's whichever of
     `declared`/`externalReported`/`inferred` matches how you actually got
     the value from that source once you looked.
5. **Before using any source outside this project** -- whether the SBOM
   author pointed you at it (step 4) or you noticed it **on your own
   initiative**: already in your context window, in another file you have
   permission to read, or at a known remote location (e.g. PyPI, arXiv,
   Hugging Face Hub, GitHub, GitLab, Codeberg, or a URL already visible in
   context) -- stop and ask the SBOM author for permission first. Name
   exactly what you found and where; an unprompted find needs an *at
   least as* explicit ask as a prompted one, since nothing invited you to
   go looking. Never fold such a finding into a fragment silently. That
   permission check is a consent gate, not a provenance role -- it still
   never makes the result `sbomAuthorSupplied`. **Non-interactive run:**
   use no outside source; list what you found and where in the final
   report as "not used -- needs consent".
6. Draft your own fragment (`*.spdx3.json`) containing only the elements
   or relationships you infer from prose (e.g. a `dataset_DatasetPackage`
   plus a `trainedOn` relationship, or a `comment` refining a license
   guess). Mark every inferred value with the provenance string above.
   If any field or comment references a file path (e.g. citing where in
   the repo you found the evidence), write it POSIX-style
   (`docs/model-card.md`, not `docs\model-card.md`) regardless of what OS
   you're running on -- Pitloom-generated SBOMs are byte-identical across
   operating systems, and a backslash path in agent-authored content would
   be the one thing that isn't.

   A `Relationship` must point at real ids: copy the model's `ai_AIPackage`
   `spdxId` from the base SBOM as its `from`, and give every new element
   its own `spdxId`. `references/examples.md` shows complete elements.

   **Default precedence: the deterministic result wins.** If step 2
   already set a field, do not silently re-propose a different value for
   it in your own fragment -- that produces two conflicting relationships
   on the same subject with no way for a reviewer to tell which one is
   current.

   **Override path**, when you disagree: you may override a
   deterministic value only when prose gives clear contradicting evidence
   (e.g. the frontmatter `license:` looks stale against what the README
   body actually says). When you do, record *both* values and your
   reasoning in the fragment entry's provenance comment:

   ```text
   Source: <your agent name> (<vendor>) | Role: inferred | Overrides: <deterministic value> | Reason: <why>
   ```

   and say so explicitly in your final report (step 11) -- an override
   must never be silent.
7. **Pre-merge check (mandatory):** read every drafted fragment (step 2's
   and step 6's) with the JSON-LD deserialiser `merge_fragments()` itself
   uses. It catches malformed JSON and SPDX-shape errors (an unknown
   property or type) before registration -- a fragment that fails to read
   is skipped with only a `WARNING:` (the merge fails if it is registered
   with `required = true`), so catch it now rather than after a wasted
   `loom` run. Exit 0 is a pass:

   ```bash
   python3 -c "
   import sys
   from spdx_python_model.bindings import v3_0_1 as spdx3
   for path in sys.argv[1:]:
       with open(path, 'rb') as f:
           spdx3.JSONLDDeserializer().read(f, spdx3.SHACLObjectSet())
   " model.enrich.spdx3.json fragments/agent-enrichment.spdx3.json
   ```

   Do not use `loom fragment validate` or `spdx3-validate` on a fragment:
   it refers to the base SBOM's ids without an `ExternalMap`, so it fails
   SHACL on its own (exit 1) even when correct. The merged SBOM is
   validated at step 10.

8. Register **both** fragments so Pitloom merges them on the next run.
   `required = true` makes a missing or unparsable fragment fail the run
   instead of being skipped with a `WARNING:`:

   ```toml
   [tool.pitloom.fragment]
   files = [
     { path = "model.enrich.spdx3.json", required = true },
     { path = "fragments/agent-enrichment.spdx3.json", required = true },
   ]
   ```

9. Re-run **the exact command that produced the base SBOM** (step 1: same
   target, `-o`, `--config`, `--id-registry`, `--use-lockfile`, `--enrich`
   and `--allow-build`/`--build-timeout` flags), so the merged, enriched
   SBOM is written. `loom generate` without `-o` exits 1.
10. **Post-merge check (mandatory):** use the `sbom-validate` skill on
    `<merged-sbom-file>` -- a syntactically valid fragment can still miss
    a required property or use the wrong relationship type, which only
    shape/SHACL validation catches. Minimal fallback: `pip install
    "pitloom[validate]"` then `loom fragment validate <merged-sbom-file>`.
11. Tell the user what was found deterministically (step 2), what was
    inferred from prose (step 6), and what the SBOM author supplied
    directly (step 4) -- and call out any override from step 6 explicitly
    -- this is provenance-tracked, agent-relayed data, not ground truth.

For the full enrichment data-source table, the `[tool.pitloom] enrich`
enable/disable model, and the dataset-relationship field map, see
`working-docs/design/sbom-enrichment.md` in the Pitloom repository.

### Troubleshooting: dangling references

Merging a fragment whose ids the base SBOM does not have makes
`merge_fragments()` log a `WARNING:` per dangling reference, then fail
(the CLI prints an `ERROR:` and exits non-zero) rather than write a broken
SBOM. Regenerate the base SBOM, re-run enrichment, and merge again; do not
retry the same merge. Check these causes in order:

- **A Pitloom upgrade** changed file discovery. Ids are content-addressed
  from the resolved file set (`doc_uuid` includes the Merkle root of the
  file list), so a more accurate list from unchanged source gives new ids.
- **A registry mismatch:** declared on one run but not the other, or a
  different file in each. Base run and `loom enrich` must resolve the same
  registry; without `--project-dir`, `loom enrich` reads no project
  config, so pass the base run's `--id-registry`/`--config`.
- **`--project-dir` omitted** for a project-level base (step 2).
- **A flag mismatch:** `--config` or `--use-lockfile`/`--no-use-lockfile`
  differs between the base run and `loom enrich`.
- **A base built with `--allow-build`** (step 2).
- **One dependency name held twice** (a dependency at two versions): a run
  never writes it to the registry, so its id can move with the source. If
  the user declared a registry, pin the first holder with `loom id generate
  <PATH> -e NAME:software_Package -o <declared-registry>`, then write the
  fragment against that id. Only one holder can be pinned, so every later
  run prints an expected `WARNING: ID registry: ... registered for both
  ...` for the other. If no registry is declared, create none; tell the
  user (`sbom-generate`'s "Pinning element ids" and its ID registry
  reference).

## Complete a standard's minimum elements

A separate entry point into the same fragment/provenance/merge mechanism
above, driven by a **checklist** (a named standard's required elements)
instead of open-ended prose reading. Use this when the request names a
standard or asks what's missing for compliance, rather than asking for
enrichment in general.

Steps a and b work on any SPDX 3 SBOM. The merge (step f) works only for
a project-directory base (see "Where a fragment can be merged" above); for
any other SBOM, stop after b and report the gaps, or, if you drafted a
fragment, hand it over unmerged and say so.

Steps below are lettered (a-g) to keep them visually distinct from the
numbered steps 1-11 above, which they reference by number.

a. **Identify the target standard(s).** NTIA 2021, CISA 2026 (the current
   baseline; supersedes NTIA 2021), or G7 SBOM for AI 2026 (additive, only
   when the SBOM has an `ai_AIPackage`). If the user doesn't name one:
   interactive, ask; non-interactive, use CISA 2026 (plus G7 AI if
   applicable) and say so in the report. See
   `references/minimum-elements.md` for the three checklists, each element
   mapped to the Pitloom/SPDX 3 field that already carries it.
b. **Gap analysis.** For each element in the chosen checklist(s), check
   the base SBOM JSON-LD for the mapped field and report present / missing
   / `NOASSERTION`-or-empty. Don't assume the reference file's
   "covered"/"conditional" calls still hold -- they were checked against
   one real generated SBOM, not guaranteed for every run.
c. **Resolve each gap using the same precedence steps 2-5 above already
   establish**: the deterministic `loom enrich` pass first, then
   README/model-card/other local file prose, then (interactive sessions
   only, consent-gated per step 5 above) anything found outside the
   project on the agent's own initiative. Only reach step d below for
   what's still unresolved after this.
d. **Interactive-only, one field at a time.** Ask the user for each
   remaining gap, using `references/minimum-elements.md`'s question bank
   for phrasing and "where to look" guidance. Apply the same role-decision
   rule as step 4 above (the user states the fact directly ->
   `sbomAuthorSupplied`; the user points at a source -> go look, role is
   `declared`/`externalReported`/`inferred` per how it was obtained). Skip
   this step entirely in a non-interactive run, same as above.

   **Step d, lead with effort-to-impact, not checklist order.** Before
   asking, rank the remaining gaps: quick answers (a plain yes/no, a fact
   the user obviously already knows) and answers that resolve multiple
   elements or multiple standards at once go first (e.g. setting
   `[[tool.pitloom.creator]]` closes both `SBOM Author` and `Component
   Producer` for the main package in one step -- see
   `references/minimum-elements.md`'s NTIA "Supplier Name" row for why).
   Say up front which few answers would close most of the remaining gap,
   so the user can judge where their time actually pays off -- don't just
   work a flat list top to bottom.

   **Step d, exit path.** The user can stop the Q&A at any point ("stop",
   "that's enough", "skip the rest", or equivalent). This is not a
   failure -- proceed straight to step f (draft/validate/merge) with
   whatever was gathered, and list the still-unresolved elements as open
   gaps in step g's final report rather than blocking on them or
   insisting they be answered first.
e. **Contradiction check.** Before drafting the fragment, compare each new
   answer against the base SBOM's existing value for that field and
   against other answers already collected this session. If they
   conflict, interactive: surface both and ask the user to confirm which
   stands, the same way step 6 above handles a prose-vs-frontmatter
   conflict. Non-interactive: keep the base value, record the conflicting
   candidate in the provenance comment, and list it as an open conflict in
   step g. Never silently pick one.
f. **Draft, validate, register, merge, validate** -- reuse steps 6-10
   above verbatim. No new mechanism: this workflow only changes *what*
   gets proposed and *how it's selected*, not how it's recorded or merged.
g. **Final report.** List which elements are now satisfied, which remain
   unknown by explicit user choice (write `NOASSERTION`/"unknown" in the
   fragment, per CISA 2026's "Explicitly Identifying Unknown Information"
   practice, rather than silently omitting the field), and which have no
   automatable path at all (SBOM Author Signature, most G7 AI Security
   Properties/KPI elements, dataset statistical properties) with a plain
   note that they need something outside this workflow.

`references/minimum-elements.md` also lists a manual, optional cross-check
(`ntia-conformance-checker`) for NTIA/CISA targets -- not a required step,
and not wired into this skill.

## Check stderr for INFO:/WARNING:/ERROR: lines

`loom enrich`/`loom project`/`loom generate`/`loom merge` log to stderr
with the `INFO:`/`WARNING:`/`ERROR:` convention described in
`sbom-generate`'s "Check stderr" section: scan it after every call and
mention any hit to the user, even when the command exited 0. The one to
expect here is the dangling-reference `WARNING:` plus `ERROR:` above. After
an ambiguous-name pin (`sbom-generate`'s `references/id-registry.md`), a
`WARNING: ID registry: ... is registered for both` line on every run is
expected, not a stale entry.

## See also

- `references/examples.md` -- full worked example.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/references/examples.md>
- `references/minimum-elements.md` -- the NTIA/CISA/G7 checklists,
  field mappings, and question bank for "Complete a standard's minimum
  elements" above.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/references/minimum-elements.md>
- The sibling `sbom-generate` skill -- generates the base SBOM this
  enriches; owns the ID registry reference.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/SKILL.md>
- The sibling `sbom-validate` skill -- the mandatory post-merge check.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
- `docs/resources.md` -- SPDX 3 spec, ontology, and JSON Schema links.
  <https://bact.github.io/pitloom/resources/>
