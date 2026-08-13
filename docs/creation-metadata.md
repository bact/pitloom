---
Created: 2026-07-08
Last-Modified: 2026-08-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Creation metadata

> **Note:** This is reference documentation for auditing or debugging a
> generated SBOM -- not needed to just generate one. The schema described
> below is still in beta and can change without notice between releases.

Every element Pitloom emits carries a record of *who* created it, *what*
tool produced it, *when*, and (optionally) *how* it was invoked -- Pitloom's
own creation-metadata model (`CreationMetadata`, see
[`pitloom.core.creation`](https://github.com/bact/pitloom/blob/main/src/pitloom/core/creation.py)).
Don't assume a whole SBOM has exactly one such record: elements created
together in the same generation event share one, but a graph is free to
contain several, each covering whichever elements actually came from that
event -- see below.

SPDX 3 is Pitloom's only output format today, and it happens to define
almost exactly this shape as `CreationInfo`, so that's what this metadata
becomes in practice: `createdBy` (who), `createdUsing` (what tool),
`created` (when), `comment` (how). Should Pitloom add other output formats
later, the same who/what/when/how model would map onto whatever equivalent
concept that format defines -- this isn't an SPDX-specific design, just its
current, and so far only, expression. The [SPDX 3
spec](https://spdx.github.io/spdx-spec/v3.1-dev/model/Core/Classes/CreationInfo/)
is the authoritative reference for the field-level detail below.

A single Pitloom run -- one CLI invocation, one Hatchling build, one
`pitloom.loom.run` -- produces one such record, shared by every element
that run generated. When a composite SBOM merges pre-generated fragments
(see the [Hatchling build hook](hatchling-build-hook.md) and [Python
API](python-api.md#tracking-decorator) tracking decorator pages) via
`[tool.pitloom.fragment]`, each fragment keeps the record from whichever
run actually produced it. The result contains as many of these records as
generation events contributed to it -- correct provenance to keep, since
each part genuinely was created separately, at a different time, possibly
by a different creator.

This means `[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]` /
`[tool.pitloom.creation]` in `pyproject.toml` only shape the record for
whatever the CLI or Hatchling build hook itself generates (the main
document) -- they do not reach into fragment files that were already
generated earlier by `pitloom.loom.run`. A fragment's record is fixed at
the moment `loom.run` produced it; give it the same creator(s) by passing an
explicit `creation_metadata=CreationMetadata(...)` to that call.

| Field (SPDX 3 name) | Meaning | What Pitloom puts there |
| :--- | :--- | :--- |
| `createdBy` (**≥1**) | *Who* created it | One or more **creators**: a person, organization, software agent, or generic agent for each one you name (`--creator-name`, repeatable); otherwise Pitloom itself, acting unattended (see below). |
| `createdUsing` (0+) | *What* tool produced it | **Pitloom** by default, with a version summary; repeat `--creation-tool` for more than one. Suppress with `--no-creation-tool`. |
| `created` (1) | *When* | `--creation-datetime` if set, else the current UTC time. |
| `comment` (0-1) | *How* it was invoked | A short static note per channel (`Generated via Pitloom CLI`, `... Hatchling build hook`, `... loom SDK`), or your `--creation-comment`. |

Pitloom's design distinguishes *who acted* from *what tool was used* --
naming a creator (`--creator-name`) never names Pitloom itself as a
`Person` or `Organization`. Pitloom is recorded as the tool in
`createdUsing` by default (suppress with `--no-creation-tool`). In SPDX 3
terms this is the `Agent`/`Tool` split: an `Agent` (`Person` /
`Organization` / `SoftwareAgent` / the generic `Agent`) is who acts; a
`Tool` is the instrument used. With no creator named, Pitloom stands in as
the `SoftwareAgent` creator too (see below) -- but never pretending a
human did the work.

- **You name one or more creators** (repeatable `--creator-name`, or
  `[[tool.pitloom.creator]]`): each becomes a person (default), organization,
  software agent, or generic agent (via `--creator-type`/`type`, bound to the
  most recently named creator). The software-agent/agent types are for
  naming an automated creator that isn't Pitloom itself -- e.g. a CI bot
  that invoked Pitloom on someone's behalf. `suppliedBy` on the main package
  -- single-valued in SPDX 3 -- is set to the *first* named creator when two
  or more are given.
- **You name no creator** (zero-config): rather than invent a fake person,
  Pitloom records itself as the creator too, but as a software agent, not a
  person or organization -- honestly "an unattended Pitloom run made this" --
  and omits a supplier for the main package. Pitloom is also recorded as
  the tool by default (unless suppressed with `--no-creation-tool`), so
  the same Pitloom can show up twice in this case: once as the (software
  agent) creator, once as the tool.

This applies uniformly to the CLI, the Hatchling build hook, and
`pitloom.loom` fragments -- all three accept the same creator/tool/timestamp
overrides and fall back to the same `SoftwareAgent` default.

`setup.cfg` (INI) is a documented exception: `configparser` cannot express
TOML array-of-tables, so `[tool:pitloom]` / `[tool:pitloom:creation]` only
support a single `creator-name`/`creator-email`/`creator-type` and a single
`creation-tool`. Projects that need more than one creator or tool should use
`pyproject.toml` or the library API.

See [Command line](cli.md#configuration) for the `--creator-*` /
`--creation-*` CLI flags and the `[[tool.pitloom.creator]]` /
`[[tool.pitloom.creation-tool]]` / `[tool.pitloom.creation]`
`pyproject.toml` tables used to set these fields -- the [Hatchling build
hook](hatchling-build-hook.md) and [Python API](python-api.md) read the
same tables.
