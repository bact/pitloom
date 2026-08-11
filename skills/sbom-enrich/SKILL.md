---
name: sbom-enrich
description: >-
  Use this skill when asked to enrich, augment, or add inferred detail to
  a Pitloom-generated SBOM or AIBOM -- for example inferring an unstated
  license, classifying a dependency's purpose, or deriving
  trainedOn/testedOn dataset relationships from a README or model card
  that no file format encodes explicitly. Trigger phrasings include
  "enrich this SBOM", "enrich SBOM", "improve this SBOM", "add more detail
  to the SBOM", "get more info into the SBOM", "fill in information to the
  SBOM", "infer the dataset used to train this model", "fill in missing
  SBOM information from the README/model card". Requires a
  Pitloom-generated SBOM to already exist -- generate one first with the
  `sbom-generate` skill if it does not (a request that asks for both in
  one breath, e.g. "generate SBOM and enrich it" or "give me a complete
  SBOM", is `sbom-generate`'s to trigger on -- see that skill's "Combine
  with enrichment" section).
license: Apache-2.0
argument-hint: "[sbom-file]"
---

<!-- Created: 2026-07-05 -->
<!-- Last-Modified: 2026-08-11 -->
<!-- SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul -->
<!-- SPDX-FileType: SOURCE -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Enrich a Pitloom-generated SBOM

Two enrichment sources feed the same SBOM. `loom enrich` is Pitloom's own
**deterministic** mechanical enrichment (parses only YAML frontmatter in a
README/model card -- no reasoning, no network by default) -- always run it
first, it is fast and free. An agent goes further: it can read **prose**,
infer a plausible license from ambiguous wording, classify a dependency's
purpose, or work out `trainedOn`/`testedOn` dataset relationships that no
structured field encodes. Do this only **after** a base SBOM exists (use
the `sbom-generate` skill first if it does not), and only when it adds
real information -- do not fabricate detail for its own sake.

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

## Contribute enrichment as a fragment, never by hand-editing

Do not edit the generated SBOM JSON directly. Pitloom has a purpose-built
mechanism for exactly this: **fragments**. Write the inferred facts as a
small, standalone SPDX 3 JSON file and let Pitloom merge it on the next
generation run. See `references/examples.md` for a full worked example.

Every inferred field's `comment` (or the fragment's
`CreationInfo.comment`) must carry a provenance marker, so it is never
confused with authoritative, extracted metadata. When you know your own
agent name, vendor, and today's date, include them -- Pitloom cannot
verify this, but it makes the record more useful to a reviewer than a
generic placeholder:

```text
Source: <your agent name> (<vendor>) | Method: inference | Date: <ISO 8601 date>
```

For example: `Source: Claude Code (Anthropic) | Method: inference | Date:
2026-08-10`. If you don't know your own name/vendor, fall back to the
generic form rather than guessing:

```text
Source: AI agent | Method: inference
```

**In an interactive session** (a human present to answer), a field the
SBOM author directly tells you is not an inference -- mark it
`sbomAuthorSupplied`, not `inference`:

```text
Source: SBOM author | Method: sbomAuthorSupplied | Date: <ISO 8601 date>
```

Steps:

1. Generate a base SBOM first, if not already done (use the
   `sbom-generate` skill).
2. **Run the deterministic pass first:** `loom enrich <model-file>` for
   each local AI model file in scope. This parses only YAML frontmatter
   (no prose, no reasoning) and writes a standalone fragment -- fast,
   free, and always safe to run before anything else. Inspect the printed
   output path and read the fragment to see exactly which fields
   (`license`, `datasets:...`) it filled.

   **If the base SBOM is project-level** (came from `sbom-generate`
   running `loom project <dir>`/`loom generate <dir>`, not a bare
   `loom model <file>`), add `--project-dir <dir>` (the same directory
   passed to `loom project`) to this `loom enrich` call. Project-level
   and single-model SBOMs assign a model's `ai_AIPackage` a *different*
   id; omitting `--project-dir` in the project-level case produces a
   fragment that references an id absent from the base SBOM, so the
   dataset relationship and enrichment evidence silently fail to attach
   once merged -- no error, just missing data in the output. When
   `--registry <file>` was used for the base SBOM, pass the same
   `--registry` here too.
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
     Method: sbomAuthorSupplied | Date: <ISO 8601 date>` -- never `Method:
     inference`; you didn't derive it, you relayed what you were told.
   - The SBOM author points at a source instead ("look at
     CONTRIBUTING.md", "read the wiki page", "try the HF card", "infer it
     from the changelog"): go look. The role is *never*
     `sbomAuthorSupplied` here -- it's whichever of
     `declared`/`externalReported`/`inferred` matches how you actually got
     the value from that source once you looked (see the role vocabulary
     in `working-docs/implementation/annotation-provenance.md`).
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
   never makes the result `sbomAuthorSupplied`.
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
   Source: <your agent name> (<vendor>) | Method: inference | Overrides: <deterministic value> | Reason: <why>
   ```

   and say so explicitly in your final report (step 11) -- an override
   must never be silent.
7. **Pre-merge check (mandatory):** validate each drafted fragment (the
   deterministic one from step 2 and your own from step 6) is
   syntactically valid JSON before registering it -- a fragment with
   broken JSON is silently dropped by `merge_fragments()`'s catch-and-warn
   behaviour, so catch it now rather than after a wasted `loom` run:

   ```bash
   python3 -c "import json,sys; json.load(open(sys.argv[1]))" \
     fragments/agent-enrichment.spdx3.json
   ```

   For a stronger check, run the fragment through the same SPDX 3
   JSON-LD deserializer `merge_fragments()` itself uses -- this catches
   the same broken-JSON-LD cases `merge_fragments()` swallows as a
   warning, plus SPDX-shape problems (e.g. an unknown property or type)
   that plain JSON-syntax validity would miss:

   ```bash
   python3 -c "
   import sys
   from spdx_python_model.bindings import v3_0_1 as spdx3
   with open(sys.argv[1], 'rb') as f:
       spdx3.JSONLDDeserializer().read(f, spdx3.SHACLObjectSet())
   " fragments/agent-enrichment.spdx3.json
   ```

8. Register **both** fragments so Pitloom merges them on the next run:

   ```toml
   [tool.pitloom.fragments]
   files = [
     "model.enrich.spdx3.json",
     "fragments/agent-enrichment.spdx3.json",
   ]
   ```

9. Re-run `loom project <path>` or `loom generate <path>` (generate again) so
   the merged, enriched SBOM is written.
10. **Post-merge check (mandatory):** use the `sbom-validate` skill on
   `<merged-sbom-file>` -- a syntactically valid fragment can still be
   missing a required property or use the wrong relationship type, which
   only shape/SHACL validation catches.

11. Tell the user what was found deterministically (step 2), what was
   inferred from prose (step 6), and what the SBOM author supplied
   directly (step 4) -- and call out any override from step 6 explicitly
   -- this is provenance-tracked, agent-relayed data, not ground truth.

For the full enrichment data-source table, the `[tool.pitloom.enrich]`
enable/disable model, and the dataset-relationship field map, see
`working-docs/design/sbom-enrichment.md` in the Pitloom repository.

## See also

- `references/examples.md` -- full worked example.
- The sibling `sbom-validate` skill -- used for the mandatory post-merge
  check above.
- `docs/resources.md` in the Pitloom repository -- SPDX 3 spec, ontology,
  and JSON Schema links.
