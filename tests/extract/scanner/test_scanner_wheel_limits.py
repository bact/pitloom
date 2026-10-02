# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The wheel scan's per-wheel extraction budget and the wording of a
termination signal during the copy.

See also: :mod:`tests.extract.scanner.test_scanner_wheel_security` (the
per-model ceiling and cleanup).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import io
import signal
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.scanner_wheel import BUDGET_FACTOR, scan_wheel_for_ai_models
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.build_and_read_shared import (
    deliver_sigterm,
    spied_raise_signal,
    use_sys_tmp,
)
from tests.warning_helpers import logged_warnings

_POSIX = sys.platform != "win32"
_MODEL = safetensors_bytes(extra=50)
_SIZE = len(_MODEL)
_CEILING = _SIZE + 200
_TINY = safetensors_bytes()
_TINY_NAME = "demo/z-tiny.safetensors"
_NAMES = [f"demo/m{i:02d}.safetensors" for i in range(12)]


def _scan(wheel: Path, max_bytes: int = _CEILING) -> list[Any]:
    return scan_wheel_for_ai_models(
        wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=max_bytes
    )


def _read_count(models: list[Any]) -> int:
    """How many models had their metadata read (a stub has no provenance)."""
    return sum(bool(m.provenance) for m in models)


def test_models_past_the_budget_are_format_only_with_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, copies: list[Path]
) -> None:
    members = {**dict.fromkeys(_NAMES, _MODEL), _TINY_NAME: _TINY}
    wheel = write_model_wheel(tmp_path, members)
    models = _scan(wheel)
    budget = BUDGET_FACTOR * _CEILING
    fits = budget // _SIZE
    # Not vacuous: the tiny model, last in order, would fit what is left.
    assert fits < len(_NAMES)
    assert fits * _SIZE + len(_TINY) <= budget
    assert [m.format_info.file_path_relative for m in models] == [*_NAMES, _TINY_NAME]
    assert [bool(m.provenance) for m in models] == [True] * fits + [False] * (
        len(_NAMES) - fits + 1
    )
    assert len(copies) == fits  # a model past the budget is not even started
    (message,) = logged_warnings(caplog)
    assert f"per-wheel budget of {budget} bytes" in message
    assert message.startswith("AI model scan: ")


def test_a_wheel_within_the_budget_reads_every_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    wheel = write_model_wheel(tmp_path, dict.fromkeys(_NAMES[:4], _MODEL))
    assert _read_count(_scan(wheel)) == 4
    assert not logged_warnings(caplog)


def test_the_budget_counts_bytes_read_not_bytes_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Each copy's stream holds more than its member declares, so the
    declared-size prefilter passes; the running count stops the copy
    mid-member (kills: no count while copying)."""
    big = safetensors_bytes(extra=90)
    ceiling = len(big) + 10
    wheel = write_model_wheel(tmp_path, dict.fromkeys(_NAMES, _MODEL))
    real_open = zipfile.ZipFile.open
    opens: dict[str, int] = {}

    def lying_open(self: zipfile.ZipFile, name: Any, *a: Any, **k: Any) -> Any:
        key = getattr(name, "filename", name)
        opens[key] = opens.get(key, 0) + 1
        if opens[key] == 2:  # the copy's open, not the header sniff's
            return io.BytesIO(big)
        return real_open(self, name, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "open", lying_open)
    models = _scan(wheel, ceiling)
    fits = (BUDGET_FACTOR * ceiling) // len(big)
    assert len(models) == len(_NAMES)
    assert _read_count(models) == fits < len(_NAMES)
    (message,) = logged_warnings(caplog)
    assert "per-wheel budget" in message


@pytest.mark.parametrize(
    ("ceiling", "read"), [(_SIZE, True), (_SIZE - 1, False)], ids=["at", "over"]
)
def test_a_model_of_exactly_the_ceiling_is_read(
    ceiling: int,
    read: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    copies: list[Path],
) -> None:
    """The ceiling is inclusive, declared and actually read alike."""
    wheel = write_model_wheel(tmp_path, {_NAMES[0]: _MODEL})
    # pylint: disable-next=unbalanced-tuple-unpacking
    (model,) = _scan(wheel, ceiling)
    assert bool(model.provenance) is read
    assert len(copies) == (1 if read else 0)  # over: refused before the copy
    assert len(logged_warnings(caplog)) == (0 if read else 1)


@pytest.mark.parametrize("count", [BUDGET_FACTOR, BUDGET_FACTOR + 1])
def test_models_totalling_exactly_the_budget_are_all_read(
    count: int, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The budget is inclusive: ``BUDGET_FACTOR`` models of the ceiling's size
    spend all of it and are read; one more is not."""
    wheel = write_model_wheel(tmp_path, dict.fromkeys(_NAMES[:count], _MODEL))
    models = _scan(wheel, _SIZE)
    assert len(models) == count
    assert _read_count(models) == BUDGET_FACTOR
    messages = logged_warnings(caplog)
    assert len(messages) == (count - BUDGET_FACTOR)  # none, then one
    assert all("per-wheel budget" in m for m in messages)


