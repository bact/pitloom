---
Created: 2026-07-05
Last-Modified: 2026-08-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Using Pitloom as a Claude Code plugin

Pitloom ships a Claude Code plugin, self-hosted from this repository, that
bundles the `sbom` and `enrich` Skills (see
[agent-skill.md](agent-skill.md)) under the `pitloom` plugin namespace.
It is the same Skills either way -- the plugin only adds an install path
and namespaced explicit invocation.

See [adoption-surfaces.md](../design/adoption-surfaces.md) for how this
fits alongside Pitloom's other surfaces.

## Installing the plugin

From a Claude Code session:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

This registers Pitloom's repository as a marketplace (named `pitloom`) and
installs the `pitloom` plugin from it. Once installed, both Skills are
available in every session, either by natural-language trigger or by
explicit invocation (`/pitloom:sbom`, `/pitloom:enrich`).

## What is in the plugin

```text
.claude-plugin/
|- plugin.json          Plugin manifest (name, description, author, license).
`- marketplace.json      Self-hosted marketplace entry (source: "./").
skills/
|- sbom/                 Generate skill (see agent-skill.md) -- bundled
|                         as-is; drives 'loom generate' / 'loom project' / 'loom wheel' / 'loom model'.
`- enrich/               Enrich skill -- same.
```

`plugin.json` declares no `skills` field: because `skills/` already sits
at the repository root (the plugin root), Claude Code auto-discovers both
`sbom/` and `enrich/`. A skill's invocable name is its **directory name**,
namespaced by the plugin's own name -- `skills/sbom/` under plugin
`pitloom` becomes `/pitloom:sbom`, and likewise `/pitloom:enrich`.

## Using the Skills

```text
/pitloom:sbom
/pitloom:sbom models/my-model.safetensors
/pitloom:enrich
```

Both remain triggerable by natural language too (e.g. "generate an SBOM
for this project"), the same as when installed standalone -- the plugin
only adds the namespaced explicit path, useful when you want to be certain
a skill runs, or want to pass a target path or model directly as an
argument.

## Design notes

- Skills are namespaced by the plugin's own name (`pitloom`), not by
  individual command files -- this is why the plugin is named plainly
  `pitloom` rather than `pitloom-sbom`: the namespace prefix already
  identifies it, so a per-skill name suffix would be redundant
  (`/pitloom:pitloom-sbom` instead of the clean `/pitloom:sbom`).
  Namespacing also means only the plugin's own name (`pitloom`) needs to
  be globally unique -- not every individual skill name underneath it,
  which is what actually protects `sbom`/`enrich` from colliding with
  skills any other plugin might define.
- The plugin declares an explicit `version` (semver) in `plugin.json` --
  this is a publicly installable, marketplace-listed plugin (not an
  internal/dev one), so a real version lets `claude plugin list`/`details`
  show something meaningful instead of a raw git commit SHA, and lets
  `claude plugin tag` cut a matching `pitloom--v<version>` release tag.
  Bump it whenever `skills/` or `plugin.json` changes in a user-visible
  way.
- `.claude-plugin/marketplace.json`'s single plugin entry uses
  `"source": "./"`, the standard self-hosting pattern when the plugin
  lives in the same repository as the marketplace that lists it. The
  entry deliberately does **not** repeat `plugin.json`'s `description`,
  `author`, `homepage`, `repository`, `license`, `keywords`, or
  `version` -- Claude Code resolves those from `plugin.json` at
  install/list/details time when the marketplace entry omits them
  (verified with `claude plugin install`/`details` against a minimal
  entry), so duplicating them here would just be two copies to keep in
  sync for no benefit. The entry keeps only what a marketplace listing
  needs that `plugin.json` doesn't carry: `category: "security"`, used
  for browsing/filtering marketplace listings.
- Both manifests declare `$schema` (SchemaStore's
  `claude-code-plugin.json` / `claude-code-marketplace.json`) purely for
  editor autocomplete/validation; it is ignored at load time.
- Each `SKILL.md`'s frontmatter declares `argument-hint` (`[target]` for
  `sbom`, `[sbom-file]` for `enrich`) so the Claude Code command palette
  shows what an explicit invocation (`/pitloom:sbom <target>`) expects,
  even though both arguments remain optional.
- `.claude-plugin/` (pure manifest, no value outside `/plugin install`)
  is excluded from the sdist, like `.github`. `skills/` stays in the
  sdist as user-facing plugin content; it was never part of the wheel
  (only `src/pitloom` is packaged there).
- `.github/workflows/plugin-validate.yml` runs `claude plugin validate`
  against both manifests whenever `.claude-plugin/` or `skills/` change.
