# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying the configuration families: the error a reader raises
(:class:`ConfigError`, made by :func:`config_invalid`, :func:`config_moved`
and :func:`hook_unknown_keys`), the one place that adds the file to it
(:meth:`ConfigError.located`), the warning for an unknown key
(:func:`warn_config_unknown_key`), and a shared validator's refusal by
stage (:func:`invalid_value`, :func:`must_be`).

A reader never takes the file it reads: it raises a :class:`ConfigError`
naming where the value sits, in the ``pyproject.toml`` spelling, and
:func:`pitloom.core._config_parse.parse_pitloom_config` catches it once and
raises :meth:`ConfigError.located` ``from None``, with ``FILE=`` and the
``setup.cfg`` spelling added.

See also: :mod:`pitloom.messages._config` (the entries).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import Any

from pitloom.core.internal_error import InternalError
from pitloom.messages._config import (
    CONFIG_INVALID,
    CONFIG_MOVED,
    CONFIG_UNKNOWN_KEY,
)
from pitloom.messages._config_found import MISSING, Found, found_text, kind_text
from pitloom.messages._config_place import (
    EXPECTED,
    ConfigPlace,
    Parameter,
    expected_text,
)
from pitloom.messages._emit import CodedTypeError, CodedValueError, emit
from pitloom.messages._options import LOOM_SDK_VALUE_LINE, OPTION_INVALID, VALUE_LINE
from pitloom.messages._types import Message


class ConfigError(CodedValueError):
    """A :class:`~pitloom.messages.CodedValueError` that says a
    configuration message (``config-invalid``, ``config-moved``, the build
    hook's ``config-unknown-key``) and keeps the values it was written from,
    so :meth:`located` can write it again with the file. It keeps a place,
    an id and a ``got`` already written (masked, escaped, cut), never the
    value found; its ``args`` are its text alone. A copy or a pickle keeps
    its text and code only, as every coded error does.

    Raises:
        ValueError: (a plain one) No ``ERROR`` line of *message* names
            *values*, or a value does not have its field's shape.
    """

    def __init__(self, message: Message, /, **values: Any) -> None:
        if "got" in values and not isinstance(values["got"], Found):
            values["got"] = Found(found_text(values["got"]))
        super().__init__(message, **values)
        self._message: Message | None = message
        self._values: dict[str, object] | None = values

    def located(
        self, source: str | os.PathLike[str] | None, is_setup_cfg: bool
    ) -> ConfigError:
        """This error naming the file *source* (``FILE=``, unless ``None``:
        a configuration of no file), its place spelt as ``setup.cfg``
        spells it when *is_setup_cfg*. Raise it ``from None``: its own text
        says what the caught one said. An error that names a file already,
        or a copy (which keeps no values), is returned as it is."""
        values = getattr(self, "_values", None)
        message = getattr(self, "_message", None)
        if values is None or message is None or "file" in values:
            return self
        place = values.get("config_key")
        if not isinstance(place, ConfigPlace):
            raise InternalError(f"{message.code}: no config_key to locate")
        again: dict[str, Any] = {**values, "config_key": place.spelt(is_setup_cfg)}
        if source is not None:
            again["file"] = source
        return type(self)(message, **again)


def _known(expected: str) -> str:
    """*expected*, an id of :data:`~pitloom.messages._config_place.EXPECTED`.

    Raises:
        pitloom.core.internal_error.InternalError: It is not one.
    """
    if expected not in EXPECTED:
        raise InternalError(f"no expected text {expected!r}")
    return expected


def config_invalid(
    place: ConfigPlace, expected: str, got: object = MISSING, *, secret: bool = False
) -> ConfigError:
    """The ``config-invalid`` error for the value *got* at *place*, which
    must be *expected* (an id of
    :data:`~pitloom.messages._config_place.EXPECTED`): ``raise
    config_invalid(ConfigPlace("tool.pitloom", "pretty"), "boolean",
    got=value)``. *got* left out: the key is missing (``nothing``).
    *secret*: the value may be a credential, so the line names its type
    only.

    Raises:
        pitloom.core.internal_error.InternalError: *expected* is not an id
            of the table, or *place* is no place.
    """
    if not isinstance(place, ConfigPlace):
        raise InternalError(f"not a config place: {place!r}")
    found = Found(kind_text(got) if secret else found_text(got))
    return ConfigError(
        CONFIG_INVALID, config_key=place, expected=_known(expected), got=found
    )


