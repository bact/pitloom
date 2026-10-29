---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# A stub model, a cut name, an escaped control: read the cause first

See also: `../SKILL.md` (step 3, which holds the rule: tell the user the cause
before inferring from prose), `deterministic-pass.md` (the stub case in step 2)
and `minimum-elements.md` (G7 model elements for a stub).

## Is the `ai_AIPackage` a stub?

An `ai_AIPackage` is a stub (Pitloom did not read the file) when it has no
`ai_*` property and no `comment` entry `Source: <the model file> | Field: ...`
(its `name` is then the file's stem, `Method: file_name_stem`). A read model
has such entries. A `comment` citing the README (`Source: README.md | Method:
yaml_frontmatter`, from `--enrich`) does not make it read.

The base run's stderr says why:

- `required library not installed` -- install `pitloom[ai]` and regenerate.
- `failed to extract metadata` -- the file has a model's header but could not be
  parsed (truncated or corrupt): check the file.
- `header is not <fmt>; not listed as an AI model` or `Git LFS pointer, content
  not read ... [lfs-pointer]` -- the file is no model and has no
  `ai_AIPackage`; relay Pitloom's advice (a code's advice is in
  `messages.md`).
- On a wheel base, the gate `INFO:` naming `--trust-wheel-model`, `...
  max-model-extract-bytes cap; metadata not read`, or `... per-wheel
  model-scan budget cap; ...` -- tell the user; never add the flag or raise the
  cap yourself (flag or key).
- Any other `...; metadata not read` -- a fixed bound.
- `... identity unknown` is the wheel's own name/version, not a model: see
  `sbom-generate`.

Fields the file itself would give (hyperparameters, inputs, outputs, an author,
a parameter count) are better read than inferred: tell the user the cause
before inferring them from prose.

## A Pitloom cap or escape, not a gap

A name ending `...~<hex>`, a CRFsuite/fastText model with `num_labels` but no
`labels` or description, or `\uXXXX` in a name or description is a Pitloom cap
or escape, not a gap to fill from prose: see `sbom-generate`'s known
limitations. Never write the cut name, a dropped label or an unescaped control
back into a fragment.
