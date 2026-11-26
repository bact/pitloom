# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The usage hint: a summary (an ``INFO:`` line of no condition, no code)
that names how the surface that runs turns the scan on, per target.

See also: tests/assemble/test_scan_model_usage.py (when it is said).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.extract.scanner import scan_ai_models
from pitloom.messages import (
    SUMMARIES,
    SURFACE_CLI,
    SURFACE_HOOK,
    SURFACE_LIBRARY,
    advice_surface,
)
from pitloom.messages.models import (
    USAGE_HINTS,
    USAGE_TARGET_PROJECT,
    USAGE_TARGET_WHEEL,
)

_FOUND = "Found 2 AI model file(s); "
_END = " to also record which Python files reference them."


@pytest.mark.parametrize(
    ("target", "surface", "how"),
    [
        (
            USAGE_TARGET_PROJECT,
            SURFACE_CLI,
            "pass --scan-model-usage (or set scan-model-usage = true)",
        ),
        (
            USAGE_TARGET_PROJECT,
            SURFACE_LIBRARY,
            "pass scan_model_usage=True (or set scan-model-usage = true)",
        ),
        (
            USAGE_TARGET_PROJECT,
            SURFACE_HOOK,
            "set scan-model-usage = true in [tool.pitloom]",
        ),
        (
            USAGE_TARGET_WHEEL,
            SURFACE_CLI,
            "pass --scan-model-usage (or set scan-model-usage = true in a "
            "--config file)",
        ),
        (
            USAGE_TARGET_WHEEL,
            SURFACE_LIBRARY,
            "pass scan_model_usage=True (or set scan-model-usage = true in "
            "pitloom_config)",
        ),
    ],
    ids=[
        "project-cli",
        "project-library",
        "project-hook",
        "wheel-cli",
        "wheel-library",
    ],
)
def test_the_hint_names_the_surface_s_way_to_turn_the_scan_on(
    target: str,
    surface: str,
    how: str,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pitloom.extract.scanner.discover_ai_models", lambda _: [object(), object()]
    )
    with caplog.at_level(logging.INFO, logger="pitloom"), advice_surface(surface):
        scan_ai_models(
            [], [], scan_usage=False, usage_hint=lambda: True, usage_target=target
        )
    (record,) = caplog.records
    assert record.levelno == logging.INFO
    assert record.getMessage() == f"{_FOUND}{how}{_END}"
    assert getattr(record, "pitloom_code", None) is None
    assert USAGE_HINTS[target].current() in SUMMARIES


def test_no_two_hints_say_the_same() -> None:
    members = [s for twins in USAGE_HINTS.values() for s in twins.members]
    assert len({s.template for s in members}) == len(members) == 5
