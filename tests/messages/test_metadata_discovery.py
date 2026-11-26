# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""File discovery's lines through ``get_wheel_files``: a discoverer that
failed or that found nothing (``file-discovery-unusable``,
``file-discovery-needs-build``), against a project that has a ``[project]``
table or none; the ``uv_build`` hint and ``--allow-build``'s failure as
lines of their own; two files that map to one wheel path
(``file-discovery-conflict``). The ``Build: `` prefix is gone from these
lines and stays on the ``--allow-build`` invocation line (PR 14).

See also: tests/core/models_wheel/test_models_wheel_dispatch.py (the
dispatch itself), tests/messages/test_metadata_surfaces.py (the command
line).
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

from pitloom.core import _models_wheel_build_and_read
from pitloom.core._models_wheel_setuptools import _dedupe_by_distribution_path
from pitloom.core._models_wheel_types import IncludedFile, warn_discovery_failed
from pitloom.core.build_options import BuildOptions
from pitloom.core.models import get_wheel_files
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    SURFACE_CLI,
    SURFACE_LIBRARY,
    advice_surface,
    trusted_message,
)
from pitloom.messages.file_discovery import warn_discovery
from tests._code_records import coded
from tests.build_and_read_shared import make_backend_project

pytestmark = pytest.mark.platform

_UNUSABLE = "file-discovery-unusable"
_NEEDS_BUILD = "file-discovery-needs-build"
_LOG = logging.getLogger("pitloom.core._models_wheel_dispatch")
_BUILD_SYSTEM = '[build-system]\nrequires = ["{b}"]\nbuild-backend = "{b}"\n'


def _discovery(caplog: pytest.LogCaptureFixture) -> list[tuple[str | None, str]]:
    """The coded records of file discovery, in order."""
    return [(c, m) for c, m in coded(caplog) if c and c.startswith("file-discovery-")]


@pytest.fixture(autouse=True)
def _stubbed_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hatchling's heuristic finds no file, and a real build (``--allow-build``)
    fails having said its own line: the line under test is the last one."""
    monkeypatch.setattr(WheelBuilder, "recurse_included_files", lambda _s: iter([]))
    monkeypatch.setattr(
        _models_wheel_build_and_read, "build_and_read_wheel", lambda *a, **k: None
    )


def _discoverer(
    monkeypatch: pytest.MonkeyPatch, *, fail: bool, backend: str = "setuptools"
) -> None:
    """The *backend* discoverer gives up (``None``), having said it failed
    (*fail*) or not."""

    def give_up(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> None:
        del pyproject_data
        if fail:
            warn_discovery_failed(
                logging.getLogger("pitloom.test_discovery"),
                "Setuptools",
                project_dir,
                RuntimeError("boom"),
            )

    monkeypatch.setattr(f"pitloom.core._models_wheel_{backend}.discover", give_up)


def _setup_py_only(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        _BUILD_SYSTEM.format(b="setuptools.build_meta").replace(
            'requires = ["setuptools.build_meta"]', 'requires = ["setuptools"]'
        ),
        encoding="utf-8",
    )


# -- rows 1 to 3: a discoverer that failed or found nothing ------------------


def _with_project(root: Path) -> None:
    make_backend_project(root, "setuptools.build_meta")


def _without_project(root: Path) -> None:
    _setup_py_only(root)


@pytest.mark.parametrize(
    ("layout", "fail", "expected"),
    [
        (
            _with_project,
            True,
            [
                (_UNUSABLE, "Setuptools file discovery failed; boom"),
                (_UNUSABLE, "file discovery failed; Hatchling heuristic used"),
            ],
        ),
        (
            _without_project,
            True,
            [
                (_UNUSABLE, "Setuptools file discovery failed; boom"),
                (_UNUSABLE, "file discovery failed and no [project] table"),
            ],
        ),
        (
            _with_project,
            False,
            [(_NEEDS_BUILD, "no static Setuptools config resolvable; Hatchling")],
        ),
        (
            _without_project,
            False,
            [(_NEEDS_BUILD, "no static Setuptools config resolvable and no [project]")],
        ),
    ],
    ids=["failed-project", "failed-no-project", "empty-project", "empty-no-project"],
)
def test_a_discoverer_that_gives_up_says_why_and_what_followed(
    layout: Callable[[Path], None],
    fail: bool,
    expected: list[tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Both sides of ``failed and [project] present``: the line's cause is
    the discoverer's failure (said above it) or that it found nothing, and
    its outcome follows ``[project]`` (the heuristic, or no file list)."""
    layout(tmp_path)
    _discoverer(monkeypatch, fail=fail)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        get_wheel_files(tmp_path)
    said = _discovery(caplog)
    assert len(said) == len(expected)
    for (code, message), (want_code, part) in zip(said, expected, strict=True):
        assert code == want_code
        assert message.startswith(f"DIR={tmp_path}: ")
        assert part in message
        assert not message.startswith("Build: ")  # the prefix is gone
        line = f"WARNING: {message} [{code}]"
        assert trusted_message(line) is not None


