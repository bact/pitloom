---
Created: 2026-09-10
Last-Modified: 2026-09-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# JAX / Orbax model support

See [model-metadata-extraction.md](model-metadata-extraction.md) for the
full planned-format table this splits out of, and
[implementation/model-metadata-extraction.md](../implementation/model-metadata-extraction.md)
for the shipped-extractor pattern this format follows
(`read_<format>(model_path: Path) -> AiModelMetadata`, registered in
`pitloom.extract.ai_model.REGISTRY`).

## Why this needs its own file

Unlike every other planned/shipped format, an Orbax checkpoint is a
**directory tree**, not a single file -- detection, fixture shape, and the
`AiModelFormat`/registry dispatch all need a dedicated branch rather than
reusing the existing magic-bytes/extension path. The findings below come
from installing `orbax-checkpoint` and inspecting real output (not from
reading the docs alone -- see "Doc-vs-reality gaps" below for where the
public docs page turned out to be wrong for the API version that's actually
installable and actually used).

## Verified environment

- `jax==0.4.38`, `jaxlib==0.4.38`, `orbax-checkpoint==0.11.5`, Python 3.11.
- This is the newest jax/jaxlib pair installable on Intel macOS (x86_64) --
  `jaxlib` has shipped no x86_64 macOS wheels since jax 0.4.38. Any CI
  matrix or contributor on Intel Mac is capped at this combination; Apple
  Silicon / Linux / Windows can go newer.
- The newer `orbax.checkpoint.v1` API (`ocp.metadata()`, the
  `orbax.checkpoint`-marker-file format described on
  <https://orbax.readthedocs.io/en/latest/guides/checkpoint/v1/checkpoint_format.html>)
  requires `jax>=0.6`, which has no x86_64 macOS wheel and could not be
  installed or verified here. It also isn't what real-world JAX code uses
  yet (Flax examples, CleanRL, Octo all target the stable
  `CheckpointManager` API) -- **this design targets the stable/v0 API**,
  not v1.
- **Apple Silicon (M4) note:** the v1-API gap above is a platform limit of
  this Intel Mac specifically, not a general unavailability -- jaxlib does
  ship current wheels for arm64 macOS. Continuing this investigation on an
  M4 machine would let the v1-API claims from the docs page get the same
  install-and-verify treatment the v0 claims got here (real
  `orbax.checkpoint` marker file? real `commit_success.txt`? does
  `ocp.metadata()` actually behave as documented?), rather than staying
  doc-only. That's a distinct thing from open question 1 below (the
  `item_metadata` warning is a Python-API usage detail, not a platform one
  -- an M4 won't resolve it any differently than more careful test code
  would here).

## On-disk structure (stable `CheckpointManager` API, verified)

```text
<checkpoint_root>/
  <step>/                          # e.g. "0" -- integer step number
    _CHECKPOINT_METADATA           # JSON, always present
    metrics/                       # only present if metrics were saved (see below)
      metrics                      # JSON: the dict passed to .save(metrics=...)
    <item_name>/                   # e.g. "default" -- one per saved item/pytree
      _METADATA                    # JSON: per-leaf shape/dtype/sharding tree
      _sharding                    # binary sharding info
      manifest.ocdbt                # TensorStore/OCDBT manifest
      d/                            # OCDBT-encoded array data
      ocdbt.process_0/              # per-process data (multi-host runs)
```

No file or marker exists at `<checkpoint_root>/` itself -- the identifying
signal is one level down, per step.

### Detection marker

