---
Created: 2026-07-05
Last-Modified: 2026-08-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Using Pitloom as a Claude Code plugin

Pitloom ships a Claude Code plugin, self-hosted from this repository, that
bundles the `sbom-generate`, `sbom-enrich`, and `sbom-validate` Skills
(see [agent-skill.md](agent-skill.md)) under the `pitloom` plugin
namespace. It is the same Skills either way -- the plugin only adds an
install path and namespaced explicit invocation.

See [adoption-surfaces.md](../design/adoption-surfaces.md) for how this
fits alongside Pitloom's other surfaces.

## Installing the plugin

From a Claude Code session:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

This registers Pitloom's repository as a marketplace (named `pitloom`) and
installs the `pitloom` plugin from it. Once installed, all three Skills
are available in every session, either by natural-language trigger or by
explicit invocation (`/pitloom:sbom-generate`, `/pitloom:sbom-enrich`,
`/pitloom:sbom-validate`).

## What is in the plugin

```text
.claude-plugin/
|- plugin.json           Plugin manifest (name, description, author, license).
`- marketplace.json      Self-hosted marketplace entry (source: "./").
skills/
|- sbom-generate/        Generate skill (see agent-skill.md) -- bundled
|                        as-is; drives 'loom generate' / 'loom project' / 'loom wheel' / 'loom model'.
|- sbom-enrich/          Enrich skill -- same.
`- sbom-validate/        Validate skill -- thin wrapper around the
                         third-party `spdx3-validate` CLI.
```

`plugin.json` declares no `skills` field: because `skills/` already sits
at the repository root (the plugin root), Claude Code auto-discovers all
three directories. A skill's invocable name is its **directory name**,
namespaced by the plugin's own name -- `skills/sbom-generate/` under
plugin `pitloom` becomes `/pitloom:sbom-generate`, and likewise for the
other two.

## Using the Skills

```text
/pitloom:sbom-generate
/pitloom:sbom-generate models/my-model.safetensors
/pitloom:sbom-enrich
/pitloom:sbom-validate
```

All three remain triggerable by natural language too (e.g. "generate an
SBOM for this project"), the same as when installed standalone -- the
plugin only adds the namespaced explicit path, useful when you want to be
certain a skill runs, or want to pass a target path or file directly as
an argument.

## Design notes

- Skills are namespaced by the plugin's own name (`pitloom`), not by
  individual command files -- this is why the plugin is named plainly
  `pitloom` rather than, say, `pitloom-sbom`: the namespace prefix
  already identifies it, so a per-skill name suffix would be redundant
  under this surface specifically (`/pitloom:pitloom-sbom-generate`
  instead of `/pitloom:sbom-generate`). Namespacing also means only the
  plugin's own name (`pitloom`) needs to be globally unique on *this*
  surface -- not every individual skill name underneath it.
- Skill directory names still carry an `sbom-` prefix
  (`sbom-generate`/`sbom-enrich`/`sbom-validate`, not bare
  `generate`/`enrich`/`validate`) even though the plugin namespace above
  already prevents collisions here. That prefix is for the *other*
  adoption surface: standalone/Agent-SDK skill installs (see
  [agent-skill.md](agent-skill.md)) have no namespace at all, and bare
  `enrich` or `validate` are exactly the kind of generic verb an
  unrelated skill from another vendor would also claim. `sbom-` costs
  nothing on the plugin surface (namespacing already disambiguates) and
  buys real safety on the un-namespaced one.
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
  install/list time when the marketplace entry omits them, so
  duplicating them here would just be two copies to keep in sync for no
  benefit. The entry keeps only what a marketplace listing needs that
  `plugin.json` doesn't carry: `category: "security"`, used for
  browsing/filtering marketplace listings.
- `marketplace.json`'s own top-level description lives under
  `metadata.description`, not a bare top-level `description` key --
  `claude plugin validate` (CLI 2.1.114) rejects the latter as an
  unrecognized key and, if omitted entirely, warns
  `"No marketplace description provided"`. This is the marketplace's own
  description (shown when browsing/listing the marketplace itself), a
  different thing from the per-plugin entry's deliberately-omitted
  `description` in the bullet above.
- Neither manifest declares `$schema` -- `claude plugin validate` (CLI
  2.1.114) rejects it as an unrecognized key at the schema root, contrary
  to an earlier version of this note claiming it was "ignored at load
  time" (it validated fine against an older CLI build; the strict-schema
  behavior changed). `plugin.json` likewise has no `displayName` field in
  the currently-validated schema -- `name` + `description` already cover
  that. Re-verify against the installed `claude` CLI version with
  `claude plugin validate .claude-plugin/plugin.json` /
  `.../marketplace.json` before assuming either key is safe to add back;
  don't rely on the SchemaStore schema URL as the source of truth --
  it's aspirational/editor-hint only, not what the CLI actually enforces.
- Each `SKILL.md`'s frontmatter declares `argument-hint` (`[target]` for
  `sbom-generate`, `[sbom-file]` for `sbom-enrich` and `sbom-validate`) so
  the Claude Code command palette shows what an explicit invocation
  (`/pitloom:sbom-generate <target>`) expects, even though the argument
  remains optional in all three.
- `.claude-plugin/` (pure manifest, no value outside `/plugin install`)
  is excluded from the sdist, like `.github`. `skills/` stays in the
  sdist as user-facing plugin content; it was never part of the wheel
  (only `src/pitloom` is packaged there).
- `.github/workflows/plugin-validate.yml` runs `claude plugin validate`
  against both manifests whenever `.claude-plugin/` or `skills/` change.
