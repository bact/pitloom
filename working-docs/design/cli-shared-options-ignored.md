---
Created: 2026-09-20
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Shared CLI options accepted, then silently ignored

See also: [roadmap.md](roadmap.md) (one-line entry),
[manual-cli-checks.md](../implementation/manual-cli-checks.md) (checks 11/12 and
the CLI matrix that found these), and
[config-sources.md](../implementation/config-sources.md) (the explicit
`--config`/`pitloom_config=` change and its own `INERT`-based "no effect"
warning mechanism, which closed every gap listed below except the two
still open).

Every gap this doc originally tracked is now either fixed (via
`core/inert_options.INERT`'s per-target-kind warning, or genuine plumbing)
or superseded, with one exception carried forward:

## Still open

- **`env`/`wheel`/`model` never scan for AI models.** Only
  `project`/`generate` on a project directory and `embed-wheel
  --project-dir` scan (`ai_models=` is `[]` in `generate_wheel_sbom`,
  `generate_env_sbom` and the standalone-wheel embed), so a built wheel or
  an installed package that carries a model file gets no `AIPackage`.
  Decided 2026-09-22: built wheels will scan (planned PR D, with
  `--scan-model-usage` gating only the `.py` usage pass); `env` stays
  unscanned for now (no file list, no AIPackage path in
  `build_deployed()`). The provenance settings are already wired (see
  `config-sources.md`).

## Found while doing this, not fixed here

- **`read_pitloom_config` gates on `Path.exists()`**
  (`core/_config_parse.py`), which swallows a different errno set on
  Python 3.14 than on 3.10-3.13 (see AGENTS.md). An unreadable *parent*
  directory therefore warns on 3.10-3.13 and falls through to the silent
  "missing config" branch on 3.14. `os.path.isfile` is the
  version-independent spelling -- already used by the newer
  `load_config_file()` (`--config`'s own reader); this one gates the
  target's own `pyproject.toml` read instead and is unchanged. Unverified
  on 3.14 -- only 3.10 was to hand.
- **`file-map.md`'s per-directory test counts drift over time** --
  updated in this pass for `cli/`/`core/`/`assemble/`; re-check before
  trusting them again after a later change.
