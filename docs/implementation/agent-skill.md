---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Using Pitloom as an AI-agent Skill

Pitloom ships two Anthropic Agent-Skills, `skills/sbom/` and
`skills/enrich/`, so an AI coding agent can generate -- and, optionally,
help enrich -- an SBOM on request, driving the same `loom` CLI a person
would use from a terminal.

See [adoption-surfaces.md](../design/adoption-surfaces.md) for how this
fits alongside Pitloom's other surfaces, and
[sbom-enrichment.md](../design/sbom-enrichment.md) for the enrichment model
the `enrich` skill builds on.

## What is in the Skills

```text
skills/
|- sbom/
|  |- SKILL.md                  Generate a base SBOM/AIBOM.
|  `- references/
|     `- examples.md            Copy-paste generate recipes.
`- enrich/
   |- SKILL.md                  Enrich an existing SBOM as a fragment.
   `- references/
      `- examples.md            A full worked fragment example.
```

Each `SKILL.md`'s YAML front matter declares a `name` (`sbom`, `enrich`)
and a `description` written as an explicit trigger sentence -- the string
an agent runtime matches against a user's request to decide whether to
load that skill. They are independent and independently triggerable:
`sbom` always runs first (there is nothing to enrich yet otherwise);
`enrich` is optional and only fires when asked for, or when a user
explicitly wants to add detail Pitloom's static extraction cannot see.

## Installing the Skills in Claude Code

Copy (or symlink) `skills/sbom/` and/or `skills/enrich/` into a skills
directory Claude Code reads from. Copy both if you want the full
generate-and-enrich workflow; `sbom` alone is enough for generation only.

```bash
# Project-scoped (checked into the repository, shared with the team):
mkdir -p .claude/skills
cp -r /path/to/pitloom/skills/sbom .claude/skills/
cp -r /path/to/pitloom/skills/enrich .claude/skills/

# User-scoped (available in every project on this machine):
mkdir -p ~/.claude/skills
cp -r /path/to/pitloom/skills/sbom ~/.claude/skills/
cp -r /path/to/pitloom/skills/enrich ~/.claude/skills/
```

Once installed, asking Claude Code to "generate an SBOM for this project"
(or any of the trigger phrasings in `sbom/SKILL.md`'s `description`) should
load that skill automatically; similarly for enrichment requests and
`enrich/SKILL.md`.

### If a skill name already exists (`sbom` or `enrich` collides)

A skill's invocable name comes from its **directory name**, not its
`SKILL.md` frontmatter -- so if you already have an unrelated skill at
`~/.claude/skills/sbom/` (or `enrich/`), copying Pitloom's version to the
same path will simply overwrite it. Claude Code does not detect or
resolve this for you.

To avoid the collision, copy under a different destination name instead,
e.g.:

```bash
cp -r /path/to/pitloom/skills/sbom ~/.claude/skills/pitloom-sbom
```

Renaming the destination folder is a pure filesystem operation and always
safe:

- It **does** change the explicit invocation (`/sbom` becomes
  `/pitloom-sbom`).
- It has **no effect** on natural-language auto-triggering -- that is
  driven entirely by the `description` field, not the folder name.
- **No edits to `SKILL.md` are required.** The frontmatter `name:` field
  is only a cosmetic display label; it does not need to match the folder
  name, and a mismatch is harmless.

## Using the Skills with the Claude Agent SDK

The Agent SDK reads skills from a filesystem path in the same format. Point
your agent's skill directory at (or copy into it) `skills/sbom/` and/or
`skills/enrich/`; consult your SDK version's skill-loading documentation
for the exact configuration option (typically a `skills` or `skill_dirs`
setting on the agent/client configuration). Because each `SKILL.md` is
self-contained -- it does not assume any Pitloom-specific tool wiring
beyond a shell -- it works the same way regardless of which agent runtime
loads it.

## What the Skills actually do

Neither skill contains Pitloom code of its own.

1. **`sbom` -- generate.** Run `loom`/`pitloom` (via `uvx`, `pipx run`, or a
   regular `pip install` fallback) against a project directory or an AI
   model file, producing an SPDX 3.0.1 JSON-LD SBOM.
2. **`enrich` -- optional, after a base SBOM exists.** Read the project's
   README or a model card, infer information static extraction cannot see
   (a license, a dependency's purpose, a `trainedOn`/`testedOn` dataset
   relationship), and contribute it back as a pitloom **fragment** -- a
   small standalone SPDX 3 JSON-LD file merged in via
   `[tool.pitloom.fragments]`. Every inferred field is provenance-marked
   `Source: AI agent | Method: inference`, so it is never confused with
   Pitloom's own extraction.

See `skills/sbom/references/examples.md` and
`skills/enrich/references/examples.md` for the exact commands and a full
worked fragment example.

## Verifying the Skills work

```bash
# sbom, project mode:
loom . -o /tmp/sbom.spdx3.json

# sbom, model mode (adjust the path to a real model file):
loom -m tests/fixtures/aimodels/onnx/squeezenet1.1-7.onnx -o /tmp/model.spdx3.json

# Both should exit 0 and produce a file containing an "@graph" array.
```

For the `enrich` recipe, follow `skills/enrich/references/examples.md` end
to end: write the fragment, add a `[tool.pitloom.fragments]` entry pointing
at it, re-run `loom`, and confirm the inferred element appears in the
output with its `Source: AI agent | Method: inference` provenance.

## Also available as a Claude Code plugin

Both Skills were written to be plugin-ready, and now are one:
`.claude-plugin/plugin.json` bundles them under the `pitloom` plugin name,
installable with `/plugin install` directly from this repository --
namespaced explicit invocation is `/pitloom:sbom` and `/pitloom:enrich`, no
changes were needed to either `SKILL.md`. See
[claude-code-plugin.md](claude-code-plugin.md).
