---
Created: 2026-10-02
Last-Modified: 2026-10-08
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
the day it was added (2026-10-02 to 2026-10-08).

## Files

- [identity-and-archives.md](identity-and-archives.md): package
  identity; ZIP and tar realities; registry ids and file keys; what an
  SBOM counts as inside the package.
- [determinism-and-parsing.md](determinism-and-parsing.md): same input,
  same bytes; parsing traps; lock-file and environment sources.
- [platform-and-toolchain.md](platform-and-toolchain.md): OS and
  Python-version traps; build tools and CI; the first test-harness items.
- [testing-traps.md](testing-traps.md): ways a test passes, fails or
  floods the log for the wrong reason.
- [spdx-modelling.md](spdx-modelling.md): SPDX 3 identity, integrity,
  claims, profiles, completeness and licences.
- [remote-metadata.md](remote-metadata.md): what core metadata and
  PyPI-style sources actually contain.
- [model-file-metadata.md](model-file-metadata.md): what AI model files
  carry and what their fields mean (ONNX `domain`, exporter-default names,
  packed versions, standard keys).
- [messages-and-surfaces.md](messages-and-surfaces.md): absent vs
  failed; one message per event; surfaces that drift apart.
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
