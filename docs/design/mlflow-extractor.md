---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-License-Identifier: CC0-1.0
SPDX-FileType: DOCUMENTATION
---

# MLflow run extractor

## Overview

This document describes the design of `loom.extractors.mlflow`, a module that
reads a completed or active MLflow run and converts its tags, parameters, and
metrics into an SPDX 3 AI BOM fragment.

The goal is to eliminate double instrumentation. A project already using MLflow
for experiment tracking should be able to produce a compliance-grade SBOM
fragment without adding a second set of `loom.bom` calls to the training script.

## Motivation and the double-instrumentation problem

The current `loom.bom` SDK requires explicit calls alongside MLflow:

```python
# Current state — duplicated effort
import mlflow
import loom.bom as bom

with mlflow.start_run():
    mlflow.set_tag("typeOfModel", "transformer")
    mlflow.log_param("learning_rate", 3e-4)
    mlflow.log_metric("accuracy", 0.95)

with bom.track("fragment.spdx3.json") as run:
    run.set_model("my-transformer")
    # The same facts, typed again
```

The MLflow extractor closes this gap. Once an MLflow run exists, Loom can read
it and emit the fragment automatically:

```python
# Desired state — one source of truth
import mlflow
import loom.bom as bom

with mlflow.start_run() as mlflow_run:
    mlflow.set_tag("typeOfModel", "transformer")
    mlflow.log_param("learning_rate", 3e-4)
    mlflow.log_metric("accuracy", 0.95)
    # ... training ...

# After training: generate SBOM fragment from the MLflow run record
bom.from_mlflow_run(
    mlflow_run.info.run_id,
    output_file="fragments/train.spdx3.json",
)
```

## STAV as a shared vocabulary layer

[STAV](https://github.com/bact/stav) (System Trustworthiness and Accountability
Vocabulary) is an OWL ontology that maps EU AI Act and SPDX AI Profile concepts
to Python string constants. Projects using STAV constants in MLflow tag keys
get a clean, lossless mapping into SPDX fields with no additional configuration.

```python
import mlflow
import stav

with mlflow.start_run():
    mlflow.set_tag(stav.MODEL_TYPE, "transformer")
    mlflow.set_tag(stav.INFO_TRAINING, "Fine-tuned on FLORES-200 for translation")
    mlflow.log_metric(stav.METRICS_ACCURACY, 0.95)
    mlflow.log_metric(stav.ENERGY_CONSUMPTION_TRAINING, 1.4)  # kWh
```

STAV is an optional dependency. The extractor falls back to string matching
against well-known MLflow tag prefixes and metric names when STAV is not installed.

## Tag and metric mapping

### MLflow tags → SPDX 3 AI Profile fields

| MLflow tag key (stav constant) | SPDX 3.0 `ai_AIPackage` field | Notes |
| :--- | :--- | :--- |
| `stav.MODEL_TYPE` / `typeOfModel` | `ai_typeOfModel` | Enum or free text |
| `stav.INFO_TRAINING` / `informationAboutTraining` | `ai_informationAboutTraining` | Free text |
| `stav.AI_PROVIDER` / `aiProvider` | `suppliedBy` | Maps to SPDX Agent |
| `stav.USE_SENSITIVE_PERSONAL_INFO` / `sensitivePersonalInformation` | `ai_sensitivePersonalInformation` | Boolean-like enum |
| `stav.AUTONOMY_TYPE` / `autonomyType` | `ai_autonomyType` | Enum |
| `stav.DOMAIN` / `domain` | `ai_domain` | Free text list |
| `mlflow.runName` | `name` | Falls back to run ID |
| `mlflow.source.name` | provenance `comment` | Training script name |
| `mlflow.source.git.commit` | provenance `comment` | Git commit SHA |
| `mlflow.source.git.repoURL` | `software_downloadLocation` | Repository link |

### MLflow params (logged via `log_param`) → SPDX `ai_hyperparameter`

All `log_param` entries are mapped to the `ai_hyperparameter` list
as `{name: key, value: str(value)}` objects. Individual params with
known stav keys are additionally promoted to their SPDX fields:

