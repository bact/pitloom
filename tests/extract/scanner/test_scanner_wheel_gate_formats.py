# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The formats gated in a wheel: fastText (a native loader), GGUF (a Python
loop per element), HDF5 (libhdf5 crashes and hangs on hostile files), ONNX
(protobuf amplification) and PyTorch ``.pt``/``.pth`` (fickling
amplification). Default wheel scan: format-only entry, reader never run, one
``INFO:`` listing the gated formats met that the caller's per-format claim
accepts; ``--trust-wheel-model`` runs the readers.

See also: :mod:`tests.assemble.test_trust_wheel_model` (every surface) and
:mod:`tests.fixtures.aimodels` README (the hostile files).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.project import ProjectFile
from pitloom.extract import scanner, scanner_wheel
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.scanner import ReaderGate
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.extract.scanner_wheel import WHEEL_GATED_FORMATS, scan_wheel_for_ai_models
from tests._wheel_models import safetensors_bytes, write_model_wheel

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "aimodels"
FASTTEXT_DIR = _FIXTURES / "fasttext"
_FASTTEXT = ["fasttext/sentimentdemo.bin", "fasttext/lid.176.ftz"]
_HOSTILE = ["hostile/hdf5-segfault.h5", "hostile/hdf5-hang.h5"]
_GATED = {
    "fasttext/sentimentdemo.bin": "fasttext",
    "fasttext/lid.176.ftz": "fasttext",
    "gguf/stories260K.gguf": "gguf",
    "hdf5/example-model.h5": "hdf5",
    "onnx/light-inception-v2.onnx": "onnx",
    "pytorch/example-model.pt": "pytorch",
    "pytorch/example-model.pth": "pytorch",
}
_TRUST = "--trust-wheel-model"


def fixture_bytes(name: str) -> bytes:
    path = _FIXTURES / name
    if not path.is_file():
        pytest.skip(f"{name} is not in this checkout")
    return path.read_bytes()


def _wheel(tmp_path: Path, names: list[str]) -> Path:
    members = {f"demo/{Path(n).name}": fixture_bytes(n) for n in names}
    members["demo/t.safetensors"] = safetensors_bytes(metadata={"k": "v"})
    return write_model_wheel(tmp_path / "dist", members)


def spy_load_model(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """Replace ``fasttext.load_model`` with an autospec'd spy of the real one."""
    fasttext = pytest.importorskip("fasttext")
    spy: mock.Mock = mock.create_autospec(
        fasttext.load_model, side_effect=fasttext.load_model
    )
    monkeypatch.setattr(fasttext, "load_model", spy)
    return spy


def _scan(
    wheel: Path,
    *,
    trust: bool = False,
    gate_hint: Callable[[AiModelFormat], bool] = lambda _fmt: True,
) -> list[AiModelMetadata]:
    return scan_wheel_for_ai_models(
        wheel,
        scan_usage=False,
        usage_hint=lambda: False,
        max_bytes=10**8,
        trust=trust,
        gate_hint=gate_hint,
    )


def gate_infos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.INFO and _TRUST in r.getMessage()
    ]


def test_the_gated_set() -> None:
    assert WHEEL_GATED_FORMATS == {
        AiModelFormat.FASTTEXT,
        AiModelFormat.GGUF,
        AiModelFormat.HDF5,
        AiModelFormat.ONNX,
        AiModelFormat.PYTORCH,
    }


def test_default_lists_every_gated_format_without_reading_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    with mock.patch.object(scanner, "read_ai_model", wraps=read_ai_model) as spy:
        models = _scan(_wheel(tmp_path, list(_GATED)))
    formats = sorted(str(m.format_info.model_format) for m in models)
    assert formats == [
        *["fasttext"] * 2,
        *["gguf", "hdf5", "onnx", "pytorch", "pytorch", "safetensors"],
    ]
    assert [c.args[0].suffix for c in spy.call_args_list] == [".safetensors"]
    for model in models:
        if str(model.format_info.model_format) != "safetensors":
            assert not model.provenance  # format-only
    (info,) = gate_infos(caplog)  # seven gated models, one line
    assert ": fasttext, gguf, hdf5, onnx, pytorch. " in info  # sorted, each once


