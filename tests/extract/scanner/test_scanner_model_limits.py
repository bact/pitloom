# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What the scanner makes of a model over a bound: one ``FORMAT=``/``FILE=``
warning and a format-only entry; per-model entry caps; the wheel budget
charging the reads inside a model archive; one escaping for reader text.

See also: :mod:`tests.extract.ai_model.test_model_bounds` (the bounds
themselves) and :mod:`tests.extract.scanner.test_scanner_wheel_limits`
(the ceiling and the budget).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io
import json
import logging
import pickle
import pickletools
import struct
import sys
import zipfile
from pathlib import Path
from unittest import mock

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.project import ProjectFile
from pitloom.extract import scanner
from pitloom.extract.ai_model import _pickle_bounds
from pitloom.extract.ai_model.limits import MAX_MODEL_ENTRIES
from pitloom.extract.scanner import _detail
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from pitloom.logging_config import loggable, one_line
from tests._wheel_models import write_model_wheel
from tests.warning_helpers import logged_warnings

# Windows file names cannot hold control characters, so a wheel named with
# a newline cannot exist there.
_NO_CONTROL_CHAR_NAMES = sys.platform == "win32"


def _scan_project(directory: Path, *names: str) -> list[AiModelMetadata]:
    return scan_project_for_ai_models(
        directory,
        [ProjectFile(physical_path=n, distribution_path=n) for n in names],
        scan_usage=False,
        usage_hint=lambda: False,
    )


# -- a bound exceeded: one warning, a stub -----------------------------------


def test_a_pickle_over_the_opcode_bound_is_one_warning_and_a_stub(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_pickle_bounds, "MAX_PICKLE_OPCODES", 5)
    (tmp_path / "m.pt").write_bytes(pickle.dumps(list(range(50)), protocol=2))
    (model,) = _scan_project(tmp_path, "m.pt")
    assert model.format_info.model_format == AiModelFormat.PYTORCH
    assert not model.provenance
    (message,) = logged_warnings(caplog)
    assert message.startswith("FORMAT=pytorch FILE=m.pt: pickle with more than 5 ")
    assert message.endswith("metadata not read")


