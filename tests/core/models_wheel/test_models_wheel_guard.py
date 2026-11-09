# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a file discovery in a Git URL's clone runs within: no module of the
clone is imported though the working directory is on the import path (a
library caller's ``python -c``), and a wall-clock cap stops an endless walk
(two folder links to ``.``). A local project imports and walks as before.

The import checks run in a child ``python -c`` (``''`` first on its import
path), so the test process's own import path is left as it is; each
module of the repository only writes a marker file.

See also: :mod:`tests.core.models_wheel.test_models_wheel_clone_code` (the
build settings that name code).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pitloom.core import _models_wheel_guard as guard
from pitloom.core._models_wheel_types import DiscoveryTimeoutError
from pitloom.core.clone_mark import reading_remote_clone
from pitloom.core.models import get_wheel_files
from pitloom.logging_config import CODE_ATTR
from tests._symlink import CAN_SYMLINK

_SRC = str(Path(guard.__file__).resolve().parents[2])
_ST = (
    b'[build-system]\nrequires = ["setuptools"]\n'
    b'build-backend = "setuptools.build_meta"\n'
    b'[project]\nname = "demo"\nversion = "1"\n'
    b'[tool.setuptools]\npackages = ["demo"]\ninclude-package-data = true\n'
)
_PD = (
    b'[build-system]\nrequires = ["pdm-backend"]\n'
    b'build-backend = "pdm.backend"\n[project]\nname = "demo"\nversion = "1"\n'
)
_ENTRY_POINTS = {
    "evil-1.dist-info/METADATA": b"Metadata-Version: 2.1\nName: evil\nVersion: 1\n",
    "evil-1.dist-info/entry_points.txt": b"[pdm.build.hook]\nx = evilmod\n"
    b"[distutils.commands]\negg_info = evilmod:X\n",
    "evilmod.py": b"MARKclass X:\n    pass\n",
}
#: (id, backend's pyproject.toml, the repository's modules).
_VECTORS = [
    ("st-cython", _ST, {"Cython/__init__.py": b"MARKraise ImportError\n"}),
    ("st-dl", _ST, {"dl.py": b"MARKraise ImportError\n"}),
    ("st-entry-point", _ST, _ENTRY_POINTS),
    ("pdm-entry-point", _PD, _ENTRY_POINTS),
]
_CHILD = (
    "import sys\n"
    "from pathlib import Path\n"
    "from pitloom.core.clone_mark import reading_remote_clone\n"
    "from pitloom.core.models import get_wheel_files\n"
    "root = Path(sys.argv[1])\n"
    "assert sys.path[0] == ''\n"
    "if sys.argv[2] == 'clone':\n"
    "    with reading_remote_clone(str(root)):\n"
    "        get_wheel_files(root)\n"
    "else:\n"
    "    get_wheel_files(root)\n"
)


def _project(
    root: Path, pyproject: bytes, files: dict[str, bytes], marker: Path
) -> Path:
    line = f"import pathlib; pathlib.Path({str(marker)!r}).write_text('x')\n"
    for name, content in {
        "pyproject.toml": pyproject,
        "demo/__init__.py": b"",
        "MANIFEST.in": b"include demo/*.txt\n",
        "demo/a.txt": b"x",
        **files,
    }.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content.replace(b"MARK", line.encode()))
    return root


def _run_child(cwd: Path, root: Path, how: str) -> None:
    env = {**os.environ, "PYTHONPATH": _SRC}
    done = subprocess.run(  # nosec B603
        [sys.executable, "-c", _CHILD, str(root), how],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")


@pytest.mark.parametrize(
    ("pyproject", "files"), [v[1:] for v in _VECTORS], ids=[v[0] for v in _VECTORS]
)
def test_no_module_of_the_clone_is_imported_from_the_working_directory(
    tmp_path: Path, pyproject: bytes, files: dict[str, bytes]
) -> None:
    marker = tmp_path / "RAN"
    root = _project(tmp_path / "clone", pyproject, files, marker)
    (tmp_path / "cwd").mkdir()
    _run_child(tmp_path / "cwd", root, "clone")
    assert not marker.exists()


def test_a_local_project_imports_from_the_working_directory_as_before(
    tmp_path: Path,
) -> None:
    """The control: the same project read locally runs that module, as
    setuptools always has."""
    marker = tmp_path / "RAN"
    root = _project(tmp_path / "local", _ST, _VECTORS[0][2], marker)
    (tmp_path / "cwd").mkdir()
    _run_child(tmp_path / "cwd", root, "local")
    assert marker.exists()


def test_the_import_path_is_restored_after_the_discovery(tmp_path: Path) -> None:
    before = list(sys.path)
    sys.path.insert(0, str(tmp_path / "inside"))
    try:
        with reading_remote_clone(str(tmp_path)):
            with guard.discovery_chdir(tmp_path):
                assert str(tmp_path / "inside") not in sys.path
                assert "" not in sys.path and "." not in sys.path
                assert all(os.path.isabs(os.fspath(e)) for e in sys.path)
        assert sys.path[0] == str(tmp_path / "inside")
    finally:
        sys.path[:] = before


@pytest.mark.parametrize("entry", ["", ".", "rel", 7, "a\0b", "/a\0b"], ids=repr)
def test_an_entry_that_is_no_absolute_path_is_off_the_path(
    tmp_path: Path, entry: object
) -> None:
    # pylint: disable-next=protected-access
    assert not guard._kept_entry(entry, tmp_path)


def test_a_discovery_past_the_cap_stops_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(guard, "DISCOVERY_SECONDS", 0.2)
    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with reading_remote_clone(str(tmp_path)):
            with pytest.raises(DiscoveryTimeoutError, match="after 0.2 seconds"):
                with guard.discovery_deadline(tmp_path):
                    while time.monotonic() - started < 60:
                        pass
    assert time.monotonic() - started < 30
    assert [getattr(r, CODE_ATTR, None) for r in caplog.records] == ["over-cap"]
    assert "larger than the 1-second file-discovery cap; file list not read" in (
        caplog.text
    )


@pytest.mark.parametrize("clone", [False, True], ids=["local", "profiled"])
def test_no_cap_out_of_a_clone_or_under_a_profiler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clone: bool
) -> None:
    """A local project has no cap; nor has a run a profiler watches, whose
    hook stays in place."""
    monkeypatch.setattr(guard, "DISCOVERY_SECONDS", 0.0)

    def profiler(_frame: object, _event: str, _arg: object) -> None:
        return None

    with ExitStack() as stack:
        if clone:
            stack.enter_context(reading_remote_clone(str(tmp_path)))
            sys.setprofile(profiler)
            stack.callback(sys.setprofile, None)
        with guard.discovery_deadline(tmp_path):
            assert sys.getprofile() is (profiler if clone else None)
            time.sleep(0.001)