def test_the_budget_is_per_wheel(tmp_path: Path) -> None:
    wheels = [
        write_model_wheel(tmp_path / str(i), dict.fromkeys(_NAMES[:4], _MODEL))
        for i in range(2)
    ]
    assert [_read_count(_scan(w)) for w in wheels] == [4, 4]


@pytest.fixture(name="sys_tmp")
def fixture_sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


def _scan_dirs(sys_tmp: Path) -> list[Path]:
    return [d for d in sys_tmp.iterdir() if d.name.startswith("pitloom-model-scan-")]


@pytest.mark.skipif(not _POSIX, reason="signal handling is POSIX-only here")
def test_sigterm_during_the_copy_waits_for_it_and_says_during(
    tmp_path: Path,
    sys_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The hold spans the copy, so the message's "during" is true and the copy
    stops at once instead of finishing first."""
    wheel = write_model_wheel(tmp_path / "d", {_NAMES[0]: _MODEL})
    real_open = zipfile.ZipFile.open
    chunks: list[int] = []

    def signalling_open(self: zipfile.ZipFile, name: Any, *a: Any, **k: Any) -> Any:
        # The stream is returned to the caller, which closes it.
        # pylint: disable-next=consider-using-with
        stream = real_open(self, name, *a, **k)
        if not scanner_wheel_is_copying():
            return stream
        real_read = stream.read

        def read(size: int = -1) -> bytes:
            chunks.append(size)
            if len(chunks) == 1:
                deliver_sigterm()
            return real_read(size)

        stream.read = read  # type: ignore[method-assign]
        return stream

    def scanner_wheel_is_copying() -> bool:
        return bool(_scan_dirs(sys_tmp))

    monkeypatch.setattr(zipfile.ZipFile, "open", signalling_open)
    with spied_raise_signal(monkeypatch) as spy:
        with pytest.raises(SystemExit) as excinfo:
            _scan(wheel)
    assert excinfo.value.code == 128 + signal.SIGTERM
    spy.assert_called_once_with(signal.SIGTERM)
    assert len(chunks) == 1  # stopped at the next chunk, not run to the end
    assert not _scan_dirs(sys_tmp)
    (message,) = [m for m in logged_warnings(caplog) if "SIGTERM" in m]
    assert message == (
        "AI model scan: received SIGTERM during the AI model file copy "
        "-- exiting after cleanup"
    )


@pytest.mark.skipif(not _POSIX, reason="signal handling is POSIX-only here")
def test_sigterm_while_the_copy_is_parsed_says_after(
    tmp_path: Path,
    sys_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def read(*_a: Any, **_k: Any) -> None:
        deliver_sigterm()
        pytest.fail("the signal did not end the scan")

    monkeypatch.setattr("pitloom.extract.scanner.read_ai_model", read)
    wheel = write_model_wheel(tmp_path / "d", {_NAMES[0]: _MODEL})
    with spied_raise_signal(monkeypatch), pytest.raises(SystemExit):
        _scan(wheel)
    assert not _scan_dirs(sys_tmp)
    (message,) = [m for m in logged_warnings(caplog) if "SIGTERM" in m]
    assert "received SIGTERM after the AI model file copy" in message


@pytest.mark.parametrize("value", [0, -1, True, "64"])
def test_a_bad_ceiling_names_pitloom_config_not_a_toml_table(
    tmp_path: Path, value: Any
) -> None:
    with pytest.raises(ValueError, match="pitloom_config") as err:
        _scan(tmp_path / "absent.whl", max_bytes=value)
    assert "[tool.pitloom]" not in str(err.value)
