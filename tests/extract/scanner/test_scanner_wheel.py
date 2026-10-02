# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The built-wheel producer of the AI model scanner, and what it shares with
the project producer.

See also: :mod:`tests.extract.scanner.test_scanner_wheel_security` (bounds,
cleanup, hostile names), :mod:`tests.extract.scanner.test_scanner_project`.
"""

# W0632 false positive: pylint infers the helper's `result = []` as empty.
# pylint: disable=missing-function-docstring,unbalanced-tuple-unpacking

from __future__ import annotations

import logging
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_wheel_sbom
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from pitloom.extract.wheel import read_wheel
from tests._raw_archive import write_raw_zip
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


def _scan_wheel(
    wheel: Path,
    *,
    usage: bool = False,
    max_bytes: int = 10**8,
    trust: bool = True,
) -> Any:
    return scan_wheel_for_ai_models(
        wheel,
        scan_usage=usage,
        usage_hint=lambda: False,
        max_bytes=max_bytes,
        trust=trust,
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


def test_only_the_dist_info_the_wheel_name_names_is_not_scanned(
    tmp_path: Path,
) -> None:
    """Regression: any top-level ``*.dist-info`` holding a ``METADATA`` or
    a ``WHEEL`` was skipped, so a hostile wheel hid a model by adding a fake
    one. The wheel's own is the one its file name names."""
    model = safetensors_bytes()
    members = {
        "demo/kept.safetensors": model,
        "demo-1.0.0.dist-info/own.safetensors": model,  # the wheel's own
        "tagged-2.dist-info/WHEEL": b"Wheel-Version: 1.0\n",
        "tagged-2.dist-info/hidden.safetensors": model,  # fake WHEEL
        "fake-2.dist-info/METADATA": b"Name: fake\n",
        "fake-2.dist-info/hidden.safetensors": model,  # fake METADATA
        "other-2.0.dist-info/foreign.safetensors": model,
        "pkg/vendored.dist-info/METADATA": b"Name: x\n",
        "pkg/vendored.dist-info/nested.safetensors": model,  # not top level
        "dir.dist-info/METADATA/inner.safetensors": model,  # a directory
    }
    found = _scan_wheel(write_model_wheel(tmp_path, members))
    assert [m.format_info.file_path_relative for m in found] == [
        "demo/kept.safetensors",
        "dir.dist-info/METADATA/inner.safetensors",
        "fake-2.dist-info/hidden.safetensors",
        "other-2.0.dist-info/foreign.safetensors",
        "pkg/vendored.dist-info/nested.safetensors",
        "tagged-2.dist-info/hidden.safetensors",
    ]


# (wheel name, version, a directory beside its own, whether it is the same one)
_DIST_INFO_CASES = [
    ("My.Pkg", "1.0", "my_pkg-1.0.0.dist-info", True),  # PEP 503 + PEP 440
    ("my_pkg", "1.0.0", "My.Pkg-1.0.dist-info", True),
    ("my_pkg", "1.0", "MY__PKG-1.0.dist-info", True),
    ("demo", "1.0+local.1", "demo-1.0+local.1.dist-info", True),
    ("demo", "1.0", "demo-1.0.1.dist-info", False),  # another version
    ("demo", "1.0", "demo-1.0+local.dist-info", False),
    ("demo", "1.0", "demo2-1.0.dist-info", False),  # another name
    ("demo", "1.0", "demo.dist-info", False),  # no version
    ("demo", "1.0", "demo-x.dist-info", False),  # not a version
    ("demo", "1.0", "demo-1.0.dist-inf0", False),  # not the suffix
    ("demo", "1.0", "demo-1.0.dist-info.d", False),
]


