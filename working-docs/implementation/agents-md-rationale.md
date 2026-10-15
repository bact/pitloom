---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AGENTS.md: long-form rationale

See also: [AGENTS.md](../../AGENTS.md) (the compact rules, which link here),
[recurring-bug-patterns.md](recurring-bug-patterns.md),
[recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md),
[recurring-bug-patterns-review-rounds.md](recurring-bug-patterns-review-rounds.md)
(the detail behind the bug-pattern one-liners).

`AGENTS.md` was compacted on 2026-10-15 to stay under the 30 KB hard limit.
The original wording of the rules that lost explanatory prose is kept
here, unchanged, under the same headings. Where the two differ, the rule in
`AGENTS.md` governs and this page explains it.

## Project context

- **`roadmap.md` stays a summary, not a duplicate**: once a roadmap item's design/open-questions detail grows enough to warrant its own file under `working-docs/design/`, move the detail there and trim the `roadmap.md` bullet back to one-to-two lines plus a `See [doc.md](doc.md)` link. Don't leave full detail in both places -- one will drift from the other unnoticed. The same split applies by kind, not just size: a completed item's decisions/rationale/paths-rejected belongs in `working-docs/implementation/` (not `design/`), trimmed from `roadmap.md` the same way once it has its own doc. A roadmap item that's abandoned or superseded but still worth keeping to prevent re-litigating it later moves to `working-docs/archive/` instead of staying in the active list. A still-unimplemented item that's genuinely small (a few lines, no real design decisions yet) is fine to keep inline in `roadmap.md` with no dedicated file -- split it out only once it grows enough to actually warrant one.

## Metadata sources

