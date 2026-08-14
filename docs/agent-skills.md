---
Created: 2026-08-11
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Agent Skills

Use this when you want an AI coding agent to generate (and optionally
enrich or validate) an SBOM on request, in any agent runtime that reads
[Agent Skills][agent-skills] from a filesystem directory -- Claude Code,
the Claude Agent SDK, or a compatible runtime.

[agent-skills]: https://www.anthropic.com/

If you use Claude Code specifically and want one-command install instead
of copying files, see the [Claude Code plugin](claude-code-plugin.md)
page -- it installs the exact same three `SKILL.md` files described here.

Pitloom ships three Skills:

- `sbom-generate` -- generates a base SBOM/AIBOM for a project, wheel, or
  AI/ML model file.
- `sbom-enrich` -- reads a README or model card and contributes inferred
  detail (a license guess, a `trainedOn` dataset) back into an existing
  SBOM as a provenance-marked fragment; in an interactive session it can
  also ask the SBOM author directly for gaps no file answers. It also
  has a standards-driven mode: run a gap analysis against a named
  standard's minimum elements (NTIA 2021, CISA 2026, or G7 SBOM for AI
  2026) and only ask about what's actually missing. Requires a base SBOM
  to already exist; run `sbom-generate` first.
- `sbom-validate` -- runs the third-party `spdx3-validate` CLI against
  any SPDX 3 JSON document (schema + SHACL), catching a missing required
  property or a wrong relationship type that a bare `@graph`-presence
  check cannot. Works on Pitloom's own output, a hand-authored fragment,
  or a third-party SPDX 3 file.

## Quick guide

Ask in plain language, or invoke explicitly once installed:

```text
/sbom-generate .
/sbom-enrich sbom.spdx3.json
/sbom-validate sbom.spdx3.json
```

## Installation

Copy (or symlink) any of `skills/sbom-generate/`, `skills/sbom-enrich/`,
and `skills/sbom-validate/` from a Pitloom checkout into a skills
directory your agent runtime reads from:

```bash
# Project-scoped (checked into the repository, shared with the team):
mkdir -p .claude/skills
cp -r /path/to/pitloom/skills/sbom-generate .claude/skills/
cp -r /path/to/pitloom/skills/sbom-enrich .claude/skills/
cp -r /path/to/pitloom/skills/sbom-validate .claude/skills/
```

```bash
# User-scoped (available in every project on this machine):
mkdir -p ~/.claude/skills
cp -r /path/to/pitloom/skills/sbom-generate ~/.claude/skills/
cp -r /path/to/pitloom/skills/sbom-enrich ~/.claude/skills/
cp -r /path/to/pitloom/skills/sbom-validate ~/.claude/skills/
```

If a skill with the same name already exists at that path, rename the
destination folder to avoid the collision.

## Usage details

Skills trigger two ways:

- **Natural language** -- ask in plain language, e.g. "generate an SBOM
  for this project", "enrich this SBOM with the dataset it was trained
  on", or "validate this SBOM". The agent matches your request against
  each `SKILL.md`'s `description` front matter and loads the matching
  Skill automatically.
- **Explicit invocation** -- `/sbom-generate [target]`,
  `/sbom-enrich [sbom-file]`, and `/sbom-validate [sbom-file]`. All
  arguments are optional (each defaults sensibly -- e.g. `sbom-generate`
  defaults to the current directory).

### Generate an SBOM

```text
/sbom-generate .                                 # project directory, current dir
/sbom-generate models/my-model.safetensors       # local AI/ML model file
/sbom-generate mistralai/Mistral-7B-v0.1         # Hugging Face Hub model ID
```

Under the hood this runs `loom generate <target>` (or the more specific
`loom project` / `loom wheel` / `loom model` -- see the [Command
line](cli.md) page). See
[`skills/sbom-generate/references/examples.md`][sbom-generate-examples]
for the full recipe set.

[sbom-generate-examples]: https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/examples.md

### Enrich an existing SBOM

```text
/sbom-generate .                     # generate the base SBOM first
/sbom-enrich sbom.spdx3.json         # then enrich it
```

The Skill reads the project's README or the model's model card, drafts a
small standalone SPDX 3 JSON fragment for whatever it can infer (never
hand-edits the generated SBOM), registers it under
`[tool.pitloom.fragment]`, and re-runs Pitloom so the fragment is
merged. Every inferred field is marked `Source: AI agent | Role:
inferred` in its `comment`, so it is never mistaken for Pitloom's own
extraction. See
[`skills/sbom-enrich/references/examples.md`][sbom-enrich-examples] for a
full worked example, including the pre-merge and post-merge validation
steps.

[sbom-enrich-examples]: https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/references/examples.md

Ask instead for a named standard -- "make this SBOM meet NTIA
standard", "is this SBOM CISA 2026 compliant", "make this AIBOM meet
the G7 SBOM for AI minimum elements" -- and the same Skill runs a gap
analysis against that standard's checklist first, resolving what it can
itself before asking you about the rest one field at a time (you can
stop at any point and it completes with whatever's gathered so far).
See
[`skills/sbom-enrich/references/minimum-elements.md`][sbom-enrich-minimum-elements]
for the checklists and field mappings this draws on.

[sbom-enrich-minimum-elements]: https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/references/minimum-elements.md

### Validate an SPDX 3 document

```text
/sbom-validate sbom.spdx3.json
```

Runs schema (JSON Schema) plus shape (SHACL) validation via the
third-party `spdx3-validate` CLI. This is the mandatory post-merge check
the `sbom-enrich` recipe above uses, but it works standalone too -- on
any SPDX 3 JSON document, not just Pitloom's own output. See
[`skills/sbom-validate/references/examples.md`][sbom-validate-examples]
for multi-file and merged-graph recipes.

[sbom-validate-examples]: https://github.com/bact/pitloom/blob/main/skills/sbom-validate/references/examples.md

## Configuration

Each Skill's `SKILL.md` front matter carries a `description` (drives
natural-language auto-trigger matching) and an `argument-hint` (the
placeholder shown for explicit invocation, e.g. `[target]` for
`sbom-generate` versus `[sbom-file]` for `sbom-enrich`/`sbom-validate` --
`sbom-generate` accepts a broader range of input types, while the other
two always need an existing SBOM file path). Nothing else needs
configuring to use the Skills as-is.

## See also

- [Claude Code plugin](claude-code-plugin.md) -- one-command install of
  these same three Skills, namespaced under `/pitloom:...`.
- [Command line](cli.md) -- the underlying `loom` commands these Skills
  run.
