# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Caller labels and caller scripts of a loom run: the cwd-relative label
rules, the frames skipped and the provenance ``Source:`` of a caller.

See also:
- :mod:`tests.core.test_loom_caller` for the stack inspection basics.
"""

from __future__ import annotations

import collections
import contextlib
import inspect
import json
import re
import runpy
import sys
from pathlib import Path

import pytest

from pitloom import _loom_caller, loom

pytestmark = pytest.mark.platform

# A symbolic link needs no privilege on a POSIX system only.
_POSIX = sys.platform != "win32"
_needs_symlinks = pytest.mark.skipif(not _POSIX, reason="symlinks: POSIX only")

_FRAME = collections.namedtuple("_FRAME", ["filename", "function"])

# Pitloom's own modules: a caller is never one of them.
_LOOM_MODULES = [
    "loom.py",
    "_loom_active_run.py",
    "_loom_caller.py",
    "_loom_dataset.py",
    "_loom_dataset_keys.py",
    "_loom_model.py",
]


@pytest.fixture(name="linked")
def linked_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The current directory is ``link``, a symbolic link to ``real``; ``real``
    holds ``sub`` and ``sub/deep``, a link to ``other/deeper``, outside it."""
    root = tmp_path.resolve()
    (root / "real" / "sub").mkdir(parents=True)
    (root / "other" / "deeper").mkdir(parents=True)
    (root / "real" / "sub" / "deep").symlink_to(
        root / "other" / "deeper", target_is_directory=True
    )
    (root / "link").symlink_to(root / "real", target_is_directory=True)
    monkeypatch.chdir(root / "link")
    return root


@_needs_symlinks
@pytest.mark.parametrize(
    ("text", "kind"),
    [("a..b.txt", "file"), ("x..y/z", "dir")],
    ids=["file", "dir"],
)
def test_a_dotted_name_is_no_parent_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str, kind: str
) -> None:
    """``..`` inside a name is not a parent step: the path stays lexical, so
    a symbolic link in it is not followed out of the current directory."""
    root = tmp_path.resolve()
    (root / "proj").mkdir()
    (root / "outside" / "dir").mkdir(parents=True)
    (root / "outside" / "target.txt").write_bytes(b"x")
    target = root / "outside" / ("target.txt" if kind == "file" else "dir")
    (root / "proj" / text.split("/", maxsplit=1)[0]).symlink_to(
        target, target_is_directory=kind == "dir"
    )
    monkeypatch.chdir(root / "proj")
    assert _loom_caller.cwd_relative_label(text) == text


@_needs_symlinks
def test_a_lexical_path_is_read_as_written_below_a_linked_cwd(linked: Path) -> None:
    """A path through the link is not below the real current directory as
    written, whatever it resolves to: the bare name, as it is read lexically."""
    label = _loom_caller.cwd_relative_label
    assert label("sub/x") == "sub/x"
    assert label(str(linked / "link" / "sub" / "x")) == "x"
    assert label(str(linked / "real" / "sub" / "x")) == "sub/x"


@_needs_symlinks
def test_a_parent_step_is_resolved_through_symlinks(linked: Path) -> None:
    """With a ``..``, the path is resolved as the OS opens it: ``deep`` is a
    link out of the directory, so ``deep/..`` leaves it."""
    label = _loom_caller.cwd_relative_label
    assert label("sub/deep/../y") == "y"
    assert label("sub/../sibling/x") == "sibling/x"
    assert label(str(linked / "link" / "sub" / ".." / "sibling" / "x")) == ("sibling/x")


