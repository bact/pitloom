# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parsing of the JSON members of a Keras v3 ``.keras`` archive.

``metadata.json`` states the Keras version and the save time;
``config.json`` the model config, the same object an HDF5 model's
``model_config`` attribute holds (read by
:func:`pitloom.extract.ai_model.hdf5_config.parse_model_config_object`), and
its ``compile_config``, read as an HDF5 model's ``training_config`` (by
:func:`pitloom.extract.ai_model.keras_training_config.parse_training_config_object`).

Each member is untrusted JSON. One that does not parse (not valid JSON or
UTF-8 text, nested too deeply, its top level no object) is one warning, and
the other member is still read. A value of the wrong type is one warning per
member part (the metadata, the model config, the compile config), and the
rest of that part is kept. Absent, ``null`` and empty values are no problem.

Not read: ``config.json``'s top-level ``metadata`` object (a convention of
some exporters, not a field Keras writes), ``compile_config``'s other keys
(as the HDF5 reader skips the same keys of ``training_config``), and the
weights member (no parameter count).

See also: :mod:`pitloom.extract.ai_model.keras` (the archive) and
:mod:`pitloom.extract.ai_model._hdf5_warnings` (the warnings).
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from typing import Any

from pitloom.core.provenance import provenance_segment
from pitloom.extract.ai_model._hdf5_warnings import (
    log_config_kept,
    log_member_problem,
    log_training_config_problem,
)
from pitloom.extract.ai_model.archive_member import read_archive_member
from pitloom.extract.ai_model.hdf5_config import (
    MODEL_CONFIG_FIELDS,
    TRAINING_CONFIG_FIELDS,
    ConfigLayout,
    ConfigProblem,
    ConfigShapeError,
    json_object,
    member_object,
    member_text,
    parse_model_config_object,
)
from pitloom.extract.ai_model.keras_training_config import (
    KERAS_COMPILE_LAYOUT,
    parse_training_config_object,
)

#: The member holding the Keras version and the save time.
METADATA_MEMBER = "metadata.json"
#: The member holding the model and compile configs.
CONFIG_MEMBER = "config.json"
#: ``metadata.json`` key -> the field it sets.
_METADATA_KEYS = {
    "keras_version": "framework_version",
    "date_saved": "properties.date_saved",
}
#: The fields ``metadata.json`` sets, named when it cannot be read.
METADATA_FIELDS = tuple(_METADATA_KEYS.values())
#: The fields ``config.json`` sets, named when it cannot be read.
CONFIG_FIELDS = (*MODEL_CONFIG_FIELDS, *TRAINING_CONFIG_FIELDS)
#: Where the model config of ``config.json`` sits: at its top, read as
#: ``config``. ``dtype`` (a dtype policy in Keras 3) is no hyperparameter,
#: and a class or model name that is not a string is skipped alone.
KERAS_LAYOUT = ConfigLayout(
    "config", skipped_keys=("name", "layers", "dtype"), skip_bad_names=True
)


@dataclass
class KerasFields:
    """What the members of a ``.keras`` archive state, filled in place.

    Attributes:
        source: Provenance source string.
        framework_version: The Keras version that saved the model.
        type_of_model: The model class.
        name: The model name.
        hyperparameters: The scalar entries of the model's ``config``.
        inputs: The model's input shape, when stated.
        properties: Text properties.
        natives: The native value of each property held as text, for
            :func:`pitloom.core.ai_metadata.source_metadata`.
        provenance: Per-field source descriptions.
    """

    source: str
    framework_version: str | None = None
    type_of_model: str | None = None
    name: str | None = None
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    properties: dict[str, str] = field(default_factory=dict)
    natives: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)


def member_json(
    zf: zipfile.ZipFile, member: str, lost: tuple[str, ...]
) -> dict[str, Any] | None:
    """The JSON object of archive *member*; ``{}`` for JSON ``null``. One that
    does not parse, or is no object, is ``None`` and one ``WARNING:``
    naming *lost*, the fields it sets.

    The bytes are parsed as :func:`json.loads` takes them (a UTF-8 byte order
    mark skipped).

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: The member is over
            its byte cap.
    """
    raw = read_archive_member(zf, member)
    try:
        return json_object(raw, member)
    except ConfigShapeError as exc:
        log_member_problem(ConfigProblem.of([exc], lost))
        return None


def read_metadata(meta: dict[str, Any], fields: KerasFields) -> None:
    """``keras_version`` (the Keras library version, not the model's) ->
    ``framework_version``; ``date_saved`` -> ``properties["date_saved"]``,
    as stated (no time zone, so no release time). A value that is not a
    string is not recorded: one ``WARNING:`` for the member names it."""
    problems: list[ConfigShapeError] = []
    lost: list[str] = []
    for key, field_name in _METADATA_KEYS.items():
        try:
            value = member_text(meta, key, f"metadata.{key}")
        except ConfigShapeError as exc:
            problems.append(exc)
            lost.append(field_name)
            continue
        if not value:
            continue
        if key == "keras_version":
            fields.framework_version = value
        else:
            fields.properties[key] = value
        fields.provenance[field_name] = provenance_segment(
            fields.source, "Field", f"{METADATA_MEMBER} {key}"
        )
    if problems:
        log_config_kept(ConfigProblem.of(problems, lost))


def read_config(config_data: dict[str, Any], fields: KerasFields) -> None:
    """The model config of ``config.json`` (its class, name,
    hyperparameters, layer count and input shape) and its
    ``compile_config`` (optimiser, loss and metrics), each part with at most
    one ``WARNING:`` naming what it could not read."""
    fields.type_of_model, fields.name, problem = parse_model_config_object(
        config_data,
        fields.source,
        fields.hyperparameters,
        fields.inputs,
        fields.properties,
        fields.provenance,
        fields.natives,
        KERAS_LAYOUT,
    )
    if problem is not None:
        log_config_kept(problem)
    try:
        compile_config = member_object(
            config_data, "compile_config", KERAS_COMPILE_LAYOUT.where
        )
    except ConfigShapeError as exc:
        log_training_config_problem(ConfigProblem.of([exc], TRAINING_CONFIG_FIELDS))
        return
    log_training_config_problem(
        parse_training_config_object(
            compile_config,
            fields.source,
            fields.properties,
            fields.provenance,
            fields.natives,
            KERAS_COMPILE_LAYOUT,
        )
    )
