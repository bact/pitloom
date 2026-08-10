---
Created: 2026-08-09
Last-Modified: 2026-08-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

<!-- markdownlint-disable-next-line MD041 -->
{% include nav.html %}

# AI Skills and the Claude Code plugin

Pitloom ships three [Agent Skills][agent-skills] -- `sbom-generate`,
`sbom-enrich`, and `sbom-validate` -- and bundles all three as a
self-hosted [Claude Code plugin][claude-code-plugins].

[agent-skills]: https://www.anthropic.com/
[claude-code-plugins]: https://code.claude.com/docs/en/plugins

- `sbom-generate` -- generates a base SBOM/AIBOM for a project, wheel, or
  AI/ML model file.
- `sbom-enrich` -- reads a README or model card and contributes inferred
  detail (a license guess, a `trainedOn` dataset) back into an existing
  SBOM as a provenance-marked fragment; in an interactive session it can
  also ask the SBOM author directly for gaps no file answers. Requires a
  base SBOM to already exist; run `sbom-generate` first.
- `sbom-validate` -- runs the third-party `spdx3-validate` CLI against
  any SPDX 3 JSON document (schema + SHACL), catching a missing required
  property or a wrong relationship type that a bare `@graph`-presence
  check cannot. Works on Pitloom's own output, a hand-authored fragment,
  or a third-party SPDX 3 file.

## Choosing an install path

| Path | Choose this when... |
| :--- | :--- |
| [Agent Skills](#install-as-agent-skills) | You use any agent runtime that reads Skills from a filesystem directory, and want any subset of the three Skills, standalone. |
| [Claude Code plugin](#install-as-a-claude-code-plugin) | You use Claude Code and want one-command install (`/plugin install`) plus namespaced explicit invocation (`/pitloom:sbom-generate`, `/pitloom:sbom-enrich`, `/pitloom:sbom-validate`). |

Both install the exact same `SKILL.md` files.

### Install as Agent Skills

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

If a skill with the same name already exists at that path,
rename the destination folder to avoid the collision.

### Install as a Claude Code plugin

From a Claude Code session:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

This registers Pitloom's repository as a marketplace named `pitloom` and
installs the `pitloom` plugin from it -- all three Skills become
available in every session immediately after.

## Using the Skills

Either surface triggers the same two ways:

- **Natural language** -- ask in plain language, e.g. "generate an SBOM
  for this project", "enrich this SBOM with the dataset it was trained
  on", or "validate this SBOM". The agent matches your request against
  each `SKILL.md`'s `description` front matter and loads the matching
  Skill automatically.
- **Explicit invocation** -- `/sbom-generate [target]`,
  `/sbom-enrich [sbom-file]`, and `/sbom-validate [sbom-file]` standalone;
  `/pitloom:sbom-generate [target]`, `/pitloom:sbom-enrich [sbom-file]`,
  and `/pitloom:sbom-validate [sbom-file]` when installed as the plugin.
  All arguments are optional.

### Generate an SBOM

```text
/sbom-generate .                                 # project directory, current dir
/sbom-generate models/my-model.safetensors       # local AI/ML model file
/sbom-generate mistralai/Mistral-7B-v0.1         # Hugging Face Hub model ID
```

Under the hood this runs `loom generate <target>` (or the more specific
`loom project` / `loom wheel` / `loom model`).

See [`skills/sbom-generate/references/examples.md`][sbom-generate-examples]
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
`[tool.pitloom.fragments]`, and re-runs Pitloom so the fragment is
merged. Every inferred field is marked `Source: AI agent | Method:
inference` in its `comment`, so it is never mistaken for Pitloom's own
extraction. See
[`skills/sbom-enrich/references/examples.md`][sbom-enrich-examples] for a
full worked example, including the pre-merge and post-merge validation
steps.

[sbom-enrich-examples]: https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/references/examples.md

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

## Verifying it works

For the plugin specifically, `claude plugin validate .claude-plugin/plugin.json`
and `claude plugin validate .claude-plugin/marketplace.json` check the
manifests, and `claude plugin details pitloom` (after installing) lists
all three Skills and an estimated token cost.