@pytest.mark.parametrize(
    ("name", "version", "directory", "own"),
    _DIST_INFO_CASES,
    ids=[f"{c[0]}-{c[1]}-{c[2]}" for c in _DIST_INFO_CASES],
)
def test_the_wheels_own_dist_info_is_compared_as_the_ecosystem_does(
    name: str, version: str, directory: str, own: bool, tmp_path: Path
) -> None:
    member = f"{directory}/m.safetensors"
    # The only .dist-info is the one under test (two that match are skipped
    # by neither: see test_the_scanner_and_read_wheel_agree_on_the_own_dist_info).
    wheel = write_raw_zip(
        tmp_path / f"{name}-{version}-py3-none-any.whl",
        {member: safetensors_bytes(), f"{directory}/METADATA": b""},
    )
    found = [m.format_info.file_path_relative for m in _scan_wheel(wheel)]
    assert found == ([] if own else [member])


def test_every_member_is_scanned_when_the_name_is_not_a_wheel_name(
    tmp_path: Path,
) -> None:
    """A library caller may pass any path: nothing is then the wheel's own."""
    member = "demo-1.0.0.dist-info/m.safetensors"
    wheel = write_model_wheel(tmp_path, {member: safetensors_bytes()})
    other = wheel.rename(tmp_path / "model.whl")
    assert [m.format_info.file_path_relative for m in _scan_wheel(other)] == [member]


_LIBRARY_CASES = [
    ("m.safetensors", AiModelFormat.SAFETENSORS, "safetensors", False),
    ("m.npz", AiModelFormat.NUMPY, "numpy", False),
    ("m.onnx", AiModelFormat.ONNX, "onnx", True),  # gated: needs trust
    ("m.gguf", AiModelFormat.GGUF, "gguf", True),
    ("m.h5", AiModelFormat.HDF5, "h5py", True),
    ("m.ftz", AiModelFormat.FASTTEXT, "fasttext", True),
]


@pytest.mark.parametrize(
    ("member", "fmt", "module", "trust"),
    _LIBRARY_CASES,
    ids=[c[0] for c in _LIBRARY_CASES],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_a_model_is_not_copied_when_its_reader_library_is_missing(
    member: str,
    fmt: AiModelFormat,
    module: str,
    trust: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    copies: list[Path],
) -> None:
    """Regression: up to the whole budget was copied out of the wheel just to
    report that the reader's library is not installed. Same stub, same
    message as the reader's own."""
    path = tmp_path / member
    path.write_bytes(b"x")
    monkeypatch.setitem(sys.modules, module, None)  # "not installed"
    with pytest.raises(ImportError) as excinfo:
        read_ai_model(path, model_format=fmt)
    wheel = write_model_wheel(tmp_path / "d", {f"demo/{member}": b"x"})
    (model,) = _scan_wheel(wheel, trust=trust)
    assert not copies
    assert model.format_info.model_format == fmt
    assert not model.provenance
    (message,) = logged_warnings(caplog)
    assert message == (
        f"FORMAT={fmt} FILE=demo/{member}: required library not installed; "
        f"{excinfo.value}"
    )


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
def test_a_python_file_over_1_mib_is_skipped_with_one_warning(
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


def test_a_duplicate_member_refuses_the_wheel_and_no_model_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No installer and no reader can tell which copy is meant: the wheel is
    refused before the scan reads either (see ``wheel_members``)."""
    wheel = tmp_path / "demo-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("demo/m.safetensors", safetensors_bytes())
        with pytest.warns(UserWarning, match="Duplicate name"):
            zf.writestr("demo/m.safetensors", safetensors_bytes(8))
        zf.writestr(
            "demo-1.0.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n",
        )
    seen: list[Path] = []
    monkeypatch.setattr(
        "pitloom.extract.scanner.read_ai_model",
        lambda path, **_: seen.append(path),
    )

    with pytest.raises(ValueError, match="duplicate member name -- wheel refused"):
        generate_wheel_sbom(wheel, offline=True)
    with pytest.raises(ValueError, match="duplicate member name -- wheel refused"):
        scan_wheel_for_ai_models(
            wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=1 << 20
        )

    assert not seen
