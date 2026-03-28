# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""HDF5/Keras model metadata extractor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata


def _decode_h5_attr(value: Any) -> str | None:
    """Decode an h5py attribute value to a Python string.

    h5py may return string attributes as ``str``, ``bytes``, or
    ``numpy.bytes_`` depending on version and how the file was written.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "tobytes"):
        return str(value.tobytes().decode("utf-8", errors="replace"))
    return str(value)


def _parse_model_config(
    raw: str, source: str
) -> tuple[str | None, str | None, dict[str, Any], dict[str, str]]:
    """Parse model_config JSON from an HDF5 Keras model.

    Args:
        raw: Raw JSON string from the model_config attribute.
        source: Provenance source string (e.g. "Source: model.h5").

    Returns:
        Tuple of (type_of_model, name, hyperparameters, provenance_updates).
        provenance_updates maps provenance keys to their values.
    """
    import json  # pylint: disable=import-outside-toplevel

    type_of_model: str | None = None
    name: str | None = None
    hyperparameters: dict[str, Any] = {}
    provenance_updates: dict[str, str] = {}

    try:
        model_config = json.loads(raw)
        type_of_model = model_config.get("class_name") or None
        if type_of_model:
            provenance_updates["type_of_model"] = (
                f"{source} | Field: model_config.class_name"
            )

        config = model_config.get("config", {})
        if isinstance(config, dict):
            name = config.get("name") or config.get("model_name") or None
            if name:
                provenance_updates["name"] = (
                    f"{source} | Field: model_config.config.name"
                )
            for key, val in config.items():
                if key == "name":
                    continue
                if isinstance(val, (int, float, bool, str)):
                    hyperparameters[key] = val
            if hyperparameters:
                provenance_updates["hyperparameters"] = (
                    f"{source} | Field: model_config.config.*"
                )
    except (json.JSONDecodeError, AttributeError):
        pass

    return type_of_model, name, hyperparameters, provenance_updates


def _parse_training_config(raw: str) -> dict[str, str]:
    """Parse training_config JSON from an HDF5 Keras model.

    Args:
        raw: Raw JSON string from the training_config attribute.

    Returns:
        Dict of property key/value pairs (optimizer, loss, metrics).
    """
    import json  # pylint: disable=import-outside-toplevel

    properties: dict[str, str] = {}
    try:
        training_config = json.loads(raw)
        optimizer = training_config.get("optimizer_config") or training_config.get(
            "optimizer"
        )
        if isinstance(optimizer, dict):
            opt_class = optimizer.get("class_name") or ""
            if opt_class:
                properties["optimizer"] = opt_class
        loss = training_config.get("loss")
        if loss is not None:
            properties["loss"] = str(loss)
        metrics = training_config.get("metrics")
        if metrics:
            properties["metrics"] = json.dumps(metrics)
    except (json.JSONDecodeError, AttributeError):
        pass
    return properties


def read_hdf5(model_path: Path) -> AiModelMetadata:
    """Extract metadata from an HDF5 model file, including Keras models.

    Requires the ``h5py`` package (``pip install h5py``).

    Keras saves models in HDF5 with JSON-encoded ``model_config`` and
    ``training_config`` root attributes.  This extractor reads:

    - ``model_config.class_name`` → :attr:`~AiModelMetadata.type_of_model`
    - ``model_config.config.name`` → :attr:`~AiModelMetadata.name`
    - Scalar entries of ``model_config.config`` → hyperparameters
    - ``training_config`` (optimizer, loss, metrics) → properties
    - ``keras_version`` → :attr:`~AiModelMetadata.version`
    - ``backend`` → properties

    Args:
        model_path: Path to a ``.h5`` or ``.hdf5`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ImportError: If ``h5py`` is not installed.
        ValueError: If the file cannot be read as a valid HDF5 file.
    """
    try:
        import h5py  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "The 'h5py' package is required to extract HDF5 model metadata. "
            "Install it with: pip install h5py"
        ) from exc

    try:
        hf = h5py.File(str(model_path), "r")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(f"Failed to read HDF5 file {model_path}: {exc}") from exc

    with hf:
        source = f"Source: {model_path.name}"
        provenance: dict[str, str] = {}
        hyperparameters: dict[str, Any] = {}
        properties: dict[str, str] = {}
        name: str | None = None
        version: str | None = None
        type_of_model: str | None = None

        model_config_raw = _decode_h5_attr(hf.attrs.get("model_config"))
        training_config_raw = _decode_h5_attr(hf.attrs.get("training_config"))
        keras_version_raw = _decode_h5_attr(hf.attrs.get("keras_version"))
        backend_raw = _decode_h5_attr(hf.attrs.get("backend"))

        if keras_version_raw:
            version = keras_version_raw
            provenance["version"] = f"{source} | Field: keras_version attribute"

        if backend_raw:
            properties["backend"] = backend_raw

        if model_config_raw:
            type_of_model, name, hyperparameters, prov_updates = _parse_model_config(
                model_config_raw, source
            )
            provenance.update(prov_updates)
            if not type_of_model and not name:
                # JSON parse failed — store raw snippet
                properties["model_config_raw"] = model_config_raw[:500]

        if training_config_raw:
            training_props = _parse_training_config(training_config_raw)
            properties.update(training_props)

        if properties:
            provenance["properties"] = (
                f"{source} | Fields: training_config, keras_version, backend"
            )

    return AiModelMetadata(
        format=AiModelFormat.HDF5,
        name=name,
        version=version,
        type_of_model=type_of_model,
        hyperparameters=hyperparameters,
        properties=properties,
        provenance=provenance,
    )
