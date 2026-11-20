# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A temporary directory that cannot be removed, on each surface that makes
one: one ``temp-dir-unwritable`` ``WARNING:`` after that surface's frame
(Git, PyPI, the Hugging Face Hub, the model scan, the build hook's staging
directory, the build's work and extraction directories), naming the
directory and never its path. The removal is made to fail on the name
``rmtree`` of :mod:`pitloom.core.temp_dirs`, never on :mod:`shutil`.
And: a line of another code after a frame that does not frame it is not
trusted.

See also: tests/core/test_temp_dirs.py (the helpers),
tests/messages/test_frames_build.py (the frames) and
tests/messages/test_build.py (the line).
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pitloom.core import temp_dirs
from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
from pitloom.core.build_signals import TerminationGuard
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.url_masking import (
    CHECKOUT_DIR_PREFIX,
    DOWNLOAD_DIR_PREFIX,
    HUB_DIR_PREFIX,
)
from pitloom.extract.remote import pypi
from pitloom.extract.remote._hub_files import hub_files
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import fetch_git_project
from pitloom.extract.scanner_wheel import _Scratch
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    BUILD_FRAME,
    FRAMES,
    GIT_FRAME,
    HF_FRAME,
    HOOK_STEP_FRAME,
    MESSAGES,
    PYPI_FRAME,
    SCAN_FRAME,
    Frame,
    Message,
    trusted_message,
)
from pitloom.messages.build import TEMP_DIR_UNWRITABLE
from tests._git_say_repos import printed
from tests._message_drift import SAMPLES
from tests.build_and_read_shared import RUN_BUILD, raising_build, use_sys_tmp
from tests.extract.conftest import make_hook, write_pyproject

pytestmark = pytest.mark.platform  # temporary directories, path spellings

_CODE = TEMP_DIR_UNWRITABLE.code
_PYPI_URL = "https://pypi.org/project/demo/1.0/"


@pytest.fixture(name="sys_tmp")
def _sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A system temp directory of the test's own: what a removal leaves
    behind is in it."""
    return use_sys_tmp(tmp_path, monkeypatch)


@pytest.fixture(name="unremovable")
def _unremovable(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every removal through the helpers fails: the directory stays. The
    paths asked to be removed are collected."""
    asked: list[Path] = []

    def rmtree(path: Path | str, *, ignore_errors: bool = False) -> None:
        del ignore_errors
        asked.append(Path(path))

    monkeypatch.setattr(temp_dirs, "rmtree", rmtree)
    return asked


#: What the record and the line show for the directory of a remote source:
#: masked in the record itself (a library caller's log holds no random
#: name, as on 0.24); the other directories show their names.
_SHOWN = {
    CHECKOUT_DIR_PREFIX: "<checkout>",
    DOWNLOAD_DIR_PREFIX: "<download>",
    HUB_DIR_PREFIX: "<download>",
}


def _only_line(
    caplog: pytest.LogCaptureFixture, frame: Frame, prefix: str, sys_tmp: Path
) -> str:
    """The one ``temp-dir-unwritable`` line said, checked: after *frame*,
    for the one directory left in *sys_tmp*, which starts with *prefix*,
    named by its name (its placeholder, :data:`_SHOWN`, for a remote
    source's) in the record and the printed line alike, never by its
    path."""
    (record,) = [r for r in caplog.records if getattr(r, CODE_ATTR, None) == _CODE]
    (left,) = [p for p in sys_tmp.iterdir() if p.name.startswith(prefix)]
    shown = _SHOWN.get(prefix, left.name)
    head = f"{frame.render({})}DIR="
    text = (
        f"{head}{shown}: could not be fully removed; left in the system temp directory"
    )
    assert record.getMessage() == text
    if prefix in _SHOWN:
        assert left.name not in caplog.text and prefix not in record.getMessage()
    lines = printed(caplog, _CODE)
    assert len(lines) == 1
    line = lines[0]
    assert trusted_message(line) is TEMP_DIR_UNWRITABLE
    assert line == f"WARNING: {text} [temp-dir-unwritable]"
    assert str(sys_tmp) not in caplog.text and sys_tmp.name not in caplog.text
    return line