def test_a_long_decimal_pickle_gives_the_same_sbom_whatever_the_digit_limit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: with the default limit the number was a malformed pickle
    (a fickling warning), with the limit off it was read."""
    setter = getattr(sys, "set_int_max_str_digits", None)
    if setter is None:
        pytest.skip("this CPython has no int digit limit to turn off")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "demo" / "m.pt").write_bytes(b"\x80\x02I" + b"9" * 5000 + b"\n.")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    runs = []
    for limit_off in (False, True):
        if limit_off:
            setter(0)  # the autouse conftest fixture restores it
            # Non-vacuous: genops really converts past 4300 digits now.
            assert len(list(pickletools.genops(b"I" + b"9" * 5000 + b"\n."))) == 2
        caplog.clear()
        runs.append(
            (generate_project_sbom(tmp_path, offline=True), logged_warnings(caplog))
        )
    assert runs[0] == runs[1]
    assert runs[0][1] == [
        "FORMAT=pytorch FILE=demo/m.pt: pickle with a decimal number over 4300 "
        "digits; metadata not read"
    ]


def test_a_safetensors_header_over_the_cap_is_one_warning_and_a_stub(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pytest.importorskip("safetensors")
    lying = struct.pack("<Q", 2**40) + b"{}"
    (tmp_path / "m.safetensors").write_bytes(lying)
    wheel = write_model_wheel(tmp_path / "dist", {"demo/w.safetensors": lying})
    for models in (
        _scan_project(tmp_path, "m.safetensors"),
        scan_wheel_for_ai_models(
            wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=10**8
        ),
    ):
        (model,) = models
        assert model.format_info.model_format == AiModelFormat.SAFETENSORS
        assert not model.provenance
    messages = logged_warnings(caplog)
    assert len(messages) == 2
    assert all(m.startswith("FORMAT=safetensors FILE=") for m in messages)
    assert all("header of 1099511627776 bytes" in m for m in messages)


def test_a_gguf_over_the_count_bound_is_one_warning_and_a_stub(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pytest.importorskip("gguf")
    bomb = b"GGUF" + struct.pack("<IQQ", 3, 0, 2**40)
    (tmp_path / "m.gguf").write_bytes(bomb)
    (model,) = _scan_project(tmp_path, "m.gguf")
    assert model.format_info.model_format == AiModelFormat.GGUF
    (message,) = logged_warnings(caplog)
    assert message.startswith("FORMAT=gguf FILE=m.gguf: GGUF header declares ")


def test_an_npz_over_the_header_bound_is_one_warning_and_a_stub_in_a_wheel(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pytest.importorskip("numpy")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.npy", b"\x93NUMPY\x02\x00" + struct.pack("<I", 2**32 - 1))
    wheel = write_model_wheel(tmp_path, {"demo/m.npz": buf.getvalue()})
    (model,) = scan_wheel_for_ai_models(
        wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=10**7
    )
    assert model.format_info.model_format == AiModelFormat.NUMPY
    assert not model.provenance
    (message,) = logged_warnings(caplog)
    assert message.startswith("FORMAT=numpy FILE=demo/m.npz: .npy header of ")


def test_an_npz_of_many_members_is_cut_to_the_entry_cap_with_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    np = pytest.importorskip("numpy")
    np.savez(tmp_path / "m.npz", **{f"a{i:04d}": np.zeros(1) for i in range(1100)})
    (model,) = _scan_project(tmp_path, "m.npz")
    assert [i["name"] for i in model.inputs] == [
        f"a{i:04d}" for i in range(MAX_MODEL_ENTRIES)
    ]
    (message,) = logged_warnings(caplog)
    assert "more than 1000 entries in inputs" in message


# -- per-model entry caps ------------------------------------------------------


def _model(n: int) -> AiModelMetadata:
    meta = AiModelMetadata(
        inputs=[{"i": i} for i in range(n)],
        outputs=[{"o": i} for i in range(n)],
        hyperparameters={f"h{i}": i for i in range(n)},
        properties={f"p{i}": str(i) for i in range(n)},
        raw_metadata={f"r{i}": i for i in range(n)},
    )
    for i in range(n):
        meta.provenance[f"properties.p{i}"] = f"src {i}"
        meta.provenance[f"hyperparameters.h{i}"] = f"src {i}"
    meta.provenance["inputs"] = "src"
    return meta


@pytest.mark.parametrize("n", [MAX_MODEL_ENTRIES, MAX_MODEL_ENTRIES + 1])
def test_the_entry_cap_is_inclusive_and_keeps_the_first_in_source_order(
    n: int, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "m.safetensors").write_bytes(b"x")
    results = []
    for _ in range(2):  # deterministic
        with mock.patch.object(scanner, "read_ai_model", return_value=_model(n)):
            caplog.clear()
            (meta,) = _scan_project(tmp_path, "m.safetensors")
        results.append(meta)
    assert results[0] == results[1]
    meta = results[-1]
    kept = min(n, MAX_MODEL_ENTRIES)
    assert [i["i"] for i in meta.inputs] == list(range(kept))
    assert [o["o"] for o in meta.outputs] == list(range(kept))
    assert list(meta.properties) == [f"p{i}" for i in range(kept)]
    assert list(meta.hyperparameters) == [f"h{i}" for i in range(kept)]
    assert list(meta.raw_metadata) == [f"r{i}" for i in range(kept)]
    assert len(meta.provenance) == 2 * kept + 1  # the dropped keys' go too
    messages = logged_warnings(caplog)
    if n <= MAX_MODEL_ENTRIES:
        assert not messages
    else:
        (message,) = messages
        assert message.startswith("FORMAT=safetensors FILE=m.safetensors: ")
        assert (
            "in hyperparameters, inputs, outputs, properties, raw_metadata" in message
        )


# -- the wheel budget counts reads inside a model archive ----------------------


def _keras(config_bytes: int) -> bytes:
    """A ``.keras`` a few hundred bytes deflated, inflating to *config_bytes*."""
    config = json.dumps({"class_name": "Sequential", "config": {"pad": " " * 10}})
    config = config.replace(" " * 10, " " * config_bytes)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.json", config)
    return buf.getvalue()


def test_inner_reads_are_charged_to_the_wheel_budget_and_the_warning_names_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Each model copies ~1 KiB but reads 300 KB inside: 3 fit the 1 MiB
    budget (4 x 256 KiB), the rest are listed without metadata."""
    data = _keras(300_000)
    assert len(data) < 2000
    wheel = write_model_wheel(
        tmp_path, {f"demo/m{i}.keras": data for i in range(8)}, name="evil name"
    )
    models = scan_wheel_for_ai_models(
        wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=256 * 1024
    )
    assert len(models) == 8
    assert sum(bool(m.provenance) for m in models) == 3
    (message,) = logged_warnings(caplog)
    assert message.startswith("AI model scan: the per-wheel budget of 1048576 bytes")
    assert "files in evil name-1.0.0-py3-none-any.whl is spent;" in message


