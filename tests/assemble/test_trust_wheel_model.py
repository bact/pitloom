# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``--trust-wheel-model`` on every surface that reads a built wheel.

By default a fastText model in a wheel is listed without metadata (its native
loader is never called) and one ``INFO:`` per run names the flag; with the
flag (``trust_wheel_model=True``; for ``embed_wheel_sbom()`` the
``ConfigOverrides`` field) the loader runs. A project scan is not gated, and
the flag there warns once that it has no effect. There is no config key.

See also: :mod:`tests.extract.scanner.test_scanner_wheel_gate_formats` (the
gate), ``tests/cli/test_cli_option_reach.py`` (the flag on every other kind).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate, generate_wheel_sbom
from pitloom.embed import ConfigOverrides, embed_wheel_sbom
from tests._wheel_models import write_model_wheel
from tests.assemble.embed_surfaces_shared import demo_project, run_cli
from tests.assemble.test_scan_model_usage import _embedded
from tests.extract.scanner.test_scanner_wheel_gate_formats import (
    FASTTEXT_DIR,
    fixture_bytes,
    gate_infos,
    spy_load_model,
)
from tests.warning_helpers import count_naming, logged_warnings

_MEMBER = "demo/sentimentdemo.bin"
_FLAG = "--trust-wheel-model"
_Runner = Callable[[Path, pytest.MonkeyPatch, bool], str]  # -> SBOM json


def _wheel(directory: Path, name: str = "demo") -> Path:
    data = (FASTTEXT_DIR / "sentimentdemo.bin").read_bytes()
    return write_model_wheel(directory, {_MEMBER: data}, name=name)


def _argv(trust: bool) -> list[str]:
    return [_FLAG] if trust else []


def _cli_wheel(tmp: Path, mp: pytest.MonkeyPatch, trust: bool) -> str:
    out = tmp / "out.json"
    argv = ["wheel", str(_wheel(tmp / "d")), "-o", str(out), "--offline"]
    run_cli([*argv, *_argv(trust)], mp)
    return out.read_text(encoding="utf-8")


def _cli_wheel_embed(tmp: Path, mp: pytest.MonkeyPatch, trust: bool) -> str:
    wheel = _wheel(tmp / "d")
    run_cli(["wheel", str(wheel), "--embed", "--offline", *_argv(trust)], mp)
    return _embedded(wheel)


def _cli_embed_wheel(tmp: Path, mp: pytest.MonkeyPatch, trust: bool) -> str:
    wheel = _wheel(tmp / "d")
    run_cli(["embed-wheel", str(wheel), "--offline", *_argv(trust)], mp)
    return _embedded(wheel)


def _cli_generate(tmp: Path, mp: pytest.MonkeyPatch, trust: bool) -> str:
    out = tmp / "out.json"
    argv = ["generate", str(_wheel(tmp / "d")), "-o", str(out), "--offline"]
    run_cli([*argv, *_argv(trust)], mp)
    return out.read_text(encoding="utf-8")


def _lib_generate(tmp: Path, _mp: pytest.MonkeyPatch, trust: bool) -> str:
    return generate(_wheel(tmp / "d"), offline=True, trust_wheel_model=trust)


def _lib_wheel(tmp: Path, _mp: pytest.MonkeyPatch, trust: bool) -> str:
    return generate_wheel_sbom(_wheel(tmp / "d"), offline=True, trust_wheel_model=trust)


def _lib_embed(tmp: Path, _mp: pytest.MonkeyPatch, trust: bool) -> str:
    wheel = _wheel(tmp / "d")
    overrides = ConfigOverrides(offline=True, trust_wheel_model=trust or None)
    embed_wheel_sbom(wheel, overrides=overrides)
    return _embedded(wheel)


_SURFACES: dict[str, _Runner] = {
    "cli-wheel": _cli_wheel,
    "cli-wheel-embed": _cli_wheel_embed,
    "cli-embed-wheel": _cli_embed_wheel,
    "cli-generate": _cli_generate,
    "lib-generate": _lib_generate,
    "lib-generate_wheel_sbom": _lib_wheel,
    "lib-embed_wheel_sbom": _lib_embed,
}


def _hyperparameters(sbom: str) -> bool:
    """Whether the SBOM's AI package carries the model's read metadata."""
    packages = [e for e in json.loads(sbom)["@graph"] if e["type"] == "ai_AIPackage"]
    assert len(packages) == 1  # listed either way
    return any(key.startswith("ai_hyperparameter") for key in packages[0])


@pytest.mark.parametrize("surface", _SURFACES)
def test_a_wheels_fasttext_model_is_read_only_when_trusted(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.INFO)
    spy = spy_load_model(monkeypatch)
    run = _SURFACES[surface]

    gated = run(tmp_path / "gated", monkeypatch, False)
    spy.assert_not_called()
    assert not _hyperparameters(gated)
    assert len(gate_infos(caplog)) == 1

    caplog.clear()
    trusted = run(tmp_path / "trusted", monkeypatch, True)
    spy.assert_called_once()
    assert _hyperparameters(trusted)
    assert gate_infos(caplog) == []
    assert not [w for w in logged_warnings(caplog) if "has no effect" in w]


def test_a_batch_says_so_once_and_gates_every_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    spy = spy_load_model(monkeypatch)
    wheels = [_wheel(tmp_path / n, name=n) for n in ("a", "b", "c")]
    run_cli(["embed-wheel", *map(str, wheels), "--offline"], monkeypatch)
    spy.assert_not_called()
    assert len(gate_infos(caplog)) == 1
    assert [_hyperparameters(_embedded(w)) for w in wheels] == [False] * 3


def test_a_batch_names_each_gated_format_once_across_its_wheels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: one slot per batch named only the first wheel's gated
    formats; a later wheel's different format got no notice."""
    caplog.set_level(logging.INFO)
    models = {
        "a": "gguf/stories260K.gguf",
        "b": "onnx/light-inception-v2.onnx",
        "c": "gguf/stories260K.gguf",  # already announced
    }
    wheels = [
        write_model_wheel(
            tmp_path / n, {f"demo/{Path(m).name}": fixture_bytes(m)}, name=n
        )
        for n, m in models.items()
    ]
    run_cli(["embed-wheel", *map(str, wheels), "--offline"], monkeypatch)
    named = [re.search(r": ([a-z0-9, ]+)\. Pass ", line) for line in gate_infos(caplog)]
    # Sorted, so that the order the wheels finish in does not matter.
    assert sorted(m.group(1) for m in named if m) == ["gguf", "onnx"]
    assert [_hyperparameters(_embedded(w)) for w in wheels] == [False] * 3


def test_a_project_scan_is_not_gated_and_the_flag_warns_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    spy = spy_load_model(monkeypatch)
    project = demo_project(tmp_path)
    data = (FASTTEXT_DIR / "sentimentdemo.bin").read_bytes()
    (project / _MEMBER).write_bytes(data)
    out = tmp_path / "out.json"
    argv = ["project", str(project), "-o", str(out), "--offline", _FLAG]
    run_cli(argv, monkeypatch)
    spy.assert_called_once()
    assert _hyperparameters(out.read_text(encoding="utf-8"))
    assert count_naming(logged_warnings(caplog), _FLAG) == 1
    assert gate_infos(caplog) == []