def test_a_failed_scan_reports_no_gate_but_still_removes_its_scratch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No SBOM is written on failure, so no line says what it lists."""
    caplog.set_level(logging.INFO)
    wheel = _wheel(tmp_path, ["onnx/light-inception-v2.onnx"])
    with (
        mock.patch.object(
            scanner, "attach_usage_references", side_effect=RuntimeError("scan failed")
        ),
        mock.patch.object(scanner_wheel._Scratch, "remove", autospec=True) as remove,
    ):
        with pytest.raises(RuntimeError, match="scan failed"):
            scan_wheel_for_ai_models(
                wheel, scan_usage=True, usage_hint=lambda: False, max_bytes=10**8
            )
    assert not gate_infos(caplog)
    remove.assert_called_once()


def test_a_successful_scan_reports_the_gate_after_removing_its_scratch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    wheel = _wheel(tmp_path, ["onnx/light-inception-v2.onnx"])
    order: list[str] = []
    real_remove, real_report = scanner_wheel._Scratch.remove, ReaderGate.report

    def remove(self: scanner_wheel._Scratch) -> None:
        order.append("remove")
        real_remove(self)

    def report(self: ReaderGate) -> None:
        order.append("report")
        real_report(self)

    with (
        mock.patch.object(
            scanner_wheel._Scratch, "remove", autospec=True, side_effect=remove
        ),
        mock.patch.object(ReaderGate, "report", autospec=True, side_effect=report),
    ):
        _scan(wheel)
    assert order == ["remove", "report"]
    (info,) = gate_infos(caplog)
    assert ": onnx. " in info


def test_trust_reads_every_gated_format(tmp_path: Path) -> None:
    with mock.patch.object(
        scanner, "read_ai_model", side_effect=lambda p, model_format: AiModelMetadata()
    ) as spy:
        _scan(_wheel(tmp_path, list(_GATED)), trust=True)
    assert spy.call_count == len(_GATED) + 1


@pytest.mark.parametrize("fixture", _HOSTILE)
def test_a_hostile_hdf5_is_listed_not_opened(tmp_path: Path, fixture: str) -> None:
    """Run in a subprocess under a timeout: were the gate broken, libhdf5
    would kill or hang the interpreter this test runs in."""
    wheel = _wheel(tmp_path, [fixture])
    code = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from pitloom.logging_config import configure_logging
        from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
        configure_logging()
        models = scan_wheel_for_ai_models(
            Path(sys.argv[1]), scan_usage=False, usage_hint=lambda: False,
            max_bytes=10**8)
        print(sorted(str(m.format_info.model_format) for m in models))
        """
    )
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, str(wheel)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "['hdf5', 'safetensors']"
    assert _TRUST in done.stderr


def test_a_project_scan_is_not_gated(tmp_path: Path) -> None:
    pytest.importorskip("fickling")
    (tmp_path / "m.pt").write_bytes(fixture_bytes("pytorch/example-model.pt"))
    (model,) = scan_project_for_ai_models(
        tmp_path,
        [ProjectFile(physical_path="m.pt", distribution_path="m.pt")],
        scan_usage=False,
        usage_hint=lambda: False,
    )
    assert model.provenance  # read, not a stub


@pytest.mark.parametrize(
    ("claimed", "named"),
    [
        ({"gguf", "onnx"}, ": gguf, onnx. "),
        ({"onnx"}, ": onnx. "),
        ({"gguf"}, ": gguf. "),
        (set(), None),
    ],
)
def test_the_info_names_only_the_formats_the_claim_accepts(
    claimed: set[str],
    named: str | None,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A batch's later wheels are still gated; a format an earlier wheel
    already announced is not named again, a new one is."""
    caplog.set_level(logging.INFO)
    asked: list[str] = []

    def claim(fmt: AiModelFormat) -> bool:
        asked.append(str(fmt))
        return str(fmt) in claimed

    names = ["gguf/stories260K.gguf", "onnx/light-inception-v2.onnx"]
    models = _scan(_wheel(tmp_path, names), gate_hint=claim)
    assert sorted(str(m.format_info.model_format) for m in models) == [
        "gguf",
        "onnx",
        "safetensors",
    ]
    assert asked == ["gguf", "onnx"]  # once per format met, in order
    infos = gate_infos(caplog)
    assert len(infos) == (named is not None)
    if named is not None:
        assert named in infos[0]


def test_a_wheel_without_a_gated_model_claims_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    asked: list[AiModelFormat] = []

    def claim(fmt: AiModelFormat) -> bool:
        asked.append(fmt)
        return True

    _scan(_wheel(tmp_path, []), gate_hint=claim)
    assert not asked
    assert gate_infos(caplog) == []


@pytest.mark.parametrize("trust", [False, True])
def test_the_real_fasttext_loader_runs_only_on_a_trusted_wheel(
    trust: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    spy = spy_load_model(monkeypatch)
    caplog.set_level(logging.INFO)
    models = _scan(_wheel(tmp_path, _FASTTEXT), trust=trust)
    assert spy.call_count == (len(_FASTTEXT) if trust else 0)
    read = sorted((str(m.format_info.model_format), bool(m.provenance)) for m in models)
    assert read == [("fasttext", trust)] * 2 + [("safetensors", True)]
    assert len(gate_infos(caplog)) == (0 if trust else 1)  # two models, one line


def test_the_gate_is_a_set_of_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another format joins by being in the set; nothing else changes."""
    assert AiModelFormat.FASTTEXT in scanner_wheel.WHEEL_GATED_FORMATS
    monkeypatch.setattr(
        scanner_wheel, "WHEEL_GATED_FORMATS", frozenset({AiModelFormat.SAFETENSORS})
    )
    spy = spy_load_model(monkeypatch)
    found = _scan(_wheel(tmp_path, _FASTTEXT[:1]))
    spy.assert_called_once()
    assert sorted(
        (str(m.format_info.model_format), bool(m.provenance)) for m in found
    ) == [
        ("fasttext", True),
        ("safetensors", False),
    ]
