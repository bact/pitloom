# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A native loader is never run on a wheel's files unless the caller trusts
the wheel: the fastText model keeps a format-only entry and one ``INFO:``
names ``--trust-wheel-model``.

See also: :mod:`tests.assemble.test_trust_wheel_model` (every surface),
:mod:`tests.extract.scanner.test_scanner_wheel` (the producer).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract import scanner_wheel
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from tests._wheel_models import safetensors_bytes, write_model_wheel

fasttext = pytest.importorskip("fasttext")

_FASTTEXT = Path(__file__).parents[2] / "fixtures" / "aimodels" / "fasttext"
_NAMES = ["sentimentdemo.bin", "lid.176.ftz"]
_INFO = "--trust-wheel-model"


def spy_load_model(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """Replace ``fasttext.load_model`` with an autospec'd spy of the real one."""
    spy: mock.Mock = mock.create_autospec(
        fasttext.load_model, side_effect=fasttext.load_model
    )
    monkeypatch.setattr(fasttext, "load_model", spy)
    return spy


def gate_infos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.INFO and _INFO in r.getMessage()
    ]


def _wheel(tmp_path: Path, names: list[str]) -> Path:
    members = {f"demo/{n}": (_FASTTEXT / n).read_bytes() for n in names}
    members["demo/t.safetensors"] = safetensors_bytes(metadata={"k": "v"})
    return write_model_wheel(tmp_path / "dist", members)


def _scan(
    wheel: Path,
    *,
    trust: bool = False,
    gate_hint: Callable[[], bool] = lambda: True,
) -> list[tuple[str, bool]]:
    """(format, whether it carries metadata) per model, in result order."""
    models = scan_wheel_for_ai_models(
        wheel,
        scan_usage=False,
        usage_hint=lambda: False,
        max_bytes=10**8,
        trust=trust,
        gate_hint=gate_hint,
    )
    return [
        (str(m.format_info.model_format), bool(m.hyperparameters or m.properties))
        for m in models
    ]


def test_default_lists_fasttext_without_loading_it_and_says_so_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    spy = spy_load_model(monkeypatch)
    caplog.set_level(logging.INFO)
    found = _scan(_wheel(tmp_path, _NAMES))
    spy.assert_not_called()
    assert sorted(found) == [
        ("fasttext", False),
        ("fasttext", False),
        ("safetensors", True),  # no other format is gated
    ]
    assert len(gate_infos(caplog)) == 1  # two gated models, one line


def test_trust_runs_the_loader_on_every_fasttext_member_quietly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    spy = spy_load_model(monkeypatch)
    caplog.set_level(logging.INFO)
    found = _scan(_wheel(tmp_path, _NAMES), trust=True)
    assert spy.call_count == len(_NAMES)
    assert sorted(found) == [
        ("fasttext", True),
        ("fasttext", True),
        ("safetensors", True),
    ]
    assert gate_infos(caplog) == []


@pytest.mark.parametrize(("claims", "lines"), [(True, 1), (False, 0)])
def test_the_info_follows_the_callers_once_per_run_claim(
    claims: bool,
    lines: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A batch's later wheels get ``False`` from the claim: still gated,
    no second line."""
    spy = spy_load_model(monkeypatch)
    caplog.set_level(logging.INFO)
    found = _scan(_wheel(tmp_path, _NAMES[:1]), gate_hint=lambda: claims)
    spy.assert_not_called()
    assert ("fasttext", False) in found
    assert len(gate_infos(caplog)) == lines


def test_a_wheel_without_a_gated_model_claims_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    claimed: list[bool] = []

    def claim() -> bool:
        claimed.append(True)
        return True

    _scan(_wheel(tmp_path, []), gate_hint=claim)
    assert not claimed
    assert gate_infos(caplog) == []


def test_the_gate_is_a_set_of_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another format joins by being in the set; nothing else changes."""
    assert AiModelFormat.FASTTEXT in scanner_wheel.WHEEL_GATED_FORMATS
    monkeypatch.setattr(
        scanner_wheel, "WHEEL_GATED_FORMATS", frozenset({AiModelFormat.SAFETENSORS})
    )
    spy = spy_load_model(monkeypatch)
    found = _scan(_wheel(tmp_path, _NAMES[:1]))
    spy.assert_called_once()
    assert sorted(found) == [("fasttext", True), ("safetensors", False)]
