# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The formats gated in a wheel beyond fastText: GGUF (a Python loop per
element), HDF5 (libhdf5 crashes and hangs on hostile files), ONNX (protobuf
amplification) and PyTorch ``.pt``/``.pth`` (fickling amplification). Default
wheel scan: format-only entry, reader never run, one ``INFO:`` listing every
gated format met.

See also: :mod:`tests.extract.scanner.test_scanner_wheel_native_gate` (the
mechanism, with fastText) and :mod:`tests.fixtures.aimodels` README
(the hostile files).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.project import ProjectFile
from pitloom.extract import scanner
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.extract.scanner_wheel import WHEEL_GATED_FORMATS, scan_wheel_for_ai_models
from tests._wheel_models import safetensors_bytes, write_model_wheel

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "aimodels"
_HOSTILE = ["hostile/hdf5-segfault.h5", "hostile/hdf5-hang.h5"]
_GATED = {
    "gguf/stories260K.gguf": "gguf",
    "hdf5/example-model.h5": "hdf5",
    "onnx/light-inception-v2.onnx": "onnx",
    "pytorch/example-model.pt": "pytorch",
    "pytorch/example-model.pth": "pytorch",
}
_TRUST = "--trust-wheel-model"


def _fixture(name: str) -> bytes:
    path = _FIXTURES / name
    if not path.is_file():
        pytest.skip(f"{name} is not in this checkout")
    return path.read_bytes()


def _wheel(tmp_path: Path, names: list[str]) -> Path:
    members = {f"demo/{Path(n).name}": _fixture(n) for n in names}
    members["demo/t.safetensors"] = safetensors_bytes(metadata={"k": "v"})
    return write_model_wheel(tmp_path / "dist", members)


def _scan(wheel: Path, *, trust: bool = False) -> list[AiModelMetadata]:
    return scan_wheel_for_ai_models(
        wheel,
        scan_usage=False,
        usage_hint=lambda: False,
        max_bytes=10**8,
        trust=trust,
    )


def _infos(caplog: pytest.LogCaptureFixture) -> list[str]:
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
    assert formats == ["gguf", "hdf5", "onnx", "pytorch", "pytorch", "safetensors"]
    assert [c.args[0].suffix for c in spy.call_args_list] == [".safetensors"]
    for model in models:
        if str(model.format_info.model_format) != "safetensors":
            assert not model.provenance  # format-only
    (info,) = _infos(caplog)  # five gated models, one line
    assert ": gguf, hdf5, onnx, pytorch. " in info  # sorted, each once


def test_the_gate_is_reported_even_when_the_scan_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A gated model met before the failure is still explained."""
    caplog.set_level(logging.INFO)
    wheel = _wheel(tmp_path, ["onnx/light-inception-v2.onnx"])
    with mock.patch.object(
        scanner, "attach_usage_references", side_effect=RuntimeError("scan failed")
    ):
        with pytest.raises(RuntimeError, match="scan failed"):
            scan_wheel_for_ai_models(
                wheel, scan_usage=True, usage_hint=lambda: False, max_bytes=10**8
            )
    (info,) = _infos(caplog)
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
    (tmp_path / "m.pt").write_bytes(_fixture("pytorch/example-model.pt"))
    (model,) = scan_project_for_ai_models(
        tmp_path,
        [ProjectFile(physical_path="m.pt", distribution_path="m.pt")],
        scan_usage=False,
        usage_hint=lambda: False,
    )
    assert model.provenance  # read, not a stub
