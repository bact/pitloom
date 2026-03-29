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

_ParseResult = tuple[
    str | None, str | None, dict[str, Any], list[dict[str, Any]], dict[str, str]
]


def _parse_model_config(config_data: dict[str, Any], source: str) -> _ParseResult:
    """Parse ``config.json`` from a ``.keras`` archive.

    Args:
        config_data: Parsed JSON object from ``config.json``.
        source: Provenance source string (e.g. ``"Source: model.keras"``).

    Returns:
        Tuple of ``(type_of_model, name, hyperparameters, inputs,
        provenance_updates)``.
    """
    type_of_model: str | None = config_data.get("class_name") or None
    provenance_updates: dict[str, str] = {}
    hyperparameters: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    name: str | None = None

    if type_of_model:
        provenance_updates["type_of_model"] = f"{source} | Field: config.class_name"

    config = config_data.get("config", {})
    if isinstance(config, dict):
        name = config.get("name") or None
        if name:
            provenance_updates["name"] = f"{source} | Field: config.config.name"
        for key, val in config.items():
            if key in ("name", "layers", "dtype"):
                continue
            if isinstance(val, (int, float, bool, str)):
                hyperparameters[key] = val
        if hyperparameters:
            provenance_updates["hyperparameters"] = f"{source} | Field: config.config.*"

    # Input shape from top-level build_config.
    build_config = config_data.get("build_config", {})
    if isinstance(build_config, dict):
        input_shape = build_config.get("input_shape")
        if input_shape is not None:
            inputs = [{"shape": input_shape}]
            provenance_updates["inputs"] = (
                f"{source} | Field: config.build_config.input_shape"
            )

    return type_of_model, name, hyperparameters, inputs, provenance_updates


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
    provenance: dict[str, str] = {}
    properties: dict[str, str] = {}
    version: str | None = None
    type_of_model: str | None = None
    name: str | None = None
    hyperparameters: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []

    try:
        with zipfile.ZipFile(str(model_path), "r") as zf:
            names = zf.namelist()

            if "metadata.json" in names:
                meta = json.loads(zf.read("metadata.json"))
                version = meta.get("keras_version") or None
                if version:
                    provenance["version"] = (
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
                type_of_model, name, hyperparameters, inputs, prov = (
                    _parse_model_config(config_data, source)
                )
                provenance.update(prov)

    except zipfile.BadZipFile as exc:
        raise ValueError(
            f"Failed to read Keras file {model_path}: not a valid ZIP archive"
        ) from exc
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(f"Failed to read Keras file {model_path}: {exc}") from exc

    return AiModelMetadata(
        format=AiModelFormat.KERAS,
        name=name,
        version=version,
        type_of_model=type_of_model,
        hyperparameters=hyperparameters,
        properties=properties,
        inputs=inputs,
        provenance=provenance,
    )
