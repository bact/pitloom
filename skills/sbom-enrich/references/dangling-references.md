---
Created: 2026-09-29
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Troubleshooting: dangling references

See also: `../SKILL.md` ("Troubleshooting: dangling references", which
holds the rule: regenerate the base SBOM, never retry the same merge, never
create an undeclared ID registry) and `deterministic-pass.md`.

Why each cause makes the ids miss, in the order to check:

- **A Pitloom upgrade** changed file discovery. Ids are content-addressed
  from the resolved file set (`doc_uuid` includes the Merkle root of the
  file list), so a more accurate list from unchanged source gives new ids.
- **A registry mismatch:** declared on one run but not the other, or a
  different file in each. Base run and `loom enrich` must resolve the same
  registry; without `--project-dir`, `loom enrich` reads no project
  config, so pass the base run's `--id-registry`/`--config`.
- **`--project-dir` omitted** for a project-level base (`../SKILL.md`,
  step 2; why: `deterministic-pass.md`).
- **A flag mismatch:** `--config` or `--use-lockfile`/`--no-use-lockfile`
  differs between the base run and `loom enrich`.
- **A base built with `--allow-build`** (`../SKILL.md`, step 2; why:
  `deterministic-pass.md`).
- **One dependency name held twice** (a dependency at two versions): a run
  never writes it to the registry, so its id can move with the source. If
  the user declared a registry, pin the first holder with `loom id generate
  <PATH> -e NAME:software_Package -o <declared-registry>`, then write the
  fragment against that id. Only one holder can be pinned, so every later
  run prints an expected `WARNING: ID registry: ... registered for both
  ...` for the other. If no registry is declared, create none and tell the
  user; see `sbom-generate`'s "Pinning element ids" and its
  `references/id-registry.md` (sibling skill; on GitHub:
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/id-registry.md>).
