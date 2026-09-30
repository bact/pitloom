---
Created: 2026-09-21
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Explicit config sources (`--config`/`pitloom_config=`): implementation record

See also:
[cli-shared-options-ignored.md](../design/cli-shared-options-ignored.md)
(the gap survey this fixes; trimmed to what's still open),
[docs/configuration.md](../../docs/configuration.md#where-settings-come-from)
(the published per-surface table), [manual-cli-checks.md](manual-cli-checks.md)
(check 12).

## The problem

Before this change, a wheel/env/model target read whichever
`pyproject.toml` happened to sit in the current working directory --
`resolve_generator_config()` walked from `Path.cwd()`. That directory
has no necessary relationship to the wheel/model/environment being
scanned: running `loom wheel dist/other-package.whl` from inside an
unrelated project silently picked up *that* project's settings
(`enrich`, `update-id-registry`, creator identity, `id-registry`). There was
also no way to point any of these targets at a config file at all --
only a project directory's own `pyproject.toml` was reachable.

## Decisions

- **Precedence**: per-run flag/parameter > `--config FILE`/
  `pitloom_config=` > the target's own `[tool.pitloom]` (project
  directory, an sdist archive (step 6.5), `embed-wheel --project-dir`,
  the Hatchling hook) > hardcoded default.
- **Replace, not merge**: `--config`/`pitloom_config=` replaces the
  target's own config outright. A field the given config leaves unset
  reverts to the built-in default, never to the target's own value --
  merging field-by-field would make the two configs' precedence order
  depend on which fields either happens to set, impossible to reason
  about from the CLI alone.
- **No implicit reads, ever, for a target with no project of its own**:
  a wheel, an installed environment, a model file, a Hugging Face
  model, `enrich` without `--project-dir`, and `embed-wheel` without
  `--project-dir` never read the current directory or the target's own
  location. `resolve_standalone_config()` (`core/config_cascade.py`) is
  the one function every such generator calls: overrides, then an
  explicit `pitloom_config`, then `PitloomConfig()`'s defaults --
  nothing else.
- **`INERT` by target kind, not by command**: `core/inert_options.py`
  keys the "options that don't apply" table by target kind (`PROJECT`,
  `SDIST`, `WHEEL`, `ENV`, `MODEL_FILE`, `HF`, `ENRICH`,
  `ENRICH_STANDALONE`, `EMBED_PROJECT`, `EMBED_STANDALONE`,
  `EMBED_SBOM`), not by CLI
  subcommand, so `loom wheel`, `loom generate x.whl` and
  `generate("x.whl")` share one row and one wording. `PARAM_TO_FLAG`
  gives each library parameter's CLI spelling for the warning; a
  `BooleanOptionalAction` flag names both spellings since either one may
  be the one given. `settle_inert()` warns in `PARAM_TO_FLAG` order, not
  the caller's mapping order, so the warning sequence is deterministic
  regardless of which dict a caller happened to build.
- **The deepest layer that drops a parameter warns about it, exactly
  once**: `forward_options()` reads the callee's signature to decide
  what it accepts; what it doesn't accept and `INERT` declares inert for
  that kind is settled there. An option the callee *does* accept is left
  for the callee's own `settle_inert()` call -- never double-warned, and
  a parameter neither the callee accepts nor `INERT` declares is a
  wiring bug (`ValueError`), not a silent drop.
- **A whole-batch warning fires once, not once per wheel**:
  `embed-wheel`'s `_settle_batch_options()` settles every option before
  the per-wheel loop starts, as `EmbedFileCache.settle()` does for the
  build flags. `_generate_embed_sbom_json()`'s own `_settle_embed_options()`
  uses `EmbedFileCache.once()` too when a cache is given, keyed on the
  inert set and on the byte cap, so a shared batch warns once for the
  whole batch, not once per call.
- **The byte cap normalises once, not per generator**:
  `max_source_metadata_bytes` used to be normalised independently inside
  each provenance-resolution call site; it now normalises once inside
  `apply_overrides()`/`_settle_embed_options()`, so a too-small value
  warns once regardless of how many downstream calls read the resolved
  `ProvenanceConfig`.
- **`load_config_file()` fails loudly**: unlike a target's own
  (optional) config, a file the user named with `--config` is a source
  that claimed to carry settings -- missing, a directory, non-UTF-8,
  invalid TOML, or an invalid setting each raise, naming the file,
  instead of degrading to defaults. A file with no `[tool.pitloom]`
  table is not an error (empty is valid TOML) but does warn, since a
  wrong path would otherwise pass unnoticed.
- **A relative `id-registry` inside `--config` resolves against the config
  file's own directory**, not the current directory and not a symlink
  target's directory -- the config means the same thing regardless of
  where Pitloom runs from.
- **A relative `--id-registry` on the command line resolves against the
  current directory, on every command** -- unlike a target's own
  `id-registry`, which is project-relative. This is a path given on the
  command line, so it follows shell-path convention, not the config's.
- **`embed-wheel` never infers a project from the current directory**:
  `--project-dir` is required to have it rescan one; without it (and
  without `--sbom`), it embeds a standalone-wheel SBOM built from the
  wheel's own contents alone.
- **`resolve_project_with_lockfile()` still does the real project
  read**: an explicit config never skips reading `project_target`'s
  metadata -- only its `[tool.pitloom]` is swapped in afterward
  (`_with_config()`). A malformed target `pyproject.toml` still raises
  even under `project --config C`, since the real read runs regardless.
- **`--use-lockfile` is an `INERT` option like the rest.** The resolver
  (`resolve_project_with_lockfile()`) no longer warns; the layer holding
  the user's value settles it -- `generate()` via `forward_options()`,
  `generate_project_sbom()` for an sdist, `enrich_model()` without
  `--project-dir` (kind `ENRICH_STANDALONE`). One ordering and one
  wording everywhere, and the reach matrix covers it.
- **`wheel --embed` embeds what `embed-wheel` embeds**: it settles the
  whole `EMBED_STANDALONE` row (same reasons as `embed-wheel` without a
  project), clears those options, and forces `EMBEDDED_SBOM_PARAMS`
  (`pretty`, `describe_relationship`, `update_id_registry`) off, so `-o`
  writes a copy of the embedded bytes. Rejected:
  a pretty `-o` plus a canonical embedded copy -- two different SBOMs
  from one run, and `describe_relationship` changes content, not only
  formatting.
- **A config key a target cannot use is documented, not warned**:
  `[tool.pitloom.fragment]` on a non-directory target, `pretty`/
  `describe-relationship` on an embedded SBOM. One config usually serves
  several commands (a shared `--config` for `project` and `wheel`), so a
  per-run warning would fire on every legitimate use. The matching
  *flag* still warns, since a flag is given for that one run.
- **`enrich --project-dir <sdist>`** resolves identity and registry as
  the sdist's own SBOM does: no file walk (`merkle_root` stays `None`),
  and only an explicit registry (the archive's directory is not a
  project).
- **`embed-wheel --sbom` does not read `--config` or `--project-dir`**:
  neither can change an SBOM embedded as is, so a missing or invalid one
  only gets the no-effect warning, not an `ERROR:`. `project_dir` is an
  `INERT[EMBED_SBOM]` parameter, so `embed_wheel_sbom(sbom_path=...,
  project_dir=...)` warns the same way.
- **A wrong-shaped config value raises, in the parser**
  (`_config_parse.py`): a non-table `[tool]`/`[tool.pitloom]`/`creation`/
  `fragment`, a non-array `fragment.files`, a non-string
  `sbom-basename`/`creation-datetime`/`creation-comment`. They used to
  degrade to defaults (dropping a `required` fragment silently) or crash
  later with `AttributeError`. Every config path gets it -- a project's
  own `pyproject.toml` too, not only `--config`.
- **Enrichment `CreationInfo.created` read the wall clock**, so two runs
  a second apart differed despite a pinned datetime (a CI flake in
  `test_flag_beats_config_beats_default[enrich-comment]` on Windows).
  Fixed here: it reuses the main `CreationInfo.created`, already resolved
  from the pin. `tests/test_wall_clock_sources.py` now fails on any new
  wall-clock read outside the allowlisted last-fallback sites.

## Tests

- `tests/cli/test_cli_option_reach.py` -- every `INERT` row reachable
  from its CLI subcommand warns with the right flag spelling and
  reason.
- `tests/cli/test_cli_no_implicit_config.py` -- CLI-level: no
  `wheel`/`env`/`model`/`enrich`/`embed-wheel` invocation reads a decoy
  `pyproject.toml`/`loom-id-registry.json` from the current directory.
- `tests/assemble/test_generator_no_implicit_config.py` -- the same
  guarantee at the library level, per generator function.
- `tests/assemble/test_explicit_config_edges.py` -- library edge cases:
  an explicit config's `use-lockfile` in every lock-file decision
  (including `enrich`'s base identity and registry), an sdist's inert
  `enrich`/registry, one warning per embed batch.
- `tests/core/test_config_cascade.py` -- `load_config_file()`: missing
  file, directory, non-UTF-8, invalid TOML, no `[tool.pitloom]` table,
  relative `id-registry` (and through a symlink).
- `tests/core/test_inert_options.py` -- `INERT` against the
  `docs/cli.md` table, and every warned flag exists on the CLI.
- Manual check 12 in
  [manual-cli-checks.md](manual-cli-checks.md#the-checks) runs the same
  no-implicit-config guarantee against the real `loom` entry point (a
  decoy project directory, `--offline`, byte-identical SBOMs, registry
  untouched).

## Paths rejected

- **The PR #228 cwd cascade** (`resolve_generator_config()` walking
  `Path.cwd()` for wheel/env/model) -- the problem this whole change
  fixes; see "The problem" above. Removed outright, not deprecated,
  since it never shipped in a release.
- **Reading a config from the target's parent directory** (e.g. a
  wheel's own containing folder) -- considered and rejected: a
  `dist/*.whl` typically sits next to unrelated build artefacts, not a
  `pyproject.toml`, and even when one exists there is no more
  trustworthy a signal than the current directory is. Only an explicit
  `--config`/`pitloom_config=` earns trust.
- **Merging `--config` with the target's own config** -- rejected for
  precedence clarity (see "Replace, not merge" above). A merge would
  also need its own tri-state semantics per field (unset vs.
  explicitly-default), which none of `PitloomConfig`'s fields carry
  today.
- **A command-keyed inert table** (one row per CLI subcommand instead of
  per target kind) -- rejected: `loom generate x.whl` and `loom wheel`
  reach the same generator, so a command-keyed table would need two
  entries kept in lockstep by hand, reintroducing the drift class
  `INERT` exists to prevent.

## Found, not fixed here

- **Config-parity findings** (error shapes, `-v` sources, key
  applicability, unknown keys, repeated warnings, ...) moved to
  [config-cascade-parity.md](../design/config-cascade-parity.md), to be
  fixed together. Two items from that list -- `loom.Run`'s cwd walk-up
  and id-minting via `id-registry` -- are resolved by PR A2: a registry
  is used only when explicitly declared, on every surface; see
  [id-registry-autosync.md](id-registry-autosync.md)'s "Revised in PR
  A2" section.
- ~~**A latent import cycle**: `core._config_parse` imports
  `extract._toml_io`, which (via `extract/__init__.py`) reaches
  `extract.project.reader`, which imports `core.config`.~~ Fixed (P11):
  `_toml_io` moved to `pitloom._toml_io`, a stdlib-only leaf, so `core`
  no longer imports `extract` at module level. A live test confirmed it
  was real: with an empty `pitloom/__init__.py`, `import
  pitloom.core.config` failed on it; the real `__init__` hid it by
  importing `assemble` (and so `extract`) first.
- ~~**A second import cycle**: `import pitloom._loom_active_run` as the
  first Pitloom import fails (it imports `pitloom.loom`, which imports it
  back).~~ Fixed (P11): `_loom_active_run` only needed
  `loom._LOOM_PROVENANCE_CONFIG`, which now lives in `_loom_active_run`
  itself.
- ~~**A third, found by the same live test**: `extract.lock.cascade`
  imports `parse_provenance_value` from `assemble.spdx3`, and
  `assemble/__init__.py` imports `extract`.~~ Fixed (P11): the parser
  (stdlib-only) moved to `pitloom.core.provenance`; `assemble` re-exports
  it.
- **Still open: `assemble/__init__.py` <-> `embed`.** The `assemble`
  facade re-exports `embed_wheel_sbom()` & co., and `embed` needs
  `assemble.spdx3`. Harmless with the real `pitloom/__init__.py`; fails
  `import pitloom.embed` with an empty one. Fixing it means dropping
  those re-exports (a public-API change; one test imports
  `embed_wheel_sbom` from `pitloom.assemble`), so it was left out of P11.
  `tests/test_import_order.py` pins it as the one known failure, so the
  fix must also drop that entry.
- **How cycles are caught now**: `tests/test_import_order.py` imports
  every `pitloom` module first, with `sys.modules` cleared before each,
  twice: with the real `pitloom/__init__.py`, and with an empty one
  (which exposes a cycle hidden by `__init__`'s import order). One
  subprocess per mode/chunk, run in parallel; about 4 s.
- **`--describe-relationship` warns on `embed-wheel`/`enrich`.** A
  current decision (a wheel-embedded SBOM is always canonical; a
  fragment has no relationships of its own to describe), not
  necessarily permanent -- revisit if either target's shape changes.
- ~~An sdist archive's own `[tool.pitloom]` is never read; an invalid
  target `[tool.pitloom]` still fails `project --config C`.~~ Both fixed
  in step 6.5: [sdist-own-config.md](sdist-own-config.md).
