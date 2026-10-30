# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The model-stub entries (``library-missing``, ``reader-unsafe``,
``model-unreadable``, ``model-wrong-format``, ``parameter-count-invalid``,
``hyperparameter-conflict``): each line reads back as its entry, a value of
the wrong shape is refused, the closed values are the ones the code uses,
and :class:`~pitloom.messages.CodedImportError` keeps its code.

See also: tests/test_model_stub_surfaces.py (every surface prints them) and
tests/messages/test_over_cap.py (the worked example of a family).
"""

from __future__ import annotations

import ast
import copy
import inspect
import logging
import pickle  # nosec B403
from typing import Any

import pytest

from pitloom.core.inert_options import PARAM_TO_FLAG
from pitloom.core.model_parameters import PARAMETER_COUNT_KEY
from pitloom.extract.ai_model import limits
from pitloom.extract.scanner_wheel import WHEEL_GATED_FORMATS
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    FIELDS,
    HYPERPARAMETER_CONFLICT,
    LIBRARY_MISSING,
    MODEL_LIMIT_REASONS,
    MODEL_UNREADABLE,
    MODEL_WRONG_FORMAT,
    NOT_A_MODEL_LINE,
    PARAMETER_COUNT_INVALID,
    READER_UNSAFE,
    CodedImportError,
    CodedValueError,
    Line,
    Message,
    _model_limits,
    _model_stub,
    code_of,
    emit,
    trusted_message,
)
from pitloom.messages._emit import _CodedError
from tests._message_drift import SRC_ROOT, TEST_LOGGER_PREFIX, raised_as

_LOG = logging.getLogger(f"{TEST_LOGGER_PREFIX}model_stub")
_ENTRIES = {m.code: m for m in _model_stub.ENTRIES}


def test_the_family_has_its_six_codes() -> None:
    assert sorted(_ENTRIES) == [
        "hyperparameter-conflict",
        "library-missing",
        "model-unreadable",
        "model-wrong-format",
        "parameter-count-invalid",
        "reader-unsafe",
    ]
    assert {m.since for m in _ENTRIES.values()} == {"0.22.0"}
    assert HYPERPARAMETER_CONFLICT.actor == HYPERPARAMETER_CONFLICT.effect == "none"
    assert all(m.actor == "user" for m in _ENTRIES.values() if m.effect != "none")


@pytest.mark.parametrize(
    ("message", "line"),
    [
        (
            LIBRARY_MISSING,
            "WARNING: FORMAT=gguf FILE=m/a.gguf: required library not installed; "
            "install pitloom[gguf] [library-missing]",
        ),
        (
            LIBRARY_MISSING,
            "ERROR: model command failed: required library not installed: "
            "huggingface_hub; install pitloom[huggingface_hub] [library-missing]",
        ),
        (
            READER_UNSAFE,
            "INFO: AI models in a wheel in these formats are listed without "
            "metadata, their reader not being run on a wheel's files: gguf, onnx. "
            "Pass --trust-wheel-model for a wheel you trust. [reader-unsafe]",
        ),
        (
            MODEL_UNREADABLE,
            "WARNING: FORMAT=onnx FILE=demo/c.onnx: failed to extract metadata; "
            "Failed to load ONNX model from 'demo/c.onnx': corrupt [model-unreadable]",
        ),
        (
            MODEL_UNREADABLE,
            "WARNING: FORMAT=gguf FILE=d.gguf: GGUF header declares 1000000000 "
            "tensors; metadata not read [model-unreadable]",
        ),
        (
            MODEL_UNREADABLE,
            "WARNING: FORMAT=keras FILE=k.keras: ZIP archive not checkable: zipfile "
            "internals changed; metadata not read [model-unreadable]",
        ),
        (
            MODEL_WRONG_FORMAT,
            "WARNING: FORMAT=gguf FILE=demo/t.gguf: header is not gguf; not listed "
            "as an AI model [model-wrong-format]",
        ),
        (
            MODEL_WRONG_FORMAT,
            "ERROR: SBOM generation failed: 'C:\\m\\t.gguf': header is not gguf "
            "[model-wrong-format]",
        ),
        (
            MODEL_WRONG_FORMAT,
            "ERROR: enrichment fragment generation failed: 'e.onnx': file is empty "
            "[model-wrong-format]",
        ),
        (
            PARAMETER_COUNT_INVALID,
            "WARNING: FORMAT=gguf FILE=m.gguf: tensor dimension -1 is not a "
            "non-negative integer; parameter count not recorded "
            "[parameter-count-invalid]",
        ),
        (
            PARAMETER_COUNT_INVALID,
            "WARNING: FORMAT=huggingface FILE=https://huggingface.co/o/m: stated "
            "parameter count is not a non-negative integer; parameter count not "
            "recorded [parameter-count-invalid]",
        ),
        (
            HYPERPARAMETER_CONFLICT,
            "WARNING: FORMAT=safetensors FILE=m.safetensors: hyperparameter "
            "parameters replaced by the parameter count [hyperparameter-conflict]",
        ),
    ],
    ids=lambda v: v.code if isinstance(v, Message) else v[9:40],
)
def test_a_printed_line_is_trusted_as_its_entry(message: Message, line: str) -> None:
    """As every surface prints it: a frame before an ``ERROR:`` (the CLI's)
    or a reader's line (the scan's) is allowed."""
    assert trusted_message(line) is message


@pytest.mark.parametrize(
    "line",
    [
        # a reason off the closed table, or a number that is no count
        "WARNING: FORMAT=gguf FILE=d.gguf: GGUF header declares many tensors; "
        "metadata not read [model-unreadable]",
        "WARNING: FORMAT=gguf FILE=d.gguf: GGUF header declares -1 tensors; "
        "metadata not read [model-unreadable]",
        # a requirement that is not Pitloom with an extra
        "WARNING: FORMAT=gguf FILE=m.gguf: required library not installed; "
        "install gguf [library-missing]",
        "ERROR: required library not installed: gguf; install pitloom[gguf]; "
        "rm -rf x [library-missing]",
        # formats that are not lower-case names, comma-separated
        "INFO: AI models in a wheel in these formats are listed without "
        "metadata, their reader not being run on a wheel's files: GGUF;onnx. "
        "Pass --trust-wheel-model for a wheel you trust. [reader-unsafe]",
        # another level, another code
        "INFO: FORMAT=gguf FILE=t.gguf: header is not gguf; not listed as an AI "
        "model [model-wrong-format]",
        "WARNING: FORMAT=gguf FILE=t.gguf: header is not gguf; not listed as an "
        "AI model [lfs-pointer-malformed]",
    ],
    ids=[
        "reason",
        "number",
        "bare-package",
        "forged-action",
        "formats",
        "level",
        "code",
    ],
)
def test_a_line_out_of_its_shapes_is_not_trusted(line: str) -> None:
    assert trusted_message(line) is None


@pytest.mark.parametrize(
    ("message", "values"),
    [
        (MODEL_UNREADABLE, {"format": "gguf", "file": "m", "reason": "too big"}),
        (MODEL_UNREADABLE, {"format": "gguf", "file": "m", "error": ""}),
        (LIBRARY_MISSING, {"format": "gguf", "file": "m", "requirement": "gguf"}),
        (READER_UNSAFE, {"formats": "gguf, onnx"}),
        (READER_UNSAFE, {"formats": "gguf"}),
        (READER_UNSAFE, {"formats": []}),
        (READER_UNSAFE, {"formats": ["GGUF"]}),
        (READER_UNSAFE, {"formats": ["gguf", 3]}),
        (MODEL_WRONG_FORMAT, {"format": None, "file": "m"}),
    ],
    ids=[
        "reason",
        "empty-error",
        "requirement",
        "formats-str",
        "formats-one-str",
        "formats-empty",
        "formats-case",
        "formats-item",
        "format-none",
    ],
)
def test_a_value_out_of_shape_is_refused_when_said(
    message: Message, values: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    level = logging.INFO if message is READER_UNSAFE else logging.WARNING
    with pytest.raises(ValueError):
        emit(_LOG, message, level, **values)
    assert not caplog.records


def test_the_formats_are_written_comma_separated() -> None:
    line = READER_UNSAFE.lines[0]
    rendered = line.render({"formats": ("fasttext", "gguf", "pytorch")})
    assert ": fasttext, gguf, pytorch. Pass --trust-wheel-model " in rendered


def test_a_closed_field_may_repeat_a_free_one_may_not() -> None:
    """Decision D6: the scan's wrong-format line names its format twice."""
    line = Line(level="WARNING", template="a %(format)s b %(format)s")
    assert line.render({"format": "gguf"}) == "a gguf b gguf"
    assert line.fields == {"format"}
    with pytest.raises(ValueError, match="free field 'file' named twice"):
        Line(level="WARNING", template="a %(file)s b %(file)s")
    assert not any(
        FIELDS[n].free for n in MODEL_WRONG_FORMAT.lines[0].fields - {"file"}
    )


