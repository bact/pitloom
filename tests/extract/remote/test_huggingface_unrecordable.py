# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The G7 honesty notice for a Hugging Face model: once when
``config.json`` states an architecture, nothing when it does not.

See also: tests/extract/ai_model/test_unrecordable.py (the line, the model
file readers, the CLI).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from typing import Any

import pytest

from pitloom.extract.ai_model.unrecordable import NOTICE_LEVEL, NOTICE_TEXT
from pitloom.extract.remote.huggingface import read_huggingface
from tests.extract.remote.hf_patches._hf_patches_base import (
    _MISTRAL_CONFIG,
    _patch_hf_calls,
)

_NO_ARCHITECTURE = {k: v for k, v in _MISTRAL_CONFIG.items() if k != "architectures"}


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            _MISTRAL_CONFIG,
            [
                "FORMAT=huggingface FILE=https://huggingface.co/o/model: "
                f"{NOTICE_TEXT}: model-architecture (written in ai_typeOfModel)"
            ],
        ),
        (_NO_ARCHITECTURE, []),
        (None, []),
    ],
    ids=["architecture", "no-architecture", "no-config"],
)
def test_a_hub_model_logs_the_notice_once_or_not_at_all(
    config: dict[str, Any] | None,
    expected: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="pitloom.extract.ai_model.unrecordable")
    with _patch_hf_calls(config=config):
        meta = read_huggingface("o/model")
    assert bool(meta.architecture) is bool(expected)
    notices = [r for r in caplog.records if NOTICE_TEXT in r.getMessage()]
    assert [r.getMessage() for r in notices] == expected
    assert all(r.levelno == NOTICE_LEVEL for r in notices)
