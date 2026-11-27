# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Validation of the byte ceilings ``max-model-extract-bytes``,
``max-dataset-hash-bytes`` and ``max-download-bytes``, and the default of the
last.

One validator for the config reader and for each consumer, which also
receives the value from a library caller's
:class:`~pitloom.core.config.PitloomConfig`, never parsed.

See also: :mod:`pitloom.core._config_parse_scan`,
:mod:`pitloom.extract.scanner_wheel`, :mod:`pitloom._loom_active_run` and
:mod:`pitloom.extract.remote.pypi` and :mod:`pitloom.extract.remote.git`
(the downloads the last one caps).
"""

from __future__ import annotations

import operator

from pitloom.messages.config import ConfigPlace, Parameter, invalid_value

__all__ = [
    "DEFAULT_MAX_DOWNLOAD_BYTES",
    "MAX_DATASET_HASH_BYTES_KEY",
    "MAX_DOWNLOAD_BYTES_KEY",
    "MAX_MODEL_EXTRACT_BYTES_KEY",
    "positive_problem",
    "require_max_dataset_hash_bytes",
    "require_max_download_bytes",
    "require_max_model_extract_bytes",
    "require_positive_ceiling",
]

MAX_MODEL_EXTRACT_BYTES_KEY = "max-model-extract-bytes"
MAX_DATASET_HASH_BYTES_KEY = "max-dataset-hash-bytes"
MAX_DOWNLOAD_BYTES_KEY = "max-download-bytes"

#: Where each key sits in a configuration file: the default stage of its
#: validator.
_MODEL_EXTRACT_PLACE = ConfigPlace("tool.pitloom", MAX_MODEL_EXTRACT_BYTES_KEY)
_DATASET_HASH_PLACE = ConfigPlace("tool.pitloom", MAX_DATASET_HASH_BYTES_KEY)
_DOWNLOAD_PLACE = ConfigPlace("tool.pitloom", MAX_DOWNLOAD_BYTES_KEY)

#: Default ``max-download-bytes``: the most bytes of a release file fetched
#: from PyPI, and of disk a Git URL's checkout takes, 512 MiB.
DEFAULT_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024


def positive_problem(value: object) -> str | None:
    """Why *value* is no ceiling: the ``expected`` id (see
    :data:`~pitloom.messages.config.EXPECTED`) ``"integer"`` (not an integer;
    a ``bool`` or a ``float`` is none) or ``"positive"`` (an integer below 1),
    else ``None``. The pure check of :func:`require_positive_ceiling`, which
    the command-line flag route calls instead of its raise."""
    if isinstance(value, bool):
        return "integer"
    try:
        number = operator.index(value)  # type: ignore[arg-type]
    except TypeError:
        return "integer"
    return "positive" if number <= 0 else None


def require_positive_ceiling(value: object, where: ConfigPlace | Parameter) -> int:
    """*value* as an ``int`` when it is an integer of at least 1.

    The one validator for every surface that takes a ceiling but the
    command-line flag (:func:`positive_problem`): the config key, the library
    keyword and ``ConfigOverrides``. *where* is the stage: a
    :class:`~pitloom.messages.config.ConfigPlace` (a configuration file)
    raises ``config-invalid``, a :class:`~pitloom.messages.config.Parameter`
    (a library caller's value) ``option-invalid``. Any
    :func:`operator.index`-able integer (a ``numpy.int64``) passes; a ``bool``
    or a ``float`` does not.

    Zero is not "unlimited": a ceiling is a safety limit, so a spelled-out
    large number is the only way to raise it.

    Raises:
        TypeError: at a ``Parameter`` stage, *value* is not an integer
            (a :class:`~pitloom.messages.CodedTypeError`).
        ValueError: *value* is an integer that is not positive, or any
            invalid value from a file (``config-invalid``); a
            :class:`~pitloom.messages.CodedValueError`.
    """
    problem = positive_problem(value)
    if problem is not None:
        raise invalid_value(where, problem, got=value)
    return operator.index(value)  # type: ignore[arg-type]


def require_max_model_extract_bytes(
    value: object,
    where: ConfigPlace | Parameter = _MODEL_EXTRACT_PLACE,
) -> int:
    """``max-model-extract-bytes`` (see :func:`require_positive_ceiling`)."""
    return require_positive_ceiling(value, where)


def require_max_dataset_hash_bytes(
    value: object,
    where: ConfigPlace | Parameter = _DATASET_HASH_PLACE,
) -> int:
    """``max-dataset-hash-bytes`` (see :func:`require_positive_ceiling`)."""
    return require_positive_ceiling(value, where)


def require_max_download_bytes(
    value: object,
    where: ConfigPlace | Parameter = _DOWNLOAD_PLACE,
) -> int:
    """``max-download-bytes`` (see :func:`require_positive_ceiling`)."""
    return require_positive_ceiling(value, where)