def test_no_field_takes_a_name_the_sayers_keep_for_themselves() -> None:
    """A field called ``extra`` would reach ``emit``'s own ``extra=``: no
    field may share a name with a parameter of ``emit`` or of a coded
    exception."""
    taken: set[str] = set()
    for function in (emit, _CodedError.__init__):
        taken |= {
            name
            for name, parameter in inspect.signature(function).parameters.items()
            if parameter.kind is not inspect.Parameter.VAR_KEYWORD
        }
    assert {"extra", "line", "message"} <= taken
    assert not taken & set(FIELDS)


def test_a_coded_import_error_keeps_its_text_and_code() -> None:
    exc = CodedImportError(LIBRARY_MISSING, module="gguf", requirement="pitloom[gguf]")
    text = "required library not installed: gguf; install pitloom[gguf]"
    assert isinstance(exc, ImportError) and not isinstance(exc, ValueError)
    assert str(exc) == text and exc.pitloom_code == code_of(exc) == "library-missing"
    assert raised_as(exc, LIBRARY_MISSING)
    for again in (pickle.loads(pickle.dumps(exc)), copy.copy(exc)):  # nosec B301
        assert isinstance(again, CodedImportError) and again.msg == text
        assert (str(again), code_of(again), again.args) == (
            text,
            exc.pitloom_code,
            (text,),
        )
    value = CodedValueError(MODEL_WRONG_FORMAT, line=NOT_A_MODEL_LINE, path="d")
    assert isinstance(copy.copy(value), CodedValueError)
    assert not isinstance(value, ImportError)