def config_moved(place: ConfigPlace, destination: str) -> ConfigError:
    """The ``config-moved`` error for the key or table at *place*, which
    goes to *destination* now (one of
    :data:`~pitloom.messages._config_place.DESTINATIONS`).

    Raises:
        ValueError: (a plain one) *destination* is not in the table.
    """
    return ConfigError(CONFIG_MOVED, config_key=place, destination=destination)


def hook_unknown_keys(place: ConfigPlace, keys: Iterable[str]) -> ConfigError:
    """The build hook's ``config-unknown-key`` error for *keys* of its table
    *place*."""
    return ConfigError(CONFIG_UNKNOWN_KEY, config_key=place, entries=tuple(keys))


# pylint: disable-next=too-many-arguments
def warn_config_unknown_key(
    log: logging.Logger,
    place: ConfigPlace,
    key: str,
    *,
    file: str | os.PathLike[str] | None,
    setting: str | None = None,
    tables: tuple[ConfigPlace, ...] = (),
    once: str | None = None,
) -> None:
    """The one ``config-unknown-key`` warning on *log* for *key* of the
    table *place* (spelt for its source by the caller) in *file* (``None``:
    a configuration of no file): with the known key *setting* it is close
    to, or the other *tables* that know it, or no hint. *once*: the said-once
    key (:func:`~pitloom.logging_config.log_once`).

    Raises:
        pitloom.core.internal_error.InternalError: Both a *setting* and
            *tables* are given.
    """
    if setting is not None and tables:
        raise InternalError("an unknown key's hint is a setting or tables")
    values: dict[str, Any] = {"config_key": place, "entry": key}
    if file is not None:
        values["file"] = file
    if setting is not None:
        values["setting"] = setting
    if tables:
        values["tables"] = tables
    emit(log, CONFIG_UNKNOWN_KEY, logging.WARNING, once=once, **values)


def invalid_value(
    where: ConfigPlace | Parameter,
    expected: str,
    got: object = MISSING,
    *,
    secret: bool = False,
) -> CodedValueError:
    """The refusal of a shared validator, by the stage *where* says: a
    :class:`ConfigPlace` (a configuration file) is ``config-invalid``
    (:func:`config_invalid`), a :class:`Parameter` (a library caller's
    value) the ``option-invalid`` line ``<parameter>: must be X, got Y``.
    *secret*: the value may be a credential, so the line names its type
    only.

    Raises:
        pitloom.core.internal_error.InternalError: *expected* is not an id
            of the table, or *where* is neither.
    """
    if isinstance(where, ConfigPlace):
        return config_invalid(where, expected, got, secret=secret)
    if not isinstance(where, Parameter):
        raise InternalError(f"not a stage: {where!r}")
    return CodedValueError(
        OPTION_INVALID,
        line=VALUE_LINE,
        option=where.name,
        expected=_known(expected),
        got=Found(kind_text(got)) if secret else got,
    )


def loom_sdk_invalid_value(
    where: Parameter, expected: str, got: object = MISSING
) -> CodedValueError:
    """The ``option-invalid`` refusal of *where*, a value given to a loom SDK
    call (``loom SDK: <parameter>: must be X, got Y``).

    Raises:
        pitloom.core.internal_error.InternalError: *expected* is not an id
            of the table.
    """
    return CodedValueError(
        OPTION_INVALID,
        line=LOOM_SDK_VALUE_LINE,
        option=where.name,
        expected=_known(expected),
        got=got,
    )


def loom_sdk_type_error(
    where: Parameter, expected: str, got: object = MISSING
) -> CodedTypeError:
    """The ``option-invalid`` refusal of *where*, a value of the wrong type
    given to a loom SDK call: :func:`loom_sdk_invalid_value`'s line, as the
    :class:`TypeError` a Python caller expects.

    Raises:
        pitloom.core.internal_error.InternalError: *expected* is not an id
            of the table.
    """
    return CodedTypeError(
        OPTION_INVALID,
        line=LOOM_SDK_VALUE_LINE,
        option=where.name,
        expected=_known(expected),
        got=got,
    )


def must_be(expected: str, got: object = MISSING) -> str:
    """``must be X, got Y`` for *expected* and *got*: the text a command
    line option's ``type=`` raises as :class:`argparse.ArgumentTypeError`,
    so its ``argument --x: ...`` line says what a setting's line says.

    Raises:
        pitloom.core.internal_error.InternalError: *expected* is not an id
            of the table.
    """
    return f"must be {expected_text(_known(expected))}, got {found_text(got)}"
