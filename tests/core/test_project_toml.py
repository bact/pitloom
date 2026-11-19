# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The loader of a project's TOML (:mod:`pitloom.core._project_toml`): each
way a file or an archive member's bytes fails is one coded error, in the
order the except chain decides (a file gone, a TOML error, a decode or I/O
error, any other ``ValueError`` or a ``RecursionError``), and the file is
named once.

See also: tests/core/test_config_load_file.py (the loader as ``--config``'s
reader) and tests/messages/test_metadata_surfaces.py (the surfaces).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from pitloom.core._project_toml import (
    decode_member_text,
    load_project_toml,
    load_project_toml_bytes,
)
from pitloom.messages import code_of
from pitloom.messages.files import CONFIG_USE, METADATA_USE

pytestmark = pytest.mark.platform

#: The fault is on line 3.
_CRLF_BAD = b'a = 1\r\nb = "x"\r\nc = = 3\r\n'
_HAS_DIGIT_LIMIT = hasattr(sys, "get_int_max_str_digits")
#: Not a TOMLDecodeError: an integer past Python's digit limit.
_OVERLONG = b"[project]\nversion = " + b"9" * 5000 + b"\n"
#: Not a TOMLDecodeError: arrays nested past the parser's limit.
_DEEP = b"x = " + b"[" * 3000 + b"]" * 3000 + b"\n"


def _load(path: Path, *, use: str = METADATA_USE) -> dict[str, object]:
    return load_project_toml(path, kind="pyproject.toml", use=use)


def test_a_good_file_is_its_table(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_bytes(b'[project]\r\nname = "demo"\r\n')
    assert _load(path) == {"project": {"name": "demo"}}


@pytest.mark.parametrize("make", ["missing", "directory"])
def test_a_path_that_is_no_file_is_input_not_found_naming_the_kind(
    tmp_path: Path, make: str
) -> None:
    path = tmp_path / "pyproject.toml"
    if make == "directory":
        path.mkdir()
    with pytest.raises(FileNotFoundError) as exc:
        load_project_toml(path, kind="config file", use=CONFIG_USE)
    assert code_of(exc.value) == "input-not-found"
    assert "config file" in str(exc.value)  # the caller's kind, not a fixed one


def test_a_toml_error_names_the_line_of_a_crlf_file_and_the_file_once(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_bytes(_CRLF_BAD)
    with pytest.raises(ValueError, match=r"line 3, column") as exc:
        _load(path)
    assert code_of(exc.value) == "config-malformed"
    assert str(exc.value).startswith(f"FILE={path}: ")
    assert str(exc.value).count("FILE=") == 1


@pytest.mark.parametrize(
    "payload", [b"\xff\xfe[project]\n", b"[project]\nx = '\xc3('\n"], ids=["bom", "cut"]
)
@pytest.mark.parametrize("use", [METADATA_USE, CONFIG_USE], ids=["metadata", "config"])
def test_bytes_that_are_not_utf8_are_unreadable_for_the_given_use(
    tmp_path: Path, payload: bytes, use: str
) -> None:
    """Not ``config-malformed``: a decode error is a ``ValueError`` too, and
    comes before the generic clause."""
    path = tmp_path / "pyproject.toml"
    path.write_bytes(payload)
    with pytest.raises(ValueError) as exc:
        _load(path, use=use)
    assert code_of(exc.value) == "file-unreadable/not-utf8"
    assert use in str(exc.value)
    assert str(exc.value).count("FILE=") == 1


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            _OVERLONG,
            id="overlong-integer",
            marks=pytest.mark.skipif(
                not _HAS_DIGIT_LIMIT, reason="no integer digit limit"
            ),
        ),
        pytest.param(_DEEP, id="deep-nesting"),
    ],
)
def test_a_value_the_parser_cannot_hold_is_malformed(
    tmp_path: Path, payload: bytes
) -> None:
    """The parser raises a plain ``ValueError`` or a ``RecursionError``, not
    a ``TOMLDecodeError``: still the TOML line, never an uncoded crash."""
    path = tmp_path / "pyproject.toml"
    path.write_bytes(payload)
    with pytest.raises(ValueError) as exc:
        _load(path)
    assert code_of(exc.value) == "config-malformed"
    assert str(exc.value).startswith(f"FILE={path}: ")