def test_a_static_config_that_failed_introspection_is_its_own_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A ``[tool.setuptools]`` table with no ``[project]``: the backend could
    read it, so the line says the config failed, not that it is absent."""
    (tmp_path / "pyproject.toml").write_text(
        _BUILD_SYSTEM.format(b="setuptools.build_meta").replace(
            'requires = ["setuptools.build_meta"]', 'requires = ["setuptools"]'
        )
        + '[tool.setuptools]\npackages = ["a"]\n',
        encoding="utf-8",
    )
    _discoverer(monkeypatch, fail=False)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        get_wheel_files(tmp_path)
    ((code, message),) = _discovery(caplog)
    assert code == _UNUSABLE
    assert "Setuptools static config failed introspection" in message


# -- rows 4 to 6: no discoverer for the backend ------------------------------


def _uv_project(root: Path, *, project: bool, overrides: str = "") -> None:
    make_backend_project(root, "uv_build")
    if not project:
        (root / "pyproject.toml").write_text(
            '[build-system]\nrequires = ["uv_build"]\nbuild-backend = "uv_build"\n',
            encoding="utf-8",
        )
    if overrides:
        with (root / "pyproject.toml").open("a", encoding="utf-8") as stream:
            stream.write(f"\n[tool.uv.build-backend]\n{overrides}\n")


_NOT_AWARE = "file discovery not backend-aware for build-backend uv_build"
_UV_HINT = "[tool.uv.build-backend] overrides the heuristic cannot see"


@pytest.mark.parametrize(
    ("project", "allow_build", "overrides", "parts"),
    [
        (True, False, "", [_NOT_AWARE + "; Hatchling heuristic used"]),
        (False, False, "", [_NOT_AWARE + " and no [project] table"]),
        (
            True,
            True,
            "",
            ["build-and-read failed and " + _NOT_AWARE + "; Hatchling"],
        ),
        (
            False,
            True,
            "",
            ["build-and-read failed and " + _NOT_AWARE + " and no [project]"],
        ),
        (  # the hint is a record of its own, after the line
            True,
            False,
            'wheel-exclude = ["a/**"]',
            [_NOT_AWARE + "; Hatchling", _UV_HINT],
        ),
        (  # --allow-build was passed and failed: no hint to pass it
            True,
            True,
            'wheel-exclude = ["a/**"]',
            ["build-and-read failed and " + _NOT_AWARE],
        ),
        (  # an override that moves, not filters, the files
            True,
            False,
            'module-root = ""',
            [_NOT_AWARE + "; Hatchling"],
        ),
    ],
    ids=[
        "plain",
        "no-project",
        "build-failed",
        "build-failed-no-project",
        "hint",
        "hint-after-allow-build",
        "module-root",
    ],
)
def test_a_backend_without_a_discoverer_says_so_with_its_hint_and_build_failure(
    project: bool,
    allow_build: bool,
    overrides: str,
    parts: list[str],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The uv hint and "build-and-read failed" are lines (and records) of
    their own, never a tail of the same text."""
    _uv_project(tmp_path, project=project, overrides=overrides)
    options = BuildOptions()
    if allow_build:
        options = BuildOptions(allow=True)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        get_wheel_files(tmp_path, build_options=options)
    said = _discovery(caplog)
    assert [c for c, _ in said] == [_NEEDS_BUILD] * len(parts)
    for (_, message), part in zip(said, parts, strict=True):
        assert message.startswith(f"DIR={tmp_path}: ")
        assert part in message
        assert not message.startswith("Build: ")
    assert sum(_UV_HINT in m for _, m in said) == (_UV_HINT in parts[-1])
    # The build's own line (build-code-unsafe) keeps its prefix: only the
    # discovery lines lose it. A library call names the library's switch.
    invoked = [m for c, m in coded(caplog) if c == "build-code-unsafe"]
    assert all(m.startswith("Build: ") for m in invoked)
    assert all("BuildOptions.allow runs a PEP 517 build" in m for m in invoked)
    assert bool(invoked) is allow_build


