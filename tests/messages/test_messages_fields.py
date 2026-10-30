# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A line's and a frame's template, and the fields it names: where a field
may stand, and that what the catalogue writes for a value always has the
shape a reader trusts the line by.

See also: tests/messages/test_messages_types.py (the entries),
tests/messages/test_messages_trust.py (reading lines back).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.lfs_pointer import size_text as lfs_size_text
from pitloom.messages import FIELDS, FRAMES, RELAY_FRAME, Frame, Line, size_text
from pitloom.messages._fields import render

#: A path ending in a backslash: one on POSIX, a directory on Windows.
_BACKSLASHED = Path("C:\\d\\")


@pytest.mark.parametrize(
    ("template", "match"),
    [
        ("%(nope)s x", "unknown field"),
        ("x %s", "names no field"),
        ("100% x", "names no field"),
        ("x %(file)s: %(file)s y", "twice"),
        ("", "empty"),
        (" x", "white space at its start"),
        ("x\ny", "line break"),
        ("x\ry", "line break"),
        ("x [skipped]", "reads as a code"),
        ("x [a/b]", "reads as a code"),
        ("%(file)s: x", "takes any text"),
        ("x %(count)s%(file)s: y", "takes any text"),
        ("x %(file)s%(count)s: y", "takes any text"),
    ],
    ids=repr,
)
def test_a_template_breaking_a_rule_is_refused(template: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Line(level="WARNING", template=template)


@pytest.mark.parametrize(
    ("level", "template", "match"),
    [("DEBUG", "x", "level"), ("WARNING", "x ", "white space at its end")],
)
def test_a_line_at_debug_or_ending_in_space_is_refused(
    level: str, template: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        Line(level=level, template=template)


def test_a_line_may_start_with_a_quoted_path_and_end_in_a_dotted_table() -> None:
    line = Line(level="ERROR", template="%(path)s: not in [tool.poetry]")
    assert line.fields == {"path"} and line.shown == "'<path>': not in [tool.poetry]"
    assert line.render({"path": Path("m.gguf")}) == "'m.gguf': not in [tool.poetry]"


@pytest.mark.parametrize(
    ("field", "value", "text"),
    [
        ("count", 0, ""),
        ("count", 1, ""),
        ("count", 2, " (2 files)"),
        ("count", 10, " (10 files)"),
        ("size", 0, "0 bytes"),
        ("size", 1, "1 byte"),
        ("size", 2, "2 bytes"),
        ("size", 2**63 - 1, f"{2**63 - 1} bytes"),
        ("file", "a b;c", "a b;c"),
        ("file", Path("d") / "m", str(Path("d") / "m")),
        ("file", "a\nb", "'a\\nb'"),
        ("path", "m.gguf", "'m.gguf'"),
        ("path", "it's", '"it\'s"'),
        ("path", "a'\"b", "'a\\'\"b'"),
        ("path", _BACKSLASHED, f"'{_BACKSLASHED}'"),
        ("oid", "0f" * 32, "0f" * 32),
        ("format", AiModelFormat.GGUF, "gguf"),
        ("format", "pytorch_pt2", "pytorch_pt2"),
        ("limit", 0, "0"),
        ("limit", 1048576, "1048576"),
        ("name", "", ""),
        ("name", "a b: c", "a b: c"),
        ("name", "x\n::error::", "'x\\n::error::'"),
        ("key", "REQUIREMENT", "REQUIREMENT"),
        ("unit", "character", "character"),
        ("purpose", ".npy-header", ".npy-header"),
        ("purpose", "per-wheel model-scan budget", "per-wheel model-scan budget"),
        ("outcome", "the first 1000 kept in labels", "the first 1000 kept in labels"),
        ("amount", "1 byte", "1 byte"),
        ("amount", "512 MiB", "512 MiB"),
        ("command", "ls-remote", "ls-remote"),
        ("use", "for file scanning", "for file scanning"),
        ("field", "project.readme", "project.readme"),
        ("dir", Path("d") / "s", str(Path("d") / "s")),
        ("dir", "a\nWARNING: x", "'a\\nWARNING: x'"),
        (
            "failure",
            PermissionError(13, "Permission denied", "/a/x"),
            "Permission denied",
        ),
        ("failure", OSError(5, "I/O\nerror", "/a/x"), "I/O error"),
        ("failure", OSError("not a regular file"), "not a regular file"),
        ("failure", ValueError(), "ValueError"),
    ],
    ids=lambda v: repr(v)[:20],
)
def test_a_field_writes_a_value_of_its_shape(field: str, value: Any, text: str) -> None:
    assert FIELDS[field].write(value) == text
    assert re.fullmatch(FIELDS[field].pattern, text)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("count", True),
        ("count", -1),
        ("count", "2"),
        ("size", 1.5),
        ("file", b"x"),
        ("file", 3),
        ("path", None),
        ("oid", "0" * 63),
        ("oid", "A" * 64),
        ("format", "GGUF"),
        ("format", None),
        ("limit", -1),
        ("limit", False),
        ("limit", "3"),
        ("name", Path("a")),
        ("key", "file"),
        ("key", "PATH"),
        ("unit", "bytes"),
        ("purpose", ""),
        ("purpose", "a b c d"),
        ("purpose", "1st"),
        ("outcome", ""),
        ("amount", 512),
        ("amount", "1 bytes"),
        ("amount", "512 MB"),
        ("command", "clone x"),
        ("use", "for anything"),
        ("use", "file scanning"),
        ("field", 3),
        ("dir", b"x"),
        ("failure", "Permission denied"),
        ("failure", None),
    ],
    ids=repr,
)
def test_a_value_of_the_wrong_shape_is_refused(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        render(f"x %({field})s y", {field: value})


@pytest.mark.parametrize("values", [{}, {"file": "a", "count": 2}], ids=["few", "many"])
def test_render_takes_exactly_the_names_of_its_template(values: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="takes"):
        render("x %(file)s y", values)


def test_size_text_has_one_writer() -> None:
    """The pointer's hash comment and its messages state a size alike."""
    assert lfs_size_text is size_text


def test_every_frame_ends_in_a_colon_and_a_space() -> None:
    assert FRAMES and all(frame.template.endswith(": ") for frame in FRAMES)
    assert len({frame.template for frame in FRAMES}) == len(FRAMES)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"levels": frozenset()}, "levels"),
        ({"levels": frozenset({"DEBUG"})}, "levels"),
        ({"template": "x"}, "does not end in"),
        ({"template": "%(file)s: "}, "takes any text"),
        ({"template": "x %s: "}, "names no field"),
    ],
    ids=lambda v: repr(v)[:24],
)
def test_a_frame_breaking_a_rule_is_refused(change: dict[str, Any], match: str) -> None:
    fields: dict[str, Any] = {
        "levels": frozenset({"ERROR"}),
        "template": "x failed: ",
        "surface": "x",
    }
    with pytest.raises(ValueError, match=match):
        Frame(**(fields | change))


def test_the_relay_frame_writes_the_scan_prefix() -> None:
    values = {"format": AiModelFormat.GGUF, "file": "m/x.gguf"}
    assert RELAY_FRAME.render(values) == "FORMAT=gguf FILE=m/x.gguf: "