| MLflow param key | SPDX field |
| :--- | :--- |
| `stav.HYPERPARAMETER` / any other | `ai_hyperparameter[{name, value}]` |

### MLflow metrics → SPDX Annotations

MLflow metrics (logged via `log_metric`) do not have a direct scalar
SPDX 3.0 field on `ai_AIPackage`. They are recorded as SPDX `Annotation`
elements attached to the `ai_AIPackage` via an `annotates` relationship:

| MLflow metric key (stav constant) | Annotation type | Notes |
| :--- | :--- | :--- |
| `stav.METRICS_ACCURACY` / `accuracy` | `ai:metric:accuracy` | |
| `stav.METRICS_F1` / `f1` / `f1_score` | `ai:metric:f1` | |
| `stav.METRICS_LOSS` / `loss` | `ai:metric:loss` | |
| `stav.ENERGY_CONSUMPTION_TRAINING` / `energyConsumption` | `ai_energyConsumption` | Promoted to SPDX field |
| Any other metric | `ai:metric:<key>` | Stored in annotation body |

## Class and module design

### File: `src/loom/extractors/mlflow.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MlflowRunMetadata:
    """Intermediate representation of an MLflow run, format-neutral.

    Fields map directly to SPDX 3 AI Profile concepts, with provenance
    preserved for each value.
    """

    run_id: str
    run_name: str | None = None
    model_name: str | None = None
    type_of_model: str | None = None
    information_about_training: str | None = None
    supplied_by: str | None = None
    download_location: str | None = None
    hyperparameters: list[dict[str, str]] = field(default_factory=list)
    energy_consumption: float | None = None
    sensitive_personal_information: str | None = None
    autonomy_type: str | None = None
    domain: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    datasets: list[str] = field(default_factory=list)
    provenance_comment: str = ""