@pytest.mark.parametrize(
    ("surface", "ask"),
    [
        (SURFACE_CLI, "pass --allow-build"),
        (SURFACE_LIBRARY, "pass BuildOptions(allow=True)"),
    ],
    ids=["cli", "library"],
)
def test_the_uv_hint_asks_for_a_build_as_the_surface_spells_it(
    surface: str, ask: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _uv_project(tmp_path, project=True, overrides='wheel-exclude = ["a/**"]')
    with caplog.at_level(logging.WARNING, logger="pitloom"), advice_surface(surface):
        get_wheel_files(tmp_path)
    (hint,) = [m for _, m in _discovery(caplog) if _UV_HINT in m]
    assert hint == (
        f"DIR={tmp_path}: {_UV_HINT}; {ask} for an exact file list from a real build"
    )


@pytest.mark.parametrize("backend", ["mesonpy", "maturin", "my_backend"])
def test_an_unrelated_backend_with_overrides_gets_no_uv_hint(
    backend: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    make_backend_project(tmp_path, backend)
    with (tmp_path / "pyproject.toml").open("a", encoding="utf-8") as stream:
        stream.write('\n[tool.uv.build-backend]\nwheel-exclude = ["a/**"]\n')
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        get_wheel_files(tmp_path)
    messages = [m for _, m in _discovery(caplog)]
    assert any(f"build-backend {backend}" in m for m in messages)
    assert not any("[tool.uv.build-backend]" in m for m in messages)


@pytest.mark.parametrize(
    "backend",
    ["a\nb", "a\x1b[31mb", "a b'c", "a\udcffb"],
    ids=["newline", "escape", "quote", "surrogate"],
)
def test_a_declared_backend_is_one_escaped_line(
    backend: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``build-backend`` is the project's text: whatever it holds, the line
    stays one line, with no raw control character, and encodes as UTF-8."""
    make_backend_project(tmp_path, "uv_build")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        get_wheel_files(tmp_path, assume_backend=backend)
    ((code, message),) = _discovery(caplog)
    assert code == _NEEDS_BUILD
    assert "\n" not in message and "\x1b" not in message
    message.encode("utf-8")  # a lone surrogate would raise here


# -- row 7: the failed discoverer, by name -----------------------------------


@pytest.mark.parametrize("name", ["Hatchling", "Setuptools", "Flit", "PDM", "Poetry"])
def test_a_failed_discoverer_is_named_and_says_its_error(
    name: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_discovery_failed(_LOG, name, tmp_path, RuntimeError("bad\nline"))
    ((code, message),) = _discovery(caplog)
    assert code == _UNUSABLE
    assert message == f"DIR={tmp_path}: {name} file discovery failed; bad line"


def test_a_failed_discoverer_of_a_downloaded_repository_shows_no_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A backend's text can quote a file it read: in a Git clone, its type
    alone."""
    monkeypatch.setattr(
        "pitloom.core._models_wheel_types.in_remote_clone", lambda: True
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_discovery_failed(_LOG, "Poetry", tmp_path, RuntimeError("/etc/secret"))
    ((_, message),) = _discovery(caplog)
    assert "RuntimeError (text not shown for a downloaded repository)" in message
    assert "/etc/secret" not in message


# -- rows 8 to 11 -------------------------------------------------------------


def test_two_files_that_map_to_one_wheel_path_are_a_conflict(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The files are named by their own paths (short ones here: a long path
    is shortened by the field)."""
    first = IncludedFile(path="a/x.py", distribution_path="pkg/x.py")
    second = IncludedFile(path="b/x.py", distribution_path="pkg/x.py")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        kept = _dedupe_by_distribution_path([first, second], tmp_path)
    assert kept == [first]
    ((code, message),) = _discovery(caplog)
    assert code == "file-discovery-conflict"
    assert message.startswith(f"DIR={tmp_path}: two files map to wheel path pkg/x.py")
    assert message.index("a/x.py") < message.index("b/x.py")
    assert message.index("kept") < message.index("a/x.py")
    assert message.index("dropped") < message.index("b/x.py")


def _setuptools_project(root: Path, extra: str, setup_py: str = "") -> None:
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n'
        f'[project]\nname = "pkgx"\nversion = "1"\n{extra}',
        encoding="utf-8",
    )
    if setup_py:
        (root / "setup.py").write_text(setup_py, encoding="utf-8")


def test_setup_py_keywords_passed_as_code_are_named(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "pkgx").mkdir()
    (tmp_path / "pkgx" / "__init__.py").write_text("", encoding="utf-8")
    _setuptools_project(
        tmp_path,
        "",
        "from setuptools import setup\nsetup(package_data={'a': []}, packages=[])\n",
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        get_wheel_files(tmp_path)
    ((code, message),) = _discovery(caplog)
    assert code == _NEEDS_BUILD
    assert "setup.py passes " in message and "imperatively" in message
    assert "package_data" in message and "packages" in message


def test_an_ambiguous_flat_layout_is_one_unusable_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _setuptools_project(tmp_path, "")
    for package in ("pkg_a", "pkg_b"):
        (tmp_path / package).mkdir()
        (tmp_path / package / "__init__.py").write_text("", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        get_wheel_files(tmp_path)
    said = _discovery(caplog)
    assert said[0][0] == _UNUSABLE
    assert "setuptools package auto-discovery is ambiguous; " in said[0][1]
    assert all("\n" not in m for _, m in said)


def test_flit_external_data_without_a_static_version_is_named(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "evilpkg").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "file.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "evilpkg" / "__init__.py").write_text(
        '"""d."""\ndef _v():\n    return "1"\n__version__ = _v()\n', encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["flit_core>=3.9"]\n'
        'build-backend = "flit_core.buildapi"\n'
        '[project]\nname = "evilpkg"\ndynamic = ["version", "description"]\n'
        '[tool.flit.external-data]\ndirectory = "data"\n',
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        get_wheel_files(tmp_path)
    ((code, message),) = _discovery(caplog)
    assert code == _NEEDS_BUILD
    assert "[tool.flit.external-data]" in message
    assert message.startswith(f"DIR={tmp_path}: ")


# -- the helper ---------------------------------------------------------------


def test_warn_discovery_carries_the_code_of_the_entry_that_holds_the_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from pitloom.messages.file_discovery import (  # pylint: disable=C0415
        FAILED_HEURISTIC_LINE,
        NO_STATIC_LINE,
    )

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_discovery(_LOG, FAILED_HEURISTIC_LINE, dir=tmp_path)
        warn_discovery(_LOG, NO_STATIC_LINE, dir=tmp_path, discoverer="PDM")
    assert [getattr(r, CODE_ATTR) for r in caplog.records] == [_UNUSABLE, _NEEDS_BUILD]
