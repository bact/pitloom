# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The built-wheel producer of the AI model scanner, and what it shares with
the project producer.

See also: :mod:`tests.extract.scanner.test_scanner_wheel_security` (bounds,
cleanup, hostile names), :mod:`tests.extract.scanner.test_scanner_project`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_wheel_sbom
from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from pitloom.extract.wheel import read_wheel
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.warning_helpers import file_values, logged_warnings

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "aimodels"
# One fixture per format.
_MODELS = [
    "fasttext/sentimentdemo.bin",
    "fasttext/lid.176.ftz",
    "gguf/stories260K.gguf",
    "hdf5/example-model.h5",
    "keras/example-model.keras",
    "numpy/example-model-v1.npy",
    "numpy/example-model-bundle.npz",
    "onnx/resnet-tiny-beans.onnx",
    "pytorch/example-model.pt",
    "pytorch_pt2/example-model.pt2",
    "safetensors/marian-tiny-random.safetensors",
]
_CAP = 1024 * 1024


def _scan_wheel(wheel: Path, *, usage: bool = False, max_bytes: int = 10**8) -> Any:
    return scan_wheel_for_ai_models(
        wheel, scan_usage=usage, usage_hint=lambda: False, max_bytes=max_bytes
    )


def _pf(name: str) -> ProjectFile:
    return ProjectFile(physical_path=name, distribution_path=name, digest_sha256="0")


@pytest.mark.parametrize("fixture", _MODELS)
def test_a_wheel_model_equals_the_same_file_in_a_project(
    tmp_path: Path, fixture: str
) -> None:
    """One model, both producers, a flat layout: the whole result agrees --
    including the provenance ``Source:`` (never the copy's name)."""
    data = (_FIXTURES / fixture).read_bytes()
    try:
        read_ai_model(_FIXTURES / fixture)
    except ImportError:
        pytest.skip("the format's reader library is not installed")
    name = f"demo/{Path(fixture).name}"
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    (project / name).write_bytes(data)
    from_project = scan_project_for_ai_models(
        project, [_pf(name)], scan_usage=False, usage_hint=lambda: False
    )
    from_wheel = _scan_wheel(write_model_wheel(tmp_path / "dist", {name: data}))
    assert len(from_wheel) == 1
    assert from_wheel == from_project
    assert any(v.startswith("Source: ") for v in from_wheel[0].provenance.values())


def test_a_nonconforming_name_keeps_its_raw_physical_path(tmp_path: Path) -> None:
    raw = "demo\\m.safetensors"
    wheel = write_model_wheel(tmp_path, {raw: safetensors_bytes()})
    (meta,) = _scan_wheel(wheel)
    assert meta.format_info.file_path_relative == "demo/m.safetensors"
    assert meta.format_info.file_name == "m.safetensors"
    assert meta.format_info.physical_path == raw


def test_model_paths_are_the_file_records_of_read_wheel(tmp_path: Path) -> None:
    members = {
        "demo/a.safetensors": safetensors_bytes(),
        "demo\\b.safetensors": safetensors_bytes(),
        "./demo/c.safetensors": safetensors_bytes(),
    }
    wheel = write_model_wheel(tmp_path, members)
    _, files = read_wheel(wheel)
    records = {(f.distribution_path, f.physical_path) for f in files}
    found = _scan_wheel(wheel)
    assert len(found) == 3
    for meta in found:
        info = meta.format_info
        assert (info.file_path_relative, info.physical_path) in records


def test_dist_info_is_not_scanned(tmp_path: Path) -> None:
    wheel = write_model_wheel(
        tmp_path,
        {
            "demo-1.0.0.dist-info/extra.safetensors": safetensors_bytes(),
            "demo/kept.safetensors": safetensors_bytes(),
        },
    )
    found = _scan_wheel(wheel)
    assert [m.format_info.file_path_relative for m in found] == [
        "demo/kept.safetensors"
    ]


