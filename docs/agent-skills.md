---
Created: 2026-08-11
Last-Modified: 2026-10-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Agent Skills

Use this when you want an AI coding agent to generate (and optionally
enrich or validate) an SBOM on request, in any agent runtime that reads
[Agent Skills][agent-skills] from a filesystem directory -- Claude Code,
the Claude Agent SDK, Codex, Gemini CLI, GitHub Copilot, or another
compatible client.

[agent-skills]: https://agentskills.io

If you use Claude Code specifically and want one-command install instead
of copying files, see the [Claude Code plugin](claude-code-plugin.md)
page -- it installs the exact same three `SKILL.md` files described here.

Pitloom ships three Skills:

- `sbom-generate` -- generates a base SBOM/AIBOM for a project, wheel, or
  AI/ML model file. Also embeds a generated (or pre-existing) SBOM
  directly into a built wheel per PEP 770's `.dist-info/sboms/`
  convention.
- `sbom-enrich` -- reads a README or model card and contributes inferred
  detail (a license guess, a `trainedOn` dataset) back into an existing
  SBOM as a provenance-marked fragment; in an interactive session it can
  also ask the SBOM author directly for gaps no file answers. It also
  has a standards-driven mode: run a gap analysis against a named
  standard's minimum elements (NTIA 2021, CISA 2026, or G7 SBOM for AI
  2026) and only ask about what's actually missing. Requires a base SBOM
  to already exist; run `sbom-generate` first.
- `sbom-validate` -- checks an SPDX 3 JSON document for schema and SHACL
  conformance (`loom fragment validate`, built on the third-party
  `spdx3-validate`), catching a missing required property or a wrong
  relationship type that a bare `@graph`-presence check cannot. Works on
  Pitloom's own output, a hand-authored fragment, or a third-party SPDX 3
  file. It also checks a wheel's PEP 770 embedded SBOM: `verify-wheel`
  (structural: present, right place, name/version match) and
  `validate-wheel` (content: schema/SHACL).

The three Skills refer to each other, so install all three together.

**Requirements.** A shell, Python 3.10 or later and `pitloom` 0.20.2 or
later (pip, `uvx` or `pipx`; earlier releases lack `--id-registry`,
`loom id` and `--build-timeout`, which the Skills use); network access to
install it and, for PyPI and Hugging Face lookups, at run time. AI model
files need `pitloom[ai]`; `sbom-enrich`'s post-merge check and
`sbom-validate` need `pitloom[validate]`; `--allow-build` needs
`pitloom[build]`. Each `SKILL.md` declares this in its `compatibility`
field. The Skills do not work where packages cannot be installed, e.g.
Claude API code execution.

## Quick guide

Ask in plain language, or invoke explicitly once installed (the syntax
depends on the client: `/sbom-generate` in Claude Code, `$sbom-generate`
in Codex):

```text
/sbom-generate .
/sbom-enrich sbom.spdx3.json
/sbom-validate sbom.spdx3.json
```

## Installation

Copy (or symlink) all three of `skills/sbom-generate/`,
`skills/sbom-enrich/` and `skills/sbom-validate/` from a Pitloom checkout
into a skills folder your client reads. `.agents/skills` is the
cross-client location; use another only for a client that needs it:

| Client | Skills folder (project) |
| :--- | :--- |
| Cross-client convention | `.agents/skills/` (user: `~/.agents/skills/`) |
| Claude Code, Claude Agent SDK | `.claude/skills/` (user: `~/.claude/skills/`) |
| Codex | `.agents/skills/` |
| Gemini CLI | `.gemini/skills/` or `.agents/skills/` |
| GitHub Copilot, VS Code | `.github/skills/`, `.claude/skills/` or `.agents/skills/` (user: `~/.copilot/skills/`) |

```bash
# Project-scoped (checked into the repository, shared with the team):
mkdir -p .agents/skills
cp -r /path/to/pitloom/skills/sbom-generate .agents/skills/
cp -r /path/to/pitloom/skills/sbom-enrich .agents/skills/
cp -r /path/to/pitloom/skills/sbom-validate .agents/skills/
```

```bash
# User-scoped (available in every project on this machine):
mkdir -p ~/.agents/skills
cp -r /path/to/pitloom/skills/sbom-generate ~/.agents/skills/
cp -r /path/to/pitloom/skills/sbom-enrich ~/.agents/skills/
cp -r /path/to/pitloom/skills/sbom-validate ~/.agents/skills/
```

For Claude Code, replace `.agents/skills` with `.claude/skills` (and
`~/.agents/skills` with `~/.claude/skills`).

