# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``over-cap`` family: a :class:`~pitloom.messages.Cap` has the shape its
values have in a line, :func:`~pitloom.messages.warn_over_cap` says the one
warning (the input after its key, or after a model's format) once when asked,
the code and the cap on its record, and the advice names settings that exist.

See also: tests/test_cap_warnings.py (every cap warns through the helper),
tests/messages/test_messages_trust.py (forged over-cap lines),
tests/test_over_cap_surfaces.py (the code on every surface).
"""

from __future__ import annotations

import dataclasses
import inspect
import logging
import sys
from typing import Any

import pytest

from pitloom import loom
from pitloom.__main__ import main
from pitloom.assemble import generate_git_project_sbom
from pitloom.core.ai_metadata import AiModelFormat, model_cap
from pitloom.core.config import INT_KEYS
from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR, configure_logging
from pitloom.messages import (
    CONFIG_MEMBER_LINE,
    OVER_CAP,
    Cap,
    CodedValueError,
    Line,
    code_of,
    emit,
    over_cap_of,
    trusted_message,
    warn_over_cap,
)
from pitloom.messages._fields import render
from pitloom.messages._over_cap import KEY_LINE, MODEL_LINE, REASON

_LOG = logging.getLogger("pitloom.test_over_cap")
_NAME = Cap(1024, "character", "name")


@pytest.mark.parametrize(
    ("fields", "match"),
    [
        ({"limit": -1}, "whole number"),
        ({"limit": True}, "whole number"),
        ({"limit": 1.5}, "whole number"),
        ({"unit": "bytes"}, "unit="),
        ({"purpose": ""}, "purpose="),
        ({"purpose": "a b c d"}, "purpose="),
        ({"purpose": "a; b"}, "purpose="),
        ({"subject": "PATH"}, "key="),
        ({"model_format": "GGUF"}, "format="),
        ({"subject": "FIELD", "model_format": "gguf"}, "names its FILE"),
    ],
    ids=repr,
)
def test_a_cap_that_no_line_can_name_is_a_programming_error(
    fields: dict[str, Any], match: str
) -> None:
    """Refused when it is built, so a warning never fails at run time."""
    good: dict[str, Any] = {"limit": 1, "unit": "byte", "purpose": "usage-scan"}
    with pytest.raises(InternalError, match=match):
        Cap(**(good | fields))
    with pytest.raises(InternalError, match=match):
        dataclasses.replace(Cap(**good), **fields)


def test_the_reason_has_one_writer() -> None:
    """A warning and an error say what an input over a cap is alike."""
    cap = Cap(1048576, "byte", "config-member")
    assert cap.reason == render(REASON, cap.reason_values())
    assert cap.reason == "larger than the 1048576-byte config-member cap"
    error = CodedValueError(
        OVER_CAP,
        line=CONFIG_MEMBER_LINE,
        path="s.tar.gz:setup.cfg",
        **cap.reason_values(),
    )
    assert str(error) == f"config file 's.tar.gz:setup.cfg': {cap.reason}; not read"
    assert code_of(error) == "over-cap"


@pytest.mark.parametrize(
    ("cap", "where", "line", "text"),
    [
        (
            Cap(10, "byte", "usage-scan"),
            "a.py",
            KEY_LINE,
            "FILE=a.py: larger than the 10-byte usage-scan cap; skipped",
        ),
        (
            Cap(4, "byte", "max-dataset-hash-bytes", "DIR"),
            "data",
            KEY_LINE,
            "DIR=data: larger than the 4-byte max-dataset-hash-bytes cap; skipped",
        ),
        (
            Cap(3, "entry", "per-field", "FIELD"),
            "",
            KEY_LINE,
            "FIELD=: larger than the 3-entry per-field cap; skipped",
        ),
        (
            model_cap(_NAME, AiModelFormat.GGUF),
            "m.gguf",
            MODEL_LINE,
            "FORMAT=gguf FILE=m.gguf: larger than the 1024-character name cap; skipped",
        ),
    ],
    ids=["file", "dir", "empty-name", "model"],
)
def test_a_cap_warns_by_its_key_or_by_its_model(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    cap: Cap,
    where: str,
    line: Line,
    text: str,
) -> None:
    """The line, its text, the code and the cap on the record; on stderr,
    the line ends in ``[over-cap]`` and is trusted as the entry."""
    configure_logging()
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_over_cap(_LOG, cap, where)
    (record,) = caplog.records
    assert record.msg == line.template
    assert record.getMessage() == text
    assert getattr(record, CODE_ATTR) == "over-cap"
    assert over_cap_of(record) == (cap, "skipped")
    (printed,) = capsys.readouterr().err.splitlines()
    assert printed == f"WARNING: {text} [over-cap]"
    assert trusted_message(printed) is OVER_CAP


@pytest.mark.parametrize(
    ("calls", "levels"),
    [
        ([("a", None), ("a", None)], [logging.WARNING, logging.DEBUG]),
        ([("a", None), ("b", None)], [logging.WARNING, logging.WARNING]),
        ([("a", "k"), ("b", "k")], [logging.WARNING, logging.DEBUG]),
        ([("a", "k"), ("a", "j")], [logging.WARNING, logging.WARNING]),
    ],
    ids=["same-input", "other-input", "same-key", "other-key"],
)
def test_once_is_per_cap_and_input_the_key_naming_the_input(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    calls: list[tuple[str, str | None]],
    levels: list[int],
) -> None:
    """A repeat is ``DEBUG``, printed with no code; *key* (default *where*)
    names the input when two spellings name one."""
    configure_logging(debug=True)
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        for where, key in calls:
            warn_over_cap(_LOG, _NAME, where, once=True, key=key)
    assert [r.levelno for r in caplog.records] == levels
    assert all(over_cap_of(r) == (_NAME, "skipped") for r in caplog.records)
    printed = capsys.readouterr().err.splitlines()
    assert [p.endswith(" [over-cap]") for p in printed] == [
        level == logging.WARNING for level in levels
    ]


def test_once_is_per_cap(caplog: pytest.LogCaptureFixture) -> None:
    """One input over two caps is said for each."""
    other = Cap(10, "byte", "usage-scan")
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        for cap in (_NAME, other, _NAME):
            warn_over_cap(_LOG, cap, "a", once=True)
    assert [r.levelno for r in caplog.records] == [
        logging.WARNING,
        logging.WARNING,
        logging.DEBUG,
    ]


def test_extra_never_replaces_the_code(caplog: pytest.LogCaptureFixture) -> None:
    """An ``extra`` naming the code attribute adds nothing to it."""
    values: dict[str, object] = {"key": "FILE", "name": "a", "outcome": "skipped"}
    values.update(_NAME.reason_values())
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        emit(
            _LOG,
            OVER_CAP,
            logging.WARNING,
            line=KEY_LINE,
            once=None,
            extra={CODE_ATTR: "lfs-pointer", "pitloom_probe": 1},
            **values,
        )
    (record,) = caplog.records
    assert getattr(record, CODE_ATTR) == "over-cap"
    assert record.__dict__["pitloom_probe"] == 1


def test_a_model_is_named_once() -> None:
    """``model_cap`` of a model's cap is the same cap; a cap naming another
    key cannot name a model."""
    once = model_cap(_NAME, "gguf")
    assert model_cap(once, "gguf") == once
    assert (once.model_format, once.subject) == ("gguf", "FILE")
    assert model_cap(_NAME, AiModelFormat.ONNX).model_format == "onnx"
    with pytest.raises(InternalError, match="names its FILE"):
        model_cap(Cap(3, "entry", "per-field", "FIELD"), "gguf")


def _help(monkeypatch: pytest.MonkeyPatch, capsys: Any, *command: str) -> str:
    monkeypatch.setattr(sys, "argv", ["loom", *command, "--help"])
    with pytest.raises(SystemExit):
        main()
    text: str = capsys.readouterr().out
    return text


def test_the_settings_the_advice_names_exist(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each knob the advice tells a user to turn exists where it says."""
    named = [
        "--max-model-extract-bytes",
        "max-model-extract-bytes",
        "max-dataset-hash-bytes",
        "--max-dataset-hash-bytes",
        "max_dataset_hash_bytes",
        "max_clone_bytes",
    ]
    assert all(name in OVER_CAP.advice for name in named)
    assert "--max-model-extract-bytes" in _help(monkeypatch, capsys, "wheel")
    assert "--max-dataset-hash-bytes" in _help(monkeypatch, capsys, "id", "generate")
    assert {"max-model-extract-bytes", "max-dataset-hash-bytes"} <= INT_KEYS[""]
    assert "max_dataset_hash_bytes" in inspect.signature(loom.Run).parameters
    assert "max_clone_bytes" in inspect.signature(generate_git_project_sbom).parameters
