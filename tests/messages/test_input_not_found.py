# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``input-not-found``: each line reads back as its entry, the error is a
:class:`FileNotFoundError` that keeps its code through a copy or a pickle,
a caller names which of its lines it says, and the helpers say what is at
the path, on the command line and in the library; the fragment variant.

See also: tests/extract/test_model_target.py (a model file named on its
own) and tests/extract/remote/test_git_fetch_models.py (a Git URL's file).
"""

from __future__ import annotations

import copy
import logging
import pickle  # nosec B403
import sys
from pathlib import Path, PureWindowsPath

import pytest

from pitloom import __main__
from pitloom.core.internal_error import InternalError
from pitloom.core.quote_source import quote_source
from pitloom.embed import embed_sbom_in_wheel
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    CodedFileNotFoundError,
    Line,
    code_of,
    trusted_message,
)
from pitloom.messages.targets import (
    FRAGMENT_LINE,
    GIT_FILE_IS_LINK_LINE,
    GIT_FILE_NOT_FOUND_LINE,
    GIT_FOLDER_NOT_FOUND_LINE,
    INPUT_NOT_FOUND,
    MODEL_FILE_NOT_FOUND_LINE,
    input_not_found,
    say_input_not_found,
    warn_fragment_not_found,
)
from tests._message_drift import raised_as
from tests._symlink import CAN_SYMLINK

pytestmark = pytest.mark.platform

_NEEDS_SYMLINK = pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symlink")


@pytest.mark.parametrize(
    ("line", "text"),
    [
        (MODEL_FILE_NOT_FOUND_LINE, "Model file not found: 'a b.gguf'"),
        (
            GIT_FILE_NOT_FOUND_LINE,
            "No file 'a b.gguf' in the repository at that branch.",
        ),
        (
            GIT_FILE_IS_LINK_LINE,
            "File 'a b.gguf' in the repository at that branch is a symbolic "
            "link; links are not followed.",
        ),
        (
            GIT_FOLDER_NOT_FOUND_LINE,
            "No folder 'a b.gguf' in the repository at that branch.",
        ),
    ],
    ids=["model-file", "git-file", "git-link", "git-folder"],
)
def test_each_line_is_a_file_not_found_error_with_its_code(
    line: Line, text: str
) -> None:
    exc = CodedFileNotFoundError(INPUT_NOT_FOUND, line=line, path="a b.gguf")
    assert isinstance(exc, FileNotFoundError) and str(exc) == text
    assert (exc.errno, exc.filename) == (None, None)
    assert raised_as(exc, INPUT_NOT_FOUND)
    for again in (pickle.loads(pickle.dumps(exc)), copy.copy(exc)):  # nosec B301
        assert isinstance(again, CodedFileNotFoundError)
        assert (str(again), code_of(again)) == (text, "input-not-found")


def test_the_caller_names_the_line() -> None:
    """Seven lines name a path alone: none is chosen for the caller."""
    with pytest.raises(ValueError, match="7 name of its ERROR lines"):
        raise CodedFileNotFoundError(INPUT_NOT_FOUND, path="a")


@pytest.mark.parametrize(
    "line",
    [
        "ERROR: Model file not found: a.gguf [input-not-found]",
        "WARNING: Model file not found: 'a.gguf' [input-not-found]",
        "ERROR: No file 'a' in the repository at that branch [input-not-found]",
    ],
    ids=["unquoted", "level", "no-period"],
)
def test_a_line_out_of_its_shapes_is_not_trusted(line: str) -> None:
    assert trusted_message(line) is None


@pytest.mark.parametrize(
    ("kind", "there", "tail"),
    [
        ("wheel file", None, ""),
        ("wheel file", "dir", " is not a file"),
        ("project directory", "file", " is not a directory"),
        ("project path", "file", ""),
        pytest.param("wheel file", "dangling", "", marks=_NEEDS_SYMLINK),
        pytest.param("project directory", "dangling", "", marks=_NEEDS_SYMLINK),
    ],
    ids=[
        "absent",
        "dir-for-file",
        "file-for-dir",
        "either",
        "dangling-for-file",
        "dangling-for-dir",
    ],
)
def test_input_not_found_says_what_is_at_the_path(
    tmp_path: Path, kind: str, there: str | None, tail: str
) -> None:
    """Nothing there, or a link that leads nowhere: not found; something of
    the other kind: says which. ``project path`` names a file or a
    directory, so it is never probed."""
    path = tmp_path / "x y"
    if there == "dir":
        path.mkdir()
    elif there == "file":
        path.write_bytes(b"")
    elif there == "dangling":
        path.symlink_to(tmp_path / "gone")
    exc = input_not_found(kind, path)
    assert str(exc) == f"{kind} not found: {quote_source(path)}{tail}"
    assert isinstance(exc, FileNotFoundError) and raised_as(exc, INPUT_NOT_FOUND)


@pytest.mark.parametrize(
    "path",
    ["a\nb.whl", "a\x1b[2Jb.whl", PureWindowsPath(r"C:\dist\a b.whl")],
    ids=["newline", "escape", "windows"],
)
def test_input_not_found_writes_any_path_on_one_trusted_line(
    path: str | PureWindowsPath,
) -> None:
    exc = input_not_found("wheel file", path)
    assert "\n" not in str(exc) and "\x1b" not in str(exc)
    assert raised_as(exc, INPUT_NOT_FOUND)


def test_an_unknown_kind_is_a_programming_error() -> None:
    with pytest.raises(InternalError, match="not in INPUT_KINDS"):
        input_not_found("wheel", "a.whl")


def test_the_command_line_says_it_framed_coded_and_trusted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "gone-1.0-py3-none-any.whl"
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", str(missing)])
    assert __main__.main() == 1
    lines = capsys.readouterr().err.splitlines()
    text = f"wheel file not found: {quote_source(missing)}"
    assert lines == [f"ERROR: loom wheel: {text} [input-not-found]"]
    assert trusted_message(lines[0]) is INPUT_NOT_FOUND


def test_the_library_raises_it_coded(tmp_path: Path) -> None:
    missing = tmp_path / "gone-1.0-py3-none-any.whl"
    with pytest.raises(FileNotFoundError) as caught:
        embed_sbom_in_wheel(missing, "{}")
    assert raised_as(caught.value, INPUT_NOT_FOUND)


def test_a_missing_fragment_is_one_coded_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Said once per call, its path escaped."""
    log = logging.getLogger("pitloom.test")
    with caplog.at_level(logging.WARNING, logger="pitloom.test"):
        warn_fragment_not_found(log, "f\n.json", required=False)
        warn_fragment_not_found(log, "f.json", required=True)
    said = [(r.getMessage(), getattr(r, CODE_ATTR)) for r in caplog.records]
    assert said == [
        (FRAGMENT_LINE.render({"path": "f\n.json"}), "input-not-found/fragment"),
        (
            "required SBOM fragment not found: 'f.json'; the merge will fail",
            "input-not-found/fragment",
        ),
    ]
    assert "\n" not in said[0][0]


@pytest.mark.parametrize(
    ("kind", "there", "path"),
    [
        ("wheel file", None, "x y.whl"),
        ("wheel file", "dir", "x y.whl"),
        ("project directory", "file", "x y"),
        ("project path", None, "x\ny"),
        ("SBOM file", None, "https://u:p@h/s.json"),
    ],
    ids=["absent", "not-a-file", "not-a-dir", "escaped", "url"],
)
def test_the_printed_line_is_the_raised_text(
    kind: str,
    there: str | None,
    path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One probe and one formatter: the command line prints, with the code,
    exactly what the library raises, a URL's credentials masked in both."""
    monkeypatch.chdir(tmp_path)
    if there == "dir":
        Path(path).mkdir()
    elif there == "file":
        Path(path).write_bytes(b"")
    say_input_not_found(kind, path)
    raised = input_not_found(kind, path)
    assert capsys.readouterr().err == f"ERROR: {raised} [input-not-found]\n"
    assert "u:p" not in str(raised)