@pytest.mark.skipif(
    sys.platform == "win32" or not hasattr(os, "getuid") or os.getuid() == 0,
    reason="POSIX permission bits, not root",
)
def test_a_file_that_cannot_be_read_is_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_bytes(b"[project]\n")
    path.chmod(0)
    try:
        with pytest.raises(ValueError) as exc:
            _load(path)
    finally:
        path.chmod(0o600)
    assert code_of(exc.value) == "file-unreadable"
    assert METADATA_USE in str(exc.value)


def test_a_permission_error_is_unreadable_on_every_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Where permission bits cannot be set (Windows, root), the same clause
    through a loader that raises ``PermissionError``."""
    path = tmp_path / "pyproject.toml"
    path.write_bytes(b"[project]\n")

    def refuse(_: Path) -> dict[str, object]:
        raise PermissionError(13, "denied")

    monkeypatch.setattr("pitloom.core._project_toml.load_toml_file", refuse)
    with pytest.raises(ValueError) as exc:
        _load(path)
    assert code_of(exc.value) == "file-unreadable"


def test_a_file_gone_since_the_check_is_not_found_not_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``FileNotFoundError`` is an ``OSError``: it must come first."""
    path = tmp_path / "pyproject.toml"
    path.write_bytes(b"[project]\n")

    def vanish(_: Path) -> dict[str, object]:
        raise FileNotFoundError(2, "gone")

    monkeypatch.setattr("pitloom.core._project_toml.load_toml_file", vanish)
    with pytest.raises(FileNotFoundError) as exc:
        _load(path)
    assert code_of(exc.value) == "input-not-found"


def test_the_file_is_named_as_given_with_a_windows_spelling() -> None:
    """The archive member name is used as given (``<archive>:<member>``),
    whatever the host's path syntax."""
    for member in (
        str(PureWindowsPath("C:/p/x.tar.gz")) + ":pyproject.toml",
        str(PurePosixPath("/p/x.tar.gz")) + ":pyproject.toml",
    ):
        with pytest.raises(ValueError) as exc:
            load_project_toml_bytes(_CRLF_BAD, file=member, use=METADATA_USE)
        assert str(exc.value).startswith(f"FILE={member}: ")
        assert str(exc.value).count("FILE=") == 1


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (_CRLF_BAD, "config-malformed"),
        (b"\xff[project]\n", "file-unreadable/not-utf8"),
        (_DEEP, "config-malformed"),
    ],
    ids=["toml", "not-utf8", "deep"],
)
def test_bytes_fail_as_a_file_does(raw: bytes, code: str) -> None:
    with pytest.raises(ValueError) as exc:
        load_project_toml_bytes(raw, file="a.tar.gz:pyproject.toml", use=METADATA_USE)
    assert code_of(exc.value) == code


def test_good_bytes_are_their_table() -> None:
    raw = b'[project]\r\nname = "demo"\r\n'
    assert load_project_toml_bytes(raw, file="a:p", use=METADATA_USE) == {
        "project": {"name": "demo"}
    }


@pytest.mark.parametrize("raw", [b"\xff", b"caf\xc3", b"\xef\xbb\xbf\xff"])
def test_a_member_that_is_not_utf8_is_unreadable_for_the_use(raw: bytes) -> None:
    with pytest.raises(ValueError) as exc:
        decode_member_text(raw, file="a.tar.gz:setup.cfg", use=METADATA_USE)
    assert code_of(exc.value) == "file-unreadable/not-utf8"
    assert str(exc.value).startswith("FILE=a.tar.gz:setup.cfg: ")
    assert METADATA_USE in str(exc.value)


def test_a_member_is_strict_utf8_text() -> None:
    assert decode_member_text("caf\u00e9\r\n".encode(), file="f", use=METADATA_USE) == (
        "caf\u00e9\r\n"
    )
