# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One outcome per kind of model file, whichever surface reads it.

A confirmed model (its header agrees with a model format) gives exactly one
entry, whatever its read outcome; a file that is not one gives none. The
surfaces are a project scan, a wheel scan, ``generate_model_sbom``,
``enrich_model`` and ``loom model``/``loom enrich`` themselves.

See also: :mod:`tests.assemble.test_model_entry_cap` (the entry cap on the
same surfaces) and :mod:`tests.extract.scanner.test_scanner` (the policy).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import importlib
import io
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_model_sbom
from pitloom.assemble._model_generator import enrich_model
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.extract.scanner_wheel import BUDGET_FACTOR, scan_wheel_for_ai_models
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.extract.ai_model.gguf_builders import gguf_file
from tests.warning_helpers import error_lines, file_values, logged_warnings

_CRFSUITE_MINIMAL = (
    Path(__file__).parent.parent
    / "fixtures"
    / "aimodels"
    / "crfsuite"
    / "minimal.model"
)
_CRFSUITE_COMPLETE = _CRFSUITE_MINIMAL.with_name("complete.crfsuite")
_LFS = b"version https://git-lfs.github.com/spec/v1\noid sha256:00\nsize 1\n"
_LFS_WARNING = "header is a Git LFS pointer; not listed as an AI model"
_NOT_A_MODEL = "not an AI model file"  # what a refused file with no reason says
_TRUNCATED = struct.pack("<Q", 200) + b'{"a": 1}'  # header cut short
_CREATED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")


@dataclass(frozen=True)
class Kind:
    """One kind of file: its name, bytes and expected outcome."""

    name: str
    data: bytes
    fmt: AiModelFormat | None  # the entry's format; ``None``: not a model
    warning: str | None  # text of the one WARNING; ``None``: silent
    needs: str | None = None  # a library the case needs installed
    block: str | None = None  # a library to make unimportable
    refusal: str | None = None  # why ``loom model`` refuses a non-model
    degraded: bool = False  # an entry read in part, not a format-only stub


def _hdf5_with_bad_config() -> bytes:
    """An HDF5 file whose ``model_config`` is not JSON: read in part, with
    the reader's own warning."""
    try:
        h5py = importlib.import_module("h5py")
    except ImportError:
        return b""
    buffer = io.BytesIO()
    with h5py.File(buffer, "w") as hf:
        hf.attrs["model_config"] = "not json"
        hf.attrs["backend"] = "tensorflow"
    return buffer.getvalue()


_KINDS = {
    "good": Kind("m.safetensors", safetensors_bytes(), AiModelFormat.SAFETENSORS, None),
    "parse": Kind(
        "m.safetensors",
        _TRUNCATED,
        AiModelFormat.SAFETENSORS,
        "failed to extract metadata",
        needs="safetensors",
    ),
    "bound": Kind(
        "m.gguf",
        gguf_file(0, 10**6),
        AiModelFormat.GGUF,
        "metadata not read",
        needs="gguf",
    ),
    "library": Kind(
        "m.safetensors",
        safetensors_bytes(),
        AiModelFormat.SAFETENSORS,
        "required library not installed",
        block="safetensors",
    ),
    # what ``np.savez(f)`` with no array writes: a ZIP with no member
    "empty_npz": Kind(
        "m.npz", b"PK\x05\x06" + bytes(18), AiModelFormat.NUMPY, None, needs="numpy"
    ),
    # what a reader warns about is relayed with the FORMAT=/FILE= prefix
    "hdf5_config": Kind(
        "m.h5",
        _hdf5_with_bad_config(),
        AiModelFormat.HDF5,
        "FORMAT=hdf5 FILE=",
        needs="h5py",
        degraded=True,
    ),
    "text_gguf": Kind(
        "m.gguf",
        b"plain text",
        None,
        "header is not gguf; not listed",
        refusal="header is not gguf",
    ),
    # a Git LFS pointer is no model under any candidate suffix: a magic one,
    # one admitting any header, PyTorch's, and one naming no format
    **{
        f"lfs{suffix}": Kind(
            f"m{suffix}", _LFS, None, _LFS_WARNING, refusal="header is a Git LFS"
        )
        for suffix in (".gguf", ".onnx", ".pt", ".bin", ".model")
    },
    # ``.model`` is shared (SentencePiece writes a protobuf one): without
    # the CRFsuite signature it is silently not a model; with it, a model
    "sentencepiece_model": Kind(
        "m.model", b"\n\x0f" + bytes(32), None, None, refusal=_NOT_A_MODEL
    ),
    "crfsuite_model": Kind(
        "m.model", _CRFSUITE_MINIMAL.read_bytes(), AiModelFormat.CRFSUITE, None
    ),
    # signature kept, header cut short: read in part, with the reader's error
    "parse_crfsuite": Kind(
        "m.crfsuite",
        _CRFSUITE_COMPLETE.read_bytes()[:-5],
        AiModelFormat.CRFSUITE,
        "failed to extract metadata",
    ),
    "parse_crfsuite_model": Kind(
        "m.model",
        _CRFSUITE_MINIMAL.read_bytes()[:-5],
        AiModelFormat.CRFSUITE,
        "failed to extract metadata",
    ),
    "text_crfsuite": Kind(
        "m.crfsuite",
        b"plain text",
        None,
        "header is not crfsuite; not listed",
        refusal="header is not crfsuite",
    ),
    "text_pth": Kind("m.pth", b"import os\n", None, None, refusal=_NOT_A_MODEL),
    "empty_onnx": Kind("m.onnx", b"", None, None, refusal="file is empty"),
}
_IDS = list(_KINDS)


