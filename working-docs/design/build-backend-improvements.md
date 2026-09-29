---
Created: 2026-09-28
Last-Modified: 2026-09-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Build backend improvements

See also: [roadmap.md](roadmap.md) (the summary bullet this file expands
on), [allow-build-termination.md](../implementation/allow-build-termination.md),
[metadata-sources.md](metadata-sources.md),
[lock-file-cascade.md](../implementation/lock-file-cascade.md).

Split out of `roadmap.md` (2026-09-28) once this section grew past the
file-size guidance -- moved verbatim, no content changed.

- [x] **Build-and-read extraction dir removed on SIGTERM/SIGHUP/Ctrl-C
  for its whole lifetime** (hashing, AI-model scanning, `embed-wheel`
  batches), not only during the build. See
  [allow-build-termination.md](../implementation/allow-build-termination.md).
- [ ] **Optional safety net for SIGKILL** -- the guard above can't run
  under SIGKILL by design (see its own known limitations); sweep stale
  `pitloom-build-and-read-*`/`plb-*` temp dirs older than N hours at the
  next run as a lightweight backstop.
- [ ] **Windows: run the build in a Job Object** -- `taskkill /T` walks
  the tree by parent PID, so processes a finished build leaves running
  are unreachable once their parent exits; and a Ctrl-Break during
  wheel extraction leaves both build temp dirs behind (files still open
  when the handler removes them; each gets a `WARNING:`, seen on Windows
  CI in PR #226). A Job Object would kill the whole tree; the leftover
  dirs need the extraction's open files closed first. See
  [allow-build-termination.md](../implementation/allow-build-termination.md#limitations).
- [ ] **Accepted residual limits of build termination** -- revisit only if
  reported; listed in
  [allow-build-termination.md](../implementation/allow-build-termination.md#limitations).
- [ ] **`--allow-build` follow-ups from the PR #226 reviews** -- build-flag
  warning inconsistencies across surfaces, build-child isolation gaps,
  `EmbedFileCache` on worker threads, and the manual checks' blind spots.
  See [allow-build-followups.md](allow-build-followups.md).
- [ ] **PEP 517 `prepare_metadata_for_build_wheel`** (opt-in) -- call the build
  backend in a subprocess to resolve dynamic metadata (Git-tag versions,
  computed deps) that static parsing cannot handle.
  See [metadata-sources.md](metadata-sources.md).
- [x] **Setuptools wheel file discovery** -- resolves a setuptools
  project's file set from static config instead of Hatchling's
  `WheelBuilder`. See
  [setuptools-support.md](../implementation/setuptools-support.md) and
  [sbom-lifecycle-stages.md](../implementation/sbom-lifecycle-stages.md).
- [x] **`get_wheel_files()` option to skip Merkle root computation** --
  `embed-wheel`'s one caller now skips per-file hashing entirely. See
  [get-wheel-files-skip-merkle-root.md](../implementation/get-wheel-files-skip-merkle-root.md).
- [x] **In-tree `.egg-info`/`.dist-info` as a supplementary metadata
  source** -- an editable-install byproduct left next to
  `pyproject.toml` gap-fills undeclared fields; static source stays
  authoritative on conflict (recorded, never silently substituted).
  See [installed-dist-info-source.md](installed-dist-info-source.md).
- [x] **Unify `extract/project/installed.py`'s RFC 822 Core-Metadata
  parser with `extract/wheel.py`'s** -- closed (2026-09-15, PR #215):
  widened to all four sites with the same duplicated `Project-URL`
  -splitting shape, consolidated into one parametrized
  `extract/_core_metadata.py::parse_project_urls()`. See
  [installed-dist-info-source.md](installed-dist-info-source.md#relationship-to-extractwheelpys-parser).
- [ ] **Real installed `.dist-info` (site-packages) as a metadata
  source** -- the deferred, backend-agnostic phase: a user-supplied
  venv/site-packages path, cross-checked via `direct_url.json`.
  See ["Deferred: real installed dist-info (site-packages)"](installed-dist-info-source.md#deferred-real-installed-dist-info-site-packages).
- [x] **Split `extract/project/installed.py`** -- closed (2026-09-15,
  PR #215): discovery+parsing stayed in `installed.py` (now ~340 lines);
  reconciliation moved to the sibling `_installed_reconcile.py`, exactly
  the seam previously identified.
- [ ] **`resolve_project_with_lockfile()`'s peek/reread pays for
  installed-metadata discovery twice** (once per `read_project()` call)
  when the lock cascade is auto-detected. Already an accepted,
  documented cost; a fix needs care -- the peek's own read may be
  load-bearing for surfacing errors the quiet re-read wouldn't catch on
  its own, so any change here needs a closer look at that ordering
  before changing it, not a quick patch.
- [x] **CLI option `--no-use-lockfile`** -- opt-out flag (also
  `[tool.pitloom] use-lockfile = false`) disabling automatic lock-file
  discovery across every usage surface; on by default. Also fixed a
  related `loom enrich` doc-identity bug found along the way.
  See [lock-file-cascade.md](../implementation/lock-file-cascade.md#--no-use-lockfile-opt-out).
- [x] **Preserve lock file hashes in `--offline` mode** -- SHA-256 digests
  parsed from `pylock.toml`/`uv.lock`/`poetry.lock`/`pdm.lock`/`Pipfile.lock`
  now populate SPDX 3 `verifiedUsing`, taking priority over a PyPI JSON API
  lookup even online.
  See [lock-hash-preservation.md](../implementation/lock-hash-preservation.md).
- [ ] **SHA-512 / BSI TR-03183-2 `verifiedUsing`** -- no lock format or the
  PyPI JSON API carries a SHA-512 digest; producing one means downloading the
  artifact and hashing it, a heavier feature than the SHA-256 lock-hash
  preservation above. `Element.verifiedUsing`'s 0..* cardinality means this
  can append to the same list without restructuring it.
  See [lock-hash-preservation.md](../implementation/lock-hash-preservation.md#scope).
- [ ] **Transitive dependency resolution and lock-hash support in Hatchling build hook** --
  gather transitive dependencies down the n-level dependency tree during build-stage
  hook execution to resolve dependencies and obtain integrity hashes, populating
  `verifiedUsing` in embedded build SBOMs without relying on source-stage lock files.
- [ ] **`pixi.lock` and `conda-lock.yml` as resolved-dependency sources** --
  the two lock-file phases the current cascade doesn't cover, for
  AI/ML stacks mixing PyPI wheels with Conda/CUDA binaries. See
  [lock-files.md](lock-files.md)'s Phase 2 -- its priority table and
  shipped-status notes are current, but its Pydantic/CycloneDX sketch
  predates and doesn't match this codebase's actual shape; follow
  `extract/lock/poetry.py` and `assemble/spdx3/deps.py`'s established
  pattern instead, as the doc itself now says.
