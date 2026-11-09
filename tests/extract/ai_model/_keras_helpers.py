# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared pieces of the Keras config tests (``test_keras_config*.py``): the
sample members and :func:`read`, which reads a ``.keras`` archive built from
them.

See also: test_keras_config.py, test_keras_config_members.py and
test_keras_config_parse_failure.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.extract.ai_model.keras import read_keras
from tests.extract.ai_model.zip_builders import dated_zip

SOURCE = "Source: m.keras | Field: "
META = {"keras_version": "3.5.0", "date_saved": "2026-01-01@00:00:00"}
MODEL = {"class_name": "Sequential", "config": {"name": "m", "units": 2}}
ADAM = {
    "module": "keras.optimizers",
    "class_name": "Adam",
    "config": {"name": "adam", "learning_rate": 0.001},
    "registered_name": None,
}


def body(value: Any) -> bytes:
    """*value* as the bytes of a JSON member (bytes are kept as they are)."""
    return value if isinstance(value, bytes) else json.dumps(value).encode()


def read(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    config: Any = None,
    metadata: Any = None,
) -> tuple[AiModelMetadata, list[str]]:
    """Read a ``.keras`` archive of the members given (``None``: absent), and
    the warnings it logged."""
    files = {
        name: body(value)
        for name, value in (("metadata.json", metadata), ("config.json", config))
        if value is not None
    }
    path = tmp_path / "m.keras"
    path.write_bytes(dated_zip(files))
    with caplog.at_level(logging.WARNING):
        meta = read_keras(path)
    return meta, [r.getMessage() for r in caplog.records]