- **`physical_path` vs `distribution_path`**: on-disk project-root-relative path vs in-package/built path -- diverge for any `src/`-layout project. `software_File.name` in the SPDX graph always uses `distribution_path`. Any file-lookup/registry code keyed by path must check both, not just `physical_path`. A second hazard, distinct from the `src/`-layout divergence: for a `--allow-build` build-and-read discovered file, `physical_path` is an *absolute* path into a temporary extraction directory, not project-relative at all (see `ProjectFile.physical_path`'s own docstring in `core/project.py`). This recurred three times across independent consumers before being consolidated (PR #215) into one shared helper, `pitloom.core.project.project_relative_or_fallback(physical_path, fallback)` -- any new consumer that joins `physical_path` onto `project_dir`, uses it as a registry-lookup key, or bakes it into a determinism-sensitive string should call this helper instead of writing a new inline `Path(...).is_absolute()` check by hand.
- **Stage-scoped helpers must take an explicit stage flag**: a helper shared by both a source-stage caller (e.g. `read_pyproject()`) and a build-stage caller (e.g. the Hatchling hook's metadata gap-fill) must not rely on call-site discipline to stay stage-appropriate -- thread an explicit parameter (`include_locked_dependencies=False`-style) through it. A source-stage-only artifact (e.g. `poetry.lock`) silently leaking into a build-stage helper because both callers happened to share one function is the same class of bug the `physical_path`/`distribution_path` split above warns about.

## Usage surfaces

Pitloom is invoked from several usage surfaces (CLI, the Hatchling build hook, the public library API, the GitHub Action, the AI skills in `skills/*/SKILL.md`, and the Claude Code plugin in `.claude-plugin/`), and the CLI itself branches into 10+ subcommands. A change that updates one surface/subcommand and not the others is easy to ship by accident, because each surface's own tests keep passing in isolation -- only a cross-surface check catches the gap. (E.g.: `--debug` was wired into the top-level parser but 7 of 10 subcommand generators each called `configure_logging()` again with no arguments, silently reverting to `INFO` -- every subcommand's *own* tests passed.) The skills/plugin surfaces have no test suite of their own -- a CLI flag rename, a changed output format, or a new required argument silently goes stale there unless it's checked by hand; when editing anything a `SKILL.md` documents invoking, grep `skills/` for the changed command/flag/output shape and update it in the same change.

- **Route a cross-cutting choice through one shared, explicit mechanism** that every surface already calls or reads, instead of updating each surface's call site by hand. E.g. `--debug` threads through the `PITLOOM_DEBUG` env var so every downstream no-argument `configure_logging()` call agrees, rather than requiring every subcommand generator to remember to pass `debug=True` itself.
- **A docstring or comment describing "how surface X does Y" is a claim, not a fact.** Verify it against that surface's actual entry-point code (`__main__.main()`, `plugins/hatch.py`, the public library-API functions) before trusting or writing it -- a stale claim invites the exact regression it was meant to prevent, the moment someone trusts it instead of rereading the code.
- **A pattern hand-copied across 3+ call sites drifts.** When the same kind of message/check/value is written at several call sites (e.g. a `WARNING:` naming which SBOM field a failure skips), factor the shared shape into one helper/constant instead of retyping it per site -- otherwise wording or behavior silently diverges between sites with no single place to notice or fix it.
- **A test asserting on one surface doesn't cover the others.** When behavior must hold identically across surfaces (CLI vs library API vs Hatchling hook vs GitHub Action) or across every subcommand, add a regression test that exercises each surface/subcommand it's meant to hold for -- not just whichever one was easiest to reach from a test.
- **A skill is discovered through its frontmatter `description` only.** A body section documenting a command does not make it triggerable, and the skills have no tests. When a CLI command/flag is added or renamed, enumerate `add_parser(` subcommands against every `skills/*/SKILL.md` description; keep Pitloom's *verify* (structural) vs *validate* (schema/SHACL) distinction explicit, since users treat them as synonyms; give combined asks ("generate SBOM meeting CISA") an explicit hand-off in both skills; and give every "ask a follow-up" step a non-interactive fallback. Audit method, decisions and the deferred gaps: [skills-trigger-coverage.md](skills-trigger-coverage.md).

## Design principles

- **Resource efficiency**: Prevent excessive network access (use caching and route optimisation). Prevent memory spikes by streaming data for large structures. Never load entire files (like ML models or archives) into memory. Always use chunked reads (`read(8192)`), memory mapping, or native lazy header extraction (e.g., `np.lib.format` for NumPy, stream loading for fickling/pickle) to extract metadata.
- **Explicit pin beats local environment**: when a dependency's version is explicitly pinned by its own data source (a lock file, an exact `==`/`===` in the spec), that pin is always authoritative -- never silently overridden by introspecting Pitloom's own execution environment, which has no relationship to the target project's environment. Environment introspection is a fallback signal only for the unpinned case.
- **Absent source data is not an error; a genuine read/access failure is.** Every extractor and metadata source (AI model format readers, project metadata parsers, lock-file readers, Hugging Face Hub / network fetches, etc.) must degrade gracefully -- a field the source simply doesn't carry stays `None`/empty/absent, silently, with no `WARNING:`/`ERROR:` and no raised exception; that's not a "no silent deviations" violation, since nothing was deviated from -- the source never claimed to carry it. This is already the convention every AI model extractor follows (`read_numpy()`'s docstring enumerates which fields stay `None`; PT2/GGUF/Safetensors do the same for their own always-absent fields) -- treat it as a general rule for any current or future extraction source, not a per-format decision to re-derive each time. Reserve `WARNING:`/`ERROR:` and raised exceptions for genuine disruptions: file corruption, an unreadable/truncated archive, a network error or timeout fetching from a remote source, a parse failure on data the format's own marker already confirmed should be well-formed. The dividing line is "did the source have an opinion and fail to deliver it" (real failure, log/raise) vs. "the source never had this data to begin with" (normal absence, stay quiet).

## Code health and continuous refactoring

- **Reuse/dedup is a defensiveness strategy, not just an efficiency one**: with this many usage surfaces, backends, and file formats (see "Usage surfaces" below), two independent implementations of the same operation (a hash, a type check, a message string, a cascade rule) don't just cost extra lines -- they're two places that can silently disagree the next time either one is touched. Reuse a shared helper even when the duplicate is small/cheap and the duplication itself wastes nothing measurable; the point is to make drift structurally impossible, not to save a few lines.

## Python

- **Untyped third-party dependency**: before adding an `ignore_missing_imports`/`ignore-missing-imports` override (mypy `[[tool.mypy.overrides]]`, `[tool.pyrefly] ignore-missing-imports`, etc.), check PyPI for a legitimate, trusted `types-<package>` stub package (the typeshed-maintained ones, e.g. `types-PyYAML`, `types-setuptools`). Add it to the `typecheck` dependency group instead -- real stubs catch genuine type errors an `Any`-blanket override would hide, and (unlike a suppression) don't need re-verifying every time a type checker changes how it treats an unresolvable/stub-less import (e.g. pyrefly 1.2 vs 1.3 disagreeing on whether `ignore-missing-imports` still applies once a module is merely stub-incomplete rather than fully unresolvable). Only fall back to a suppression override when no such stub package exists.