def test_a_block_ending_past_the_cap_ends_unstopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No call is made in the block; the cap is past when it ends, and its
    end is not cut short."""
    monkeypatch.setattr(guard, "DISCOVERY_SECONDS", 0.0)
    with reading_remote_clone(str(tmp_path)):
        with guard.discovery_deadline(tmp_path):
            pass
    assert sys.getprofile() is None


def test_a_swallowing_handler_does_not_keep_the_cap_from_stopping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backend's ``except Exception`` does not catch the stop."""
    monkeypatch.setattr(guard, "DISCOVERY_SECONDS", 0.05)
    swallowed: list[BaseException] = []
    give_up = time.monotonic() + 30  # the clock may tick in 15 ms steps
    with reading_remote_clone(str(tmp_path)):
        with pytest.raises(DiscoveryTimeoutError):
            with guard.discovery_deadline(tmp_path):
                while time.monotonic() < give_up:
                    try:
                        time.sleep(0.01)
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        swallowed.append(exc)
    assert not swallowed and sys.getprofile() is None


_LOOP = {"demo/a": ".", "demo/b": "."}
_FIND = b'packages.find.where = ["."]\n'
_DATA = b'[tool.setuptools.package-data]\ndemo = ["**/*.txt"]\n'
_LOOPS = [
    ("setuptools-auto", _ST.replace(b'packages = ["demo"]\n', b"")),
    ("setuptools-find", _ST.replace(b'packages = ["demo"]\n', _FIND)),
    ("setuptools-package-data", _ST + _DATA),
    ("pdm-includes", _PD + b'[tool.pdm.build]\nincludes = ["demo/**/*"]\n'),
]


# A walk the cap cuts short can leave a standard-library scandir iterator
# to be closed only when the stop is dropped.
@pytest.mark.filterwarnings("ignore:unclosed scandir iterator:ResourceWarning")
@pytest.mark.filterwarnings(
    "ignore:Exception ignored in. <(posix|nt).ScandirIterator"
    ":pytest.PytestUnraisableExceptionWarning"
)
@pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symlink")
@pytest.mark.parametrize(
    "pyproject", [v[1] for v in _LOOPS], ids=[v[0] for v in _LOOPS]
)
def test_a_link_loop_in_a_clone_is_stopped_by_the_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    pyproject: bytes,
) -> None:
    """A clone fetched by Pitloom has no folder link left; one read in a
    marked folder of a library caller's own still ends."""
    monkeypatch.setattr(guard, "DISCOVERY_SECONDS", 1.0)
    root = tmp_path / "clone"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    (root / "pyproject.toml").write_bytes(pyproject)
    for name, target in _LOOP.items():
        (root / name).symlink_to(target, target_is_directory=True)
    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with reading_remote_clone(str(root)):
            _merkle, _files, cleanup = get_wheel_files(root)
    cleanup()
    assert time.monotonic() - started < 60
    # The fallback discovery may pass the short cap too on a loaded machine.
    codes = [getattr(r, CODE_ATTR, None) for r in caplog.records]
    assert "over-cap" in codes
    assert "file discovery failed" not in caplog.text


@pytest.mark.parametrize(
    ("event", "exiting", "until", "stops"),
    [
        ("call", False, -1.0, True),
        ("c_call", False, -1.0, True),
        ("return", False, -1.0, False),
        ("call", True, -1.0, False),
        ("call", False, 60.0, False),
    ],
    ids=["call", "c-call", "return", "exit", "in-time"],
)
def test_the_hook_stops_a_call_past_the_cap_only(
    tmp_path: Path, event: str, exiting: bool, until: float, stops: bool
) -> None:
    """The hook itself (a profile hook is not traced, so it is called here):
    a call of Python or C past the cap stops, never one of the cap's own
    end."""
    # pylint: disable=protected-access
    deadline = guard._Deadline(tmp_path)
    deadline._until = time.monotonic() + until
    here = test_the_hook_stops_a_call_past_the_cap_only.__code__
    frame: Any = SimpleNamespace(f_code=guard._EXIT_CODE if exiting else here)
    with pytest.raises(guard._Expired) if stops else ExitStack():
        deadline._check(frame, event, None)
