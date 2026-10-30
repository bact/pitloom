---
# Created: 2026-07-05
# Last-Modified: 2026-10-30
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

name: sbom-enrich
description: >-
  Enrich an existing Pitloom-generated SBOM or AIBOM through a merged
  fragment: an unstated licence, a dependency's purpose, trainedOn/testedOn
  datasets read from README or model-card prose. Triggers: "enrich (this)
  SBOM", "improve this SBOM", "add more detail to the SBOM", "fill in
  missing SBOM information", "infer the dataset used to train this model".
  Also completing or checking a standard's elements (NTIA 2021, FSCT 2024,
  CISA 2026, G7 SBOM for AI 2026, BSI TR-03183-2): "make this SBOM meet
  NTIA minimum elements", "is this SBOM CISA 2026/FSCT compliant", "does
  it meet BSI TR-03183", "check this SBOM against NTIA/CISA/G7 AI",
  "what's missing for compliance", "complete/help filling the minimum
  elements". That is completeness, not schema validity (sbom-validate). If
  no SBOM exists yet, or generation plus enrichment or a standard is asked
  in one breath ("generate SBOM and enrich it", "give me a complete SBOM",
  "SBOM with CISA 2026 minimum elements"), sbom-generate triggers and hands
  off here.
license: Apache-2.0
compatibility: >-
  Requires a shell, Python 3.10+ and pitloom >= 0.22.0 (pip, uvx or pipx);
  a local AI model file needs pitloom[ai] and the post-merge check needs
  pitloom[validate]. Needs an existing Pitloom SBOM (sbom-generate) and file
  write access to the project. Needs network access to install pitloom;
  outside sources such as PyPI or Hugging Face are used only with the user's
  consent. Not usable where packages cannot be installed, e.g. Claude API
  code execution.
---

# Enrich a Pitloom-generated SBOM

