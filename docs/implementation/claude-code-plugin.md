---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Using Pitloom as a Claude Code plugin

Pitloom ships a Claude Code plugin, self-hosted from this repository, that
bundles the `pitloom-sbom` Skill (see
[agent-skill.md](agent-skill.md)) with an explicit `/pitloom-sbom` slash
command. It is the same Skill either way -- the plugin only adds an
install path and an unambiguous invocation.

See [adoption-surfaces.md](../design/adoption-surfaces.md) for how this
fits alongside Pitloom's other surfaces.

## Installing the plugin

From a Claude Code session:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom-sbom@pitloom
```

This registers Pitloom's repository as a marketplace (named `pitloom`) and
installs the `pitloom-sbom` plugin from it. Once installed, both the
`pitloom-sbom` Skill and the `/pitloom-sbom` command are available in every
session.

## What is in the plugin

```text
.claude-plugin/
|- plugin.json          Plugin manifest (name, description, author, license).
`- marketplace.json      Self-hosted marketplace entry (source: "./").
commands/
`- pitloom-sbom.md       The /pitloom-sbom slash command.
skills/
`- pitloom-sbom/         The existing Skill (see agent-skill.md) -- bundled
                          as-is; no changes were needed to add the plugin.
```

`plugin.json` declares no `skills` field: because `skills/pitloom-sbom/`
already sits at the repository root (the plugin root), Claude Code
auto-discovers it. The same is true for `commands/pitloom-sbom.md`.

## Using `/pitloom-sbom`

```text
/pitloom-sbom
/pitloom-sbom models/my-model.safetensors
/pitloom-sbom enrich
```

The command is a thin wrapper: it tells the agent to follow the Skill's
Tier 1 procedure (generating a project or model SBOM), and its Tier 2
procedure too if the request or argument asks to "enrich" the result. It
adds an explicit, unambiguous invocation on top of the Skill's own
automatic trigger-matching -- useful when you want to be certain the Skill
runs, or want to pass a target path or model directly as an argument.

A dedicated `generate` / `enrich` command split (instead of one command
that reads the argument) is tracked as a future evolution in
[roadmap.md](../design/roadmap.md); it is not required for this initial
plugin.

## Design notes

- The plugin's `version` field is deliberately omitted from both
  `plugin.json` and the marketplace entry, matching Claude Code's
  documented guidance for an actively-developed/internal plugin --
  version resolution falls back to the git commit SHA. `claude plugin
  validate` reports this as an expected warning, not an error.
- `.claude-plugin/marketplace.json`'s single plugin entry uses
  `"source": "./"`, the standard self-hosting pattern when the plugin
  lives in the same repository as the marketplace that lists it.
- `.claude-plugin/` (pure manifest, no value outside `/plugin install`)
  is excluded from the sdist, like `.github`. `commands/` and `skills/`
  stay in the sdist as user-facing plugin content, matching how `skills/`
  was already treated. Neither was ever part of the wheel (only
  `src/pitloom` is packaged there).
- `.github/workflows/plugin-validate.yml` runs `claude plugin validate`
  against both manifests whenever `.claude-plugin/`, `commands/`, or
  `skills/` change.
