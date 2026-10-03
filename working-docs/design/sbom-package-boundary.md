---
Created: 2026-10-03
Last-Modified: 2026-10-03
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# What an SBOM counts as inside the package, and package-format independence

Status: open question, nothing decided. Raised during #269 / PR #271 (stale
hashes in embedded SBOMs), which settled the wheel case and left the general
question open.

See also: [format-neutral-representation.md](format-neutral-representation.md)
(the same idea on the output side: SBOM spec independent of the internal
model), [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md),
[wheel-embedding.md](../implementation/wheel-embedding.md) (what #271
decided for wheels).

## The question

An SBOM describes "the project that is about to be packaged", not the package
container. Two things follow that are not yet answered:

1. **Where is the boundary?** Which files count as inside the package (listed,
   hashed into the package root) and which are outside (container metadata)?
2. **Can the SBOM be independent of the package spec?** Today the answer to (1)
   uses wheel knowledge. Another format (sdist, conda, deb, OCI layer) has a
   different layout, so a rule written for wheels does not carry over.

## What #271 decided for wheels

The measured result on every surface, as a matrix, is in
[wheel-embedding.md](../implementation/wheel-embedding.md) ("Behaviour matrix").

- Listed: the payload, i.e. every wheel member except the wheel's own
  `.dist-info`. Another `*.dist-info` vendored under a package is payload.
- Not listed: the own `.dist-info` (`METADATA`, `WHEEL`, `RECORD`,
  `licenses/`, `sboms/`, signatures), including links to it (no license-file
  elements, no `hasDeclaredLicense` on a license file).
- Pitloom may still write into the container (the embedded SBOM under
  `sboms/`, `RECORD`): that is packaging enrichment, separate from SBOM
  content.
- The package root is a Merkle root over the payload, and what it covers follows
  the SBOM type (Source/hook: the pre-build source walk; Analyzed: the built
  wheel).

## Where the wheel spec still leaks in

- **The exclusion rule itself** needs wheel knowledge: which top-level
  directory is "own" (`resolve_own_dist_info`: PEP 503 names, PEP 440
  versions), and that everything under it is container metadata.
- **`.data/`** (PEP 427: `scripts/`, `data/`, `headers/` moved to their
  destination on install) is listed as payload under its wheel path
  (`demo-1.0.data/data/share/demo/d.txt`), not its install destination
  (`share/demo/d.txt`). The name carries the wheel layout, and a Source SBOM of
  the same project names that file by its source path.
- **Names** are `distribution_path`, relative to the archive: for a `src/`
  layout, the Source and wheel SBOMs name one file differently (the existing
  `physical_path` / `distribution_path` split).
- **The package root** depends on all of the above, so a recompute recipe has to
  say how to find the own `.dist-info` and how names are normalised.
- **Build-added payload** (generated or repaired files, `.data/` content the
  source walk cannot see) exists only in the artifact. Is it project content?
  Today it is, for Analyzed SBOMs.

## Directions to weigh (none chosen)

- **A per-format adapter** that turns an artifact into a format-neutral pair:
  payload files with neutral paths, and container metadata kept aside. Core
  code (SBOM assembly, the root) sees only the neutral side; wheel knowledge
  lives in the wheel adapter, sdist's in another.
- **Neutral path naming**: the install destination (or the project-relative
  source path) instead of the archive path, so one file has one name across
  Source, Build and Analyzed SBOMs. Costs: needs a mapping per format (`.data`
  schemes, `src/` layout) and changes existing ids/paths in registries.
- **The root over neutral paths and digests only**, so it is comparable across
  formats and independent of container layout.
- **Container metadata as an optional, separate description** (not in the SBOM
  graph, or in a clearly typed element) if a consumer wants it, instead of
  dropping it silently.

## Open questions

- Is a file the build adds to the artifact "the project"? Both answers are
  defensible (Source vs Analyzed already disagree).
- Should Source, Build and Analyzed SBOMs of one project share file names and a
  root where their contents agree?
- How far to go before a second package format exists to test the abstraction
  against (sdist is the nearest candidate)?
