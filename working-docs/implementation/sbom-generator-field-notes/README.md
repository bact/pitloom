---
Created: 2026-10-02
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes for building an SBOM generator

See also:
[ai-model-scan-security-lessons.md](../ai-model-scan-security-lessons.md)
(the AI-model half of the same paper notes: hostile model files, archive
bombs, Git LFS pointers),
[recurring-bug-patterns.md](../recurring-bug-patterns.md) and
[recurring-bug-patterns-platform.md](../recurring-bug-patterns-platform.md)
(the full war stories behind many items here).

Small, concrete, non-obvious details for anyone starting an SBOM
generator, in any language or ecosystem. The evidence is Pitloom's: Python
packages (sdists, wheels, Hatchling and other PEP 517 backends, five
lock-file formats plus pinned `requirements.txt`), SPDX 3 JSON-LD output. Each
item gives the exact format, byte value, version or measured number; the PR
that found or fixed it; and one "Do:" rule. Items the AI-model notes already
cover are linked, not repeated. Every claim was checked against the current
code, a repository fixture, a live interpreter or the cited PR's own record on
the day it was added (2026-10-02 to 2026-10-30).

## Files

- [identity-and-archives.md](identity-and-archives.md): package
  identity; ZIP and tar realities; registry ids and file keys; what an
  SBOM counts as inside the package.
- [id-registry-v3-lessons.md](id-registry-v3-lessons.md): a typed,
  content-gated id registry; Merkle leaves that bind the path; deferring
  work to run exit; harvest churn; what a fresh reviewer found after
  the tests passed.
- [path-keys-lessons.md](path-keys-lessons.md): path key versus name key for
  an AI-BOM identity; one helper per cross-cutting choice; a loose alias
  rule narrowed after review; a gate that meets a pin made before the data
  exists; an `INFO:` for every deviation.
- [determinism-and-parsing.md](determinism-and-parsing.md): same input,
  same bytes; parsing traps; lock-file and environment sources.
- [platform-and-toolchain.md](platform-and-toolchain.md): OS and
  Python-version traps; build tools and CI; the first test-harness items.
- [testing-traps.md](testing-traps.md): ways a test passes, fails or
  floods the log for the wrong reason.
- [spdx-modelling.md](spdx-modelling.md): SPDX 3 identity, integrity,
  claims, profiles, completeness and licences; dependency scope for extras;
  author strings.
- [remote-metadata.md](remote-metadata.md): what core metadata and
  PyPI-style sources actually contain.
- [model-file-metadata.md](model-file-metadata.md): what AI model files
  carry and what their fields mean (ONNX `domain`, exporter-default names,
  packed versions, standard keys, parameter-count shapes).
- [messages-and-surfaces.md](messages-and-surfaces.md): absent vs
  failed; one message per event; surfaces that drift apart.
- [datasets-and-reproducible-results.md](datasets-and-reproducible-results.md):
  one dataset under several names and capture routes; who made the SBOM versus
  who supplies the component; conformance counts that depend on the machine;
  what a CI matrix found; review rounds of PR #311 to #315.
- [remote-git-sources.md](remote-git-sources.md): a Git URL on any forge:
  GitLab's 301, page-URL syntax per platform, ref versus folder, measured
  platforms; git-lfs, forged log lines and symlinks from an untrusted
  repository; where the logic should live; rejections said once; test traps.
- [evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md):
  caps bound reading, never reporting; five evidence levels; recording why a
  value is missing; a record count in a bytes property.
- [provenance-injection-and-message-contract.md](provenance-injection-and-message-contract.md):
  a `|` in a name forging a provenance segment; stderr codes as the contract
  with the AI skills; what moving skill text to references loses.
- [message-catalogue-decisions.md](message-catalogue-decisions.md): the
  catalogue's taxonomy repaired at three entries (causes only, `/` for
  variants); effect and actor; forged codes and the accepted residual; the
  exception carrier; the ratchet; skills as consumers.
- [open-research-questions.md](open-research-questions.md): where the
  formats cannot say what a generator needs (a string that may be one value
  or a list, author kinds, extras and scope, backend disagreements,
  hostile input, name or path keys for ids); each item says what was
  measured, chosen and left open.
- [process-lessons.md](process-lessons.md): how the review rounds and
  test tiers were run; the merge bar; proving a test compaction.

## Five rules that cover most items

1. Compare identifiers the way their ecosystem does (PEP 503 names,
   PEP 440 versions), never as raw strings.
2. Read the raw bytes the archive or file actually holds, not the value a
   library has already normalised for the current OS.
3. Every collection that reaches the output, or picks one candidate, needs
   an explicit stable order that you own.
4. Treat every external file and tool output as untrusted data: check the
   type of each value, not only the presence of each key.
5. Absent data is silent; a failed read is one message, worded once, on
   every surface.
