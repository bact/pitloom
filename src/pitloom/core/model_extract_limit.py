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

__all__ = [
    "MAX_DATASET_HASH_BYTES_KEY",
    "MAX_MODEL_EXTRACT_BYTES_KEY",
    "require_max_dataset_hash_bytes",
    "require_max_model_extract_bytes",
    "require_positive_ceiling",
]

MAX_MODEL_EXTRACT_BYTES_KEY = "max-model-extract-bytes"
MAX_DATASET_HASH_BYTES_KEY = "max-dataset-hash-bytes"


def require_positive_ceiling(
    value: object, key: str, table_path: str = "[tool.pitloom]"
) -> int:
    """*value* when it is a positive ``int``; errors name *key* in
    *table_path*.

    Zero is not "unlimited": a ceiling is a safety limit, so a spelled-out
    large number is the only way to raise it.

    Raises:
        ValueError: *value* is a ``bool``, not an ``int``, or not positive.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"{table_path} {key!r} must be an integer, got "
            f"{type(value).__name__}: {value!r}"
        )
    if value <= 0:
        raise ValueError(
            f"{table_path} {key!r} must be a positive integer, got {value}"
        )
    return value


def require_max_model_extract_bytes(
    value: object, table_path: str = "[tool.pitloom]"
) -> int:
    """``max-model-extract-bytes`` (see :func:`require_positive_ceiling`)."""
    return require_positive_ceiling(value, MAX_MODEL_EXTRACT_BYTES_KEY, table_path)


def require_max_dataset_hash_bytes(
    value: object, table_path: str = "[tool.pitloom]"
) -> int:
    """``max-dataset-hash-bytes`` (see :func:`require_positive_ceiling`)."""
    return require_positive_ceiling(value, MAX_DATASET_HASH_BYTES_KEY, table_path)
