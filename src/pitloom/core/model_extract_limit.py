# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Validation of ``max-model-extract-bytes``.

One validator for the config reader and for the wheel scan, which also
receives the value from a library caller's
:class:`~pitloom.core.config.PitloomConfig`, never parsed.

See also: :mod:`pitloom.core._config_parse_scan` and
:mod:`pitloom.extract.scanner_wheel`.
"""

from __future__ import annotations

_KEY = "max-model-extract-bytes"


def require_max_model_extract_bytes(
    value: object, table_path: str = "[tool.pitloom]"
) -> int:
    """*value* when it is a positive ``int``.

    Zero is not "unlimited": this is a safety ceiling, so a spelled-out
    large number is the only way to raise it.

    Raises:
        ValueError: *value* is a ``bool``, not an ``int``, or not positive.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"{table_path} {_KEY!r} must be an integer, got "
            f"{type(value).__name__}: {value!r}"
        )
    if value <= 0:
        raise ValueError(
            f"{table_path} {_KEY!r} must be a positive integer, got {value}"
        )
    return value