For claude.ai, zip each Skill folder (`cd /path/to/pitloom/skills && zip -r
sbom-generate.zip sbom-generate`, likewise for the other two) and upload
each zip: Customize > Skills > "+" > "+ Create skill" > "Upload a skill".
Code execution must be enabled first (Settings > Capabilities > "Code
execution and file creation"; on Team and Enterprise plans an organisation
owner enables it under Organization settings > Plugins & skills). The
Skills need `pitloom` installed where they run, so they work on claude.ai
only where its code sandbox can install packages.

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
  `/sbom-enrich [sbom-file]`, and `/sbom-validate [sbom-file]`. The syntax
  depends on the client (e.g. `$sbom-generate` in Codex). All arguments
  are optional (each defaults sensibly -- e.g. `sbom-generate` defaults to
  the current directory).

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

### Embed an SBOM into a wheel (PEP 770)

```text
/sbom-generate .                                                        # build the SBOM
loom embed-wheel dist/mypackage-1.0.0-py3-none-any.whl --project-dir .  # embed it (or --sbom <file>)
```

Runs `loom embed-wheel` (or `loom wheel --embed` for a single wheel's own
Analyzed SBOM, no project directory) under the hood, mutating the `.whl`
archive in place and updating `RECORD` to match -- works on any wheel
regardless of build backend, since a wheel is just a ZIP archive.
`--project-dir` is required to have `embed-wheel` rescan the source
project; without it (and without `--sbom`), it embeds a standalone SBOM
built from the wheel alone, with no `[tool.pitloom]` of its own.

### Enrich an existing SBOM

```text
/sbom-generate .                     # generate the base SBOM first
/sbom-enrich sbom.spdx3.json         # then enrich it
```

The Skill reads the project's README or the model's model card, drafts a
small standalone SPDX 3 JSON fragment for whatever it can infer (never
hand-edits the generated SBOM), registers it under
`[tool.pitloom.fragment]`, and re-runs Pitloom so the fragment is
merged. The merge works only for an SBOM Pitloom generates from a
project directory; for any other base (a single model, a Hugging Face
model, a wheel, an environment, an sdist or a third-party SBOM) the
fragment is handed over unmerged, and the Skill says so. Every inferred
field is marked in its `comment`, preferably `Source: <agent name>
(<vendor>) | Role: inferred | Date: <date>` and otherwise the generic
`Source: AI agent | Role: inferred`, so it is never mistaken for Pitloom's
own extraction. See
[`skills/sbom-enrich/references/examples.md`][sbom-enrich-examples] for
a full worked example, including the pre-merge and post-merge validation
steps.

[sbom-enrich-examples]: https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/references/examples.md

Ask instead for a named standard (NTIA 2021, CISA 2026 or G7 SBOM for AI
2026) -- "make this SBOM meet NTIA standard", "is this SBOM CISA 2026
compliant", "complete the minimum elements" -- and the same Skill runs a
gap analysis against that standard's checklist first, resolving what it
can itself before asking you about the rest one field at a time (you can
stop at any point and it completes with whatever's gathered so far). See
[`skills/sbom-enrich/references/minimum-elements.md`][sbom-enrich-minimum-elements]
for the checklists and field mappings this draws on.

[sbom-enrich-minimum-elements]: https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/references/minimum-elements.md

### Validate an SPDX 3 document

```text
/sbom-validate sbom.spdx3.json
```

Runs schema (JSON Schema) plus shape (SHACL) validation with `loom
fragment validate`, built on the third-party `spdx3-validate`. This is
the mandatory post-merge check the `sbom-enrich` recipe above uses, but
it works standalone too -- on any SPDX 3 JSON document, not just
Pitloom's own output. For a wheel's embedded SBOM it runs both `loom
verify-wheel` (present, right place, name/version match) and `loom
validate-wheel` (content). See
[`skills/sbom-validate/references/examples.md`][sbom-validate-examples]
for multi-file and merged-graph recipes.

[sbom-validate-examples]: https://github.com/bact/pitloom/blob/main/skills/sbom-validate/references/examples.md

## Configuration

Each Skill's `SKILL.md` front matter carries a `description` (drives
natural-language auto-trigger matching) and a `compatibility` note (what
the Skill needs to run, above). It has no `argument-hint`: that key is
outside the Agent Skills specification, and claude.ai and the Skills API
reject it. Each Skill's body says what argument it takes instead --
`sbom-generate` accepts a project directory, sdist, wheel, model file or
Hugging Face model ID, while the other two need an existing SBOM file
path. Nothing else needs configuring to use the Skills as-is.

## See also

- [Claude Code plugin](claude-code-plugin.md) -- one-command install of
  these same three Skills, namespaced under `/pitloom:...`.
- [Command line](cli.md) -- the underlying `loom` commands these Skills
  run.
