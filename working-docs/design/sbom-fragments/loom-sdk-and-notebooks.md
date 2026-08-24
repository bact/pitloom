---
Created: 2026-08-25
Last-Modified: 2026-08-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM fragments: `loom` SDK and notebook recording

See also [README.md](README.md) (index),
[fragment-merge-design.md](fragment-merge-design.md) (start here for the
core fragment mechanism),
[extractor-integrations.md](extractor-integrations.md),
[roadmap-and-resources.md](roadmap-and-resources.md).

Split from this directory's former single `sbom-fragments.md`
(2026-08-25) -- the `pitloom.loom` tracking SDK redesign (MLflow-style
`log_*` API, persistent sessions) and Jupyter/notebook recording mode.
All content here is unbuilt design, corresponding to roadmap Phase 2 in
[roadmap-and-resources.md](roadmap-and-resources.md).

### 3. `loom.py` SDK: sparse API surface

The current `Run` context manager supports only `set_model` and
`add_dataset`. This is far less expressive than ML tracking SDKs that
practitioners already use daily. Key missing capabilities:

- No equivalent of `log_param` / `log_metric` / `log_tag` / `log_artifact`.
- No incremental / accumulative recording suitable for notebooks
  (running a cell multiple times should append, not overwrite).
- No Jupyter integration (IPython magic commands, cell-level provenance).
- No serialisation of individual dataset elements with schema, provenance,
  or curation notes.
- No model evaluation / scoring records.
- Error is raised if `loom.*` functions are called outside a `Run` block;
  notebook workflows need a more lenient persistent-session mode.

## Enhanced `loom.py` SDK

### Design goals

The redesigned SDK should feel familiar to practitioners who already use
MLflow, W&B, or Weave -- using the same vocabulary where possible -- while
emitting SPDX 3 elements rather than metrics records.

The API adopts the MLflow `log_*` naming convention because it is widely
understood and directly maps to the double-instrumentation problem described
in `working-docs/design/mlflow-extractor.md`.

### Proposed public API

```python
from pitloom import loom

# --- Context-managed fragment recording (existing, enhanced) ---
with loom.run("fragments/bert-v3.spdx3.json") as run:
    run.set_model("my-bert", model_type="transformer")

    # MLflow-compatible logging functions
    run.log_param("learning_rate", 3e-4)
    run.log_param("batch_size", 32)
    run.log_metric("accuracy", 0.91)
    run.log_metric("f1_score", 0.88)
    run.log_tag("domain", "natural_language_processing")
    run.log_tag(stav.INFO_TRAINING, "Fine-tuned on FLORES-200")

    # Dataset documentation
    ds = run.add_dataset("flores-200", dataset_type="text")
    ds.set_size(rows=5_000_000)
    ds.set_license("CC-BY-4.0")
    ds.set_source_url("https://huggingface.co/datasets/facebook/flores")
    ds.set_preprocessing("tokenized, lowercased, de-duplicated")
    ds.log_tag("language_count", "200")

    # Evaluation results (maps to SPDX Annotation)
    run.log_evaluation("flores-dev", {"accuracy": 0.91, "bleu": 42.3})

# --- Persistent session mode (for notebooks) ---
loom.start_session("fragments/notebook-run.spdx3.json")

# ... cell 1 ...
loom.set_model("incremental-model", model_type="classifier")
loom.log_param("epochs", 10)

# ... cell 2 (appends to same session) ...
loom.log_metric("accuracy", 0.85)
loom.add_dataset("my-dataset", dataset_type="tabular")

# ... cell N (explicit save / auto-saved on kernel shutdown) ...
loom.save_session()
loom.end_session()
```

### Accumulation mode for notebooks

The persistent session is backed by an `_ActiveSession` object (distinct
from `_ActiveRun`) that persists in module-level state and writes a
checkpoint file to disk on each `loom.save_session()` call. If the kernel
restarts, `loom.resume_session("fragments/notebook-run.spdx3.json")` reads
the last checkpoint and continues accumulating.

Key difference from `Run`: a session does **not** discard partial output
on exception; it preserves whatever has been recorded up to the crash.

### IPython magic integration

```python
# In a Jupyter notebook cell:
%load_ext pitloom.loom.magic

%%pitloom_record model=my-bert role=ai output=fragments/cell3.spdx3.json
learning_rate = 3e-4
epochs = 5
# Cell body executed normally; pitloom captures locals() as log_param entries
# and writes a fragment on cell completion.
```

The `%%pitloom_record` cell magic:

- Captures all assigned scalar variables as `log_param` entries.
- Records the cell source code as a `comment` on the fragment.
- Records the notebook file name and cell index as provenance.
- On error, writes a partial fragment tagged `status=error`.

---

### 6. No Jupyter / notebook recording mode

Interactive notebooks build up knowledge about a dataset or model
incrementally. There is no mechanism to accumulate BOM records across
multiple notebook cells or sessions, nor to attach cell-level provenance
to SPDX elements. Existing research tools such as ProvBook and MLProvLab
demonstrate demand for this capability, but use RDF-based ontologies
(REPRODUCE-ME, PROV-O, P-Plan) rather than SPDX, leaving a gap that
Pitloom can fill.

---

## Jupyter / notebook integration

### Notebook provenance challenge

Notebooks execute cells in user-defined order, re-execute cells, and may
run for hours. The SBOM recording challenge is that:

- There is no single "entry point" or "build step" to hook into.
- Each "training run" may span multiple cells with intermediate checkpoints.
- The user wants to accumulate BOM notes incrementally, correcting or
  supplementing earlier cells as understanding evolves.
- The final fragment should reflect the *intention* of the complete session,
  not just the last state of every variable.

### Approach: persistent session with manual checkpoints

The `loom.start_session()` / `loom.end_session()` API (described under the
SDK redesign above) is the primary mechanism. The session writes a checkpoint
JSON on every `loom.save_session()` call; the IPython magic `%%pitloom_record`
triggers an implicit checkpoint.

Additionally, Pitloom can read existing provenance captured by ProvBook
(which stores REPRODUCE-ME RDF in notebook cell metadata) and translate it
to SPDX elements, bridging the RDF-based provenance research community with
the SBOM community.

### Auto-capture of the notebook environment

When a Pitloom session is active inside a Jupyter kernel, Pitloom can
optionally capture:

- The list of installed packages at session start (via `importlib.metadata`).
- The Python version and platform.
- The notebook file name and path (via `ipykernel` / `IPython.display`).
- The kernel start time.

These are emitted as a `build_BuildEnvironment` element (SPDX 3 Build
profile) and a `software_Sbom` with `software_sbomType = runtime`,
linking to the notebook file as a `software_File` element.

### Notebook file as a `software_File` element

When the session ends and the output path is configured, Pitloom creates
a `software_File` element for the notebook file itself (`.ipynb`), with:

- `verifiedUsing`: SHA-256 hash of the notebook at session end.
- `software_fileKind`: `file`.
- An SPDX `Relationship` of type `generatedFrom` from the model/dataset
  element to the notebook file element.

This makes the notebook a first-class provenance artefact in the SBOM,
satisfying transparency requirements for AI systems under the EU AI Act
(which requires documentation of training procedures and data sources).