Two enrichment sources feed the same SBOM. `loom enrich` is Pitloom's own
**deterministic** pass (only YAML frontmatter in a README/model card -- no
reasoning, no network by default); with a local AI model file in scope, run it
first. An agent goes further: it reads **prose**, infers a plausible licence,
classifies a dependency's purpose, or works out `trainedOn`/`testedOn`
relationships no structured field encodes. Do this only **after** a base SBOM
exists (use `sbom-generate` first if not), and only when it adds real
information. If generating that base needs `--allow-build` and the user asked
for it, always pass an explicit `--build-timeout` (`sbom-generate`'s "Choosing
`--build-timeout`").

**Limitation:** enrichment only adds evidence to elements the base SBOM
already has. Non-Python dependencies of a mixed-ecosystem project get none
(`sbom-generate`'s "Known limitations"): say so, don't imply it closes the gap.

Part of a trio with `sbom-generate` and `sbom-validate`. Invoke by trigger
phrasing or `/sbom-enrich [sbom-file]` (`/pitloom:sbom-enrich` via the Claude
Code plugin; `$sbom-enrich` in Codex). For a worked example, read
`references/examples.md`.

## Requirements

Python >= 3.10 and **pitloom >= 0.22.0** (earlier releases cannot read ID
registry format 4): `pip install "pitloom>=0.22.0"`; an AI model file needs
`"pitloom[ai]>=0.22.0"`, the post-merge check `"pitloom[validate]>=0.22.0"`.
Ephemeral runs: `sbom-generate`'s "Run without installing anything persistent".
Snippets are POSIX shell: on Windows use `python`/`py` for `python3` and
PowerShell equivalents (5.1 has no `&&`).

## Contribute enrichment as a fragment, never by hand-editing

Do not edit the generated SBOM JSON directly. Write inferred facts as a
small, standalone SPDX 3 JSON **fragment** that Pitloom merges on the next run.

Every inferred field's `comment` (or the fragment's `CreationInfo.comment`)
must carry a provenance marker, so it is never confused with extracted
metadata. Use your own agent name, vendor and today's date, never another
agent's:

```text
Source: <your agent name> (<vendor>) | Role: inferred | Date: <ISO 8601 date>
```

Unknown name/vendor: use `Source: AI agent | Role: inferred`, not a guess.
Other `Role:` values: `declared`, `externalReported`, `sbomAuthorSupplied`.
Before writing a marker line, read `references/provenance-roles.md` for the
exact lines and filled-in examples.

**Where a fragment can be merged.** Registered fragments are merged only into
an SBOM that Pitloom generates from a project directory: `loom project <dir>`,
`loom generate <dir>`, the Hatchling build hook, or `loom embed-wheel
--project-dir <dir>`. Any other base (`loom model`, a Hugging Face model, a
wheel, `loom env`, an sdist, a third-party SBOM) never merges them,
**silently** (exit 0, no `WARNING:`). For such a base, do steps 1-7, then stop:
report the gaps, hand the drafted fragment(s) over unmerged, and say they were
not merged. To put an enriched SBOM into a wheel, hand off to `sbom-generate`
("Embed an SBOM into a wheel"; a signed wheel needs the user's
`--allow-signed-wheel`).

Steps:

1. Generate a base SBOM first, if not already done (`sbom-generate`), and
   **record the exact command that produced it** -- target, `-o`, `--config`,
   `--id-registry`, `--use-lockfile`/`--no-use-lockfile`, `--enrich`,
   `--allow-build` with its `--build-timeout`. Step 9 reuses it whole and step 2
   needs its `--config`, `--id-registry` and `--use-lockfile` parts: ids are
   content-addressed, so any difference can make the fragment miss the base.
   After a Pitloom upgrade, regenerate the base first if the CHANGELOG shows
   changed file discovery for this project's build backend.
2. **Run the deterministic pass first**, when a local AI model file is in
   scope; skip it otherwise (plain Python project, Hugging Face model, or a
   file that is not a model: `loom enrich` fails with an `ERROR:`: skip it and
   relay Pitloom's advice) and when the base run used `--enrich` (same pass:
   merging both duplicates each dataset and `trainedOn`). Read the fragment's
   `@graph` for what it filled:

   ```bash
   loom enrich <model-file> --project-dir <dir> -o <dir>/model.enrich.spdx3.json
   ```

   - **Always pass `-o <project-dir>/model.enrich.spdx3.json`** (step 8
     registers a project-relative path) and `--project-dir <dir>` (the directory
     given to `loom project`/`loom generate`) plus the base run's `--config`,
     `--id-registry` and `--use-lockfile`/`--no-use-lockfile` if used; without
     `--project-dir` every reference dangles. Omit it for a `loom model` base.
   - The fragment attaches only if the base has an `ai_AIPackage` for that
     model; if not, say so instead of merging.
   - A base built with `--allow-build` cannot be reproduced by `loom enrich`:
     where the file lists differ the merge fails; say so, do not merge.

   If `loom enrich` prints a `WARNING:` or `ERROR:`, the model is a stub, or
   the frontmatter has a `license`, read `references/deterministic-pass.md`.
3. Read the project's `README.md` / model card **prose** and other local docs.
   Propose only fields for gaps step 2 left untouched. If the model's
   `ai_AIPackage` is a **stub** (no `ai_*` property and no `comment` entry
   `Source: <the model file> | Field: ...`: Pitloom did not read the file), a
   name ends `...~<hex>`, a CRFsuite/fastText model has `num_labels` but no
   `labels`, or `\uXXXX` appears in a name or description, read
   `references/model-stub-diagnosis.md` and tell the user the cause before
   inferring what the file itself would give. Never add `--trust-wheel-model` or
   raise a model-scan cap yourself; never write a cut name, dropped label or
   unescaped control back into a fragment.
4. **Interactive session only -- ask the SBOM author about remaining gaps
   they're plausibly positioned to know** (intended use, training-data
   provenance/consent, deployment restrictions; not facts derivable from
   files), with targeted questions for *specific* gaps. **Skip this step in a
   non-interactive run** -- do not block waiting for input. **The answer
   decides the role:** a fact the author states is `sbomAuthorSupplied`, never
   `inferred`; if the author points at a source, go look, and the role is
   *never* `sbomAuthorSupplied` (`references/provenance-roles.md`).
