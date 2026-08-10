---
Created: 2026-07-05
Last-Modified: 2026-08-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Using Pitloom as an AI-agent Skill

Pitloom ships three Anthropic Agent-Skills -- `skills/sbom-generate/`,
`skills/sbom-enrich/`, and `skills/sbom-validate/` -- so an AI coding
agent can generate, optionally enrich, and validate an SBOM on request,
driving the same `loom` CLI a person would use from a terminal (plus,
for validation, the third-party `spdx3-validate` CLI).

See [adoption-surfaces.md](../design/adoption-surfaces.md) for how this
fits alongside Pitloom's other surfaces, and
[sbom-enrichment.md](../design/sbom-enrichment.md) for the enrichment model
the `sbom-enrich` skill builds on.

## What is in the Skills

```text
skills/
|- sbom-generate/
|  |- SKILL.md                  Generate a base SBOM/AIBOM.
|  `- references/
|     `- examples.md            Copy-paste generate recipes.
|- sbom-enrich/
|  |- SKILL.md                  Enrich an existing SBOM as a fragment.
|  `- references/
|     `- examples.md            A full worked fragment example.
`- sbom-validate/
   |- SKILL.md                  Validate an SPDX 3 document (schema + SHACL).
   `- references/
      `- examples.md            Copy-paste validate recipes.
```

Each `SKILL.md`'s YAML front matter declares a `name`
(`sbom-generate`/`sbom-enrich`/`sbom-validate`), a `description` written
as an explicit trigger sentence -- the string an agent runtime matches
against a user's request to decide whether to load that skill -- and an
`argument-hint` (`[target]`, `[sbom-file]`) shown by Claude Code's
command palette when invoking the skill explicitly (e.g.
`/sbom-generate <target>`). All three are independent and independently
triggerable: `sbom-generate` always runs first (there is nothing to
enrich or validate yet otherwise); `sbom-enrich` is optional and only
fires when asked for, or when a user explicitly wants to add detail
Pitloom's static extraction cannot see; `sbom-validate` runs on any SPDX
3 JSON document, Pitloom-generated or not.

## Installing the Skills in Claude Code

Copy (or symlink) any of `skills/sbom-generate/`, `skills/sbom-enrich/`,
and `skills/sbom-validate/` into a skills directory Claude Code reads
from. Copy all three for the full generate-enrich-validate workflow;
`sbom-generate` alone is enough for generation only.

```bash
# Project-scoped (checked into the repository, shared with the team):
mkdir -p .claude/skills
cp -r /path/to/pitloom/skills/sbom-generate .claude/skills/
cp -r /path/to/pitloom/skills/sbom-enrich .claude/skills/
cp -r /path/to/pitloom/skills/sbom-validate .claude/skills/

