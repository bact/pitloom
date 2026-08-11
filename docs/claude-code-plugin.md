---
Created: 2026-08-11
Last-Modified: 2026-08-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Claude Code plugin

Use this when you use [Claude Code][claude-code-plugins] and want the
three Pitloom [Agent Skills](agent-skills.md) (`sbom-generate`,
`sbom-enrich`, `sbom-validate`) installable with one command, namespaced
under the plugin so they never collide with a same-named Skill from
another source.

[claude-code-plugins]: https://code.claude.com/docs/en/plugins

Both this plugin and standalone [Agent Skills](agent-skills.md) install
the exact same `SKILL.md` files -- pick whichever install path fits:

| Path | Choose this when... |
| :--- | :--- |
| [Agent Skills](agent-skills.md) | You use any agent runtime that reads Skills from a filesystem directory, and want any subset of the three Skills, standalone. |
| Claude Code plugin (this page) | You use Claude Code and want one-command install (`/plugin install`) plus namespaced explicit invocation (`/pitloom:sbom-generate`, `/pitloom:sbom-enrich`, `/pitloom:sbom-validate`). |

## Quick guide

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

Then, in the same session, ask in plain language or invoke explicitly:

```text
/pitloom:sbom-generate .
```

> `/plugin marketplace add` and `/plugin install` are slash commands for
> the **Claude Code CLI** (the terminal `claude` tool). The **Claude
> Desktop app** (macOS/Windows) doesn't support these slash commands --
> use its built-in plugin browser instead: click **+**, select
> **Plugins**, then **Add plugin**, and point it at `bact/pitloom`.

## Installation

From a Claude Code CLI session:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

This registers Pitloom's repository as a marketplace named `pitloom` and
installs the `pitloom` plugin from it -- all three Skills become
available in every session immediately after.

From the Claude Desktop app, use the plugin browser instead of the slash
commands above: click the **+** button, select **Plugins**, choose **Add
plugin**, and provide `bact/pitloom` as the source.

## Usage details

Either trigger path works, same as standalone Skills:

- **Natural language** -- "generate an SBOM for this project", "enrich
  this SBOM with the dataset it was trained on", "validate this SBOM".
- **Explicit invocation**, namespaced under the plugin:

  ```text
  /pitloom:sbom-generate [target]
  /pitloom:sbom-enrich [sbom-file]
  /pitloom:sbom-validate [sbom-file]
  ```

All arguments are optional. See the [Agent Skills](agent-skills.md) page
for what each of the three Skills actually does and worked-example
recipes -- the behavior is identical to the standalone install, only the
invocation prefix changes.

## Verifying it works

```bash
claude plugin validate .claude-plugin/plugin.json
claude plugin validate .claude-plugin/marketplace.json
```

checks the manifests, and after installing:

```bash
claude plugin details pitloom
```

lists all three Skills and an estimated token cost.

## See also

- [Agent Skills](agent-skills.md) -- per-skill usage details, recipes,
  and the standalone (non-plugin) install path.
- [Command line](cli.md) -- the underlying `loom` commands these Skills
  run.