@pytest.mark.parametrize("usage", [False, True])
def test_a_python_member_is_opened_only_for_the_usage_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, usage: bool
) -> None:
    wheel = write_model_wheel(
        tmp_path,
        {"demo/m.safetensors": safetensors_bytes(), "demo/use.py": b'"m.safetensors"'},
    )
    opened: list[str] = []
    real_open = zipfile.ZipFile.open

    def spy(self: zipfile.ZipFile, name: Any, *a: Any, **k: Any) -> Any:
        opened.append(getattr(name, "filename", name))
        return real_open(self, name, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "open", spy)
    (meta,) = _scan_wheel(wheel, usage=usage)
    assert ("demo/use.py" in opened) is usage
    assert meta.usage_files == (["demo/use.py"] if usage else [])


def _cap_case(tmp_path: Path, producer: str, size: int) -> Any:
    """The scan of one model and one ``.py`` of *size* bytes naming it."""
    script = b'M = "m.safetensors"\n'.ljust(size, b"#")
    assert len(script) == size
    members = {"demo/m.safetensors": safetensors_bytes(), "demo/use.py": script}
    if producer == "wheel":
        return _scan_wheel(write_model_wheel(tmp_path, members), usage=True)
    root = tmp_path / "proj"
    (root / "demo").mkdir(parents=True)
    for name, data in members.items():
        (root / name).write_bytes(data)
    return scan_project_for_ai_models(
        root, [_pf(n) for n in members], scan_usage=True, usage_hint=lambda: False
    )


@pytest.mark.parametrize("producer", ["project", "wheel"])
@pytest.mark.parametrize(
    ("size", "scanned"), [(_CAP, True), (_CAP + 1, False)], ids=["at-cap", "over-cap"]
)
def test_a_python_file_over_1_MiB_is_skipped_with_one_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    producer: str,
    size: int,
    scanned: bool,
) -> None:
    (meta,) = _cap_case(tmp_path, producer, size)
    assert meta.usage_files == (["demo/use.py"] if scanned else [])
    messages = logged_warnings(caplog)
    assert len(messages) == (0 if scanned else 1)
    if not scanned:
        assert "usage-scan cap" in messages[0]
        assert file_values(messages) == ["demo/use.py"]


@pytest.mark.parametrize("producer", ["project", "wheel"])
def test_exception_text_names_the_stable_path_not_the_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    producer: str,
) -> None:
    def fail(path: Path, **_kwargs: Any) -> None:
        raise ValueError(f"cannot parse {path} ({path.resolve()})")

    monkeypatch.setattr("pitloom.extract.scanner.read_ai_model", fail)
    caplog.set_level(logging.WARNING)
    _cap_case(tmp_path, producer, 100)
    (message,) = logged_warnings(caplog)
    assert "failed to extract metadata; cannot parse demo/m.safetensors (" in message
    assert message.count("demo/m.safetensors") == 3  # FILE= and both mentions
    assert str(tmp_path) not in message
    assert str(tmp_path.resolve()) not in message


def test_a_duplicate_member_is_reported_once_and_the_last_copy_is_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    first, last = safetensors_bytes(), safetensors_bytes(8)
    wheel = tmp_path / "demo-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("demo/m.safetensors", first)
        with pytest.warns(UserWarning, match="Duplicate name"):
            zf.writestr("demo/m.safetensors", last)
        zf.writestr(
            "demo-1.0.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n",
        )
    seen: list[bytes] = []
    real = read_ai_model

    def spy(path: Path, **kwargs: Any) -> Any:
        seen.append(path.read_bytes())
        return real(path, **kwargs)

    monkeypatch.setattr("pitloom.extract.scanner.read_ai_model", spy)
    sbom = generate_wheel_sbom(wheel, offline=True)
    assert "ai_AIPackage" in sbom
    assert seen == [last]
    assert len([m for m in logged_warnings(caplog) if "overwritten" in m]) == 1
