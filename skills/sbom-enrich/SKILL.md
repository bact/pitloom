---
# Created: 2026-07-05
# Last-Modified: 2026-10-01
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
compatibility: >-
  Requires a shell, Python 3.10+ and pitloom >= 0.20.0 (pip, uvx or pipx);
  a local AI model file needs pitloom[ai] and the post-merge check needs
  pitloom[validate]. Needs an existing Pitloom SBOM (sbom-generate) and file
  write access to the project. Needs network access to install pitloom;
  outside sources such as PyPI or Hugging Face are used only with the user's
  consent. Not usable where packages cannot be installed, e.g. Claude API
  code execution.
---

# Enrich a Pitloom-generated SBOM

Two enrichment sources feed the same SBOM. `loom enrich` is Pitloom's own
**deterministic** enrichment (parses only YAML frontmatter in a README/model
card -- no reasoning, no network by default); with a local AI model file in
scope, run it first, as it is fast and free. An agent goes further: it can
read **prose**, infer a plausible license from ambiguous wording, classify
a dependency's purpose, or work out `trainedOn`/`testedOn` dataset
relationships no structured field encodes. Do this only **after** a base
SBOM exists (use `sbom-generate` first if not), and only when it adds real
information. If generating
that base SBOM needs `--allow-build` and the user asked for it, always
pass an explicit `--build-timeout` (see `sbom-generate`'s "Choosing
`--build-timeout`").

**Limitation inherited from the base SBOM:** enrichment can only add
evidence to elements the base SBOM already contains. In a project that
mixes Python with another ecosystem (a JS frontend, a Rust extension), the
non-Python dependencies have no element to attach a fragment to, and
reading prose will not surface them. See `sbom-generate`'s "Known
limitations" section; say so rather than implying enrichment closes that
gap.

This skill is one of three (`sbom-generate`, `sbom-enrich`,
`sbom-validate`) meant to be installed together: it refers to sections of
`sbom-generate` and hands off to `sbom-validate`.

Triggers automatically on natural-language requests (see the trigger
phrasings above), or invoke it explicitly with `/sbom-enrich [sbom-file]`
(`/pitloom:sbom-enrich [sbom-file]` when installed via the Claude Code
plugin; the syntax depends on the client, e.g. `$sbom-enrich` in Codex).
`sbom-file` is optional -- point it at a specific already-generated SBOM
when a project has more than one; omit it to let the agent find the one to
enrich.

See `references/examples.md` for a full worked example.

## Requirements

Python >= 3.10 and **pitloom >= 0.20.0** (earlier releases lack
`--id-registry`, `loom id` and `--build-timeout`), the `loom`/`pitloom`
entry point: `pip install "pitloom>=0.20.0"`; an AI model file needs
`pip install "pitloom[ai]>=0.20.0"`; the mandatory post-merge check needs
`pip install "pitloom[validate]>=0.20.0"`. Ephemeral runs and the pin
spelling: `sbom-generate`'s "Run without installing anything persistent".

Snippets are POSIX shell. On Windows use `python` or `py` for `python3`,
and PowerShell equivalents (PowerShell 5.1 has no `&&`: run the commands
one per line).

## Contribute enrichment as a fragment, never by hand-editing

Do not edit the generated SBOM JSON directly. Write the inferred facts as
a small, standalone SPDX 3 JSON **fragment** and let Pitloom merge it on
the next generation run.

Every inferred field's `comment` (or the fragment's
`CreationInfo.comment`) must carry a provenance marker, so it is never
confused with authoritative, extracted metadata. Include your own agent
name, vendor and today's date when you know them (Pitloom cannot verify
them, but they help a reviewer):

```text
Source: <your agent name> (<vendor>) | Role: inferred | Date: <ISO 8601 date>
```

Fill in your own identity, e.g. `Source: Claude Code (Anthropic) | Role:
inferred | Date: 2026-08-10` or `Source: Codex (OpenAI) | Role: inferred |
Date: 2026-08-10` -- never copy another agent's name. If you don't know
your own name/vendor, fall back to the generic form rather than guessing:

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

