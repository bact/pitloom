# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The arguments a caller gives the loom SDK: their one check
(:func:`check_sdk_arguments`), one rule per parameter name, the same in
every call that takes it, so a wrong type is refused at the call with
``option-invalid`` (``loom SDK: <parameter>: must be ...``), not deep in a
binding or at the run's exit; and the config a run's ``pitloom_config``
names (:func:`loom_config`).

See also: :mod:`pitloom.loom` (the public facade) and
:mod:`pitloom._loom_active_run` (where each call checks).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Final, NamedTuple

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import load_config_file
from pitloom.core.creation import CreationMetadata
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.core.internal_error import InternalError
from pitloom.id_registry import IdRegistry
from pitloom.messages import CodedValueError, recoded
from pitloom.messages.config import (
    Parameter,
    invalid_value,
    loom_sdk_invalid_value,
    loom_sdk_type_error,
)
from pitloom.messages.targets import is_empty_input

__all__ = ["DATASET_TYPES", "check_sdk_arguments", "loom_config"]

#: The ``dataset_DatasetType`` terms a dataset may be declared as: the
#: binding's named individuals, by name.
DATASET_TYPES: Final = frozenset(spdx3.dataset_DatasetType.NAMED_INDIVIDUALS)


def _is_path(value: object) -> bool:
    """A ``str`` or an :class:`os.PathLike` naming a ``str`` path."""
    if isinstance(value, str):
        return True
    if not isinstance(value, os.PathLike):
        return False
    try:
        return isinstance(os.fspath(value), str)
    except TypeError:
        return False


def _is_strings(value: object) -> bool:
    """A ``list`` or ``tuple`` of ``str``."""
    return isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value)


def _is_string_mapping(value: object) -> bool:
    """A mapping of ``str`` to ``str``."""
    return isinstance(value, Mapping) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    )


class _Rule(NamedTuple):
    """What a parameter takes: its ``EXPECTED`` id, the test of its type
    and, for a value of that type, of its value (``None``: any) with the
    ``EXPECTED`` id a refused value is told (``None``: *expected*)."""

    expected: str
    type_ok: Callable[[object], bool]
    value_ok: Callable[[object], bool] | None = None
    value_expected: str | None = None


def _of(kind: type | tuple[type, ...]) -> Callable[[object], bool]:
    """The test of an instance of *kind*."""
    return lambda value: isinstance(value, kind)


def _is_str(value: object) -> bool:
    """A ``str``."""
    return isinstance(value, str)


def _is_named(value: object) -> bool:
    """A path (:func:`_is_path`) not spelt as nothing (``""``), which
    :class:`pathlib.Path` would read as the current directory."""
    return isinstance(value, (str, os.PathLike)) and os.fspath(value) != ""


#: Each SDK parameter by name.
_RULES: Final[Mapping[str, _Rule]] = {
    "output_file": _Rule("path", _is_path, _is_named, "non-empty"),
    "pretty": _Rule("python-bool", _of(bool)),
    "creation_metadata": _Rule("creation-metadata", _of(CreationMetadata)),
    "id_registry": _Rule(
        "registry-source",
        lambda v: _is_path(v) or isinstance(v, IdRegistry),
        lambda v: isinstance(v, IdRegistry) or _is_named(v),
        "non-empty",
    ),
    "credentials": _Rule("credential-policy", _of(CredentialPolicy)),
    "name": _Rule("string", _is_str),
    "model_type": _Rule("string", _is_str),
    "hyperparameters": _Rule("mapping-of-strings", _is_string_mapping),
    "generated": _Rule("python-bool", _of(bool)),
    "path": _Rule("path", _is_path),
    "dataset_type": _Rule("one-of-dataset-type", _is_str, lambda v: v in DATASET_TYPES),
    "croissant": _Rule("path", _is_path),
    "declared_license": _Rule("string", _is_str),
    "data_preprocessing": _Rule("list-of-strings", _is_strings),
    "input_datasets": _Rule("list-of-strings", _is_strings),
}


def check_sdk_arguments(required: Collection[str], /, **values: object) -> None:
    """Refuse the first of *values* (SDK arguments, by parameter name) that
    its rule does not take; ``None`` is taken where the parameter is not
    in *required* (its default).

    Raises:
        pitloom.messages.CodedTypeError: A value of the wrong type
            (``option-invalid``).
        pitloom.messages.CodedValueError: A value of the right type that
            the parameter does not take (an unknown ``dataset_type``, an
            empty ``output_file``).
        pitloom.core.internal_error.InternalError: A name has no rule.
    """
    for name, value in values.items():
        rule = _RULES.get(name)
        if rule is None:
            raise InternalError(f"no loom SDK rule for {name!r}")
        if value is None and name not in required:
            continue
        if not rule.type_ok(value):
            raise loom_sdk_type_error(Parameter(name), rule.expected, got=value)
        if rule.value_ok is not None and not rule.value_ok(value):
            raise loom_sdk_invalid_value(
                Parameter(name), rule.value_expected or rule.expected, got=value
            )


def loom_config(pitloom_config: PitloomConfig | str | Path | None) -> PitloomConfig:
    """The config of a loom run: *pitloom_config* itself, the file it names
    loaded like ``--config`` (a relative path from the current directory),
    else the defaults. Never an implicit ``[tool.pitloom]``.

    Raises:
        ValueError: the named file is missing or the path empty
            (``input-not-found``),
            unreadable (``file-unreadable``) or invalid (``config-invalid``,
            ``config-malformed``): a :class:`~pitloom.messages.CodedValueError`
            naming it.
    """
    if pitloom_config is None:
        return PitloomConfig()
    if isinstance(pitloom_config, PitloomConfig):
        return pitloom_config
    if not isinstance(pitloom_config, (str, os.PathLike)):
        raise invalid_value(
            Parameter("pitloom_config"), "config-source", pitloom_config
        )
    if is_empty_input(pitloom_config):
        # Path("") is the current directory: an empty option, as --config ''.
        raise invalid_value(Parameter("pitloom_config"), "non-empty", got="")
    try:
        return load_config_file(Path(pitloom_config), source="pitloom_config")
    except FileNotFoundError as exc:
        raise recoded(CodedValueError, exc) from None
