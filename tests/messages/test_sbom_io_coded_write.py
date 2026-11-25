# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``coded_write`` and ``write_sbom_output``: a refused write is
``file-unwritable`` with the system's error as its cause, any other error
passes as it is, and ``-`` is standard output, never a file.

See also: tests/messages/test_file_unwritable_output.py (every surface).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pitloom._sbom_io import coded_write, is_stdout, write_sbom_output
from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import CodedOSError, code_of

pytestmark = pytest.mark.platform

_SYMLINKS = os.name == "posix"


def test_a_refused_write_has_the_system_error_as_its_cause() -> None:
    refused = PermissionError(13, "Permission denied")
    with pytest.raises(CodedOSError) as caught:
        with coded_write("out.json"):
            raise refused
    assert caught.value.__cause__ is refused
    assert code_of(caught.value) == "file-unwritable"


def test_a_write_to_a_missing_directory_has_the_system_error_as_its_cause(
    tmp_path: Path,
) -> None:
    with pytest.raises(CodedOSError) as caught:
        write_sbom_output("{}", tmp_path / "missing" / "out.json")
    assert isinstance(caught.value.__cause__, OSError)
    assert not isinstance(caught.value.__cause__, CodedOSError)


@pytest.mark.parametrize(
    "error",
    [ValueError("plain"), InternalError("a programming error"), KeyError("k")],
    ids=["value-error", "internal-error", "key-error"],
)
def test_an_error_that_is_not_an_os_error_passes_as_it_is(error: Exception) -> None:
    with pytest.raises(type(error)) as caught:
        with coded_write("out.json"):
            raise error
    assert caught.value is error
    assert code_of(caught.value) is None


def test_a_coded_os_error_passes_as_it_is() -> None:
    coded = OSError(13, "x")
    setattr(coded, CODE_ATTR, "file-unreadable")
    with pytest.raises(OSError) as caught:
        with coded_write("out.json"):
            raise coded
    assert caught.value is coded


def test_the_dash_is_standard_output_and_names_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_sbom_output("{}", "-")
    assert capsys.readouterr().out == "{}\n"
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize(
    ("spelling", "expected"),
    [
        ("-", True),
        (Path("-"), True),
        (None, False),
        ("", False),
        ("-out.json", False),
        ("--", False),
        (" -", False),
        (Path("-") / "x", False),
    ],
    ids=["str", "path", "none", "empty", "dash-prefixed", "two", "space", "below"],
)
def test_only_a_lone_dash_is_standard_output(
    spelling: Path | str | None, expected: bool
) -> None:
    assert is_stdout(spelling) is expected


@pytest.mark.skipif(not _SYMLINKS, reason="needs POSIX symlinks")
def test_a_symlinked_output_stays_a_link_to_the_written_file(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_bytes(b"old")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    write_sbom_output("{}\n", link)
    assert link.is_symlink()
    assert target.read_bytes() == b"{}\n"