- `inferred` -- your own reasoning from prose.
- `declared` -- the subject's own claim, read where it states it (a
  file's own license field).
- `externalReported` -- another party's determination, relayed as given
  (a paper's, a hub's).
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
   dangling references"). If Pitloom was upgraded since the base SBOM was
   generated, regenerate it before merging when the upgrade could have
   changed file discovery for this project's build backend (check the
   CHANGELOG).
2. **Run the deterministic pass first**, when a local AI model file is in
   scope; skip it otherwise (a plain Python project, or a Hugging Face
   model, for which `loom enrich` fails with an `ERROR:`). It parses only
   YAML frontmatter and writes a standalone fragment -- fast, free, safe.
   Read the fragment to see which fields (`license`, `datasets:...`) it
   filled:

   ```bash
   loom enrich <model-file> --project-dir <dir> -o <dir>/model.enrich.spdx3.json
   ```

   - **Always pass `-o <project-dir>/model.enrich.spdx3.json`**: step 8
     registers a project-relative path.
   - **Only a project-directory base can be merged into** (see "Where a
     fragment can be merged"), so pass `--project-dir <dir>` (the directory
     given to `loom project`/`loom generate`); without it every reference
     dangles (a `WARNING:` each, then an `ERROR:`). Also pass the base
     run's `--config`, `--id-registry` and `--use-lockfile`/
     `--no-use-lockfile` when it used them. For a `loom
     model` base (never merged into) omit `--project-dir`.
   - The fragment attaches only if the base has an `ai_AIPackage` for that
     model (the model file is among the build's files); if not, say so
     instead of merging.
   - A base generated with `--allow-build` cannot be reproduced by `loom
     enrich` (static discovery only): where the file lists differ the
     merge fails; say so, and do not merge.

   Why each rule holds: `references/deterministic-pass.md`.
3. Read the project's `README.md` / model card **prose** and other local
   docs. Propose only fields for gaps step 2 left untouched; do not
   restate what it already found.
   - An `ai_AIPackage` whose `name` is its format (`gguf`, `onnx`, ...)
     **and** that has no other `ai_*` or `comment` property is a stub:
     Pitloom did not read the file (a format-named entry *with* properties
     was read; some formats carry no name). The base run's stderr says why:
     `required library not installed` -- install `pitloom[ai]` and
     regenerate; `... metadata not read` -- a fixed safety bound, not
     configurable. Fields the file itself would give (hyperparameters,
     inputs, outputs) are better read than inferred: tell the user the cause
     before inferring them from prose. (`max-model-extract-bytes` and
     `--trust-wheel-model` apply to wheel scans only, never a merge base.)
4. **Interactive session only -- ask the SBOM author about remaining
   gaps they're plausibly positioned to know:** intended use, training-data
   provenance/consent, deployment restrictions -- not facts derivable from
   files (steps 2-3). Ask targeted questions for *specific* gaps, not an
   open-ended interview. **Skip this step in a non-interactive run** (CI,
   batch) -- do not block waiting for input.

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
5. **Before using any source outside this project** -- one the SBOM
   author pointed you at (step 4), or one you noticed **on your own
   initiative** (in your context window, in another readable file, or at a
   remote location such as PyPI, arXiv, Hugging Face Hub, GitHub, GitLab,
   Codeberg or a URL already in context) -- stop and ask the SBOM author
   for permission first. Name exactly what you found and where; an
   unprompted find needs an *at least as* explicit ask, since nothing
   invited you to look. Never fold such a finding into a fragment
   silently. This consent gate is not a provenance role: it never makes
   the result `sbomAuthorSupplied`. **Non-interactive run:** use no
   outside source; list what you found and where in the final report as
   "not used -- needs consent".
6. Draft your own fragment (`*.spdx3.json`) containing only the elements
   or relationships you infer from prose (e.g. a `dataset_DatasetPackage`
   plus a `trainedOn` relationship, or a `comment` refining a license
   guess). Mark every inferred value with the provenance string above.
   Write any file path in a field or comment POSIX-style
   (`docs/model-card.md`, not `docs\model-card.md`) on every OS:
   Pitloom-generated SBOMs are byte-identical across operating systems,
   and a backslash path would be the one thing that isn't.

   A `Relationship` must point at real ids: copy the model's `ai_AIPackage`
   `spdxId` from the base SBOM as its `from`, and give every new element
   its own `spdxId`. `references/examples.md` shows complete elements.

   **The deterministic result wins by default:** if step 2 already set a
   field, do not re-propose a different value in your own fragment (two
   conflicting relationships on one subject, no way to tell which is
   current). **Override** only when prose clearly contradicts it (e.g. a
   stale frontmatter `license:`): record *both* values and your reasoning
   in that entry's provenance comment,

   ```text
   Source: <your agent name> (<vendor>) | Role: inferred | Overrides: <deterministic value> | Reason: <why>
   ```

   and say so in your final report (step 11) -- never silently.
7. **Pre-merge check (mandatory):** read every drafted fragment (step 2's
   and step 6's) with the JSON-LD deserialiser `merge_fragments()` itself
   uses. It catches malformed JSON and many SPDX-shape errors (an unknown
   property on a known type, a wrongly typed value, an element without an
   `spdxId`, a misspelled type that carries properties) before
   registration -- otherwise a fragment that fails to read is skipped with
   only a `WARNING:` (the merge fails if it is registered with `required =
   true`), a wasted `loom` run. It does not catch a bare unrecognised type
   with no other key, not even `spdxId` (read as an extensible object), or
   a missing required property (step 10 does). Exit 0 is a pass. This is
   the one home of the snippet.

   It imports `spdx_python_model`, which only Pitloom's own environment
   has, so run it with the interpreter Pitloom is installed in, not
   whichever `python3` is on `PATH`:

   ```bash
   python3 -c "import sys,io,pathlib; from spdx_python_model.bindings import v3_0_1 as s; [s.JSONLDDeserializer().read(io.BytesIO(pathlib.Path(p).read_bytes()), s.SHACLObjectSet()) for p in sys.argv[1:]]" model.enrich.spdx3.json fragments/agent-enrichment.spdx3.json
   ```

   With no persistent install, replace `python3` by `uvx --from
   "pitloom>=0.20.0" python` (or, with pipx, `pipx run --spec
   "pitloom>=0.20.0" python`; its "already on your PATH" notice is
   harmless). With `pipx install`, use the venv's
   interpreter (`$(pipx environment --value PIPX_LOCAL_VENVS)/pitloom/bin/python`;
   `Scripts\python.exe` on Windows); on Windows otherwise use `py` or
   `python`.

   Do not use `uv run --with` for this: in a project directory it creates
   `.venv` and `uv.lock` there and builds the project (running its
   build backend, against the `--allow-build` hard rule).

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
   SBOM is written (`loom generate` without `-o` exits 1).
10. **Post-merge check (mandatory):** use the `sbom-validate` skill on
    `<merged-sbom-file>` -- a syntactically valid fragment can still miss
    a required property or use the wrong relationship type, which only
    shape/SHACL validation catches. Minimal fallback: `pip install
    "pitloom[validate]>=0.20.0"` then `loom fragment validate
    <merged-sbom-file>`.
11. Tell the user what was found deterministically (step 2), what was
    inferred from prose (step 6), and what the SBOM author supplied
    directly (step 4) -- and call out any override from step 6 explicitly
    -- this is provenance-tracked, agent-relayed data, not ground truth.

For `loom enrich` and the `[tool.pitloom] enrich` and
`[tool.pitloom.fragment]` settings, see
<https://bact.github.io/pitloom/cli/#enrich-an-sbom> and
<https://bact.github.io/pitloom/configuration/>.

### Troubleshooting: dangling references

Merging a fragment whose ids the base SBOM does not have makes
`merge_fragments()` log a `WARNING:` per dangling reference, then fail (the
CLI prints an `ERROR:` and exits non-zero) rather than write a broken SBOM.
Regenerate the base SBOM, re-run enrichment and merge again; never retry
the same merge. Never create or write an ID registry the user did not
declare to fix it. Likely causes, in order: a Pitloom upgrade changed file
discovery; a registry mismatch between the base run and `loom enrich`;
`--project-dir` omitted; a `--config`/`--use-lockfile` mismatch; a base
built with `--allow-build`; one dependency name held twice. Why each
misses, and the fix for the last: `references/dangling-references.md`.

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

a. **Identify the standard(s):** NTIA 2021, CISA 2026 (current baseline;
   supersedes NTIA 2021), G7 SBOM for AI 2026 (additive; only with an
   `ai_AIPackage`). Unnamed: interactive, ask; non-interactive, use CISA
   2026 (plus G7 AI if applicable) and say so in the report.
   `references/minimum-elements.md` has the checklists, each element
   mapped to the SPDX 3 field that carries it.
b. **Gap analysis:** per element, check the mapped field in the base SBOM
   and report present / missing / `NOASSERTION`-or-empty. Don't trust the
   reference's "covered"/"conditional" calls: they were checked against
   one real SBOM.
c. **Resolve gaps by the precedence of steps 2-5:** deterministic `loom
   enrich`, then local prose, then (interactive only, consent-gated per
   step 5) outside sources. Only what is left reaches step d.
d. **Interactive only, one field at a time,** using
   `references/minimum-elements.md`'s question bank and step 4's role rule.
   Ask quick or high-impact answers first. The user can stop at any point:
   go to step f with what was gathered; list the rest as open gaps. Skip
   in a non-interactive run.
e. **Contradiction check** before drafting: compare each new answer with
   the base SBOM's value and earlier answers. Interactive: ask which
   stands. Non-interactive: keep the base value, record the candidate in
   the provenance comment, list an open conflict in step g. Never pick
   silently.
f. **Draft, validate, register, merge, validate:** reuse steps 6-10
   verbatim. Only *what* is proposed changes, not how it is recorded.
g. **Final report:** elements now satisfied; those unknown by the user's
   choice (write `NOASSERTION`, don't omit the field); those with no
   automatable path (SBOM Author Signature, most G7 AI Security/KPI
   elements, dataset statistical properties), which need something outside
   this workflow.

Detail for steps d and g: `references/minimum-elements-workflow.md`.

## Check stderr for INFO:/WARNING:/ERROR: lines

`loom enrich`/`project`/`generate`/`merge` log to stderr with the
convention in `sbom-generate`'s "Check stderr" section: scan it after
every call and mention any hit, even on exit 0. Expect the
dangling-reference `WARNING:` plus `ERROR:` above. After an ambiguous-name
pin (`sbom-generate`'s `references/id-registry.md`, on GitHub:
<https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/id-registry.md>),
a `WARNING: ID registry: ... is registered for both` line on every run is
expected, not a stale entry.

## See also

- `references/examples.md` -- full worked example.
- `references/minimum-elements.md` -- the NTIA/CISA/G7 checklists, field
  mappings and question bank; `references/minimum-elements-workflow.md`
  -- step detail for "Complete a standard's minimum elements".
- `references/deterministic-pass.md`, `references/dangling-references.md`
  -- `loom enrich` detail and merge-failure causes.
- All of these are on GitHub:
  <https://github.com/bact/pitloom/tree/main/skills/sbom-enrich/references>
- The sibling `sbom-generate` skill -- generates the base SBOM this
  enriches; owns the ID registry reference.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/SKILL.md>
- The sibling `sbom-validate` skill -- the mandatory post-merge check.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
- `docs/resources.md` -- SPDX 3 spec, ontology, and JSON Schema links.
  <https://bact.github.io/pitloom/resources/>
