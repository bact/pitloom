# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A hostile member or file name forges no log line at ``DEBUG`` either.

See also: :mod:`tests.extract.scanner.test_scanner_wheel_security` (the same
check at ``WARNING``), :mod:`tests.extract.scanner.test_scanner_reader_logs`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io
import logging
import sys
import zipfile
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_ai_model
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.assemble.embed_surfaces_shared import run_cli

_EVIL = ["\n::error::x", "\nERROR: x"]


@pytest.mark.parametrize("evil", _EVIL)
def test_debug_scan_of_hostile_names_forges_no_line(
    evil: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: object
) -> None:
    """The ``Discovered AI model`` and ``Found usage`` records quote the
    model's and the script's names."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PITLOOM_DEBUG", "0")  # restored on teardown
    model = f"a{evil}.safetensors"
    wheel = write_model_wheel(
        tmp_path / "d",
        {
            f"demo/{model}": safetensors_bytes(),
            f"demo/use{evil}.py": f'M = "{model}"\n'.encode(),
        },
    )
    run_cli(
        [
            "--debug",
            "wheel",
            str(wheel),
            "--offline",
            "-o",
            str(tmp_path / "out.json"),
            "--scan-model-usage",
            "--trust-wheel-model",
        ],
        monkeypatch,
    )
    err = capfd.readouterr().err  # type: ignore[attr-defined]
    lines = [line for line in err.splitlines() if line]
    assert any(line.startswith("DEBUG: Discovered AI model") for line in lines)
    assert any(line.startswith("DEBUG: Found usage of") for line in lines)
    assert all(line.startswith(("DEBUG: ", "INFO: ", "WARNING: ")) for line in lines)


_BAD = b"not a model" * 20


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buffer.getvalue()


# Content each reader gets as far as its generic failure handler with.
_CONTENT = {
    ".safetensors": safetensors_bytes()[:-2],  # tensor data cut short
    ".npy": _BAD,
    ".keras": _zip({"config.json": b"{not json", "metadata.json": b"{}"}),
    ".gguf": _BAD,
}


@pytest.mark.skipif(sys.platform == "win32", reason="a file name cannot hold a newline")
@pytest.mark.parametrize("evil", _EVIL)
@pytest.mark.parametrize(
    ("suffix", "fmt"),
    [
        (".safetensors", AiModelFormat.SAFETENSORS),
        (".npy", AiModelFormat.NUMPY),
        (".keras", AiModelFormat.KERAS),
        (".gguf", AiModelFormat.GGUF),
    ],
)
def test_a_reader_debugs_a_hostile_path_on_one_line(
    evil: str,
    suffix: str,
    fmt: AiModelFormat,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``read_ai_model`` called with no scanner in between."""
    path = tmp_path / f"m{evil}{suffix}"
    path.write_bytes(_CONTENT[suffix])
    with caplog.at_level(logging.DEBUG, logger="pitloom"), pytest.raises(ValueError):
        read_ai_model(path, model_format=fmt)
    debug = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert debug, "the reader logged nothing at DEBUG"
    assert not [m for m in debug if "\n" in m]
