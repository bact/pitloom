# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Keras v3 native model metadata extractor.

The ``.keras`` format introduced in Keras 3 is a ZIP archive containing:

- ``metadata.json`` -- Keras version and save timestamp.
- ``config.json``   -- Full model architecture (class name, layer configs)
  and the compile settings (optimizer, loss, metrics).
- ``model.weights.h5`` -- Weights stored in HDF5 (not read here).

The file starts with the standard ZIP magic ``PK\\x03\\x04`` which is shared
with other ZIP-based formats (PyTorch, etc.), so format detection relies on
the ``.keras`` extension rather than magic-byte sniffing.

The JSON members are parsed by :mod:`pitloom.extract.ai_model.keras_config`,
with the config parsing the HDF5 reader shares.

For legacy Keras v1/v2 models stored in HDF5 (``.h5``/``.hdf5``) use
:func:`pitloom.extract.ai_model.hdf5.read_hdf5` instead.

References:
    - https://keras.io/api/saving/model_saving_and_loading/
    - https://keras.io/guides/serialization_and_saving/
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from pitloom.core.ai_metadata import (
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    source_metadata,
)
from pitloom.core.provenance import provenance_source
from pitloom.core.quote_source import quote_source
from pitloom.extract.ai_model.archive_member import (
    open_model_zip,
    record_archive_contents,
)
from pitloom.extract.ai_model.keras_config import (
    CONFIG_FIELDS,
    CONFIG_MEMBER,
    METADATA_FIELDS,
    METADATA_MEMBER,
    KerasFields,
    member_json,
    read_config,
    read_metadata,
)
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)


def _read_members(zf: zipfile.ZipFile, fields: KerasFields) -> None:
    """Read the archive structure and the JSON members of *zf* into
    *fields*; a member that does not parse is one warning, and the other is
    still read."""
    names = zf.namelist()
    fields.natives.update(
        record_archive_contents(
            names, fields.source, fields.properties, fields.provenance
        )
    )
    if METADATA_MEMBER in names:
        meta = member_json(zf, METADATA_MEMBER, METADATA_FIELDS)
        if meta is not None:
            read_metadata(meta, fields)
    if CONFIG_MEMBER in names:
        config_data = member_json(zf, CONFIG_MEMBER, CONFIG_FIELDS)
        if config_data is not None:
            read_config(config_data, fields)


def read_keras(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a Keras v3 ``.keras`` archive.

    No extra dependencies are required -- the standard-library
    :mod:`zipfile` and :mod:`json` modules are used.

    Reads:

    - The ZIP structure: member names -> ``properties["archive_contents"]``,
      their number -> ``properties["archive_member_count"]``.
    - ``metadata.json``: ``keras_version`` ->
      :attr:`~AiModelMetadata.framework_version`; ``date_saved`` -> properties.
    - ``config.json``: ``class_name`` ->
      :attr:`~AiModelMetadata.type_of_model`; ``config.name`` (else
      ``config.model_name``) -> :attr:`~AiModelMetadata.name`; scalar config
      entries -> hyperparameters; the number of ``config.layers`` ->
      ``properties["layer_count"]``; the input shape (an ``InputLayer``'s
      ``batch_shape``, else a layer's or the model's
      ``build_config.input_shape``) -> inputs; ``compile_config``'s
      optimizer, loss and metrics -> properties.

    Args:
        model_path: Path to a ``.keras`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ValueError: If the file is not a valid ``.keras`` archive, or a
            member cannot be extracted.
        pitloom.extract.ai_model.limits.ModelLimitExceeded: The archive or one
            of its members is over a bound.
    """
    fields = KerasFields(provenance_source(model_path.name))
    try:
        with open_model_zip(model_path) as zf:
            _read_members(zf, fields)
    except ModelLimitExceeded:
        raise
    except zipfile.BadZipFile as exc:
        raise ValueError(
            f"Failed to read Keras file {quote_source(model_path)}: "
            "not a valid ZIP archive"
        ) from exc
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.debug(
            "Failed to read Keras file %s: %s",
            loggable(str(model_path)),
            loggable(str(exc)),
        )
        raise ValueError(
            f"Failed to read Keras file {quote_source(model_path)}: {exc}"
        ) from exc
    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.KERAS,
            format_version="v3",  # .keras is always the Keras v3 native format
            framework="keras",
            framework_version=fields.framework_version,
        ),
        name=fields.name,
        type_of_model=fields.type_of_model,
        hyperparameters=fields.hyperparameters,
        properties=fields.properties,
        **source_metadata(fields.properties, fields.natives),
        inputs=fields.inputs,
        provenance=fields.provenance,
    )
