---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Lock/pin cascade: `--no-use-lockfile` opt-out

See also:

- [The cascade][main] (priority order, wiring, provenance)
- [Per-format notes][fmt] (extraction and shared code)

[main]: lock-file-cascade.md
[fmt]: lock-file-cascade-formats.md

## `--no-use-lockfile` opt-out

`read_project()`'s `include_locked_dependencies` parameter existed from
the start (gating this whole cascade plus the `poetry.lock` early-read
path), but until now no user-facing surface ever set it to `False` for a
call that kept real metadata -- only build-stage, metadata-discarding
callers (`embed-wheel`, the Hatchling hook's `_poetry_fallback_metadata()`,
the shared CLI options helper's config-only peek) hardcoded it off.
`--no-use-lockfile` / `[tool.pitloom] use-lockfile = false` close that
gap: on `loom project`/`loom generate`, it feeds straight into
`generate_project_sbom()`'s `use_lockfile` parameter, which resolves
`CLI flag > [tool.pitloom] > True` and then decides which
`read_project()` call to make. Default stays `True` (opt-out, not
opt-in) -- this cascade already shipped default-on, and reversing that
now would be an unrelated behaviour change. (Originally shipped as
`--locked-dependencies`/`--no-locked-dependencies`; briefly renamed to
`--lockfile`/`--no-lockfile` for brevity, borrowing yarn/pnpm's flag
name for the same "consult the lockfile or not" concept -- deliberately
not the bare `--locked`/`--no-locked` cargo/uv use, since those assert
lockfile consistency rather than opting into reading one at all. Renamed
again to `--use-lockfile`/`--no-use-lockfile`: a bare `lockfile` bool sat
in the same Python scopes as `ProjectMetadata.locked_dependencies` -- the
unrelated, actual resolved-dependency data from a separate PR -- and read
too easily as "the lockfile itself" rather than a toggle, exactly the
kind of conflated naming this repo's recurring-bug-pattern notes warn
about. The CLI flag/config key/Action input all carry the `use-lockfile`
spelling too, for the same "usage surfaces" consistency this whole
rename was already chasing -- only the internal
`resolve_project_with_lockfile()` function name was left as-is, since
it's a verb phrase describing behaviour, not a bool identifier.)

Resolving the setting before the real metadata read requires a cheap
"peek" call (`read_project(..., include_locked_dependencies=False)`,
which does no lock-file I/O -- but does still do in-tree installed-
metadata discovery/parsing, per
[installed-dist-info-source.md](../design/installed-dist-info-source.md);
that I/O is paid twice, once per `read_project` call, in the on-cascade
case below, the same accepted-cost umbrella as the double metadata parse
itself) purely to read `[tool.pitloom] use-lockfile` when no explicit CLI
flag was given, reusing the peeked metadata/config when it already
matches the final decision rather than reading twice.
`generate_project_sbom()`, `loom project`'s own command handler,
`loom generate`'s own command handler (for a project-directory target
only -- see below), and `enrich_model()` (see below) all need
this same peek-then-decide behaviour, so it lives in one place --
`pitloom.extract.project.resolve_project_with_lockfile()` -- rather than
being hand-copied per caller (the "pattern hand-copied across 3+ call
sites drifts" rule). The peek-then-reread's own duplicate-`WARNING:`
risk (same file parsed twice) is closed via a `quiet` parameter threaded
through the shared read path, so the reread never re-emits what the peek
already logged; the sdist-archive case (which never varies by this
setting) skips the peek/reread dance entirely instead.

`loom generate`'s command handler special-cases a project target (a
directory or sdist, `pitloom.assemble.target_resolves_to_project()`): it
runs `loom project`'s own code path
(`cli/commands/project.generate_project_from_args()`), so the project is
read once. Every other target (env/wheel/model file/Hugging Face) goes
through the shared `generate()` dispatcher and reads no project config
at all (see `config-sources.md`).

`loom enrich`'s `enrich_model()` (`_model_generator.py`, via
`_doc_identity_of()`) also threads this setting: it must match whatever
value produced the *base* document being merged into, or the fragment's
`doc_uuid` reference diverges (see `test_model_generator_doc_identity.py`'s
regression coverage, which reads the base identity back off
`enrich_model()`'s fragment). When `loom enrich` is given no explicit
`--use-lockfile` flag, `enrich_model()` auto-peeks `--project-dir`'s own
`[tool.pitloom] use-lockfile` config and uses that -- so a base SBOM
generated purely from config (no CLI override) is matched automatically,
with an explicit flag still available to cover the CLI-override case.

Every no-op case -- an explicit `--use-lockfile`/`--no-use-lockfile`
given for a target the setting doesn't apply to -- logs a `WARNING:`
identifying itself and explaining that the override was ignored, per the
"no silent deviations" rule: the sdist-archive case above
(`resolve_project_with_lockfile()`), `generate()`'s env/wheel/model-file/
Hugging-Face targets, and `enrich_model()` when called without
`project_target`/`--project-dir`.

The Hatchling build hook is a deliberate no-op for this setting, the
same way it already is for `[tool.pitloom] pretty`: lock/pin files are
source-stage-only and were already excluded from build-hook output
before this change (`hatchling.py::_poetry_fallback_metadata`'s
`include_locked_dependencies=False`).
