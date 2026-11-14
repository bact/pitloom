# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``text-malformed``: the one helper for text holding lone surrogates, its
two lines, the escape done once, and the code on the command line's line.

See also: tests/test_lone_surrogate_name_surfaces.py (a non-UTF-8 file
name, every surface), tests/assemble/test_lone_surrogates.py (a model, a
card), tests/core/test_untrusted_text.py (the escape).
"""

from __future__ import annotations

import logging
import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_model_sbom
from pitloom.core.untrusted_text import escape_lone_surrogates_in_elements
from pitloom.logging_config import CODE_ATTR, loggable
from pitloom.messages import trusted_message
from pitloom.messages.files import (
    TEXT_MALFORMED,
    warn_lone_surrogates,
)

#: A logger the record check of ``tests/conftest.py`` watches.
_LOG = logging.getLogger("pitloom.text_malformed_check")
_SAID = "lone surrogates written as \\uXXXX"


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if _SAID in r.getMessage()]


@pytest.mark.parametrize(
    ("model_format", "text"),
    [
        (None, f"FILE=a/c.json: {_SAID}"),
        ("gguf", f"FORMAT=gguf FILE=a/c.json: {_SAID}"),
    ],
    ids=["file", "model"],
)
def test_each_line_is_said_with_its_code(
    caplog: pytest.LogCaptureFixture, model_format: str | None, text: str
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_lone_surrogates(_LOG, file="a/c.json", model_format=model_format)
    (record,) = _records(caplog)
    assert record.getMessage() == text
    assert getattr(record, CODE_ATTR) == "text-malformed"
    assert trusted_message(f"WARNING: {text} [text-malformed]") is TEXT_MALFORMED


@pytest.mark.parametrize(
    "given", ["a\nWARNING: x", loggable("a\nWARNING: x")], ids=["raw", "escaped"]
)
def test_a_name_is_escaped_once_whether_or_not_the_caller_did(
    caplog: pytest.LogCaptureFixture, given: str
) -> None:
    """The field escapes the name; a caller that escaped it already gets
    the same line, never the quotes twice."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_lone_surrogates(_LOG, file=given)
    (record,) = _records(caplog)
    assert record.getMessage() == f"FILE='a\\nWARNING: x': {_SAID}"


def test_an_element_with_no_name_is_still_named() -> None:
    """The SBOM's line names an element by its name, else its id, else its
    type: never an empty ``FILE=``, which the line refuses."""
    graph = [
        {"type": "CreationInfo", "comment": "x\ud800"},
        {"@id": "_:b", "a": "\udc00"},
    ]
    assert escape_lone_surrogates_in_elements(graph) == ["CreationInfo", "_:b"]
    assert escape_lone_surrogates_in_elements([{"x": "\ud800"}]) == ["element"]


def _keras(path: Path) -> Path:
    """A Keras v3 archive whose config holds a lone surrogate."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in (
            ("metadata.json", '{"keras_version": "3.0.0"}'),
            (
                "config.json",
                '{"class_name": "Sequential", "config": {"name": "a\\ud800"}}',
            ),
            ("model.weights.h5", ""),
        ):
            archive.writestr(zipfile.ZipInfo(name), data)
    return path


def test_the_command_line_prints_the_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = _keras(tmp_path / "m.keras")
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(model), "-o", str(out)])
    assert __main__.main() == 0
    lines = [ln for ln in capsys.readouterr().err.splitlines() if _SAID in ln]
    assert lines == [f"WARNING: FORMAT=keras FILE={model}: {_SAID} [text-malformed]"]


def test_the_library_record_carries_the_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    model = _keras(tmp_path / "m.keras")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_model_sbom(model)
    (record,) = _records(caplog)
    assert getattr(record, CODE_ATTR) == "text-malformed"
