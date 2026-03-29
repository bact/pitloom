# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic HDF5 model metadata extractor with Keras v1/v2 legacy support.

HDF5 is a general-purpose hierarchical data format used by many frameworks.
Keras v1 and v2 stored models in HDF5 (``.h5`` / ``.hdf5``) with a set of
JSON-encoded root attributes.  This extractor:

1. **Detects Keras legacy HDF5** by checking for the ``keras_version`` root
   attribute, which is the decisive Keras-specific marker.  Other attributes
   such as ``model_config`` or ``backend`` may also appear in non-Keras HDF5
   files, so they are not used alone for detection.
2. **Extracts all available Keras metadata** when that attribute is found:

   - ``keras_version``
     → :attr:`~AiModelMetadata.version`
   - ``backend``
     → ``properties["backend"]``
   - ``model_config.class_name``
     → :attr:`~AiModelMetadata.type_of_model`
   - ``model_config.config.name``
     → :attr:`~AiModelMetadata.name`
   - Scalar entries of ``model_config.config``
     → :attr:`~AiModelMetadata.hyperparameters`
   - ``model_config.config.layers`` count
     → ``properties["layer_count"]``
   - ``model_config.build_config.input_shape`` (or layer batch_shape)
     → :attr:`~AiModelMetadata.inputs`
   - ``training_config.optimizer_config.class_name``
     → ``properties["optimizer"]``
   - ``training_config.loss``
     → ``properties["loss"]``
   - ``training_config.metrics``
     → ``properties["metrics"]``

3. Records a **per-field provenance entry** for every populated field so
   that downstream consumers can trace each value back to its exact HDF5
   attribute and JSON path.

For plain HDF5 files without Keras attributes the extractor returns a
minimal :class:`~pitloom.core.ai_metadata.AiModelMetadata` with only
``format=AiModelFormat.HDF5`` populated.

Native Keras v3 models use the ``.keras`` format (ZIP archive) and are
handled by the separate :mod:`pitloom.extract._keras` extractor.

References:
    - https://docs.hdfgroup.org/hdf5/
    - https://keras.io/api/saving/model_saving_and_loading/
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata

# Root HDF5 attribute names written by Keras v1/v2.
# 'keras_version' is the decisive Keras-specific marker; 'model_config' and
# 'backend' may also appear in other HDF5-based frameworks and are not used
# alone to identify a Keras file.
_KERAS_ATTRS = frozenset({"keras_version", "model_config", "backend"})


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


def _is_keras_hdf5(attrs: Any) -> bool:
    """Return ``True`` if the HDF5 root attributes indicate a Keras v1/v2 model.

    Uses ``keras_version`` as the decisive marker — it is unique to Keras and
    not present in generic HDF5 files from other frameworks.  Attributes such
    as ``model_config`` or ``backend`` may also appear in non-Keras HDF5 files
    and are therefore not used here for classification.

    Args:
        attrs: The ``h5py.File.attrs`` mapping.
    """
    return "keras_version" in attrs


def _extract_input_from_layers(
    layers: list[Any], source: str
) -> tuple[list[dict[str, Any]], str]:
    """Extract the model input shape from a Keras ``config.layers`` list.

    Tries each layer in order:

    - **InputLayer**: uses ``config.batch_shape``.
    - **Other layers**: uses ``build_config.input_shape``.

    Args:
        layers: The ``config.layers`` list from ``model_config``.
        source: Provenance source string (e.g. ``"Source: model.h5"``).

    Returns:
        Tuple of ``(inputs, provenance_value)`` where ``inputs`` is a
        one-element list or empty and ``provenance_value`` is the source
        description string (empty string when nothing was found).
    """
    for i, layer in enumerate(layers):
        layer_class = layer.get("class_name", "")
        if layer_class == "InputLayer":
            batch_shape = (layer.get("config") or {}).get("batch_shape")
            if batch_shape is not None:
                prov = (
                    f"{source} | Field: model_config.config.layers"
                    "[InputLayer].config.batch_shape"
                )
                return [{"shape": batch_shape}], prov
        else:
            in_shape = (layer.get("build_config") or {}).get("input_shape")
            if in_shape is not None:
                prov = (
                    f"{source} | Field: model_config.config.layers[{i}]"
                    ".build_config.input_shape"
                )
                return [{"shape": in_shape}], prov
    return [], ""