@pytest.fixture(name="kind")
def _kind(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Kind:
    kind: Kind = _KINDS[request.param]
    if kind.needs:
        pytest.importorskip(kind.needs)
    if kind.block:
        monkeypatch.setitem(sys.modules, kind.block, None)
    return kind


def _scan_project(directory: Path, kind: Kind) -> list[AiModelMetadata]:
    (directory / kind.name).write_bytes(kind.data)
    return scan_project_for_ai_models(
        directory,
        [ProjectFile(physical_path=kind.name, distribution_path=kind.name)],
        scan_usage=False,
        usage_hint=lambda: False,
    )


def _scan_wheel(directory: Path, kind: Kind) -> list[AiModelMetadata]:
    wheel = write_model_wheel(directory / "dist", {f"demo/{kind.name}": kind.data})
    return scan_wheel_for_ai_models(
        wheel,
        scan_usage=False,
        usage_hint=lambda: False,
        max_bytes=10**7,
        trust=True,
    )


def _generate(path: Path, out: Path) -> str:
    return generate_model_sbom(path, output_path=out)


def _enrich(path: Path, out: Path) -> str:
    return enrich_model(path, output_path=out)


_SCANS = {"project": _scan_project, "wheel": _scan_wheel}
_SINGLE = {"generate_model_sbom": _generate, "enrich_model": _enrich}


def _normalised(messages: list[str]) -> list[str]:
    """*messages* with the ``FILE=`` value, which names the file as each
    surface knows it, and the path echoed in a reader's error text, replaced."""
    out = []
    for message in messages:
        (path,) = file_values([message])
        name = Path(path).name
        out.append(message.replace(path, "<file>").replace(name, "<name>"))
    return out


def _expect_warning(kind: Kind, messages: list[str]) -> list[str]:
    assert len(messages) == (kind.warning is not None)
    for message in messages:
        assert kind.warning is not None and kind.warning in message
    return _normalised(messages)


def _stub_shape(meta: AiModelMetadata, fmt: AiModelFormat) -> None:
    assert meta.format_info.model_format == fmt
    assert not meta.provenance and not meta.properties and not meta.inputs


@pytest.mark.parametrize("kind", _IDS, indirect=True)
@pytest.mark.parametrize("scan", _SCANS)
def test_a_scan_lists_one_entry_for_a_confirmed_model_and_none_otherwise(
    kind: Kind, scan: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    models = _SCANS[scan](tmp_path, kind)
    assert [m.format_info.model_format for m in models] == (
        [kind.fmt] if kind.fmt else []
    )
    if kind.fmt and kind.warning and not kind.degraded:
        _stub_shape(models[0], kind.fmt)
    _expect_warning(kind, logged_warnings(caplog))


@pytest.mark.parametrize("kind", _IDS, indirect=True)
@pytest.mark.parametrize("surface", _SINGLE)
def test_a_single_file_gets_the_scans_entry_and_the_scans_warning(
    kind: Kind,
    surface: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    _scan_project(scan_dir, kind)
    scan_messages = _expect_warning(kind, logged_warnings(caplog))
    caplog.clear()

    path = tmp_path / kind.name
    path.write_bytes(kind.data)
    out = tmp_path / "out.json"
    if kind.fmt is None:
        with pytest.raises(ValueError, match=kind.refusal):
            _SINGLE[surface](path, out)
        assert not out.exists()
        return
    text = _SINGLE[surface](path, out)
    assert out.read_text(encoding="utf-8") == text
    graph = json.loads(text)["@graph"]
    packages = [e for e in graph if e["type"] == "ai_AIPackage"]
    # A fragment names the package only to enrich it; an SBOM holds it.
    assert len(packages) == (surface == "generate_model_sbom")
    if kind.warning and packages and not kind.degraded:
        # A format-only entry, named after its file
        assert packages[0]["name"] == Path(kind.name).stem
    assert _expect_warning(kind, logged_warnings(caplog)) == scan_messages


@pytest.mark.parametrize("kind", _IDS, indirect=True)
@pytest.mark.parametrize("command", ["model", "enrich", "generate"])
def test_the_cli_writes_a_stub_for_a_failed_read_and_refuses_a_non_model(
    kind: Kind,
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / kind.name
    path.write_bytes(kind.data)
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["loom", command, str(path), "-o", str(out)])
    code = __main__.main()
    err = capsys.readouterr().err
    if kind.fmt is None:
        assert code == 1
        assert len(error_lines(err)) == 1
        assert kind.refusal is not None and kind.refusal in err
        assert "WARNING:" not in err
        assert not out.exists()
    else:
        assert code == 0
        assert not error_lines(err)
        assert out.is_file()
        assert err.count("WARNING: ") == (kind.warning is not None)


def test_a_missing_file_is_still_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        generate_model_sbom(tmp_path / "gone.safetensors")


def test_the_entry_set_does_not_depend_on_the_wheel_budget(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a model failing to parse was dropped while the budget
    lasted and listed once it was spent, so the entry set depended on where
    the file stood in the wheel."""
    pytest.importorskip("safetensors")
    names = [f"demo/big{i}.safetensors" for i in range(8)]
    wheel = write_model_wheel(tmp_path, dict.fromkeys(names, _TRUNCATED))
    size = len(_TRUNCATED)

    def scan(ceiling: int) -> list[str]:
        models = scan_wheel_for_ai_models(
            wheel,
            scan_usage=False,
            usage_hint=lambda: False,
            max_bytes=ceiling,
        )
        return [str(m.format_info.file_path_relative) for m in models]

    assert BUDGET_FACTOR * size < len(names) * size  # the budget runs out
    assert scan(size) == names
    assert any("per-wheel budget" in m for m in logged_warnings(caplog))  # it did
    caplog.clear()
    assert scan(10**7) == names  # unconstrained: the same set
    assert not any("per-wheel budget" in m for m in logged_warnings(caplog))


@pytest.mark.parametrize("kind", ["good", "parse"])
def test_the_set_of_listed_files_does_not_depend_on_an_installed_library(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: a file failing to parse was dropped, one the missing
    library kept unread was listed."""
    pytest.importorskip("safetensors")
    case = _KINDS[kind]
    read = _scan_project(tmp_path, case)
    reason = [m.split(": ", 1)[1] for m in logged_warnings(caplog)]
    caplog.clear()
    monkeypatch.setitem(sys.modules, "safetensors", None)
    stubbed = _scan_project(tmp_path, case)
    assert [m.format_info.file_path_relative for m in read] == [
        m.format_info.file_path_relative for m in stubbed
    ]
    assert not stubbed[0].provenance
    # not vacuous: the two runs did read differently
    assert bool(read[0].provenance) is (kind == "good")
    assert [m for m in logged_warnings(caplog) if "not installed" in m]
    assert (not reason) is (kind == "good")


def test_the_candidate_route_adds_nothing_to_a_good_models_bytes(
    tmp_path: Path,
) -> None:
    """Drift guard: ``generate_model_sbom`` (through the scan's read rule)
    emits what ``build_model`` emits for the reader's own result."""
    pytest.importorskip("safetensors")
    path = tmp_path / "good.safetensors"
    path.write_bytes(safetensors_bytes(metadata={"k": "v"}))
    via_candidate = generate_model_sbom(path, creation_metadata=_CREATED)
    via_reader = build_model(
        read_ai_model(path), _CREATED, entity_spdx_id=_entity_id(via_candidate)
    ).to_json(pretty=False, describe_relationship=False)
    assert via_candidate == via_reader


def _entity_id(sbom: str) -> str:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return str(next(e["spdxId"] for e in graph if e["type"] == "ai_AIPackage"))
