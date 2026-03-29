# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Keras v3 native model metadata extractor.

The ``.keras`` format introduced in Keras 3 is a ZIP archive containing:

- ``metadata.json`` — Keras version and save timestamp.
- ``config.json``   — Full model architecture (class name, layer configs).
- ``model.weights.h5`` — Weights stored in HDF5 (not read here).

The file starts with the standard ZIP magic ``PK\\x03\\x04`` which is shared
with other ZIP-based formats (PyTorch, etc.), so format detection relies on
the ``.keras`` extension rather than magic-byte sniffing.

For legacy Keras v1/v2 models stored in HDF5 (``.h5``/``.hdf5``) use
:func:`pitloom.extract._hdf5.read_hdf5` instead.

References:
    - https://keras.io/api/saving/model_saving_and_loading/
    - https://keras.io/guides/serialization_and_saving/
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata


def _parse_model_config(
    config_data: dict[str, Any],
    source: str,
    hyperparameters: dict[str, Any],
    inputs: list[dict[str, Any]],
    provenance: dict[str, str],
) -> tuple[str | None, str | None]:
    """Parse ``config.json`` from a ``.keras`` archive.

    Extracts:

    - ``class_name`` → ``type_of_model`` (returned)
    - ``config.name`` → ``name`` (returned)
    - Scalar entries of ``config`` (excluding ``name``, ``layers``, ``dtype``)
      → ``hyperparameters`` (updated in-place)
    - ``build_config.input_shape``
      → ``inputs`` (updated in-place)
    - Per-field source paths → ``provenance`` (updated in-place)

    Args:
        config_data: Parsed JSON object from ``config.json``.
        source: Provenance source string (e.g. ``"Source: model.keras"``).
        hyperparameters: Updated in-place with scalar config entries.
        inputs: Updated in-place with extracted input shape entries.
        provenance: Updated in-place with per-field source descriptions.

    Returns:
        Tuple of ``(type_of_model, name)``.
    """
    type_of_model: str | None = config_data.get("class_name") or None
    name: str | None = None

    if type_of_model:
        provenance["type_of_model"] = f"{source} | Field: config.class_name"

    config = config_data.get("config", {})
    if isinstance(config, dict):
        name = config.get("name") or None
        if name:
            provenance["name"] = f"{source} | Field: config.config.name"
        for key, val in config.items():
            if key in ("name", "layers", "dtype"):
                continue
            if isinstance(val, (int, float, bool, str)):
                hyperparameters[key] = val
        if hyperparameters:
            provenance["hyperparameters"] = f"{source} | Field: config.config.*"

    # Input shape from top-level build_config.
    build_config = config_data.get("build_config", {})
    if isinstance(build_config, dict):
        input_shape = build_config.get("input_shape")
        if input_shape is not None:
            inputs.append({"shape": input_shape})
            provenance["inputs"] = f"{source} | Field: config.build_config.input_shape"

    return type_of_model, name


def read_keras(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a Keras v3 ``.keras`` archive.

    No extra dependencies are required — the standard-library
    :mod:`zipfile` and :mod:`json` modules are used.

    Reads:

    - ``metadata.json``: ``keras_version`` →
      :attr:`~AiModelMetadata.version`; ``date_saved`` → properties.
    - ``config.json``: ``class_name`` →
      :attr:`~AiModelMetadata.type_of_model`; ``config.name`` →
      :attr:`~AiModelMetadata.name`; scalar config entries →
      hyperparameters; ``build_config.input_shape`` → inputs.

    Args:
        model_path: Path to a ``.keras`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ValueError: If the file is not a valid ``.keras`` archive.
    """
    source = f"Source: {model_path.name}"
    # .keras is always Keras v3 native format
    format_version = "v3"
    framework = "keras"
    framework_version: str | None = None
    name: str | None = None
    type_of_model: str | None = None
    hyperparameters: dict[str, Any] = {}
    properties: dict[str, str] = {}
    inputs: list[dict[str, Any]] = []
    provenance: dict[str, str] = {}

    try:
        with zipfile.ZipFile(str(model_path), "r") as zf:
            names = zf.namelist()

            if "metadata.json" in names:
                meta = json.loads(zf.read("metadata.json"))
                # keras_version is the Keras library version, not the model version.
                framework_version = meta.get("keras_version") or None
                if framework_version:
                    provenance["framework_version"] = (
                        f"{source} | Field: metadata.json keras_version"
                    )
                date_saved = meta.get("date_saved") or None
                if date_saved:
                    properties["date_saved"] = date_saved
                    provenance["properties"] = (
                        f"{source} | Field: metadata.json date_saved"
                    )

            if "config.json" in names:
                config_data = json.loads(zf.read("config.json"))
                type_of_model, name = _parse_model_config(
                    config_data, source, hyperparameters, inputs, provenance
                )

    except zipfile.BadZipFile as exc:
        raise ValueError(
            f"Failed to read Keras file {model_path}: not a valid ZIP archive"
        ) from exc
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(f"Failed to read Keras file {model_path}: {exc}") from exc

    return AiModelMetadata(
        format=AiModelFormat.KERAS,
        format_version=format_version,
        framework=framework,
        framework_version=framework_version,
        name=name,
        type_of_model=type_of_model,
        hyperparameters=hyperparameters,
        properties=properties,
        inputs=inputs,
        provenance=provenance,
    )
