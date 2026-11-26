# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``DETAIL_EXC`` cases said from a wheel or a model file: a member name
given twice, a ``METADATA`` header block over its caps, a model member that
cannot be read or copied, one over the extraction ceiling, a file whose
header is no model, a tensor dimension that is no count, a setuptools
without a private piece a Git URL clone's discovery calls; through ``loom
verify-wheel``, ``loom wheel``, ``loom model`` and the setuptools
discovery.

See also: tests/messages/test_detail_classes.py (the harness and the
meta-tests).
"""

from __future__ import annotations

import errno
from pathlib import Path
from typing import Any, cast

import pytest

from pitloom.core import wheel_dist_info
from pitloom.core._models_wheel_setuptools import discover
from pitloom.core.clone_mark import reading_remote_clone
from pitloom.core.model_parameters import MAX_PARAMETER_COUNT, PARAMETER_COUNT_CAP
from pitloom.extract import scanner_wheel
from pitloom.extract.remote.huggingface_field import hub_producer_and_count
from tests._wheel_fixtures import DIST_INFO, make_wheel
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.messages.test_detail_classes import (
    Case,
    Env,
    Outcome,
    Trigger,
    call,
    cap_reason,
    case_id,
    cli,
    make_env,
    prove,
)

pytestmark = pytest.mark.platform  # archives, member names, files

_SCANNER_WHEEL = "src/pitloom/extract/scanner_wheel.py"
_DIST_INFO = "src/pitloom/core/wheel_dist_info.py"
_MODEL = "m.safetensors"


def _duplicate(env: Env) -> Outcome:
    wheel = make_wheel(env.tmp, extra={"demo/a.py": b"", "demo\\a.py": b""})
    return cli(env, "verify-wheel", wheel)


def _header_block(env: Env, metadata: bytes, **caps: int) -> Outcome:
    for name, value in caps.items():
        env.monkeypatch.setattr(wheel_dist_info, name, value)
    wheel = make_wheel(env.tmp, extra={f"{DIST_INFO}/METADATA": metadata})
    return cli(env, "wheel", wheel, "-o", env.tmp / "out.spdx3.json")


def _model_wheel(env: Env, model: bytes, *argv: object) -> Outcome:
    wheel = write_model_wheel(env.tmp / "dist", {f"demo/{_MODEL}": model})
    return cli(env, "wheel", wheel, "-o", env.tmp / "out.spdx3.json", *argv)


# pylint: disable-next=too-few-public-methods
class _Refusing:
    """A wheel whose members cannot be opened: what ``zipfile`` raises on a
    member it cannot decompress."""

    def __init__(self, zf: Any) -> None:
        self._zf = zf

    def open(self, info: Any) -> Any:
        raise RuntimeError(f"member {info.filename} refused by the test")


def _unreadable_member(env: Env) -> Outcome:
    """A member the sniff cannot read (the wheel's own read, before the
    scan, refuses a member damaged on disk)."""
    # pylint: disable-next=protected-access
    real = scanner_wheel._sniffer
    env.monkeypatch.setattr(
        scanner_wheel, "_sniffer", lambda zf, info: real(cast(Any, _Refusing(zf)), info)
    )
    return _model_wheel(env, safetensors_bytes())


def _uncopyable_member(env: Env) -> Outcome:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError(errno.EACCES, "copy refused by the test")

    env.monkeypatch.setattr(scanner_wheel, "open", refuse, raising=False)
    return _model_wheel(env, safetensors_bytes())


def _grown_copy(env: Env) -> Outcome:
    """A member that reads longer than it said it was."""
    # pylint: disable-next=protected-access
    real = scanner_wheel._copy_out

    def copy_out(zf: Any, info: Any, target: Path, scratch: Any) -> None:
        scratch.max_bytes = 1
        real(zf, info, target, scratch)

    env.monkeypatch.setattr(scanner_wheel, "_copy_out", copy_out)
    return _model_wheel(env, safetensors_bytes())


def _onnx_dims(env: Env, *shapes: list[int]) -> Outcome:
    """An ONNX model with one initializer per shape (dimensions are the
    format's ``int64``)."""
    onnx = pytest.importorskip("onnx")
    tensors = [
        onnx.TensorProto(name=f"w{i}", data_type=onnx.TensorProto.FLOAT, dims=dims)
        for i, dims in enumerate(shapes)
    ]
    graph = onnx.helper.make_graph([], "g", [], [], initializer=tensors)
    model = onnx.helper.make_model(graph)
    return _model_file(env, "m.onnx", model.SerializeToString())


def _negative_dimension(env: Env) -> Outcome:
    return _onnx_dims(env, [-1])


def _half_cap_tensors(env: Env) -> Outcome:
    """Two tensors each within the cap, whose sum is over it."""
    half = MAX_PARAMETER_COUNT // 2 + 1
    return _onnx_dims(env, [half], [half])


def _model_file(env: Env, name: str, content: bytes) -> Outcome:
    (env.tmp / name).write_bytes(content)
    return cli(env, "model", env.tmp / name, "-o", env.tmp / "out.spdx3.json")


def _not_a_model_scan(env: Env) -> Outcome:
    wheel = write_model_wheel(env.tmp / "dist", {"demo/m.gguf": b"no model here"})
    return cli(env, "wheel", wheel, "-o", env.tmp / "out.spdx3.json")


def _header_case(function: str, trigger: Trigger, tag: str) -> Case:
    return Case(
        "HeaderBlockOverCap",
        ("pitloom.core.wheel_dist_info", "HeaderBlockOverCap"),
        (_DIST_INFO, function),
        "carrier",
        trigger,
        code="over-cap",
        payload=cap_reason,
        tag=tag,
    )


def _setuptools_piece_gone(env: Env) -> Outcome:
    pytest.importorskip("setuptools")
    # pylint: disable-next=import-outside-toplevel
    from setuptools.config import pyprojecttoml

    (env.tmp / "pyproject.toml").write_bytes(
        b'[build-system]\nrequires = ["setuptools"]\n'
        b'build-backend = "setuptools.build_meta"\n'
        b'[project]\nname = "demo"\nversion = "1"\n'
    )
    env.monkeypatch.delattr(pyprojecttoml, "_apply")
    with reading_remote_clone(str(env.tmp)):
        return call(env, lambda: discover(env.tmp))


_LONG_LINE = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\nSummary: " + b"x" * 99
_MANY = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\nSummary: s\n\n"

CASES = [
    Case(
        "on_duplicate",
        ("pitloom.messages._wheels_say", "WheelRefused"),
        ("src/pitloom/core/archive_member_names.py", "archive_members"),
        "detail",
        _duplicate,
        code="wheel-invalid",
        made_in=("src/pitloom/messages/_wheels_say.py", "refuse_duplicate_name"),
        relayed=True,
    ),
    _header_case(
        "_lines",
        lambda env: _header_block(env, _LONG_LINE, MAX_METADATA_BYTES=64),
        "line",
    ),
    _header_case(
        "read_header_block",
        lambda env: _header_block(env, _MANY, MAX_METADATA_BYTES=48),
        "bytes",
    ),
    _header_case(
        "read_header_block",
        lambda env: _header_block(env, _MANY, MAX_METADATA_HEADERS=3),
        "headers",
    ),
    Case(
        "MemberReadError",
        ("pitloom.extract.scanner_wheel", "MemberReadError"),
        (_SCANNER_WHEEL, "_sniffer._sniff"),
        "detail",
        _unreadable_member,
        code="file-unreadable",
    ),
    Case(
        "MemberReadError",
        ("pitloom.extract.scanner_wheel", "MemberReadError"),
        (_SCANNER_WHEEL, "_materializer._materialize"),
        "detail",
        _uncopyable_member,
        code="model-unreadable",
    ),
    Case(
        "ModelOverCap",
        ("pitloom.extract.ai_model.limits", "ModelOverCap"),
        (_SCANNER_WHEEL, "_materializer._materialize"),
        "carrier",
        lambda env: _model_wheel(
            env, safetensors_bytes(extra=64), "--max-model-extract-bytes", 16
        ),
        code="over-cap",
        payload=cap_reason,
    ),
    Case(
        "ModelOverCap",
        ("pitloom.extract.ai_model.limits", "ModelOverCap"),
        (_SCANNER_WHEEL, "_copy_out"),
        "carrier",
        _grown_copy,
        code="over-cap",
        payload=cap_reason,
    ),
    Case(
        "NotAModel",
        ("pitloom.extract.ai_model", "NotAModel"),
        ("src/pitloom/extract/scanner.py", "sniff_model_format"),
        "carrier",
        _not_a_model_scan,
        code="model-wrong-format",
        payload=lambda exc: f"FORMAT={exc.model_format}",
        tag="scan",
    ),
    Case(
        "NotAModel",
        ("pitloom.extract.ai_model", "NotAModel"),
        ("src/pitloom/extract/scanner.py", "sniff_model_format"),
        "detail",
        lambda env: _model_file(env, "m.gguf", b"no model here"),
        code="model-wrong-format",
        tag="named",
    ),
    Case(
        "ParameterCountRejected",
        ("pitloom.core.model_parameters", "ParameterCountRejected"),
        ("src/pitloom/core/model_parameters.py", "tensor_elements"),
        "detail",
        _negative_dimension,
        code="parameter-count-invalid",
    ),
    Case(
        "BackendPieceMissingError",
        ("pitloom.core._models_wheel_types", "BackendPieceMissingError"),
        ("src/pitloom/core/_models_wheel_setuptools_clone.py", "_private"),
        "detail",
        _setuptools_piece_gone,
        code="file-discovery-unusable",
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[case_id(c) for c in CASES])
def test_a_detail_class_is_said_by_its_kind(
    case: Case,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    prove(case, make_env(tmp_path, monkeypatch, capsys, caplog))


# Raised through the factory ``_over_cap()``, which the site meta-test cannot
# see (it reads only direct ``raise Name(...)``): so these are no ``CASES`` of
# it. The instance is built in the factory; the line is the ``over-cap`` one,
# said from the cap, never the exception's text. Real values, no patched cap.
_PARAMETERS = "src/pitloom/core/model_parameters.py"


def _factory_case(function: str, trigger: Trigger, tag: str) -> Case:
    return Case(
        "ParameterCountRejected",
        ("pitloom.core.model_parameters", "ParameterCountRejected"),
        (_PARAMETERS, function),
        "carrier",
        trigger,
        code="over-cap",
        payload=lambda exc: str(PARAMETER_COUNT_CAP.reason),
        made_in=(_PARAMETERS, "_over_cap"),
        tag=tag,
    )


FACTORY_CASES = [
    _factory_case(
        "stated_parameter_count",
        lambda env: call(
            env,
            lambda: hub_producer_and_count(
                {"safetensors_total": MAX_PARAMETER_COUNT + 1}, {}, "o/m"
            ),
        ),
        "stated",
    ),
    _factory_case(
        "tensor_elements",
        lambda env: _onnx_dims(env, [MAX_PARAMETER_COUNT + 1]),
        "dimension",
    ),
    _factory_case("tensor_element_sum", _half_cap_tensors, "sum"),
]


@pytest.mark.parametrize("case", FACTORY_CASES, ids=[case_id(c) for c in FACTORY_CASES])
def test_a_count_over_the_cap_is_said_as_over_cap(
    case: Case,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    prove(case, make_env(tmp_path, monkeypatch, capsys, caplog))
