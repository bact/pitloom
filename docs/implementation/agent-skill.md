---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Using Pitloom as an AI-agent Skill

Pitloom ships an Anthropic Agent-Skill at `skills/pitloom-sbom/` so an AI
coding agent can generate -- and, optionally, help enrich -- an SBOM on
request, driving the same `loom` CLI a person would use from a terminal.

See [adoption-surfaces.md](../design/adoption-surfaces.md) for how this
fits alongside Pitloom's other surfaces, and
[sbom-enrichment.md](../design/sbom-enrichment.md) for the enrichment model
the Skill's Tier 2 guidance builds on.

## What is in the Skill

```text
skills/pitloom-sbom/
|- SKILL.md                  Operating instructions (Tier 1 generate,
|                             Tier 2 enrich).
`- references/
   `- examples.md            Copy-paste generate + enrich recipes,
                              including a minimal fragment example.
```

`SKILL.md`'s YAML front matter declares `name: pitloom-sbom` and a
`description` written as an explicit trigger sentence -- the string an
agent runtime matches against a user's request to decide whether to load
the skill.

## Installing the Skill in Claude Code

Copy (or symlink) the `skills/pitloom-sbom/` directory into a skills
directory Claude Code reads from:

```bash
# Project-scoped (checked into the repository, shared with the team):
mkdir -p .claude/skills
cp -r /path/to/pitloom/skills/pitloom-sbom .claude/skills/

# User-scoped (available in every project on this machine):
mkdir -p ~/.claude/skills
cp -r /path/to/pitloom/skills/pitloom-sbom ~/.claude/skills/
```

Once installed, asking Claude Code to "generate an SBOM for this project"
(or any of the trigger phrasings in `SKILL.md`'s `description`) should load
the skill automatically.

## Using the Skill with the Claude Agent SDK

The Agent SDK reads skills from a filesystem path in the same format. Point
your agent's skill directory at (or copy into it) `skills/pitloom-sbom/`;
consult your SDK version's skill-loading documentation for the exact
configuration option (typically a `skills` or `skill_dirs` setting on the
agent/client configuration). Because `SKILL.md` is self-contained -- it
does not assume any Pitloom-specific tool wiring beyond a shell -- it works
the same way regardless of which agent runtime loads it.

## What the Skill actually does

The Skill contains no Pitloom code of its own. It instructs the agent to:

1. **Tier 1 -- generate.** Run `loom`/`pitloom` (via `uvx`, `pipx run`, or a
   regular `pip install` fallback) against a project directory or an AI
   model file, producing an SPDX 3.0.1 JSON-LD SBOM.
2. **Tier 2 -- enrich (optional).** After generating a base SBOM, the agent
   may read the project's README or a model card, infer information static
   extraction cannot see (a license, a dependency's purpose, a
   `trainedOn`/`testedOn` dataset relationship), and contribute it back as
   a pitloom **fragment** -- a small standalone SPDX 3 JSON-LD file merged
   in via `[tool.pitloom.fragments]`. Every inferred field is
   provenance-marked `Source: AI agent | Method: inference`, so it is never
   confused with Pitloom's own extraction.

See `skills/pitloom-sbom/references/examples.md` for the exact commands
and a full worked fragment example.

## Verifying the Skill works

```bash
# Tier 1, project mode:
loom . -o /tmp/sbom.spdx3.json

# Tier 1, model mode (adjust the path to a real model file):
loom -m tests/fixtures/aimodels/onnx/squeezenet1.1-7.onnx -o /tmp/model.spdx3.json

# Both should exit 0 and produce a file containing an "@graph" array.
```

For the Tier 2 fragment recipe, follow
`skills/pitloom-sbom/references/examples.md` end to end: write the
fragment, add a `[tool.pitloom.fragments]` entry pointing at it, re-run
`loom`, and confirm the inferred element appears in the output with its
`Source: AI agent | Method: inference` provenance.

## Also available as a Claude Code plugin

`SKILL.md` was written to be plugin-ready, and now is one:
`.claude-plugin/plugin.json` bundles this Skill alongside a `/pitloom-sbom`
slash command and a `marketplace.json`, installable with `/plugin install`
directly from this repository -- no changes were needed to `SKILL.md`
itself. See [claude-code-plugin.md](claude-code-plugin.md).
