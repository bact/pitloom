# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The usage hint: a summary (an ``INFO:`` line of no condition, no code),
its text unchanged, the setting spelt per producer.

See also: tests/assemble/test_scan_model_usage.py (when it is said).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.extract.scanner import scan_ai_models
from pitloom.messages import SUMMARIES
from pitloom.messages.models import (
    USAGE_HINTS,
    USAGE_SETTING_PROJECT,
    USAGE_SETTING_WHEEL,
)


@pytest.mark.parametrize(
    "setting", [USAGE_SETTING_PROJECT, USAGE_SETTING_WHEEL], ids=["project", "wheel"]
)
def test_the_hint_is_an_uncoded_summary_of_unchanged_text(
    setting: str, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pitloom.extract.scanner.discover_ai_models", lambda _: [object(), object()]
    )
    with caplog.at_level(logging.INFO, logger="pitloom"):
        scan_ai_models(
            [], [], scan_usage=False, usage_hint=lambda: True, usage_setting=setting
        )
    (record,) = caplog.records
    assert record.levelno == logging.INFO
    assert record.getMessage() == (
        f"Found 2 AI model file(s); pass --scan-model-usage (or set {setting}) "
        "to also record which Python files reference them."
    )
    assert getattr(record, "pitloom_code", None) is None
    assert USAGE_HINTS[setting] in SUMMARIES
