# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The text a model file states in a field: a blank one states nothing.

One rule for every reader (GGUF, Safetensors, ONNX), so an empty or
white-space-only string reads as absent, and a cascade of keys moves on to
the next candidate.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pitloom.core.ai_metadata import value_text


def stated_text(value: Any, *, scalar: bool = False) -> str | None:
    """*value* stripped, or ``None`` when absent or blank. Only a string
    counts, unless *scalar*: then a number is its text too (a version may
    be written as one). A bool never counts."""
    if isinstance(value, str):
        text = value.strip()
    elif scalar and isinstance(value, (int, float)) and not isinstance(value, bool):
        text = value_text(value)
    else:
        return None
    return text or None


def first_stated_text(
    fields: Mapping[str, Any], keys: Iterable[str]
) -> tuple[str, str] | None:
    """``(key, text)`` of the first of *keys* in *fields* whose value is
    :func:`stated_text`, or ``None``. A blank value gives way to the next
    key."""
    for key in keys:
        text = stated_text(fields.get(key))
        if text:
            return key, text
    return None