5. **Before using any source outside this project** -- one the SBOM author
   pointed you at (step 4), or one you noticed **on your own initiative** (in
   your context window, another readable file, or a remote location such as
   PyPI, arXiv, Hugging Face Hub, GitHub, GitLab, Codeberg or a URL already in
   context) -- stop and ask the SBOM author for permission first. Name exactly
   what you found and where; an unprompted find needs an *at least as* explicit
   ask. Never fold such a finding into a fragment silently. This gate is not a
   provenance role: it never makes the result `sbomAuthorSupplied`.
   **Non-interactive run:** use no outside source; list what you found and where
   in the final report as "not used -- needs consent".
6. Draft your own fragment (`*.spdx3.json`) containing only the elements or
   relationships you infer from prose (e.g. a `dataset_DatasetPackage` plus a
   `trainedOn` relationship, or a `comment` refining a licence guess), each
   marked with the provenance string above and file paths POSIX-style on every
   OS. A `Relationship` must point at real ids: copy the model's `ai_AIPackage`
   `spdxId` from the base SBOM, and restate a base element exactly (`spdxId`
   and `name`) to add to it: a stale id silently adds a second `ai_AIPackage`
   that still validates. **The deterministic result wins by default:** do not
   re-propose a different value for a field step 2 set. **Override** only when
   prose clearly contradicts it (e.g. a stale frontmatter `license:`): record
   *both* values and your reason in that entry's provenance comment (the
   `Overrides:`/`Reason:` form is in `references/provenance-roles.md`) and say
   so in your final report (step 11) -- never silently. For a complete example,
   read `references/examples.md`.
