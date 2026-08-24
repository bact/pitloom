---
Created: 2026-08-25
Last-Modified: 2026-08-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM fragments: extractor integrations (Weave, DVC, MLflow)

See also [README.md](README.md) (index),
[fragment-merge-design.md](fragment-merge-design.md) (start here for the
core fragment mechanism),
[loom-sdk-and-notebooks.md](loom-sdk-and-notebooks.md),
[roadmap-and-resources.md](roadmap-and-resources.md),
[working-docs/design/mlflow-extractor.md](../mlflow-extractor.md) (the
existing, separate MLflow extractor design the MLflow updates below
build on).

Split from this directory's former single `sbom-fragments.md`
(2026-08-25) -- new-extractor designs for external ML tracking tools:
W&B Weave, DVC, and MLflow extractor updates. All content here is
unbuilt design, corresponding to roadmap Phase 3 in
[roadmap-and-resources.md](roadmap-and-resources.md).

### 4. No W&B Weave integration

W&B Weave captures automatic execution traces, versioned model objects,
versioned dataset objects, and structured evaluation results -- all of which
map cleanly to SPDX 3 AI and Dataset profile elements. There is currently no
extractor for Weave, even though it is rapidly becoming the primary tracking
layer for LLM-based applications.

## W&B Weave extractor

### Why Weave is significant

W&B Weave ([github.com/wandb/weave](https://github.com/wandb/weave)) is a
next-generation tracing layer specifically designed for LLM-based
applications. Unlike MLflow's run-centric model or W&B's artifact-centric
model, Weave captures the **full call graph** of an AI application --
automatically, via function decoration -- including:

- All inputs and outputs to every decorated function (`@weave.op()`).
- Model versioning based on code hash (a new version is created whenever
  the function body changes).
- Dataset object versioning with row-level identity.
- Structured evaluation results linking a specific model version to a
  specific dataset version, with per-scorer metrics.
- Parent/child relationships between nested calls (execution traces).

This call graph structure maps with high fidelity to SPDX 3 elements:
SPDX relationships capture the `from/to` structure of Weave's trace tree;
SPDX `Annotation` elements carry evaluation metrics; `software_Sbom`
elements group the Model + Dataset + Evaluation into a coherent AI BOM.

### Object mapping

| Weave concept | SPDX 3.0 element / field |
| :---- | :---- |
| `weave.Model` + version hash | `ai_AIPackage` with `software_packageVersion` = Weave version URI |
| `weave.Dataset` + version | `dataset_DatasetPackage` with `ExternalRef` to Weave ref URI |
| `weave.Evaluation` result | `Annotation` elements attached to `ai_AIPackage` |
| `@weave.op()` call inputs | `ai_hyperparameter` (training-time params) |
| `@weave.op()` call outputs | `comment` with structured output summary |
| `weave.ref(...)` URI | `software_downloadLocation` or `ExternalRef` |
| Trace `trace_id` + `parent_id` | SPDX `Relationship` (`generatedFrom`, `usedBy`) |
| Token usage metadata | `ai_energyConsumption` (inference cost) or `Annotation` |

### Extractor design: `pitloom.extract.weave`

```python
class WeaveExtractor:
    """Extracts SPDX 3 AI BOM metadata from a W&B Weave project.

    Args:
        project: Weave project reference ("entity/project").
        model_ref: Specific model ref URI or name:version string.
        evaluation_ref: Optional evaluation ref to include metrics.
        api_key: Optional W&B API key. Uses WANDB_API_KEY env var if unset.
    """

    def extract(self) -> WeaveRunMetadata: ...
    def to_fragment(self, output_file: str | Path | None = None) -> str: ...
```

```python
# loom.py public API addition
def from_weave_model(
    model_ref: str,
    project: str,
    output_file: str | Path,
    evaluation_ref: str | None = None,
    api_key: str | None = None,
) -> None:
    """Generate an SPDX fragment from a W&B Weave model object."""
```

The extractor accesses Weave via the `weave` Python client, which is
available as `pip install weave`. The `WANDB_API_KEY` environment variable
provides authentication. All Weave imports are lazy (deferred inside
functions) to keep the optional-dependency pattern consistent.

### Weave-specific provenance patterns

Weave model versions use content-addressed URIs:
`weave:///entity/project/object/ModelName:abc123def456`

This URI is a natural fit for `software_downloadLocation` on
`ai_AIPackage` -- it is both a stable reference and an integrity signal
(the hash is part of the URI). The full Weave trace URL provides a
navigable link back to the execution record in the W&B UI.

---

### 5. No DVC integration

DVC tracks data and model files via metafiles committed to Git. The
`dvc.yaml` pipeline graph and `.dvc` content-addressed pointers are rich
provenance sources for dataset and model file elements in SPDX.

## DVC integration

DVC ([dvc.org](https://dvc.org)) tracks data files and ML models via small
metafiles (`.dvc`, `dvc.lock`) committed to Git. The `dvc.yaml` file
defines a pipeline of stages, each with declared inputs (`deps`),
outputs (`outs`), and commands.

### What DVC provides for SBOMs

| DVC artefact | SBOM value |
| :---- | :---- |
| `.dvc` file (content hash + remote path) | Dataset `verifiedUsing` hash + `downloadLocation` |
| `dvc.yaml` stage definition | Build step provenance (command, inputs, outputs) |
| `dvc.lock` (frozen deps + hashes) | Deterministic, auditable dataset/model ancestry |
| DVC remote URL | `ExternalRef` pointing to the remote storage location |
| Git commit where `.dvc` was modified | Timestamp and version anchor for `createdTime` |

### Extractor design: `pitloom.extract.dvc`

```python
class DvcExtractor:
    """Reads dvc.yaml and dvc.lock to extract dataset and model provenance.

    Args:
        project_dir: Root of the DVC repository.
        stage: Specific stage name to extract (e.g., "train"). If None,
            extracts all stages and their outputs.
    """

    def extract(self) -> list[DatasetMetadata | AiModelMetadata]: ...
```

The extractor reads `dvc.lock` (the frozen, hash-committed view of the
pipeline) rather than `dvc.yaml` (the mutable intent) to ensure that the
SBOM reflects the actual data used, not just what was planned.

---

## Integration with MLflow (existing design, updates)

See `working-docs/design/mlflow-extractor.md` for the full MLflow extractor design.

Updates motivated by this document:

1. **Dataset references from MLflow runs** -- MLflow 2.x supports
   `mlflow.log_input(mlflow.data.from_pandas(...))` to log dataset provenance
   per run. The MLflow extractor should read `run.inputs.dataset_inputs` and
   emit `dataset_DatasetPackage` elements linked via `trainedOn` / `testedOn`
   relationships. This eliminates manual `add_dataset` calls in most workflows.

2. **MLflow Model Registry** -- a registered model version in the Model Registry
   has a `model_uri` (`models:/name/version` or `runs:/run_id/artifacts/model`).
   This URI maps to `software_downloadLocation` on `ai_AIPackage`.
   The `MlflowExtractor` should accept a registered model version reference
   as an alternative to a raw run ID.

3. **Artifact logging** -- `mlflow.log_artifact(path)` uploads files.
   Large non-model artifacts (dataset files, evaluation outputs) could be
   translated to `software_File` elements with `verifiedUsing` checksums
   if MLflow stores the artifact hash (it does in MLflow 2.9+).
