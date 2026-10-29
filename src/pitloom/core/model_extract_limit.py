# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Validation of the byte ceilings ``max-model-extract-bytes`` and
``max-dataset-hash-bytes``.

One validator for the config reader and for each consumer, which also
receives the value from a library caller's
:class:`~pitloom.core.config.PitloomConfig`, never parsed.

See also: :mod:`pitloom.core._config_parse_scan`,
:mod:`pitloom.extract.scanner_wheel` and :mod:`pitloom._loom_active_run`.
"""

from __future__ import annotations

import operator

__all__ = [
    "MAX_DATASET_HASH_BYTES_KEY",
    "MAX_MODEL_EXTRACT_BYTES_KEY",
    "require_max_dataset_hash_bytes",
    "require_max_model_extract_bytes",
    "require_positive_ceiling",
]

MAX_MODEL_EXTRACT_BYTES_KEY = "max-model-extract-bytes"
MAX_DATASET_HASH_BYTES_KEY = "max-dataset-hash-bytes"


def require_positive_ceiling(value: object, label: str) -> int:
    """*value* as an ``int`` when it is an integer of at least 1.

    The one validator for every surface that takes a ceiling: the config
    key, the command-line flag, the library keyword and ``ConfigOverrides``.
    *label* names the setting in the error, e.g.
    ``[tool.pitloom] 'max-model-extract-bytes'``; ``""`` leaves the message
    to a caller that names the setting itself. Any :func:`operator.index`-able
    integer (a ``numpy.int64``) passes; a ``bool`` or a ``float`` does not.

    Zero is not "unlimited": a ceiling is a safety limit, so a spelled-out
    large number is the only way to raise it.

    Raises:
        ValueError: *value* is not an integer, or is not positive.
    """
    try:
        if isinstance(value, bool):
            raise TypeError
        number = operator.index(value)  # type: ignore[arg-type]
    except TypeError:
        raise ValueError(
            f"{label} must be an integer, got {type(value).__name__}: {value!r}".strip()
        ) from None
    if number <= 0:
        raise ValueError(f"{label} must be a positive integer, got {number}".strip())
    return number


def require_max_model_extract_bytes(
    value: object, table_path: str = "[tool.pitloom]"
) -> int:
    """``max-model-extract-bytes`` (see :func:`require_positive_ceiling`)."""
    return require_positive_ceiling(
        value, f"{table_path} {MAX_MODEL_EXTRACT_BYTES_KEY!r}"
    )


def require_max_dataset_hash_bytes(
    value: object, table_path: str = "[tool.pitloom]"
) -> int:
    """``max-dataset-hash-bytes`` (see :func:`require_positive_ceiling`)."""
    return require_positive_ceiling(
        value, f"{table_path} {MAX_DATASET_HASH_BYTES_KEY!r}"
    )
