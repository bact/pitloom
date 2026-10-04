---
Created: 2026-09-21
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Step 6.5: an sdist reads its own `[tool.pitloom]`

See also: [config-sources.md](config-sources.md) (the rule this completes,
PR #231), [roadmap.md](../design/roadmap.md) (steps 7-10),
[canonical-output-followups.md](../design/canonical-output-followups.md)
(item #2, still open; #1/#3/#4 were folded in here).

## What was built

An sdist archive is a project target, so it now reads its own config as
the unpacked directory does. Before, `read_project()` returned
`PitloomConfig()` for an archive, so `loom project x.tar.gz` and
`loom project <unpacked x>/` gave different SBOMs from the same config.

- `extract/project/sdist.py`: one member scan shared by tar and zip
  (`_scan()` over `(name, open)` pairs). It keeps the first root-level
  (`<top>/<name>`) `PKG-INFO`, `pyproject.toml` and `setup.cfg`, streams
  everything in 8192-byte chunks, and caps a config member at 1 MiB
  (`CONFIG_MEMBER_MAX_BYTES`; over it is a read failure, below).
  `PKG-INFO` is kept as its header block only, read as a wheel's
  `METADATA` is (`wheel_dist_info.read_header_block()`: 16 MiB, 10,000
  headers; [wheel-identity.md](wheel-identity.md) D3), while the member is
  still hashed whole. A whole-file byte cap would not bound memory: 16 MiB
  of one-line headers parses to over 500 MiB. Over a cap: one `WARNING:`,
  metadata from the root `pyproject.toml` as with no `PKG-INFO` when the
  sdist has one; without it the metadata fields stay unset.
  `read_sdist()` returns `SdistContents(metadata, files, config,
  config_member)`.
  `read_sdist()` sorts `files` by `distribution_path`, as `read_wheel()`
  does: SPDX ids are minted in file order, so archive order must not show
  in them. The root-member tie between two top-level directories stays
  decided by archive order.
- One selection rule for both targets:
  `core/_config_parse.py:select_project_config()` -- the pyproject
  config when `pyproject_config_applies()` (it names the project or
  *declares* `[tool.pitloom]`, even empty), else `setup.cfg`'s
  `[tool:pitloom]`, else the defaults; it also returns the source, so a
  directory's `-v` names the file the values came from.
  `reader._fallback_to_setuptools` and `sdist._config` both call it; the
  drift test runs the same shapes through a directory and a
  `.tar.gz`/`.zip` and compares config and source. Rejected (first
  version, carried over from the directory code): "sets anything",
  `pyproject != PitloomConfig()` -- a value comparison, so an explicit
  `pretty = false` lost to `setup.cfg`'s `pretty = true`.
- The TOML is decoded as `tomllib.load()` decodes a file
  (`_toml_io.load_toml_bytes`, strict UTF-8).
- A config member that cannot be read (not TOML, not UTF-8 or a BOM, over
  the cap, a `setup.cfg` `configparser` error such as a bare `%` in
  `[tool:pitloom]`; `[metadata]` is read raw, only for `name`) or is
  invalid raises `ValueError("config file
  demo-1.0.0.tar.gz:pyproject.toml: ...")`, the `load_config_file()`
  wording with the member in place of a path -- as a directory fails.
  Never a fall-through to `setup.cfg`: an over-cap member still counts as
  the first of its name. Without the config read, a PKG-INFO-less
  archive's unparseable `pyproject.toml` is one `WARNING:` naming the
  metadata fields lost, as before.
- `read_project()` returns `archive/member` as the config path;
  `config_source_label()` turns it into `demo-1.0.0.tar.gz:pyproject.toml`
  for `-v` (`config_file_display()` gives `<archive path>:<member>` for the
  "Config file" row), and `sdist_config_source()` re-reads only the root
  members to find the raw table. `-v` runs after generation, and with
  `--config` it reports that file, so it never re-reads a broken archive.

## Decisions

1. **`id-registry` and fragments: documented, not warned.** #231's rule: a
   config *key* a target cannot use is documented; a *flag* warns. The
   `id-registry` could only name a file inside the archive, so `read_sdist()`
   drops it -- and the fragments -- at the source, so the CLI, the
   library, `enrich --project-dir` and `embed-wheel --project-dir` all get
   the same config with no caller-side "explicit or own" branch (the
   first version dropped fragments only in `_generators.py`, and
   `embed-wheel --project-dir <sdist>` still merged them). A `required =
   true` fragment does not fail an sdist. `embed-wheel` also skips an
   explicit `--config`'s fragments for an sdist, as `project` does. The
   same holds for `use-lockfile`, `enrich`, `extract-file-header` and
   `content-type`, whose flags warn for an sdist (`INERT[SDIST]`): all
   are listed in `docs/configuration.md`. Rejected: one `WARNING:` per key (the design doc's
   first proposal) -- it would warn on every third-party sdist that
   ships a normal config.
2. **Identity keys apply** (creators, creation comment and datetime), as
   for a cloned directory.
3. **`setup.cfg` is read** when the pyproject has no usable config, for
   parity with a directory.
4. **An invalid config raises**, as for a directory. The error names the
   archive's path (as the command resolved it) plus the
   member, as `load_config_file()` names a `--config` path; the SBOM's own provenance keeps the bare file name,
   so its bytes do not depend on where the archive sits.
5. **`--config`/`pitloom_config=` does not parse the config it replaces.**
   `read_config` is threaded through `read_project()` ->
   `read_pyproject()`/`read_setuptools()`/`read_setup_cfg()`/
   `read_sdist()`; `resolve_project_with_lockfile()` passes
   `read_config=explicit_config is None`. Without this, decision 4
   would make a broken third-party sdist unusable. An explicit flag, not
   call-site discipline (AGENTS.md "stage-scoped helpers").
6. **`sbom-basename` must be a file name** (no `/`, `\`, `:`, NUL,
   `.`/`..`), for every target: a third-party sdist's config must not
   choose where the SBOM is written without `-o`. One predicate,
   `core/file_names.is_plain_file_name()`, also guards the name embedded
   in a wheel (`--sbom-basename`), so the key and the flag agree.
7. **A pyproject that names the project holds its config**, even when
   its metadata then comes from `setup.cfg` (a `[tool.poetry]` whose read
   failed): its `[tool.pitloom]`, or the defaults, not `setup.cfg`'s --
   the sdist rule, now shared by the directory (before, a directory took
   `setup.cfg`'s there).

Rejected: warn-and-defaults for an unparseable `pyproject.toml` (the
first plan). With a `setup.cfg` beside it, the selection then fell
through to `setup.cfg`'s config while the directory failed.

Rejected: rescanning the archive inside `config_source_label()`, which
runs on every invocation, not only under `-v`.

## Canonical output folded in

- **LF and UTF-8** (#4): `pitloom/_sbom_io.py` is the one writer for
  SBOM, fragment and registry text, stdout included (UTF-8 bytes, one
  trailing `\n`). `tests/test_sbom_io.py` scans `src/` for any other
  text-mode write.
- **UTC `Z`** (#3): `builtTime` goes through `parse_iso_datetime()` and
  `to_spdx3_datetime()`; a raw `fromisoformat()` rejected `Z` on 3.10
  (the Hatchling build failed) and kept offsets. A scan in
  `tests/test_wall_clock_sources.py` confines raw parsing to
  `creation_info.py`.
- **Sorted keys** (#1): at the choke points, not per reader --
  `record_dict_field_provenance()`, `_populate_ai_pkg_hyperparameters()`
  (quantization stays first) and the `pitloom.loom` run's
  hyperparameters and their provenance.

## Found, not fixed here

- **Config-parity findings** (error shapes, `-v` sources, key
  applicability, unknown keys, repeated warnings, ...) moved to
  [config-cascade-parity.md](../design/config-cascade-parity.md), to be
  fixed together. `loom.Run`'s cwd walk-up and id-minting via
  `id-registry` are resolved by PR A2 -- see
  [config-sources.md](config-sources.md#found-not-fixed-here).
- `[tool.poetry] version = 3` crashed with an uncaught `AttributeError`:
  fixed in #254 (wrong-typed keys warn and are ignored).
- Same class, not fixed: `[project] name = 3` still crashes at
  `extract/project/pyproject.py`'s `(project_data.get("name") or "").strip()`
  before `pyproject-metadata` can report the type error.
- Same class, not fixed: a non-table `[tool]` (`tool = 3`) still crashes
  with `AttributeError` on `data.get("tool", {}).get(...)` in
  `extract/project/pyproject_dynamic.py` and `extract/project/pdm.py`
  (e.g. with `dynamic = ["version"]`). Only reachable with an explicit
  `--config`/`pitloom_config=`, which skips the `[tool] must be a table`
  check.
  #254 guards the Poetry path only (`read_poetry_section()`).
- The `pitloom._loom_active_run` import cycle: see
  [config-sources.md](config-sources.md#found-not-fixed-here).