A directory is a stable-API Orbax checkpoint step if it contains
`_CHECKPOINT_METADATA` and that file parses as JSON with an `item_handlers`
key. This is the "source needs its own identifying marker" check (per the
project's recurring-bug notes on cascades/format detection) -- don't
classify a directory as Orbax just because it has numeric-looking
subdirectories.

`pitloom.extract.ai_model.detect_ai_model_format()` currently only branches
on `model_path.is_file()` (magic bytes) and falls back to extension lookup;
it needs a new `is_dir()` branch that looks for this marker, since
`AiModelFormat.JAX` has no extension or magic bytes to register.

### Doc-vs-reality gaps (do not repeat these claims uncritically)

The public v1-API docs page lists `_CHECKPOINT_METADATA` keys as `metrics`,
`performance_metrics`, `init_timestamp_nsecs`, `commit_timestamp_nsecs`,
`custom_metadata`. Verified against real 0.11.5 output, for the **stable**
API:

- The key is `"custom"`, not `"custom_metadata"`, at the raw JSON level (the
  `StepMetadata` Python object exposes it as `.custom_metadata` -- the
  attribute name and the JSON key differ).
- `"metrics"` in `_CHECKPOINT_METADATA` stays `{}` even when a real
  `metrics=` dict is passed to `.save()` -- it is **silently dropped**
  unless `CheckpointManagerOptions(best_fn=..., best_mode=...)` is
  configured (best-checkpoint tracking enabled). This is a real
  "no silent deviations"-shaped gap in Orbax itself, not in Pitloom, but it
  means an extractor must not assume `_CHECKPOINT_METADATA["metrics"]` is
  ever populated in practice.
- When tracking *is* enabled, the actual metrics values are **not** in
  `_CHECKPOINT_METADATA` at all -- they land in a sibling file,
  `<step>/metrics/metrics` (JSON), readable via
  `CheckpointManager(dir, options=...).metrics(step)`.
- `"performance_metrics"` is **not** model performance (accuracy/loss/etc).
  It deserializes to Orbax's own `SaveStepStatistics` dataclass -- timing of
  the checkpoint *save I/O operation itself* (wait times, blocking
  duration). Not useful for G7's model-performance elements; do not map it
  there.

Conclusion: verify every claim in this file (and any future revision of it)
against a real installed `orbax-checkpoint`, not against the hosted docs --
the docs describe the newer v1 API, which is not what this design targets
and is not installable on every supported platform anyway.

## Metadata-only read API

`orbax.checkpoint.CheckpointManager(directory, options=...).metadata(step)`
returns a `StepMetadata` dataclass without restoring array data:

```python
StepMetadata(
    item_handlers={...},
    item_metadata=None,          # populated by item_metadata(step) instead
    metrics={},                  # see caveats above
    performance_metrics=SaveStepStatistics(...),  # save-I/O timing, not model perf
    init_timestamp_nsecs=...,
    commit_timestamp_nsecs=...,
    custom_metadata={...},       # the real extension point, see below
)
```

Per-array shape/dtype/sharding comes from
`CheckpointManager.item_metadata(step)`, a `TreeMetadata` whose `.tree` maps
pytree paths (e.g. `('params', 'dense1', 'kernel')`) to `ArrayMetadata`
(`shape`, `dtype`, `sharding`). Neither call touches tensor bytes -- matches
the project's "never load full tensor data into memory" rule, same pattern
as the Safetensors/NumPy extractors.

`item_metadata(step)` logged a `WARNING:absl` about an unprovided
`CheckpointHandlerRegistry` in ad-hoc testing here; needs a clean
reproduction with a properly configured registry before the extractor
relies on it, to confirm this is cosmetic and not a real restore attempt.

## Field mapping to `AiModelMetadata` / G7

| Signal | Source | Reliability |
| :--- | :--- | :--- |
| Parameter count | Sum of element counts across `item_metadata(step).tree` leaf shapes | Reliable -- always derivable from any valid checkpoint |
| Per-array shape/dtype | Same, per leaf -> `AiModelMetadata.inputs` | Reliable |
| Framework | Hardcoded `"jax"` / `"orbax"` | Reliable |
| Model name / architecture / version | `StepMetadata.custom_metadata`, *iff* the training code populated it via `.save(custom_metadata=...)` | Not guaranteed -- same "open properties bag" situation as GGUF `general.*` / Safetensors `__metadata__`, not a structural guarantee |
| Performance metrics (loss/accuracy/etc, G7 "Model properties") | `CheckpointManager.metrics(step)` / `<step>/metrics/metrics`, *iff* `best_fn` tracking was enabled **and** metrics were passed at save time | Double-conditional -- likely absent in most real checkpoints; when present, this is a genuine, currently-unique-among-extractors way to close a G7 gap flagged elsewhere as **not automatable** (see `skills/sbom-enrich/references/minimum-elements.md`'s "Operational performance KPIs" row) |
| Checkpoint init/commit timestamps | `_CHECKPOINT_METADATA.init_timestamp_nsecs`/`commit_timestamp_nsecs` | Reliable, but informational provenance only -- must not feed `CreationInfo.created` (the SBOM's own build timestamp) or any other "when was this generated" field; these describe the checkpoint's own history, not the SBOM's |

No new SPDX3 `ExternalRef`/`ExternalIdentifier` vocabulary term is needed
(resolved in conversation, not yet written up elsewhere): the codebase's
existing `other` + explanatory `comment` convention
(`src/pitloom/assemble/spdx3/_ai_package.py`'s DOI/arXiv handling) already
covers "no vocab term fits", and `format_version`/`framework`/
`framework_version` are pre-existing unmapped-to-SPDX3 gaps tracked in
`working-docs/design/sbom-enrichment.md`, not something JAX-specific.

## Fixture plan

Every existing fixture under `tests/fixtures/aimodels/` is a single file
under 6 MB, mostly synthetic ("Generated for testing purposes", CC0-1.0) --
see `tests/fixtures/aimodels/README.md`. An Orbax checkpoint is inherently a
small directory tree of several tiny files, which is a first for this
fixture set structurally, though not in spirit (still small and synthetic).

Plan: generate a minimal synthetic checkpoint via the real
`CheckpointManager` API (a couple of small arrays, `custom_metadata` set so
the "populated" extraction path has a fixture, plus a second fixture
*without* `custom_metadata`/metrics set to exercise the "absent, not just
empty" path -- per the project's recurring empty-vs-absent bug pattern).
Save script becomes a documented, reproducible generator (same spirit as
the numpy/keras fixture generation scripts), not a hand-crafted JSON blob,
so it stays honest about real Orbax output shape.

Flax's MNIST example, CleanRL's JAX/Flax scripts, and Octo (all suggested
as real-world references) are good **manual verification targets** once the
extractor exists -- run it against real output from each, don't vendor them
as committed fixtures (too large / real-world instability risk for a
committed test fixture, per the project's existing preference for small
synthetic fixtures over vendored real ones outside the Hub-sourced
ONNX/Safetensors/GGUF fixtures that already have a stable pinned source).

## Open questions before implementation

Not platform-blocked -- answerable on any machine with careful test code:

1. `item_metadata(step)`'s `WARNING:absl` about `CheckpointHandlerRegistry`
   -- confirm cosmetic, not a real behavior change needed.
2. Multi-item checkpoints (e.g. separate `params`/`opt_state` items saved
   under one step) -- confirm the extractor sums parameter counts across
   all items' trees, not just a hardcoded `"default"` item name.
3. CLI path handling -- `loom model <path>` needs to accept a directory
   argument; confirm current arg validation doesn't reject non-file paths
   before this reaches the extractor.
4. Sidecar YAML config file (mentioned in the original roadmap entry) --
   no fixed filename convention found in Orbax itself during this
   investigation; likely out of scope for a first cut, revisit if a real
   project's convention turns up during the Flax/CleanRL verification pass.

Blocked on this Intel Mac, open pending an Apple Silicon (or Linux) machine
with a current jaxlib wheel:

5. Whether the v1-API docs page's claims (`orbax.checkpoint` marker file,
   `commit_success.txt`, `ocp.metadata()`, the `_CHECKPOINT_METADATA` key
   set it lists) hold up under the same install-and-verify treatment the v0
   claims got here. Matters even though this design targets v0: if v1
   becomes the de facto API before this ships, the detection-marker section
   above would need a second branch, not a rewrite.