# -- each surface --------------------------------------------------------------


def _git() -> None:
    with pytest.raises(RemoteSourceError):  # offline: refused inside the block
        with fetch_git_project(
            "https://example.org/g/p", policy=RemoteFetchPolicy(offline=True)
        ):
            pass


def _pypi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pypi, "_download", lambda *_a, **_k: SimpleNamespace())
    with pypi.fetch_pypi_file(_PYPI_URL, kind=pypi.WHEEL):
        pass


def _hub() -> None:
    with hub_files(RemoteFetchPolicy()):
        pass


def _scan() -> None:
    with TerminationGuard() as guard:
        scratch = _Scratch(guard, 1000, "m.whl")
        assert scratch.path().is_dir()
        scratch.remove()


def _hook(tmp_path: Path, finalize: Callable[[Any, dict[str, Any]], None]) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    write_pyproject(project)
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    finalize(hook, build_data)


def _by_hook_finalize(hook: Any, build_data: dict[str, Any]) -> None:
    hook.finalize("standard", build_data, "")


def _by_weakref_finalize(hook: Any, build_data: dict[str, Any]) -> None:
    """Hatchling never calls ``finalize()`` (``--hooks-only``, a failed
    build): the ``weakref.finalize`` runs it when the hook is collected or the
    process exits, run here in-process."""
    del build_data
    assert hook._remove_staging.alive  # pylint: disable=protected-access
    hook._remove_staging()  # pylint: disable=protected-access


_SURFACES: list[Any] = [
    pytest.param(_git, GIT_FRAME, CHECKOUT_DIR_PREFIX, id="git"),
    pytest.param(_pypi, PYPI_FRAME, DOWNLOAD_DIR_PREFIX, id="pypi"),
    pytest.param(_hub, HF_FRAME, HUB_DIR_PREFIX, id="hub"),
    pytest.param(_scan, SCAN_FRAME, "pitloom-model-scan-", id="scan"),
]


@pytest.mark.parametrize(("surface", "frame", "prefix"), _SURFACES)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_a_surface_says_a_directory_it_could_not_remove_once_after_its_frame(
    surface: Callable[..., None],
    frame: Frame,
    prefix: str,
    sys_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    unremovable: list[Path],
) -> None:
    with caplog.at_level(logging.INFO):
        if surface is _pypi:
            surface(monkeypatch)
        else:
            surface()
    _only_line(caplog, frame, prefix, sys_tmp)
    assert [p.parent for p in unremovable] and {p.parent for p in unremovable} == {
        sys_tmp
    }
    assert len(list(sys_tmp.iterdir())) == 1


@pytest.mark.parametrize(
    "finalize",
    [_by_hook_finalize, _by_weakref_finalize],
    ids=["finalize", "weakref"],
)
@pytest.mark.usefixtures("unremovable")
def test_the_hook_staging_directory_is_one_warning_after_the_hook_frame(
    tmp_path: Path,
    sys_tmp: Path,
    caplog: pytest.LogCaptureFixture,
    finalize: Callable[[Any, dict[str, Any]], None],
) -> None:
    with caplog.at_level(logging.INFO):
        _hook(tmp_path, finalize)
    line = _only_line(caplog, HOOK_STEP_FRAME, "pitloom-hatch-", sys_tmp)
    assert HOOK_STEP_FRAME.render({}) in line


