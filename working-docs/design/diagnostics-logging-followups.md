---
Created: 2026-09-28
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Diagnostics / logging follow-ups

See also: [roadmap.md](roadmap.md) (the summary bullet this file expands
on), [debug-logging.md](../implementation/debug-logging.md),
[config-sources.md](../implementation/config-sources.md),
[config-cascade-parity.md](config-cascade-parity.md).

Split out of `roadmap.md` (2026-09-28) once this section grew past the
file-size guidance -- moved verbatim, no content changed.

- [x] **`--debug` flag / `PITLOOM_DEBUG` env var, and promoting
  silent-data-loss `DEBUG:` messages to `WARNING:`** -- both shipped
  together. See [debug-logging.md](../implementation/debug-logging.md)
  ([PR #201](https://github.com/bact/pitloom/pull/201)).
- [ ] **`loom <cmd> -o -` corrupts piped JSON** -- with stdout as the
  SBOM output, `_print_sbom_output_path()`
  (`cli/commands/utils.py`) still prints
  `PITLOOM_SBOM_OUTPUT_PATH=-` to stdout after the JSON, on the same
  stream a consumer expects to be pure SBOM. Found during a
  `--build-timeout` review, 2026-09-19.
- [ ] **Hatchling-heuristic fallback WARNING embeds an untagged
  multi-line exception** -- `_models_wheel_hatchling.py`'s discovery-
  failure `WARNING:` (~L64) appends a real exception's full text after
  its one `WARNING:` tag, so continuation lines reach stderr with no
  `LEVEL:` prefix of their own -- breaks "every line starts with
  exactly one `LEVEL:`" (CLAUDE.md's "CLI output"). Found during a
  `--build-timeout` review, 2026-09-19.
- [ ] **Ctrl-C prints a raw `KeyboardInterrupt` traceback** -- no
  top-level handler in `__main__.py` catches it, unlike every other
  failure mode (`ERROR:` via `cli_error_handler`). Found during a
  `--build-timeout` review, 2026-09-19.
- [x] **Shared options accepted, then silently ignored** -- fixed via
  `core/inert_options.INERT`, a per-target-kind "has no effect" warning
  every shared flag now goes through. See
  [config-sources.md](../implementation/config-sources.md); remaining
  open gap in
  [cli-shared-options-ignored.md](cli-shared-options-ignored.md).
- [ ] **Canonical output follow-ups** -- name comparison across types;
  key-order audit of project-metadata sources. Sorted keys, UTC `Z`, LF and
  percent-encoded names in ids (an AI model name with a space gave an invalid
  IRI) are built.
  See [canonical-output-followups.md](canonical-output-followups.md).
- [ ] **`enrich` and `merge` stdout is not `KEY=VALUE`** -- they print
  prose (`Enrichment fragment written to: ...`, `pitloom: merged N
  fragment(s) into ...`), unlike `PITLOOM_SBOM_OUTPUT_PATH=` from every
  other SBOM command ("CLI output" in CLAUDE.md); so do `id` and
  `fragment validate`.
- [x] **A relative `--id-registry` resolves against the project directory**
  -- fixed: it now resolves against the current directory on every
  command, like every other path option. See
  [config-sources.md](../implementation/config-sources.md).
- [x] **`loom id generate` crashes on a symlinked path** -- fixed: PATH
  arguments now resolve via `os.path.realpath` (matching `project_dir`'s
  own `.resolve()`), and a PATH outside `--project-dir` is a clean
  `ERROR:` line instead of a raw `relative_to()` traceback.
- [ ] **`loom id generate` mints a random registry namespace** -- a
  UUID4 per run, so two fresh registries for the same project differ.
  Decide whether that is intended (a registry is minted once) or should
  be derived like an SBOM's namespace.
- [ ] **`loom id generate -e NAME:TYPE` accepts any TYPE** -- `My Type#1`
  is registered as a type no element ever has, so the entry is never looked
  up; its id is percent-encoded (PR #253). Reject a TYPE that is not an
  SPDX 3 class name with one `ERROR:`.
- [ ] **`loom id generate` only excludes the default registry filename
  from its own indexing** -- it skips `loom-id-registry.json` so the
  registry doesn't index itself, but a custom-named registry declared
  via `--id-registry`/`id-registry` under an indexed path (e.g.
  `data/my-registry.json` when `data` is scanned) indexes itself. Found
  during PR A2's explicit-registry review, 2026-09-28. Same root as the
  in-package-tree registry item in
  [id-registry-followups.md](id-registry-followups.md#a-declared-registry-inside-the-package-tree-never-settles).

- [ ] **Big item: config cascade parity across usage surfaces** -- ~20
  differences in how a setting is read, applied, errored on and reported
  (`-v`) across CLI, library, hook, `pitloom.loom`, directory vs sdist;
  one resolver with recorded sources, one reader per format, a key
  applicability table, a surface x setting matrix test. Fix together.
  See [config-cascade-parity.md](config-cascade-parity.md).
- [ ] **Leftovers from #231/#232** (two import cycles; the Poetry
  `version = 3` crash is fixed in #254). See
  [config-sources.md](../implementation/config-sources.md#found-not-fixed-here),
  [sdist-own-config.md](../implementation/sdist-own-config.md#found-not-fixed-here).
