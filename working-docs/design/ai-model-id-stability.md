---
Created: 2026-08-15
Last-Modified: 2026-08-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model id stability

See also: [roadmap.md](roadmap.md) (Near-term -- "AI model id
stability", follow-up to [PR #178](https://github.com/bact/pitloom/pull/178)).

Open design question, not a committed plan.

## Deterministic same-model identification for auto-harvest

`ai_AIPackage` elements are currently excluded from the Loom ID
registry's auto-harvest (`_sync_registry` in
`src/pitloom/assemble/_generators.py`) because `ai_model.name` is
extraction-dependent (varies with whether `ai` extras are installed),
so a name-keyed harvest would write entries that never match
`_lookup_ai_model_entity`'s lookup candidates. The only currently-stable
path is the extras-free, filename-stem-keyed `pitloom ids generate`.
Revisit whether auto-harvest can be safely extended once there's a
reliable way to say "this is the same model I saw last time":

- **Content hash (SHA-256 of the raw model file bytes)** is the
  mechanism already used for regular files (`register_file`/
  `lookup_file`) and would be directly reusable -- `IdRegistry.generate()`
  already computes this hash for every file, AI models included,
  before separately doing the stem-based registration. The blocker is
  that `_lookup_ai_model_entity()` never tries a hash-based lookup
  against `registry.files`, only name/path/stem candidates against
  `registry.entities`; and the harvest side would need the model's
  hash reachable from the `ai_AIPackage` element at harvest time, not
  just on a separately-linked `software_File`.
- **Caveat**: content hash is strictly *narrower* than "same model" for
  AI models, unlike source files where any byte change legitimately
  means "different provenance." A model re-exported, re-quantized, or
  re-saved with a different serialization -- or retrained
  non-deterministically from the same recipe -- changes every byte
  without changing what a person would call "the same model."
  Content-hash matching would under-match (mint a new id) in exactly
  the cases stability matters most. Source files don't have this
  problem; AI model files might.
- **"Machine ID" scoping idea**: record a randomly-generated (not
  identifying) machine tag in `loom-ids.json` itself, so the registry
  can distinguish "these runs are from the same working environment
  across time" from "these came from different machines/CI runners,"
  without claiming any actual machine identity. This addresses a
  different axis than the matching criterion above -- how much a match
  should be *trusted* -- rather than what counts as a match. Loose
  heuristic matching (e.g. same relative path, ignore content) might be
  acceptable within one developer's local iteration loop but unsafe
  once a registry is shared, committed, or consulted from CI. Not yet
  clear whether this is needed at all once the content-hash caveat
  above is settled, or how the two ideas would interact.

No implementation direction chosen yet -- open design question, not a
committed plan.