class MlflowExtractor:
    """Extracts SPDX 3 AI BOM metadata from an MLflow run.

    MLflow is a required runtime dependency; import errors raise a clear
    message with install instructions. STAV is optional.

    Args:
        run_id: The MLflow run UUID.
        tracking_uri: Optional MLflow tracking server URI. Uses
            ``MLFLOW_TRACKING_URI`` from the environment if not given.
        model_name: Override the SBOM package name. Defaults to the MLflow
            run name or ``mlflow-run-{run_id[:8]}``.
    """

    def __init__(
        self,
        run_id: str,
        tracking_uri: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._run_id = run_id
        self._tracking_uri = tracking_uri
        self._model_name_override = model_name

    def extract(self) -> MlflowRunMetadata:
        """Fetch the run from MLflow and return a format-neutral metadata object.

        Raises:
            ImportError: If the ``mlflow`` package is not installed.
            MlflowException: If the run ID does not exist on the tracking server.
        """
        try:
            import mlflow  # noqa: PLC0415 (lazy import)
        except ImportError as exc:
            raise ImportError(
                "MLflow is required for this extractor. "
                "Install it with: pip install 'loom[mlflow]'"
            ) from exc

        if self._tracking_uri:
            mlflow.set_tracking_uri(self._tracking_uri)

        run = mlflow.get_run(self._run_id)
        return self._map_run(run)

    def to_fragment(self) -> str:
        """Return a JSON-LD SPDX 3 fragment for this MLflow run.

        Raises:
            ImportError: If ``mlflow`` is not installed.
        """
        metadata = self.extract()
        return _build_spdx_fragment(metadata)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _map_run(self, run: Any) -> MlflowRunMetadata:
        """Map an mlflow.entities.Run to MlflowRunMetadata."""
        tags = dict(run.data.tags)
        params = dict(run.data.params)
        metrics = dict(run.data.metrics)

        # Determine model name
        model_name = (
            self._model_name_override
            or tags.get("mlflow.runName")
            or tags.get("mlflow.source.name")
            or f"mlflow-run-{run.info.run_id[:8]}"
        )

        # Map tags using the stav/fallback key mapping
        spdx_fields = _map_tags(tags)

        # All params become hyperparameters
        hyperparameters = [
            {"name": k, "value": str(v)} for k, v in params.items()
        ]

        # Build provenance string
        provenance_parts: list[str] = [
            f"Source: MLflow run {run.info.run_id[:8]}",
            f"experiment_id={run.info.experiment_id}",
        ]
        git_commit = tags.get("mlflow.source.git.commit")
        if git_commit:
            provenance_parts.append(f"git_commit={git_commit}")
        source_name = tags.get("mlflow.source.name")
        if source_name:
            provenance_parts.append(f"source={source_name}")

        return MlflowRunMetadata(
            run_id=run.info.run_id,
            run_name=tags.get("mlflow.runName"),
            model_name=model_name,
            type_of_model=spdx_fields.get("type_of_model"),
            information_about_training=spdx_fields.get("information_about_training"),
            supplied_by=spdx_fields.get("supplied_by"),
            download_location=tags.get("mlflow.source.git.repoURL"),
            hyperparameters=hyperparameters,
            energy_consumption=spdx_fields.get("energy_consumption"),
            sensitive_personal_information=spdx_fields.get(
                "sensitive_personal_information"
            ),
            autonomy_type=spdx_fields.get("autonomy_type"),
            domain=spdx_fields.get("domain", []),
            metrics=metrics,
            provenance_comment=" | ".join(provenance_parts),
        )


# ------------------------------------------------------------------
# Tag mapping helpers
# ------------------------------------------------------------------

# Canonical tag key aliases (stav constants → fallback string keys)
_TAG_ALIASES: dict[str, list[str]] = {
    "type_of_model": ["typeOfModel", "type_of_model", "model_type"],
    "information_about_training": [
        "informationAboutTraining",
        "information_about_training",
        "training_info",
    ],
    "supplied_by": ["aiProvider", "ai_provider", "supplier"],
    "energy_consumption": [
        "energyConsumptionTraining",
        "energy_consumption_training",
        "energyConsumption",
    ],
    "sensitive_personal_information": [
        "sensitivePersonalInformation",
        "sensitive_personal_information",
        "use_sensitive_personal_info",
    ],
    "autonomy_type": ["autonomyType", "autonomy_type"],
    "domain": ["domain"],
}


def _resolve_stav_constants() -> dict[str, str]:
    """Return a dict of {stav_constant_value: canonical_field_name} if stav is installed."""
    try:
        import stav  # noqa: PLC0415 (lazy import)

        mapping: dict[str, str] = {}
        field_to_stav: dict[str, str] = {
            "type_of_model": getattr(stav, "MODEL_TYPE", None),
            "information_about_training": getattr(stav, "INFO_TRAINING", None),
            "supplied_by": getattr(stav, "AI_PROVIDER", None),
            "energy_consumption": getattr(
                stav, "ENERGY_CONSUMPTION_TRAINING", None
            ),
            "sensitive_personal_information": getattr(
                stav, "USE_SENSITIVE_PERSONAL_INFO", None
            ),
            "autonomy_type": getattr(stav, "AUTONOMY_TYPE", None),
        }
        for field_name, stav_key in field_to_stav.items():
            if stav_key:
                mapping[stav_key] = field_name
        return mapping
    except ImportError:
        return {}


def _map_tags(tags: dict[str, str]) -> dict[str, Any]:
    """Map MLflow run tags to SPDX AI Profile field names."""
    stav_map = _resolve_stav_constants()
    result: dict[str, Any] = {}

    for tag_key, tag_value in tags.items():
        # Check stav constants first
        if tag_key in stav_map:
            result[stav_map[tag_key]] = tag_value
            continue
        # Check fallback aliases
        for field_name, aliases in _TAG_ALIASES.items():
            if tag_key in aliases:
                if field_name == "domain":
                    result.setdefault("domain", []).append(tag_value)
                elif field_name == "energy_consumption":
                    try:
                        result["energy_consumption"] = float(tag_value)
                    except ValueError:
                        result["energy_consumption"] = tag_value
                else:
                    result[field_name] = tag_value
                break

    return result


# ------------------------------------------------------------------
# SPDX fragment builder
# ------------------------------------------------------------------

def _build_spdx_fragment(metadata: MlflowRunMetadata) -> str:
    """Serialize MlflowRunMetadata to an SPDX 3 JSON-LD fragment string."""
    from datetime import datetime, timezone
    from uuid import uuid4

    from spdx_python_model import v3_0_1 as spdx3

    from loom.core.models import generate_spdx_id
    from loom.exporters.spdx3_json import Spdx3JsonExporter

    doc_uuid = str(uuid4())
    creation_info = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime.now(timezone.utc),
    )

    # Creator
    tool = spdx3.Tool(
        spdxId=generate_spdx_id("Tool", "loom-mlflow-extractor", doc_uuid),
        name="Loom MLflow Extractor",
        creationInfo=creation_info,
    )
    creation_info.createdBy = [tool.spdxId]

    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(creation_info)

    # Build ai_AIPackage
    model_name = metadata.model_name or f"mlflow-run-{metadata.run_id[:8]}"
    ai_pkg = spdx3.ai_AIPackage(
        spdxId=generate_spdx_id("AIPackage", model_name, doc_uuid),
        name=model_name,
        creationInfo=creation_info,
        comment=(
            f"Metadata provenance: {metadata.provenance_comment}"
            if metadata.provenance_comment
            else None
        ),
    )

    if metadata.type_of_model:
        ai_pkg.ai_typeOfModel = [metadata.type_of_model]
    if metadata.information_about_training:
        ai_pkg.ai_informationAboutTraining = metadata.information_about_training
    if metadata.hyperparameters:
        ai_pkg.ai_hyperparameter = metadata.hyperparameters
    if metadata.download_location:
        ai_pkg.software_downloadLocation = metadata.download_location

    exporter.add_package(ai_pkg)

    # Metrics as Annotations
    for metric_name, metric_value in metadata.metrics.items():
        annotation = spdx3.Annotation(
            spdxId=generate_spdx_id("Annotation", metric_name, doc_uuid),
            creationInfo=creation_info,
            annotationType=spdx3.AnnotationType.review,
            subject=ai_pkg.spdxId,
            statement=f"ai:metric:{metric_name}={metric_value}",
        )
        exporter.add_annotation(annotation)

    return exporter.to_json()


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def extract_from_mlflow_run(
    run_id: str,
    output_file: str | Path | None = None,
    tracking_uri: str | None = None,
    model_name: str | None = None,
) -> str:
    """Extract an SPDX 3 AI BOM fragment from a completed MLflow run.

    Args:
        run_id: The MLflow run UUID to read.
        output_file: If given, write the fragment JSON to this path.
        tracking_uri: Optional MLflow tracking server URI.
        model_name: Override the SBOM package name.

    Returns:
        JSON-LD string of the SPDX fragment.

    Raises:
        ImportError: If ``mlflow`` is not installed.
    """
    extractor = MlflowExtractor(
        run_id=run_id,
        tracking_uri=tracking_uri,
        model_name=model_name,
    )
    fragment_json = extractor.to_fragment()

    if output_file is not None:
        p = Path(output_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(fragment_json, encoding="utf-8")

    return fragment_json
```

### Integration with `loom.bom`

`loom.bom` gains one new top-level function delegating to the extractor:

```python
# In src/loom/bom.py

def from_mlflow_run(
    run_id: str,
    output_file: str | Path,
    tracking_uri: str | None = None,
    model_name: str | None = None,
) -> None:
    """Generate an SPDX fragment from an MLflow run and write it to a file.

    This is a convenience wrapper around
    :func:`loom.extractors.mlflow.extract_from_mlflow_run`.

    Args:
        run_id: The MLflow run UUID to read.
        output_file: Path to write the SPDX JSON-LD fragment.
        tracking_uri: Optional MLflow tracking server URI.
        model_name: Override the SBOM package name.
    """
    from loom.extractors.mlflow import extract_from_mlflow_run  # noqa: PLC0415

    extract_from_mlflow_run(
        run_id=run_id,
        output_file=output_file,
        tracking_uri=tracking_uri,
        model_name=model_name,
    )
```

## Optional dependencies

MLflow and stav are heavyweight and optional. They must not be imported
at module level; all imports are deferred inside functions.

### Additions to `pyproject.toml`

```toml
[project.optional-dependencies]
gguf = ["gguf>=0.10.0"]
mlflow = ["mlflow>=2.0.0", "stav>=0.1.0"]
model = ["onnx>=1.14.1", "safetensors[numpy]>=0.4.0", "gguf>=0.10.0"]
onnx = ["onnx>=1.14.1"]
safetensors = ["safetensors[numpy]>=0.4.0"]
```

Users who need MLflow extraction install:

```bash
pip install "loom[mlflow]"
```

## End-to-end usage example

```python
import mlflow
import stav
import loom.bom as bom

# --- Training script (train.py) ---

mlflow.set_tracking_uri("http://mlflow.example.com")

with mlflow.start_run(run_name="bert-finetune-v3") as mlflow_run:
    mlflow.set_tag(stav.MODEL_TYPE, "transformer")
    mlflow.set_tag(stav.INFO_TRAINING, "Fine-tuned on multilingual NLI dataset")
    mlflow.set_tag(stav.AI_PROVIDER, "Acme AI Lab")
    mlflow.log_param("learning_rate", 2e-5)
    mlflow.log_param("batch_size", 32)
    mlflow.log_param("epochs", 5)
    mlflow.log_metric(stav.METRICS_ACCURACY, 0.91)
    mlflow.log_metric(stav.ENERGY_CONSUMPTION_TRAINING, 2.3)

    train_model(...)

    # Emit SPDX fragment after training completes
    bom.from_mlflow_run(
        mlflow_run.info.run_id,
        output_file="fragments/bert-finetune-v3.spdx3.json",
    )
```

The resulting fragment can then be listed under
`[tool.hatch.build.hooks.loom] fragments` so it is merged into the wheel SBOM
at build time.

## New files and changes

### New source files

```text
src/loom/
└── extractors/
    └── mlflow.py           ← MlflowExtractor, extract_from_mlflow_run
tests/
└── test_mlflow_extractor.py
```

### Changes to existing files

| File | Change |
| :--- | :--- |
| `src/loom/bom.py` | Add `from_mlflow_run()` top-level function |
| `pyproject.toml` | Add `mlflow` optional-dependency group |

## Test plan

| Test | Description |
| :--- | :--- |
| `test_extract_basic_tags` | Mock `mlflow.get_run`; assert SPDX fields are populated from stav-keyed tags. |
| `test_extract_fallback_aliases` | Use non-stav tag keys; assert field mapping still works. |
| `test_params_become_hyperparameters` | Assert all `log_param` entries appear in `ai_hyperparameter`. |
| `test_metrics_become_annotations` | Assert metrics produce Annotation elements in the fragment. |
| `test_energy_consumption_promoted` | Assert `energyConsumptionTraining` metric maps to `ai_energyConsumption`. |
| `test_missing_mlflow_import_error` | Import extractor without mlflow installed; assert `ImportError` with install hint. |
| `test_stav_not_required` | Run extraction without stav installed; assert fallback alias mapping works. |
| `test_output_file_written` | Pass `output_file`; assert JSON file is created at the path. |
| `test_bom_from_mlflow_run_delegates` | Assert `bom.from_mlflow_run()` calls `extract_from_mlflow_run()`. |

## References

- STAV ontology: <https://w3id.org/stav>
- STAV GitHub: <https://github.com/bact/stav>
- MLflow tracking API: <https://mlflow.org/docs/latest/ml/tracking/tracking-api/>
- SPDX 3.0 AI profile: <https://spdx.github.io/spdx-spec/v3.0/>
- SPDX AI BOM example: <https://github.com/bact/sentimentdemo>
