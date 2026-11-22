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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.given_path import GivenPath, TypedPath
from pitloom.core.lfs_pointer import size_text as lfs_size_text
from pitloom.messages import FIELDS, FRAMES, RELAY_FRAME, Frame, Line, size_text
from pitloom.messages._field_writers import (
    FAILURE_CHARACTERS,
    entities_text,
    failure_text,
)
from pitloom.messages._fields import _merged
from pitloom.messages._fields_licence import LICENCE_FIELDS
from pitloom.messages._fields_lock import value_type_text
from pitloom.messages._templates import render

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
        # As typed (a URL's "//" kept), its credentials masked.
        ("file", TypedPath("https://h//x.whl"), "https://h//x.whl"),
        ("path", TypedPath("ftp://u:SECRET@h/x"), "'ftp://***:***@h/x'"),
        ("path", GivenPath("/abs/r.json", "r.json"), "'r.json'"),
        ("dir", "https://h/d?token=SECRET", "https://h/d?token=***"),
        ("path", "C:\\d\\x.whl", "'C:\\d\\x.whl'"),
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


class _BytesPath:
    """An :class:`os.PathLike` whose path is bytes."""

    def __fspath__(self) -> bytes:
        return b"x"

    def __repr__(self) -> str:
        return "_BytesPath()"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("count", True),
        ("count", -1),
        ("count", "2"),
        ("size", 1.5),
        ("file", b"x"),
        ("file", _BytesPath()),
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("bad <Thing object at 0x7f3a9c1d2e50> inside", "bad <Thing object> inside"),
        ("two <A at 0x1F> and <B at 0xab>", "two <A> and <B>"),
        ("an at 0xyz and 0x12 stay", "an at 0xyz and 0x12 stay"),
        (
            "could not open 'report at 0xbeef.json'",
            "could not open 'report at 0xbeef.json'",
        ),
        ("header corrupt at 0x1a: bad magic", "header corrupt at 0x1a: bad magic"),
        ("x at 0x1fooBar", "x at 0x1fooBar"),
        (
            "<Wrap object at 0x10112ebf0 wrapping <__main__.A object>>",
            "<Wrap object wrapping <__main__.A object>>",
        ),
        (
            '<code object f at 0x10107c2f0, file "a.py", line 26>',
            '<code object f, file "a.py", line 26>',
        ),
        ("<cell at 0x10112e5f0: int object>", "<cell: int object>"),
        ("<weakref at 0x101148cc0; to 'A'>", "<weakref; to 'A'>"),
        ("bad <A> at 0x1a then <B at 0x2b>", "bad <A> at 0x1a then <B>"),
    ],
    ids=[
        "address",
        "two-addresses",
        "not-an-address",
        "file-name",
        "offset",
        "word",
        "nested-repr",
        "code-object",
        "cell",
        "weakref",
        "address-after-a-closed-bracket",
    ],
)
def test_failure_text_drops_a_memory_address(text: str, expected: str) -> None:
    """A deserialiser's default repr must not make stderr differ per run."""
    assert failure_text(TypeError(text)) == expected


def test_failure_text_is_cut_after_masking() -> None:
    """A server's error page (``huggingface_hub`` puts it in the exception's
    text) cannot make the line longer than a reader trusts, and a token
    straddling the cut is masked, not half shown."""
    token = "hf_" + "A" * 34
    text = "a" * (FAILURE_CHARACTERS - 10) + f" Bearer {token} " + "b" * 100_000
    shown = failure_text(ValueError(text))
    assert len(shown) == FAILURE_CHARACTERS + len("...")
    assert shown.endswith("...") and token[:8] not in shown
    userinfo = "a" * (FAILURE_CHARACTERS - 20) + " https://user:SECRETPASSWORD@host/x "
    straddling = failure_text(ValueError(userinfo))
    assert "SECRET" not in straddling and "https://***:***@" in straddling
    assert failure_text(OSError(5, "e" * 2000)).endswith("...")
    assert failure_text(ValueError("short")) == "short"
    assert failure_text(ValueError("x" * FAILURE_CHARACTERS)) == "x" * (
        FAILURE_CHARACTERS
    )


def test_size_text_has_one_writer() -> None:
    """The pointer's hash comment and its messages state a size alike."""
    assert lfs_size_text is size_text


def _shared_templates(frames: Sequence[Frame]) -> list[str]:
    """The templates two frames share at a level both allow (a reader could
    not tell which one a printed line came from); the same text at disjoint
    levels, as the hook's ``ERROR`` and ``WARNING`` frames, is not one."""
    return sorted(
        {
            first.template
            for index, first in enumerate(frames)
            for second in frames[index + 1 :]
            if first.template == second.template and first.levels & second.levels
        }
    )


def test_every_frame_ends_in_a_colon_and_a_space() -> None:
    assert FRAMES and all(frame.template.endswith(": ") for frame in FRAMES)
    assert not _shared_templates(FRAMES)
    # The hook's two frames do share a template, at disjoint levels.
    assert len({frame.template for frame in FRAMES}) < len(FRAMES)


@pytest.mark.parametrize(
    ("second_levels", "shared"),
    [
        (frozenset({"WARNING"}), ["x failed: "]),
        (frozenset({"WARNING", "INFO"}), ["x failed: "]),
        (frozenset({"INFO"}), []),
    ],
    ids=["same-level", "overlapping", "disjoint"],
)
def test_two_frames_share_a_template_only_at_disjoint_levels(
    second_levels: frozenset[str], shared: list[str]
) -> None:
    codes = frozenset({"x"})
    first = Frame(
        levels=frozenset({"WARNING"}), template="x failed: ", surface="a", codes=codes
    )
    second = Frame(
        levels=second_levels, template="x failed: ", surface="b", codes=codes
    )
    assert _shared_templates([first, second]) == shared


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


def test_a_field_named_in_two_tables_is_refused() -> None:
    """``FIELDS`` merges the general and the ID registry tables: a name in
    both would let one silently replace the other."""
    entity = {"entity": FIELDS["entity"]}
    with pytest.raises(ValueError, match="'entity' is defined twice"):
        _merged(entity, entity)


@pytest.mark.parametrize("value", ["a, b", None], ids=["str", "none"])
def test_entities_take_a_list_or_tuple_only(value: object) -> None:
    with pytest.raises(ValueError, match="not a list"):
        entities_text(value)


@pytest.mark.parametrize("name", sorted(LICENCE_FIELDS))
def test_a_licence_field_taking_any_text_is_free(name: str) -> None:
    """A value as read takes any text: a template may not start with it or
    put it beside another field."""
    field = LICENCE_FIELDS[name]
    assert (field.pattern, field.free) == (r".+", True)


@pytest.mark.parametrize(
    ("value", "text"),
    [([], "list"), ({}, "dict"), ("x", "str")],
    ids=["list", "dict", "str"],
)
def test_a_lock_value_is_named_by_its_type(value: object, text: str) -> None:
    assert value_type_text(value) == text


def test_a_value_of_a_type_no_lock_reader_loads_is_refused() -> None:
    """The type name is a closed field value: a reader never hands one on
    that TOML and JSON cannot load (a set, a path)."""
    with pytest.raises(ValueError, match="not a type a lock file holds"):
        value_type_text({1})