@pytest.mark.usefixtures("unremovable")
def test_a_build_says_its_work_and_extraction_directories_once_each(
    tmp_path: Path,
    sys_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The work directory goes through ``TemporaryDirectory.cleanup`` and
    falls back to the helper when that raises, as it does on Windows with a
    file still open; the extraction directory through the helper."""

    # pylint: disable-next=too-few-public-methods
    class Refusing:
        """A ``TemporaryDirectory`` whose cleanup always fails."""

        def __init__(self, prefix: str, **_kw: object) -> None:
            self.name = tempfile.mkdtemp(prefix=prefix)

        def cleanup(self) -> None:
            raise PermissionError(13, "in use", self.name)

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.tempfile",
        SimpleNamespace(TemporaryDirectory=Refusing),
    )
    # The extraction directory is made by the helper, which uses its own name.
    monkeypatch.setattr(RUN_BUILD, raising_build(RuntimeError("x"), sys_tmp, set()))
    project = tmp_path / "proj"
    project.mkdir()
    with caplog.at_level(logging.INFO):
        assert build_and_read_wheel(project, timeout=60) is None
    lines = printed(caplog, _CODE)
    prefix = f"WARNING: {BUILD_FRAME.render({})}DIR="
    names = sorted(line[len(prefix) :].split(":", 1)[0] for line in lines)
    assert [n.split("-", 1)[0] for n in names] == ["pitloom", "plb"]
    assert names[0].startswith("pitloom-build-and-read-")
    assert all(line.startswith(prefix) for line in lines)
    assert all(trusted_message(line) is TEMP_DIR_UNWRITABLE for line in lines)
    assert sorted(p.name for p in sys_tmp.iterdir()) == names
    assert str(sys_tmp) not in caplog.text


def test_a_removal_that_works_says_nothing(
    sys_tmp: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The other side: the helper's own ``rmtree`` removes, so no line."""
    with caplog.at_level(logging.INFO):
        with temp_dirs.temp_dir("t-", frame=GIT_FRAME) as work:
            (work / "f").write_text("x", encoding="utf-8")
    assert not printed(caplog) and not list(sys_tmp.iterdir())


# -- a line is trusted after the frames that frame its code --------------------

#: Each code a frame frames, by frame, and the codes the frames in all frame.
_FRAMED = sorted({c for f in FRAMES if f.codes for c in f.codes})


def _text(message: Message, level: str) -> str:
    line = next(ln for ln in message.lines if ln.level == level)
    return line.render({n: SAMPLES[n] for n in line.fields})


@pytest.mark.parametrize(
    "frame",
    [GIT_FRAME, HF_FRAME, PYPI_FRAME, SCAN_FRAME, HOOK_STEP_FRAME, BUILD_FRAME],
    ids=["git", "hf", "pypi", "scan", "hook", "build"],
)
@pytest.mark.parametrize("code", _FRAMED)
def test_a_line_is_trusted_after_a_frame_only_if_the_frame_frames_its_code(
    frame: Frame, code: str
) -> None:
    """The prefix of one frame before the line of a code that another frame
    frames: trusted exactly when this frame allows the code (and the line's
    level)."""
    message = MESSAGES[code]
    for line in message.lines:
        text = line.render({n: SAMPLES[n] for n in line.fields})
        printed_line = f"{line.level}: {frame.render({})}{text} [{code}]"
        trusted = trusted_message(printed_line) is message
        # Two frames can share a prefix (the hook's ERROR frame and its steps).
        allowed = any(
            f.allows(code, line.level) for f in FRAMES if f.template == frame.template
        )
        assert trusted is allowed, printed_line


@pytest.mark.parametrize(
    "prefixes",
    [
        (BUILD_FRAME, GIT_FRAME),
        (GIT_FRAME, BUILD_FRAME),
        (HF_FRAME, PYPI_FRAME, SCAN_FRAME),
    ],
    ids=["build-git", "git-build", "three"],
)
def test_two_frames_before_one_line_are_no_line_of_pitloom(
    prefixes: tuple[Frame, ...],
) -> None:
    """A frame is one prefix: a second one is the line's own text, which
    the template does not hold."""
    text = _text(TEMP_DIR_UNWRITABLE, "WARNING")
    head = "".join(f.render({}) for f in prefixes)
    assert trusted_message(f"WARNING: {head}{text} [{_CODE}]") is None
    assert trusted_message(f"WARNING: {prefixes[0].render({})}{text} [{_CODE}]")


@pytest.mark.parametrize("prefix", ["Fetch: ", "Pitloom: ", "build: ", "Build:"])
def test_a_prefix_of_no_frame_is_not_trusted(prefix: str) -> None:
    text = _text(TEMP_DIR_UNWRITABLE, "WARNING")
    assert trusted_message(f"WARNING: {prefix}{text} [{_CODE}]") is None
