# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Why a model is a stub, or no model, is said with its code on every
surface: a project's and a wheel's scan on the command line's stderr (read
as bytes, as a script reads it), ``loom model``, ``loom enrich`` and ``loom
generate`` naming a file, ``loom model`` naming a Hugging Face model whose
client is missing, the Hatchling build hook, and the library's log records
and exceptions. The GitHub Action's annotation keeps the code too
(tests/scripts/action/test_generate_step.py).

See also: tests/messages/test_model_stub.py (the entries) and
tests/assemble/test_model_outcome_parity.py (one outcome per kind of file).
"""

from __future__ import annotations

import logging
import os
import struct
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_model_sbom, generate_project_sbom
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.extract.ai_model import read_ai_model
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import MESSAGES, code_of, trusted_message
from tests._message_drift import raised_as
from tests._wheel_models import write_model_wheel
from tests.extract.ai_model.gguf_builders import gguf_file
from tests.extract.conftest import make_hook

_SRC = str(Path(__file__).resolve().parents[1] / "src")
#: A Hatchling project whose wheel ships the ``demo`` package, models included.
_PYPROJECT = (
    b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    b'[project]\nname = "demo"\nversion = "1.0"\n'
    b'[tool.hatch.build.targets.wheel]\npackages = ["demo"]\n'
)
#: A Safetensors header declaring 200 bytes that holds 8: its reader fails.
_TRUNCATED = struct.pack("<Q", 200) + b'{"a": 1}'
#: Runs ``loom`` with the modules of its first argument made unimportable.
_RUN = (
    "import sys\n"
    "for name in filter(None, sys.argv[1].split(',')):\n"
    "    sys.modules[name] = None\n"
    "from pitloom.__main__ import main\n"
    "sys.argv = ['loom', *sys.argv[2:]]\n"
    "sys.exit(main())\n"
)


def _negative_onnx() -> bytes:
    """An ONNX model whose initializer has a dimension of -1: no count."""
    onnx = pytest.importorskip("onnx")
    weight = onnx.TensorProto(name="w", data_type=onnx.TensorProto.FLOAT)
    weight.dims.extend([-1, 2])
    x, y = (
        onnx.helper.make_tensor_value_info(n, onnx.TensorProto.FLOAT, [1])
        for n in ("x", "y")
    )
    node = onnx.helper.make_node("Identity", ["x"], ["y"])
    graph = onnx.helper.make_graph([node], "g", [x], [y], initializer=[weight])
    data: bytes = onnx.helper.make_model(graph).SerializeToString()
    return data


#: The files of the project scanned, and the code each one's line ends in.
def _models() -> dict[str, tuple[bytes, str]]:
    return {
        "parse.safetensors": (_TRUNCATED, "model-unreadable"),
        "declares.gguf": (gguf_file(10**9, 0), "model-unreadable"),
        "text.gguf": (b"plain text", "model-wrong-format"),
        "shape.onnx": (_negative_onnx(), "parameter-count-invalid"),
    }


def _project(root: Path) -> Path:
    pytest.importorskip("gguf")
    pytest.importorskip("safetensors")
    (root / "demo").mkdir(parents=True)
    (root / "pyproject.toml").write_bytes(_PYPROJECT)
    (root / "demo" / "__init__.py").write_bytes(b"")
    for name, (data, _) in _models().items():
        (root / "demo" / name).write_bytes(data)
    return root


def _loom(
    args: list[str], cwd: Path, block: str = ""
) -> subprocess.CompletedProcess[bytes]:
    """``loom`` in a child process, *block* (``a,b``) unimportable there; its
    output as bytes, not decoded."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [_SRC, env.get("PYTHONPATH")]))
    return subprocess.run(  # nosec B603
        [sys.executable, "-c", _RUN, block, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
        timeout=300,
    )


def _coded(stderr: bytes) -> dict[str, str]:
    """Each trusted line of *stderr* (a carriage return dropped) by its text
    and its code, as a script reads them."""
    found = {}
    for raw in stderr.decode("utf-8").split("\n"):
        line = raw.removesuffix("\r")
        message = trusted_message(line)
        if message is not None:
            found[line] = message.code
    return found


def _codes_by_file(stderr: bytes) -> dict[str, str]:
    """The code of the trusted line naming each model file."""
    lines = _coded(stderr)
    return {
        name: code
        for name in _models()
        for line, code in lines.items()
        if f"/{name}:" in line or f"\\{name}:" in line
    }


def test_a_project_scan_ends_each_cause_in_its_code(tmp_path: Path) -> None:
    project = _project(tmp_path / "proj")
    done = _loom(["project", str(project), "-o", str(tmp_path / "o.json")], tmp_path)
    assert done.returncode == 0, done.stderr
    assert _codes_by_file(done.stderr) == {n: c for n, (_, c) in _models().items()}


def test_a_missing_library_is_said_per_model_with_its_extra(tmp_path: Path) -> None:
    project = _project(tmp_path / "proj")
    args = ["project", str(project), "-o", str(tmp_path / "o.json")]
    done = _loom(args, tmp_path, block="safetensors,gguf")
    assert done.returncode == 0, done.stderr
    lines = _coded(done.stderr)
    missing = sorted(line for line, code in lines.items() if code == "library-missing")
    assert len(missing) == 2
    assert missing[0].endswith(
        "declares.gguf: required library not installed; install pitloom[gguf] "
        "[library-missing]"
    )
    assert missing[1].endswith("; install pitloom[safetensors] [library-missing]")


def test_a_wheel_scan_names_its_gated_formats_once(tmp_path: Path) -> None:
    members = {"demo/m.gguf": gguf_file(0, 0), "demo/m.onnx": b"\x08\x07"}
    wheel = write_model_wheel(tmp_path / "dist", members)
    done = _loom(["wheel", str(wheel), "-o", str(tmp_path / "w.json")], tmp_path)
    assert done.returncode == 0, done.stderr
    (line,) = [ln for ln, code in _coded(done.stderr).items() if code]
    assert line.startswith("INFO: AI models in a wheel in these formats ")
    assert line.endswith(
        ": gguf, onnx. Pass --trust-wheel-model for a wheel you trust. [reader-unsafe]"
    )


@pytest.mark.parametrize("command", ["model", "enrich", "generate"])
@pytest.mark.parametrize(
    ("name", "data", "status", "code"),
    [
        ("parse.safetensors", _TRUNCATED, 0, "model-unreadable"),
        ("text.gguf", b"plain text", 1, "model-wrong-format"),
        ("empty.onnx", b"", 1, "model-wrong-format"),
    ],
    ids=["unreadable", "wrong-format", "empty"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_a_model_file_named_on_its_own_gets_its_code(
    tmp_path: Path, command: str, name: str, data: bytes, status: int, code: str
) -> None:
    """A failed read is a stub with the scan's line (exit 0); a file that is
    no model is refused with one ``ERROR:`` (exit 1)."""
    pytest.importorskip("safetensors")
    path = tmp_path / name
    path.write_bytes(data)
    done = _loom([command, str(path), "-o", str(tmp_path / "o.json")], tmp_path)
    assert done.returncode == status, done.stderr
    coded = _coded(done.stderr)
    assert list(coded.values()) == [code]
    line = next(iter(coded))
    assert line.startswith("ERROR: " if status else "WARNING: FORMAT=safetensors ")


def test_a_directory_named_as_a_model_is_refused(tmp_path: Path) -> None:
    (tmp_path / "d.onnx").mkdir()
    done = _loom(["model", str(tmp_path / "d.onnx")], tmp_path)
    assert done.returncode == 1
    coded = _coded(done.stderr)
    assert list(coded.values()) == ["model-wrong-format"]
    line = next(iter(coded))
    assert line.endswith(
        ": not an AI model file of a supported format [model-wrong-format]"
    )
    assert line.startswith("ERROR: model command failed: '")


def test_a_hub_model_without_its_client_says_the_extra(tmp_path: Path) -> None:
    """The import is checked before anything is fetched: no network."""
    args = ["model", "google-bert/bert-base-uncased", "-o", str(tmp_path / "h.json")]
    done = _loom(args, tmp_path, block="huggingface_hub")
    assert done.returncode == 1
    assert _coded(done.stderr) == {
        "ERROR: model command failed: required library not installed: "
        "huggingface_hub; install pitloom[huggingface_hub] [library-missing]": (
            "library-missing"
        )
    }


def _record_codes(caplog: pytest.LogCaptureFixture) -> dict[str, str]:
    """The code of the warning naming each model file, from the records."""
    return {
        name: getattr(record, CODE_ATTR)
        for record in caplog.records
        if hasattr(record, CODE_ATTR)
        for name in _models()
        if f"{name}:" in record.getMessage()
    }


def test_the_build_hook_says_each_with_its_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path / "proj")
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        hook.initialize("standard", build_data)
    hook.finalize("standard", build_data, "")
    assert _record_codes(caplog) == {n: c for n, (_, c) in _models().items()}


def test_the_library_puts_each_code_on_its_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path / "proj")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_project_sbom(project, output_path=tmp_path / "o.json", offline=True)
    assert _record_codes(caplog) == {n: c for n, (_, c) in _models().items()}


@pytest.mark.parametrize(
    ("make", "code"),
    [
        (lambda p: (p / "t.gguf").write_bytes(b"plain text"), "model-wrong-format"),
        (lambda p: (p / "t.gguf").mkdir(), "model-wrong-format"),
    ],
    ids=["text", "directory"],
)
def test_the_library_raises_a_refusal_with_its_code(
    tmp_path: Path, make: Any, code: str
) -> None:
    make(tmp_path)
    for read in (generate_model_sbom, read_ai_model):
        with pytest.raises(ValueError) as caught:
            read(tmp_path / "t.gguf")
        assert code_of(caught.value) == code and raised_as(caught.value, MESSAGES[code])


def test_the_library_raises_a_missing_hub_client_with_its_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    with pytest.raises(ImportError) as caught:
        generate_model_sbom("google-bert/bert-base-uncased", output_path=tmp_path / "h")
    assert code_of(caught.value) == "library-missing"
    assert raised_as(caught.value, MESSAGES["library-missing"])


def test_a_models_own_parameters_key_gives_way_with_its_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="m.safetensors", model_format=AiModelFormat.SAFETENSORS
        ),
        hyperparameters={"parameters": "7B"},
        parameter_count=7,
    )
    created = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        build_model(model, created)
    (record,) = [r for r in caplog.records if hasattr(r, CODE_ATTR)]
    assert getattr(record, CODE_ATTR) == "hyperparameter-conflict"
    assert record.getMessage() == (
        "FORMAT=safetensors FILE=m.safetensors: hyperparameter parameters "
        "replaced by the parameter count"
    )