def _parse_model_config(
    raw: str, source: str
) -> tuple[
    str | None,
    str | None,
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, str],
    dict[str, str],
]:
    """Parse ``model_config`` JSON from a Keras v1/v2 HDF5 model.

    Extracts:

    - ``class_name`` → ``type_of_model``
    - ``config.name`` / ``config.model_name`` → ``name``
    - Scalar entries of ``config`` (excluding ``name`` and ``layers``)
      → ``hyperparameters``
    - ``config.layers`` count → ``config_properties["layer_count"]``
    - Input shape from layers or ``build_config.input_shape``
      → ``inputs``

    Args:
        raw: Raw JSON string from the ``model_config`` HDF5 attribute.
        source: Provenance source string (e.g. ``"Source: model.h5"``).

    Returns:
        Tuple of ``(type_of_model, name, hyperparameters, inputs,
        config_properties, provenance_updates)``.
        ``config_properties`` contains additional string properties derived
        from the model config (e.g. ``layer_count``).
        ``provenance_updates`` maps field names to their source descriptions.
    """
    import json  # pylint: disable=import-outside-toplevel

    type_of_model: str | None = None
    name: str | None = None
    hyperparameters: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    config_properties: dict[str, str] = {}
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

            layers = config.get("layers")
            if isinstance(layers, list):
                config_properties["layer_count"] = str(len(layers))
                provenance_updates["properties.layer_count"] = (
                    f"{source} | Field: model_config.config.layers (count)"
                )
                inputs, inputs_prov = _extract_input_from_layers(layers, source)
                if inputs_prov:
                    provenance_updates["inputs"] = inputs_prov

            for key, val in config.items():
                if key in ("name", "layers"):
                    continue
                if isinstance(val, (int, float, bool, str)):
                    hyperparameters[key] = val

            if hyperparameters:
                provenance_updates["hyperparameters"] = (
                    f"{source} | Field: model_config.config.*"
                    " (scalar entries, excluding name and layers)"
                )

        # Top-level build_config — fallback if layers didn't give a shape.
        if not inputs:
            in_shape = (model_config.get("build_config") or {}).get("input_shape")
            if in_shape is not None:
                inputs = [{"shape": in_shape}]
                provenance_updates["inputs"] = (
                    f"{source} | Field: model_config.build_config.input_shape"
                )

    except (json.JSONDecodeError, AttributeError):
        pass

    return (
        type_of_model,
        name,
        hyperparameters,
        inputs,
        config_properties,
        provenance_updates,
    )


def _parse_training_config(
    raw: str, source: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Parse ``training_config`` JSON from a Keras v1/v2 HDF5 model.

    Extracts:

    - ``optimizer_config.class_name`` (or ``optimizer.class_name``)
      → ``properties["optimizer"]``
    - ``loss``
      → ``properties["loss"]``
    - ``metrics``
      → ``properties["metrics"]``

    Args:
        raw: Raw JSON string from the ``training_config`` HDF5 attribute.
        source: Provenance source string (e.g. ``"Source: model.h5"``).

    Returns:
        Tuple of ``(properties, provenance_updates)``.
        ``provenance_updates`` maps ``"properties.<key>"`` to its HDF5/JSON
        source path so that the caller can record per-field provenance.
    """
    import json  # pylint: disable=import-outside-toplevel

    properties: dict[str, str] = {}
    provenance_updates: dict[str, str] = {}

    try:
        training_config = json.loads(raw)

        opt_key = (
            "optimizer_config" if "optimizer_config" in training_config else "optimizer"
        )
        optimizer = training_config.get(opt_key)
        if isinstance(optimizer, dict):
            opt_class = optimizer.get("class_name") or ""
            if opt_class:
                properties["optimizer"] = opt_class
                provenance_updates["properties.optimizer"] = (
                    f"{source} | Field: training_config.{opt_key}.class_name"
                )

        loss = training_config.get("loss")
        if loss is not None:
            properties["loss"] = str(loss)
            provenance_updates["properties.loss"] = (
                f"{source} | Field: training_config.loss"
            )

        metrics = training_config.get("metrics")
        if metrics:
            properties["metrics"] = json.dumps(metrics)
            provenance_updates["properties.metrics"] = (
                f"{source} | Field: training_config.metrics"
            )

    except (json.JSONDecodeError, AttributeError):
        pass

    return properties, provenance_updates


def read_hdf5(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a generic HDF5 file (``.h5`` or ``.hdf5``).

    Requires the ``h5py`` package (``pip install h5py``).

    Detects Keras v1/v2 legacy models by checking for the ``keras_version``
    root attribute (the decisive Keras marker) and extracts all available
    Keras metadata when found.  See the module docstring for the full list of
    extracted fields and their HDF5/JSON source paths.

    For native Keras v3 (``.keras``) files use
    :func:`pitloom.extract._keras.read_keras` instead.

    Args:
        model_path: Path to a ``.h5`` or ``.hdf5`` file.

    Returns:
        :class:`~pitloom.core.ai_metadata.AiModelMetadata` with all
        available fields populated.  Plain HDF5 files without Keras
        attributes return a minimal object with only ``format`` set.

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
        inputs: list[dict[str, Any]] = []
        name: str | None = None
        version: str | None = None
        type_of_model: str | None = None

        keras_version_raw = _decode_h5_attr(hf.attrs.get("keras_version"))
        model_config_raw = _decode_h5_attr(hf.attrs.get("model_config"))
        training_config_raw = _decode_h5_attr(hf.attrs.get("training_config"))
        backend_raw = _decode_h5_attr(hf.attrs.get("backend"))

        if keras_version_raw:
            version = keras_version_raw
            provenance["version"] = f"{source} | Field: keras_version attribute"

        if backend_raw:
            properties["backend"] = backend_raw
            provenance["properties.backend"] = f"{source} | Field: backend attribute"

        if model_config_raw:
            type_of_model, name, hyperparameters, inputs, cfg_props, prov_updates = (
                _parse_model_config(model_config_raw, source)
            )
            properties.update(cfg_props)
            provenance.update(prov_updates)
            if not type_of_model and not name:
                properties["model_config_raw"] = model_config_raw[:500]
                provenance["properties.model_config_raw"] = (
                    f"{source} | Field: model_config attribute (unparsed)"
                )

        if training_config_raw and _is_keras_hdf5(hf.attrs):
            training_props, training_prov = _parse_training_config(
                training_config_raw, source
            )
            properties.update(training_props)
            provenance.update(training_prov)

    return AiModelMetadata(
        format=AiModelFormat.HDF5,
        name=name,
        version=version,
        type_of_model=type_of_model,
        hyperparameters=hyperparameters,
        properties=properties,
        inputs=inputs,
        provenance=provenance,
    )