def test_a_coded_import_error_without_its_line_is_refused() -> None:
    with pytest.raises(ValueError) as caught:
        raise CodedImportError(READER_UNSAFE, formats=["gguf"])
    assert not isinstance(caught.value, ImportError)


def test_the_gate_line_names_the_flag_and_every_gated_format() -> None:
    (line,) = READER_UNSAFE.lines
    assert f" Pass {PARAM_TO_FLAG['trust_wheel_model']} for " in line.template
    summary = READER_UNSAFE.summary.lower()
    assert all(str(fmt) in summary for fmt in WHEEL_GATED_FORMATS)


def test_the_conflict_line_names_the_counts_key() -> None:
    (line,) = HYPERPARAMETER_CONFLICT.lines
    assert f": hyperparameter {PARAMETER_COUNT_KEY} replaced " in line.template


def _limit_calls() -> list[tuple[str, ast.Call]]:
    """Every ``ModelLimitExceeded(...)`` call in ``src/pitloom``."""
    found = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and (
                getattr(node.func, "id", None) == "ModelLimitExceeded"
                or getattr(node.func, "attr", None) == "ModelLimitExceeded"
            ):
                found.append((path.relative_to(SRC_ROOT).as_posix(), node))
    return found


_TABLE_NAMES = {
    name for name, value in vars(_model_limits).items() if value in MODEL_LIMIT_REASONS
}


def test_every_bound_check_raises_a_reason_of_the_table() -> None:
    """Decision D5: ``model-unreadable`` names a bound check's reason as a
    closed field, so a reader raises only the table's texts (``%`` one
    number): an off-table text would be refused at run time."""
    calls = _limit_calls()
    assert len(calls) >= 12  # the scan finds them
    for where, call in calls:
        (arg,) = call.args
        head = arg.left if isinstance(arg, ast.BinOp) else arg
        assert isinstance(head, ast.Name) and head.id in _TABLE_NAMES, where
        assert not isinstance(arg, ast.BinOp) or isinstance(arg.op, ast.Mod), where
    assert len(_TABLE_NAMES) == len(MODEL_LIMIT_REASONS)


def test_only_the_scanner_handled_subclasses_carry_another_reason() -> None:
    """``ModelOverCap`` and ``ScanBudgetExceeded`` say their own text and are
    caught before the scan says a bound check's reason."""
    assert set(limits.ModelLimitExceeded.__subclasses__()) == {
        limits.ModelOverCap,
        limits.ScanBudgetExceeded,
    }


@pytest.mark.parametrize("text", MODEL_LIMIT_REASONS)
def test_each_reason_is_a_reason(text: str, caplog: pytest.LogCaptureFixture) -> None:
    reason = text % 7 if "%d" in text else text
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        emit(
            _LOG,
            MODEL_UNREADABLE,
            logging.WARNING,
            format="gguf",
            file="m",
            reason=reason,
        )
    (record,) = caplog.records
    assert getattr(record, CODE_ATTR) == "model-unreadable"
    assert record.getMessage() == f"FORMAT=gguf FILE=m: {reason}; metadata not read"