7. **Pre-merge check (mandatory):** read every drafted fragment (step 2's and
   step 6's) with the JSON-LD deserialiser `merge_fragments()` uses, run with
   the interpreter Pitloom is installed in, not whichever `python3` is on
   `PATH`; exit 0 is a pass (otherwise an unreadable fragment is skipped with
   only a `WARNING:`). Before running it, read
   `references/pre-merge-check.md`: the one-liner, the `uvx`/`pipx` spellings
   and what it catches. Never `uv run --with` for it (in a project directory it
   builds the project, against the `--allow-build` hard rule), and never
   `loom fragment validate`/`spdx3-validate` on a fragment (it fails SHACL on
   its own; the merged SBOM is validated at step 10).
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

9. Re-run **the exact command that produced the base SBOM** (step 1) so the
   merged SBOM is written (`loom generate` without `-o` exits 1). If either
   run reads licences, prepare the licence database before both, as
   `sbom-generate`'s Requirements say: a run without it has other licence ids.
10. **Post-merge check (mandatory):** use the `sbom-validate` skill on
    `<merged-sbom-file>` -- a valid fragment can still miss a required property
    or use the wrong relationship type, which only shape/SHACL validation
    catches. Minimal fallback: `pip install "pitloom[validate]>=0.22.0"` then
    `loom fragment validate <merged-sbom-file>`.
11. Tell the user what was found deterministically (step 2), inferred from
    prose (step 6) and supplied by the SBOM author (step 4), and call out any
    override: provenance-tracked, agent-relayed data, not ground truth.

### Troubleshooting: dangling references

Merging a fragment whose ids the base SBOM does not have makes
`merge_fragments()` log a `WARNING:` per dangling reference, then fail (the CLI
prints an `ERROR:` and exits non-zero). Regenerate the base SBOM, re-run
enrichment and merge again; never retry the same merge. Never create or write
an ID registry to fix it, and never pin ids from this skill: if the user asks to
pin ids or create a registry, hand off to `sbom-generate` ("Pinning element
ids"); non-interactive: change nothing and report the `loom id generate`
command. Before regenerating, read `references/dangling-references.md`:
the causes in order and the fix for each (a repeat run can fail the same way).

## Complete a standard's minimum elements

A separate entry point into the same fragment/provenance/merge mechanism,
driven by a **checklist** (a named standard's required elements) instead of
open-ended prose reading. Use it when the request names a standard or asks
what's missing for compliance. Steps a and b work on any SPDX 3 SBOM; the merge
(step f) needs a project-directory base: for any other SBOM stop after b and
report the gaps, or hand over a drafted fragment unmerged and say so.

a. **Identify the standard(s):** NTIA 2021; FSCT 2024; CISA 2026 (current
   baseline; supersedes NTIA 2021); G7 SBOM for AI 2026 (additive; only with an
   `ai_AIPackage`); BSI TR-03183-2 v2.1. Unnamed: interactive, ask;
   non-interactive, use CISA 2026, plus G7 SBOM for AI 2026 when the SBOM has an
   `ai_AIPackage`, and say in the report these were the default. Checklists:
   read `references/minimum-elements.md`.
b. **Gap analysis:** per element, report present / missing /
   `NOASSERTION`-or-empty (a licence with no relationship is missing); the
   reference's "covered"/"conditional" calls were checked against one real SBOM,
   so don't trust them. A stub `ai_AIPackage` (step 3) counts every G7 model
   element as missing: report its stderr cause first. Optional cross-check, when
   the user asks or agrees (non-interactive: only if `sbomcheck` is already
   installed, else report the command), `-c` one of `ntia`, `fsct3`, `cisa2026`,
   `g7ai`, `bsi`:

   ```bash
   sbomcheck -s spdx3 -c cisa2026 -r json -o report.json sbom.spdx3.json
   ```

   Its `present` means the property exists, not that the value is right; for
   install, outcomes and per-`missing` action read "Cross-check with the
   checker" in `references/minimum-elements-workflow.md`.
c. **Resolve gaps by the precedence of steps 2-5.** This fills *extraction*
   gaps, not *recording* gaps (an element whose SPDX 3.0.1 field does not
   exist): never stretch a neighbouring property; list it in step g.
d. **Interactive only, one field at a time.** When you ask, read
   `references/minimum-elements-questions.md` and apply step 4's role rule; the
   user can stop at any point (go to step f, list the rest as open gaps). Skip
   in a non-interactive run.
e. **Contradiction check** before drafting, against the base SBOM's value and
   earlier answers. Interactive: ask which stands. Non-interactive: keep the
   base value, record the candidate in the provenance comment, list an open
   conflict in step g. Never pick silently.
f. **Draft, validate, register, merge, validate:** reuse steps 6-10.
g. **Final report:** elements now satisfied; those unknown by the user's choice
   (write `NOASSERTION`, don't omit the field); those with no automatable path.
   Name the standards applied.

Read `references/minimum-elements-workflow.md` for step d's ranking, step g's
licence-`NOASSERTION` recipe and its no-automatable-path list;
`references/minimum-elements-datasets.md` for G7 Dataset Properties;
`references/minimum-elements-bsi.md` for BSI.

## Check stderr for INFO:/WARNING:/ERROR: lines

`loom enrich`/`project`/`generate`/`merge` log to stderr with the convention in
`sbom-generate`'s "Check stderr" section: scan it after every call and mention
any hit, even on exit 0. When a line ends in a `[code]`, read
`references/messages.md` for what it means and what to tell the user; relay
its advice, never run the fix. Expect the dangling-reference `WARNING:` plus
`ERROR:` above. After an ambiguous-name pin (`sbom-generate`'s
`references/id-registry.md`), a `WARNING: ID registry: ... is registered for
both` line on every run is expected. `ERROR: ID registry file ...: version 3,
expected 4` means an old-format registry: never delete or rewrite it from this
skill; hand the user to `sbom-generate` ("Pinning element ids"), or when
non-interactive stop and report the `ERROR:`.

## See also

- Sibling `sbom-generate` (generates the base SBOM; owns the ID registry
  reference):
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/SKILL.md>
- Sibling `sbom-validate` (the mandatory post-merge check):
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
