---
Created: 2026-09-02
Last-Modified: 2026-09-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SARIF output

See also: [roadmap.md](roadmap.md) (Adoption surfaces -- "SARIF
output").

Replaces an earlier `::warning::`/`::error::` GitHub Actions
workflow-command annotation idea. Emit a SARIF file as a build
artifact, uploaded via a separate `github/codeql-action/upload-sarif`
step. Sidesteps the streaming/race problem that stalled the
workflow-command approach entirely: SARIF is written synchronously
once `loom` finishes, then uploaded as its own step -- no `tee`/
process-substitution race to prove free of. Gets PR "Files changed"
inline annotations and a GitHub Security-tab view for free, no custom
UI work.

Not an SBOM format -- SARIF is a diagnostics/findings interchange
format, unrelated to the CycloneDX assembler item (roadmap
Medium-term); the two don't overlap or compete.

## Findings sources to map, once each exists

- Every `WARNING:`/`ERROR:` a `loom` run emits today (e.g.
  artifact-metadata truncation, see
  [metadata-provenance.md](../implementation/provenance/metadata-provenance.md))
  -- already done for AI-agent Skills, see
  [agent-skill.md](../implementation/agent-skill.md#relaying-warningerror-stderr-to-the-user).
- OSV.dev vulnerability lookup (roadmap Near-term / Metadata quality,
  once built -- see [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md))
  -- one SARIF `result` per CVE (`ruleId=CVE-xxxx`, `level=`severity,
  location = the dependency's declaration line in `pyproject.toml`).
- Declared-vs-detected license conflicts (already shipped, see
  [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md),
  [PR #121](https://github.com/bact/pitloom/pull/121)) -- currently a
  warning message only, would become an inline PR annotation on the
  license line.
