# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Poetry-backed wheel file discovery
(:mod:`pitloom.core._models_wheel_poetry`).

See also: tests/core/models_wheel/test_models_wheel_dispatch.py for
the facade-level backend-dispatch/fallback-warning tests;
tests/core/models_wheel/test_models_wheel_setuptools.py for the
setuptools discovery module's own tests, which this file mirrors in shape.
"""

import logging
import os
from pathlib import Path
from typing import Any

import pytest

from pitloom.core._models_wheel_poetry import discover
from pitloom.core.clone_mark import reading_remote_clone
from tests._symlink import CAN_SYMLINK

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "projects"
SRC_LAYOUT_FIXTURE = FIXTURES / "sampleproject-poetry-src"
INCLUDE_EXCLUDE_FIXTURE = FIXTURES / "sampleproject-poetry-include-exclude"


def test_discover_src_layout_regression() -> None:
    """A ``packages = [{include = ..., from = "src"}]`` layout
    must resolve the distribution path without the ``src/`` prefix leaking
    in -- the same ``physical_path``/``distribution_path`` divergence
    setuptools' ``where=`` case guards against."""
    result = discover(SRC_LAYOUT_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {"sampleproject_poetry_src/__init__.py"}
    assert not any(p.startswith("src/") for p in distribution_paths)


def test_discover_resolves_absolute_physical_paths() -> None:
    """``IncludedFile.path`` must be absolute, matching Hatchling's own
    ``IncludedFile.path`` contract."""
    result = discover(SRC_LAYOUT_FIXTURE)

    assert result is not None
    for included_file in result:
        assert Path(included_file.path).is_absolute()


def test_discover_honors_include_and_exclude() -> None:
    """``include`` pulls in a file outside the auto-discovered package
    directory; ``exclude`` drops a file that would otherwise be included
    by default. Both must take effect together, matching a real Poetry
    wheel build."""
    result = discover(INCLUDE_EXCLUDE_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {
        "extra_data/included.txt",
        "sampleproject_poetry_include_exclude/__init__.py",
    }
    assert "sampleproject_poetry_include_exclude/data.json" not in distribution_paths
    assert not any(p.startswith("notes/") for p in distribution_paths)


def test_discover_accepts_pyproject_data_kwarg() -> None:
    """Matches :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s
    shared call signature: poetry-core's ``Factory`` reads ``pyproject.toml``
    itself, so the argument is accepted and ignored."""
    result = discover(
        SRC_LAYOUT_FIXTURE, pyproject_data={"tool": {"poetry": {"name": "pkg"}}}
    )

    assert result is not None


def test_discover_returns_none_and_warns_on_non_poetry_project(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A project with no resolvable ``[tool.poetry]``/``[project]`` name
    or version fails poetry-core's own ``Factory`` -- discover() must
    catch that and return ``None`` with a warning, not propagate the
    exception, so the caller can fall back accordingly."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["poetry-core"]\n'
        'build-backend = "poetry.core.masonry.api"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        result = discover(tmp_path)

    assert result is None
    assert "Poetry file discovery failed" in caplog.text


_POETRY_HEAD = (
    b'[build-system]\nrequires = ["poetry-core"]\n'
    b'build-backend = "poetry.core.masonry.api"\n'
)
_TOOL = b'[tool.poetry]\nname = "demo"\nversion = "1"\ndescription = "d"\n'


@pytest.mark.parametrize(
    ("table", "entries"),
    [
        (_TOOL + b'packages = [{include = "*", from = "HOST"}, {include = "demo"}]\n',
         ["HOST"]),
        (b'[project]\nname = "demo"\nversion = "1"\n[tool.poetry]\n'
         b'packages = [{include = "**/*.txt", from = "HOST/.."}, {include = "demo"}]\n',
         ["HOST/.."]),
        (_TOOL + b'packages = [{include = "../host/*"}, {include = "demo"}]\n'
         b'include = ["HOST/secret.txt", {path = ".git/config", format = "wheel"}]\n'
         b'exclude = ["../host/x*"]\n',
         ["../host/*", "HOST/secret.txt", ".git/config", "../host/x*"]),
        (_TOOL + b'packages = [{include = "*", from = "lnk"}, {include = "demo"}]\n',
         ["lnk"]),
    ],
    ids=["from-star", "from-star-project", "include-exclude", "from-link"],
)  # fmt: skip
def test_a_clones_entry_out_of_it_is_left_out_before_any_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    table: bytes,
    entries: list[str],
) -> None:
    """In a Git URL's clone a ``packages`` source, an ``include`` or an
    ``exclude`` out of it (or in its ``.git``) is named as written, and no
    folder of the host is listed."""
    host = tmp_path / "host"
    host.mkdir()
    (host / "secret.txt").write_bytes(b"HOSTSECRET\n")
    (host / "hostpkg").mkdir()
    root = tmp_path / "clone"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_bytes(b"x")
    if b'"lnk"' in table:
        if not CAN_SYMLINK:
            pytest.skip("needs a symlink")
        (root / "lnk").symlink_to(host, target_is_directory=True)
    (root / "pyproject.toml").write_bytes(
        _POETRY_HEAD + table.replace(b"HOST", host.as_posix().encode())
    )
    listed: list[str] = []
    real_scandir = os.scandir

    def scandir(path: Any = ".") -> Any:
        if not isinstance(path, int):
            listed.append(os.path.abspath(os.fspath(path)))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", scandir)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with reading_remote_clone(str(root)):
            found = discover(root)
    assert found is not None
    assert [f.distribution_path for f in found] == ["demo/__init__.py"]
    assert not [p for p in listed if Path(p).is_relative_to(host)]
    assert "secret.txt" not in caplog.text.replace(f"{host.as_posix()}/secret.txt", "")
    assert [r.getMessage() for r in caplog.records] == [
        f"FILE={entry}: outside the downloaded repository; not read"
        for entry in sorted({e.replace("HOST", host.as_posix()) for e in entries})
    ]
