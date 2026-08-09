---
Created: 2026-08-09
Last-Modified: 2026-08-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

<!-- markdownlint-disable-next-line MD041 -->
{% include nav.html %}

# AI Skills and the Claude Code plugin

Pitloom ships two [Agent Skills][agent-skills] --
`sbom` and `enrich` -- and bundles both as a self-hosted [Claude Code
plugin][claude-code-plugins].

[agent-skills]: https://www.anthropic.com/
[claude-code-plugins]: https://code.claude.com/docs/en/plugins

- `sbom` -- generates a base SBOM/AIBOM for a project, wheel, or AI/ML
  model file.
- `enrich` -- reads a README or model card and contributes inferred
  detail (a license guess, a `trainedOn` dataset) back into an existing
  SBOM as a provenance-marked fragment. Requires a base SBOM to already
  exist; run `sbom` first.

## Choosing an install path

| Path | Choose this when... |
| :--- | :--- |
| [Agent Skills](#install-as-agent-skills) | You use any agent runtime that reads Skills from a filesystem directory, and want just the two Skills, standalone. |
| [Claude Code plugin](#install-as-a-claude-code-plugin) | You use Claude Code and want one-command install (`/plugin install`) plus namespaced explicit invocation (`/pitloom:sbom`, `/pitloom:enrich`). |

Both install the exact same `SKILL.md` files.

### Install as Agent Skills

Copy (or symlink) `skills/sbom/` and/or `skills/enrich/` from a Pitloom
checkout into a skills directory your agent runtime reads from:

```bash
# Project-scoped (checked into the repository, shared with the team):
mkdir -p .claude/skills
cp -r /path/to/pitloom/skills/sbom .claude/skills/
cp -r /path/to/pitloom/skills/enrich .claude/skills/
```

```bash
# User-scoped (available in every project on this machine):
mkdir -p ~/.claude/skills
cp -r /path/to/pitloom/skills/sbom ~/.claude/skills/
cp -r /path/to/pitloom/skills/enrich ~/.claude/skills/
```

If a skill with the same name already exists at that path,
rename the destination folder to avoid the collision.

### Install as a Claude Code plugin

From a Claude Code session:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

This registers Pitloom's repository as a marketplace named `pitloom` and
installs the `pitloom` plugin from it -- both Skills become available in
every session immediately after.

## Using the Skills

Either surface triggers the same two ways:

- **Natural language** -- ask in plain language, e.g. "generate an SBOM
  for this project" or "enrich this SBOM with the dataset it was trained
  on". The agent matches your request against each `SKILL.md`'s
  `description` front matter and loads the matching Skill automatically.
- **Explicit invocation** -- `/sbom [target]` and `/enrich [sbom-file]`
  standalone; `/pitloom:sbom [target]` and `/pitloom:enrich [sbom-file]`
  when installed as the plugin. Both arguments are optional.

### Generate an SBOM

```text
/sbom .                                 # project directory, current dir
/sbom models/my-model.safetensors       # local AI/ML model file
/sbom mistralai/Mistral-7B-v0.1         # Hugging Face Hub model ID
```

Under the hood this runs `loom generate <target>` (or the more specific
`loom project` / `loom wheel` / `loom model`).

See [`skills/sbom/references/examples.md`][sbom-examples] for the full recipe
set.

[sbom-examples]: https://github.com/bact/pitloom/blob/main/skills/sbom/references/examples.md

### Enrich an existing SBOM

```text
/sbom .                     # generate the base SBOM first
/enrich sbom.spdx3.json     # then enrich it
```

The Skill reads the project's README or the model's model card, drafts a
small standalone SPDX 3 JSON fragment for whatever it can infer (never
hand-edits the generated SBOM), registers it under
`[tool.pitloom.fragments]`, and re-runs Pitloom so the fragment is
merged. Every inferred field is marked `Source: AI agent | Method:
inference` in its `comment`, so it is never mistaken for Pitloom's own
extraction. See
[`skills/enrich/references/examples.md`][enrich-examples] for a full
worked example, including the pre-merge and post-merge validation steps.

[enrich-examples]: https://github.com/bact/pitloom/blob/main/skills/enrich/references/examples.md

## Verifying it works

For the plugin specifically, `claude plugin validate .claude-plugin/plugin.json`
and `claude plugin validate .claude-plugin/marketplace.json` check the
manifests, and `claude plugin details pitloom` (after installing) lists
both Skills and an estimated token cost.