# User-scoped (available in every project on this machine):
mkdir -p ~/.claude/skills
cp -r /path/to/pitloom/skills/sbom-generate ~/.claude/skills/
cp -r /path/to/pitloom/skills/sbom-enrich ~/.claude/skills/
cp -r /path/to/pitloom/skills/sbom-validate ~/.claude/skills/
```

Once installed, asking Claude Code to "generate an SBOM for this project"
(or any of the trigger phrasings in `sbom-generate/SKILL.md`'s
`description`) should load that skill automatically; similarly for
enrichment requests and `sbom-enrich/SKILL.md`, and validation requests
and `sbom-validate/SKILL.md`.

### If a skill name already exists (collides)

A skill's invocable name comes from its **directory name**, not its
`SKILL.md` frontmatter -- so if you already have an unrelated skill at
`~/.claude/skills/sbom-generate/` (or `sbom-enrich/`, `sbom-validate/`),
copying Pitloom's version to the same path will simply overwrite it.
Claude Code does not detect or resolve this for you. (The `sbom-`
prefix on all three names already makes a collision unlikely -- see
[claude-code-plugin.md](claude-code-plugin.md)'s design notes for why
that prefix was chosen even though the Claude Code plugin surface itself
doesn't need it.)

To avoid a collision, copy under a different destination name instead,
e.g.:

```bash
cp -r /path/to/pitloom/skills/sbom-generate ~/.claude/skills/pitloom-sbom-generate
```

Renaming the destination folder is a pure filesystem operation and always
safe:

- It **does** change the explicit invocation (`/sbom-generate` becomes
  `/pitloom-sbom-generate`).
- It has **no effect** on natural-language auto-triggering -- that is
  driven entirely by the `description` field, not the folder name.
- **No edits to `SKILL.md` are required.** The frontmatter `name:` field
  is only a cosmetic display label; it does not need to match the folder
  name, and a mismatch is harmless.

## Using the Skills with the Claude Agent SDK

The Agent SDK reads skills from a filesystem path in the same format. Point
your agent's skill directory at (or copy into it) any of
`skills/sbom-generate/`, `skills/sbom-enrich/`, and `skills/sbom-validate/`;
consult your SDK version's skill-loading documentation for the exact
configuration option (typically a `skills` or `skill_dirs` setting on the
agent/client configuration). Because each `SKILL.md` is self-contained --
it does not assume any Pitloom-specific tool wiring beyond a shell -- it
works the same way regardless of which agent runtime loads it.

## What the Skills actually do

None of the three skills contains Pitloom code of its own.

1. **`sbom-generate`.** Run `loom`/`pitloom` (via `uvx`, `pipx run`, or a
   regular `pip install` fallback) against a project directory or an AI
   model file, producing an SPDX 3.0.1 JSON-LD SBOM.
2. **`sbom-enrich` -- optional, after a base SBOM exists.** Read the
   project's README or a model card, infer information static extraction
   cannot see (a license, a dependency's purpose, a
   `trainedOn`/`testedOn` dataset relationship), and contribute it back
   as a pitloom **fragment** -- a small standalone SPDX 3 JSON-LD file
   merged in via `[tool.pitloom.fragments]`. Every inferred field is
   provenance-marked `Source: AI agent | Method: inference`, so it is
   never confused with Pitloom's own extraction.
3. **`sbom-validate`.** Run the third-party
   [`spdx3-validate`](https://github.com/JPEWdev/spdx3-validate) CLI
   against any SPDX 3 JSON document -- schema (JSON Schema) plus shape
   (SHACL) validation, catching a missing required property or a wrong
   relationship type that a bare `@graph`-presence check cannot. Works on
   Pitloom's own output, a hand-authored fragment, or a third-party SPDX
   3 file.

See `skills/sbom-generate/references/examples.md`,
`skills/sbom-enrich/references/examples.md`, and
`skills/sbom-validate/references/examples.md` for the exact commands and
a full worked fragment example.

## Verifying the Skills work

```bash
# sbom-generate, project mode:
loom project . -o /tmp/sbom.spdx3.json

# sbom-generate, model mode (adjust the path to a real model file):
loom model tests/fixtures/aimodels/onnx/squeezenet1.1-7.onnx -o /tmp/model.spdx3.json

# Both should exit 0 and produce a file containing an "@graph" array.

# sbom-validate, against either output above:
pip install spdx3-validate  # if not already installed
spdx3-validate --json /tmp/sbom.spdx3.json
```

For the `sbom-enrich` recipe, follow
`skills/sbom-enrich/references/examples.md` end to end: write the
fragment, add a `[tool.pitloom.fragments]` entry pointing at it, re-run
`loom`, and confirm the inferred element appears in the output with its
`Source: AI agent | Method: inference` provenance.

## Also available as a Claude Code plugin

All three Skills were written to be plugin-ready, and now are one:
`.claude-plugin/plugin.json` bundles them under the `pitloom` plugin name,
installable with `/plugin install` directly from this repository --
namespaced explicit invocation is `/pitloom:sbom-generate`,
`/pitloom:sbom-enrich`, and `/pitloom:sbom-validate`, no changes were
needed to any `SKILL.md`. See
[claude-code-plugin.md](claude-code-plugin.md).
