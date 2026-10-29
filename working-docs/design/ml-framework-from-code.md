---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# ML framework and `transformers` use from the code

See also: [roadmap.md](roadmap.md#backlog-designed-not-scheduled),
[github-issues-triage.md](github-issues-triage.md),
[model-metadata-extraction.md](model-metadata-extraction.md).

Status: needs a design note. Nothing here is decided or built.

## Question

Can Pitloom infer which ML framework a project uses, and which Hub model it
loads, from the code instead of from a model file on disk?

- Infer the framework from the dependencies or the imports.
- Infer a Hub model from `from_pretrained("org/name")`.

Today `--scan-model-usage` matches model file names only (see
`extract/scanner.py`); a `from_pretrained()` call in code is not read.

## Issues

- [#66](https://github.com/bact/pitloom/issues/66): `transformers` use.
- [#68](https://github.com/bact/pitloom/issues/68): ML framework detection;
  only a Hub card's `library_name` is read today.
- [#65](https://github.com/bact/pitloom/issues/65): testing with Qwen;
  `loom project` on the Qwen repositories finds no Python project, so the rest
  is code inference.

## To settle in the note

- What counts as evidence: an import, a dependency, a literal model name in a
  call. A name built at run time is not evidence.
- What the SBOM records for a use found in code, and how it differs from a
  model file Pitloom read (see
  [evidence-levels.md](evidence-levels.md)).
- Whether it belongs in core or in the `sbom-enrich` Skill (see the scope split
  in [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md)).