@_needs_symlinks
def test_a_parent_of_a_linked_cwd_names_the_bare_file(
    linked: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(linked / "link" / "sub")
    assert _loom_caller.cwd_relative_label("../sibling/x") == "x"
    assert _loom_caller.cwd_relative_label("x/y") == "x/y"


@_needs_symlinks
def test_caller_script_below_a_linked_cwd_is_relative(
    linked: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The script is below the current directory whichever way it is named;
    its path is kept as invoked."""
    (linked / "real" / "s.py").write_bytes(b"x = 1\n")
    frames = [_FRAME(str(linked / "link" / "s.py"), "f")]
    monkeypatch.setattr(inspect, "stack", lambda: frames)
    # pylint: disable-next=protected-access
    path = _loom_caller._get_caller_script_path()
    assert path is not None and path == frames[0].filename
    assert _loom_caller.cwd_relative_label(path) == "s.py"


def test_caller_provenance_names_the_script_below_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Source:`` is the label from the current directory, never the
    absolute machine path."""
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path)
    frames = [_FRAME(str(tmp_path / "sub" / "train.py"), "fit")]
    monkeypatch.setattr(inspect, "stack", lambda: frames)
    # pylint: disable-next=protected-access
    info = _loom_caller._get_caller_info()
    assert info.startswith("Source: sub/train.py | ")
    assert str(tmp_path) not in info
    assert info.endswith("function: fit)")


def test_caller_info_names_the_calling_function_not_a_loom_module() -> None:
    """The frame of ``_get_caller_info`` itself is in a skipped module."""
    # pylint: disable-next=protected-access
    info = _loom_caller._get_caller_info()
    assert "function: test_caller_info_names_the_calling_function" in info
    assert "_loom_caller.py" not in info


@pytest.mark.parametrize("module", _LOOM_MODULES)
def test_a_loom_module_frame_is_never_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: str
) -> None:
    """The caller is the first frame outside Pitloom's loom modules."""
    script = tmp_path / "user_script.py"
    script.write_bytes(b"x = 1\n")
    frames = [
        _FRAME(str(Path("src") / "pitloom" / module), "inner"),
        _FRAME(str(script), "outer"),
    ]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(inspect, "stack", lambda: frames)
    # pylint: disable=protected-access
    info = _loom_caller._get_caller_info()
    assert info.startswith("Source: user_script.py | ")
    assert info.endswith("function: outer)")
    assert _loom_caller._get_caller_script_path() == str(script)


def test_contextlib_frame_is_not_the_script_of_a_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Between ``loom.run`` and a function it decorates stands ``contextlib``:
    the script is the function's caller, not the standard library."""
    script = tmp_path / "user_script.py"
    script.write_bytes(b"x = 1\n")
    frames = [_FRAME(contextlib.__file__, "inner"), _FRAME(str(script), "outer")]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(inspect, "stack", lambda: frames)
    # pylint: disable-next=protected-access
    assert _loom_caller._get_caller_script_path() == str(script)


def test_decorated_run_records_the_script_that_calls_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real stack of a decorated run: the script file element is this
    file, not ``contextlib.py``."""
    output = tmp_path / "frag.spdx3.json"
    monkeypatch.chdir(Path(__file__).parent)

    @loom.run(output)
    def train() -> None:
        loom.set_model("m")
        loom.add_dataset("d")

    train()
    graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    names = {e["name"] for e in graph if e.get("type") == "software_File"}
    assert Path(__file__).name in names
    assert "contextlib.py" not in names


@_needs_symlinks
def test_a_script_run_through_a_link_is_named_as_invoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``link.py -> real/s.py``: the script's file and every provenance
    ``Source:`` name ``link.py``, never the file the link points to."""
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "s.py").write_bytes(b"x = 1\n")
    (tmp_path / "link.py").symlink_to(tmp_path / "real" / "s.py")
    monkeypatch.chdir(tmp_path)
    frames = [_FRAME(str(tmp_path / "link.py"), "main")]
    monkeypatch.setattr(inspect, "stack", lambda: frames)
    with loom.run(tmp_path / "frag.json"):
        loom.set_model("m")
        loom.add_dataset("d")
    graph = json.loads((tmp_path / "frag.json").read_text(encoding="utf-8"))["@graph"]
    files = [e["name"] for e in graph if e.get("type") == "software_File"]
    sources = {
        source
        for e in graph
        if e.get("type") == "Annotation"
        for source in re.findall(r'"source":"([^"]*)"', e.get("statement", ""))
    }
    assert files == ["link.py"]
    assert sources == {"link.py"}


def test_a_script_that_changes_directory_is_still_hashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A script named relatively (``train.py``) is hashed at the run's exit
    from where it was, though it changed directory during the run."""
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(tmp_path)
    source = (
        "import os\nfrom pitloom import loom\n"
        "with loom.run(OUT):\n"
        "    loom.set_model('m')\n    loom.add_dataset('d')\n"
        "    os.chdir(OTHER)\n"
    )
    (tmp_path / "train.py").write_bytes(source.encode())
    out = tmp_path / "frag.json"
    runpy.run_path("train.py", {"OUT": out, "OTHER": other})
    assert Path.cwd().samefile(other)
    graph = json.loads(out.read_text(encoding="utf-8"))["@graph"]
    (script,) = [e for e in graph if e.get("type") == "software_File"]
    assert script["name"] == "train.py"
    assert script.get("verifiedUsing")
