---
Created: 2026-09-21
Last-Modified: 2026-09-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Config cascade parity across usage surfaces

See also: [roadmap.md](roadmap.md) (one-line entry),
[config-sources.md](../implementation/config-sources.md) (PR #231: explicit
config sources, `INERT`),
[sdist-own-config.md](../implementation/sdist-own-config.md) (PR #232: an
sdist's own config).

Not started. One big item, to be fixed together rather than one finding
at a time: each item below was found while fixing a neighbour, and each
past fix of one surface left the others to drift.

## Goal

A setting resolves the same way, from the same sources, with the same
errors and the same reporting, on every surface: CLI commands, library
functions, the Hatchling hook, the GitHub Action, `pitloom.loom`, and a
project directory vs its sdist. Where a surface genuinely cannot use a
setting, that is one declared, tested, documented fact -- never an
accident of which code path it goes through.

## Root causes

1. **Several readers of the same config.** A `--config` file
   (`load_config_file()`), a directory's `pyproject.toml`
   (`read_pyproject()`), a directory's `setup.cfg` (`read_setup_cfg()`),
   an sdist's members (`read_sdist()`), the hook (`self.metadata`), and
   `-v`'s second read (`_load_pitloom_tool_section()`,
   `sdist_config_source()`) each parse and fail in their own way.
2. **Sources are re-derived, not recorded.** `-v` re-reads config to
   guess where a value came from, instead of the resolver recording the
   source of each value as it resolves it.
3. **Applicability is declared for flags only.** `INERT` covers flags;
   which config *keys* a surface ignores is written in prose
   (`docs/configuration.md`) and checked by nothing.
4. **Surfaces outside the CLI/generator path** (`pitloom.loom`, the hook,
   `embed-wheel`'s own assembly) were not moved onto #231's rules.

## Known differences

### Reading and errors (root cause 1)

- **Error shape differs by source.** `--config`: `config file <path>:
  ...`; sdist: `config file <archive>:<member>: ...`; a directory's own
  `pyproject.toml`/`setup.cfg`: no file named at all.
- **A directory's `setup.cfg` errors are multi-line** (`configparser`
  text with a `\t[line N]` continuation, `<string>`), breaking "one
  `LEVEL:` per line"; the sdist path collapses them.
- **`%` in `setup.cfg`**: a directory interpolates `[metadata]` and fails
  on `description = 100% pure`; an sdist reads `[metadata]` raw.
- **`setup.cfg` key errors say `[tool.pitloom]`**, not `[tool:pitloom]`
  (both go through `parse_pitloom_config()` after conversion).
- **Unknown `[tool.pitloom]` keys are ignored silently** -- a typo such as
  `ofline = true` changes nothing and says nothing; likelier in a named
  `--config` file.
- **`read_pitloom_config` gates on `Path.exists()`** -- see
  [cli-shared-options-ignored.md](cli-shared-options-ignored.md#found-while-doing-this-not-fixed-here).

### What takes effect (root causes 3-4)

- **Hatchling hook ignores `pretty`/`describe-relationship`** (canonical
  JSON per PEP 770). Deliberate, but stated only in the hook docstring,
  not in the per-surface table.
- **`enrich --project-dir D` without `--config` uses the default
  creator**, while `project D` uses D's `creators`, so a fragment's
  creators differ from its base SBOM's.
- **`loom.Run(id_registry=None)` walks up from the current directory** for a
  registry -- the one surface still doing an implicit cwd read.
- **`sbom-basename = "x.spdx3.json"`**: `project` writes
  `x.spdx3.json.spdx3.json`, `embed-wheel` strips the extension and
  writes `x.spdx3.json`.
- **`embed-wheel --project-dir <sdist>` runs Hatchling file discovery on
  the archive path** (and warns it failed), while `project <sdist>` uses
  the archive's own listing.
- **An explicit config's `id-registry` reaches `wheel`/`env`/`model`** --
  the id-minting collision it widened is fixed (see
  [id-registry-autosync.md](../implementation/id-registry-autosync.md#id-mint-collision-fix-branch-id-mint-collision)).
- **`--max-source-metadata-bytes -1`** runs as no cap with no message;
  check whether the config key accepts it too.

### Reporting (root cause 2)

- **`-v` labels sources for `project`/`generate` only**; `wheel`/`env`/
  `model`/`enrich` print values without sources.
- **`-v` labels a `setup.cfg` value `[default]`**, for a directory and an
  sdist alike (`_load_pitloom_tool_section()` returns `{}` for it).
- **`-v` "Config file" row is tagged `[command-line]`** even for the
  project's own config.
- **A too-small `max-source-metadata-bytes` warns twice on `project`**
  (the config is read twice), once on `embed-wheel`.
- **A no-effect warning's subject differs by command**: the target as
  typed (`wheel`), a resolved absolute path (local model), the literal
  `"embed-wheel"` (standalone embed batch).
- **`ID registry: could not load` repeats once per wheel** in an
  `embed-wheel` batch.

## Direction (to decide before building)

- **One resolver** returning each setting's value *and* its source
  (flag, `--config` path, `pyproject.toml`, `setup.cfg`, sdist member,
  default). Every surface calls it; `-v` prints what it recorded, so no
  second read, one warning per problem.
- **One reader per format**, shared by directory, sdist and `--config`:
  same decoding, one-line errors prefixed `config file <path>[:<member>]:`,
  keys named in the format's own syntax.
- **A key applicability table** next to `INERT`, keyed by surface and
  config key; `docs/configuration.md`'s per-surface statements are
  checked against it by a test.
- **A surface x setting matrix test** (library, CLI, hook, Action,
  `pitloom.loom`, directory vs sdist) asserting the same resolved
  settings and sources -- the drift guard.

## Open questions

- Unknown keys: `WARNING:` or error? (A strict mode may be wanted for a
  named `--config`.)
- `enrich --project-dir`: should D's identity keys apply without
  `--config`?
- `sbom-basename`: always a base name (strip a given extension
  everywhere), or a full file name?
- `loom.Run`: remove the cwd walk-up outright, or deprecate first
  (private alpha: no compatibility needed)?
- Hatchling hook: keep ignoring `pretty` (PEP 770) -- then declare it in
  the table -- or honour it?