@pytest.mark.skipif(_NO_CONTROL_CHAR_NAMES, reason="control characters in file names")
def test_the_budget_warning_escapes_the_wheel_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    data = _keras(300_000)
    wheel = write_model_wheel(
        tmp_path, {f"demo/m{i}.keras": data for i in range(8)}, name="a\n::error::x"
    )
    scan_wheel_for_ai_models(
        wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=256 * 1024
    )
    (message,) = logged_warnings(caplog)
    assert "\n" not in message


# -- one escaping ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a\n::error::x\tb", "a ::error::x b"),
        ("a\x1b[31m", "'a\\x1b[31m'"),
        ("ok  name", "ok name"),
        (ValueError(), "ValueError"),
        (ValueError("  \n"), "ValueError"),
    ],
)
def test_one_line_composes_loggable(value: object, expected: str) -> None:
    assert one_line(value) == expected
    assert loggable(one_line(value)) == one_line(value)  # idempotent


@pytest.mark.parametrize(
    ("value", "limit", "expected"),
    [
        ("a  b\nc" + "d" * 10, 5, "a b c"),
        ("abc", 3, "abc"),  # at the limit: whole
        ("a\x1bbcdef", 3, "'a\\x1bb'"),  # cut first, then escaped and quoted
        ("abc", None, "abc"),
        (ValueError(), 5, "ValueError"),
    ],
)
def test_one_line_cuts_before_it_escapes(
    value: object, limit: int | None, expected: str
) -> None:
    """Regression: cutting the escaped text lost its closing quote."""
    assert one_line(value, limit) == expected


@pytest.mark.parametrize("exc", [ValueError(), KeyError(), EOFError("")])
def test_a_reader_detail_is_never_empty(exc: BaseException) -> None:
    assert _detail(exc, None, "m.bin") == type(exc).__name__


def test_a_reader_detail_is_on_one_line_and_scrubbed(tmp_path: Path) -> None:
    path = tmp_path / "0.bin"
    text = _detail(ValueError(f"bad\n{path}\r\n::error::x"), path, "demo/m.bin")
    assert text == "bad demo/m.bin ::error::x"


def test_a_log_relayed_reader_record_is_on_one_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def reader(_path: Path, model_format: AiModelFormat) -> AiModelMetadata:
        logging.getLogger("pitloom.extract.ai_model.fake").warning("a\nb\r\n::c")
        return AiModelMetadata()

    (tmp_path / "m.safetensors").write_bytes(b"x")
    with mock.patch.object(scanner, "read_ai_model", side_effect=reader):
        _scan_project(tmp_path, "m.safetensors")
    (message,) = logged_warnings(caplog)
    assert message.endswith(": a b ::c")
