# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""In a Git URL's clone, ``get_wheel_files()`` reads no file the build
backend lists outside the downloaded repository (a ``force-include`` of an
absolute or ``..`` path, a link out) or in its ``.git`` directory: left out,
unread, said in ``file-unreadable/outside-repository`` ``WARNING:`` lines
that name a setting's entry as written, or count the files, never naming a
host file. A ``force-include`` out of the clone is left out before any
directory is walked. A local project keeps them, as its backend would.

See also: :mod:`tests.assemble.test_generate_git_project_outside` (the
SBOM of such a project) and
:mod:`tests.core.models_wheel.test_models_wheel_unreadable` (a file that
cannot be read).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import pytest

from pitloom.core import _models_wheel
from pitloom.core._models_wheel_clone import drop_outside_clone
from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.clone_mark import reading_remote_clone
from pitloom.core.models import get_wheel_files
from pitloom.logging_config import CODE_ATTR
from tests._symlink import CAN_SYMLINK

_OUTSIDE = "file-unreadable/outside-repository"
_HB_FORCE = (
    b'[build-system]\nrequires = ["hatchling"]\n'
    b'build-backend = "hatchling.build"\n'
    b'[project]\nname = "demo"\nversion = "1.0"\n'
    b"[tool.hatch.build.targets.wheel.force-include]\n"
)
_HEADER = b"# SPDX-FileCopyrightText: 2026 HOSTSECRET-COPY\nx = 1\n"


def _host(tmp_path: Path) -> Path:
    host = tmp_path / "host"
    host.mkdir(parents=True)
    (host / "secret.py").write_bytes(_HEADER)
    (host / "shared.txt").write_bytes(b"shared\n")
    return host


def _project(root: Path, host: Path, *, link: bool) -> Path:
    """A Hatchling project at *root* whose ``force-include`` names a host
    file by its absolute path and another by ``..``, maybe with a link out
    in its package."""
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    up = "../" * len(root.relative_to(host.parent).parts)
    (root / "pyproject.toml").write_bytes(
        b'[build-system]\nrequires = ["hatchling"]\n'
        b'build-backend = "hatchling.build"\n'
        b'[project]\nname = "demo"\nversion = "1.0"\n'
        b"[tool.hatch.build.targets.wheel.force-include]\n"
        + f'"{(host / "secret.py").as_posix()}" = "demo/secret.py"\n'.encode()
        + f'"{up}host/shared.txt" = "demo/shared.txt"\n'.encode()
    )
    if link:
        (root / "demo" / "link.txt").symlink_to(host / "shared.txt")
    return root


def _outside_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, CODE_ATTR, None) == _OUTSIDE]


_LINK = [False, True] if CAN_SYMLINK else [False]


@pytest.mark.parametrize("link", _LINK, ids=["include", "and-link"][: len(_LINK)])
def test_a_file_out_of_the_clone_is_left_out_unread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    link: bool,
) -> None:
    host = _host(tmp_path)
    root = _project(tmp_path / "clone", host, link=link)
    opened: list[Path] = []
    real = _models_wheel._build_project_file_entry  # pylint: disable=protected-access

    def spy(source: Path, *args: object, **kwargs: object) -> object:
        opened.append(source)
        return real(source, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_models_wheel, "_build_project_file_entry", spy)
    with caplog.at_level(logging.WARNING, logger="pitloom"), reading_remote_clone():
        _root, files, cleanup = get_wheel_files(root, scan_file_headers=True)
    cleanup()
    assert [f.distribution_path for f in files] == ["demo/__init__.py"]
    assert all(host not in p.parents for p in opened)
    up = "../" * len((tmp_path / "clone").relative_to(host.parent).parts)
    expected = [
        f"FILE={entry}: outside the downloaded repository; not read"
        for entry in sorted([(host / "secret.py").as_posix(), f"{up}host/shared.txt"])
    ]
    if link:
        expected.append("listed files outside the downloaded repository; not read")
    records = _outside_records(caplog)
    assert [r.getMessage() for r in records] == expected
    assert {r.levelno for r in records} == {logging.WARNING}


def test_a_file_out_of_the_folder_but_in_the_clone_is_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The bound is the repository, not the folder the URL names: a monorepo
    project's ``..`` to a file of the repository is read."""
    clone = tmp_path / "clone"
    host = _host(clone)
    root = _project(clone / "pkgs" / "a", host, link=False)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with reading_remote_clone(str(clone)):
            _root, files, _cleanup = get_wheel_files(root)
    assert [f.distribution_path for f in files] == [
        "demo/__init__.py",
        "demo/secret.py",
        "demo/shared.txt",
    ]
    assert not _outside_records(caplog)


def test_a_local_project_keeps_its_backends_list(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path / "clone", _host(tmp_path), link=False)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        _root, files, _cleanup = get_wheel_files(root, scan_file_headers=True)
    assert [f.distribution_path for f in files] == [
        "demo/__init__.py",
        "demo/secret.py",
        "demo/shared.txt",
    ]
    assert not _outside_records(caplog)


_ST = (
    b'[build-system]\nrequires = ["setuptools"]\n'
    b'build-backend = "setuptools.build_meta"\n'
    b'[project]\nname = "demo"\nversion = "1.0"\n'
)


def _host_tree(tmp_path: Path) -> Path:
    """A host directory whose files and folders a walk would name."""
    host = tmp_path / "host"
    (host / "hostpkg" / "deep").mkdir(parents=True)
    (host / "hostpkg" / "__init__.py").write_bytes(b"")
    (host / "hostpkg" / "deep" / "hostfile-2to3.py").write_bytes(b"")
    return host


_CFG = b"[metadata]\nname = demo\nversion = 1.0\n[options]\npackages = demo\n"


@pytest.mark.parametrize(
    ("file", "config", "entry"),
    [
        ("pyproject.toml", _HB_FORCE + b'"HOST" = "demo/h"\n', "HOST"),
        ("pyproject.toml", _HB_FORCE + b'"~/" = "demo/home"\n', "~/"),
        (
            "pyproject.toml",
            _HB_FORCE.replace(b"targets.wheel.", b"") + b'"HOST" = "demo/h"\n',
            "HOST",
        ),
        (
            "pyproject.toml",
            _ST + b'[tool.setuptools]\npackages = ["hostpkg", "demo"]\n'
            b'package-dir = {hostpkg = "HOST/hostpkg"}\n',
            "HOST/hostpkg",
        ),
        (
            "pyproject.toml",
            _ST + b"[tool.setuptools.packages.find]\n"
            b'where = ["HOST", "."]\ninclude = ["demo*", "hostpkg*"]\n',
            "HOST",
        ),
        (
            "pyproject.toml",
            _ST + b'[tool.setuptools]\npackages = ["demo"]\n'
            b'[tool.setuptools.package-data]\ndemo = ["../../host/**", "*.txt"]\n',
            "../../host/**",
        ),
        (
            "setup.cfg",
            _CFG + b"package_dir =\n    hostpkg = HOST/hostpkg\n",
            "HOST/hostpkg",
        ),
        (
            "setup.cfg",
            _CFG.replace(b"packages = demo", b"packages = find:")
            + b"[options.packages.find]\nwhere = HOST\n",
            "HOST",
        ),
        (
            "setup.cfg",
            _CFG + b"[options.package_data]\ndemo = *.txt, ../../host/**\n",
            "../../host/**",
        ),
    ],
    ids=[
        "force-include",
        "force-include-home",
        "force-include-all-targets",
        "package-dir",
        "find-where",
        "data",
        "cfg-package-dir",
        "cfg-find-where",
        "cfg-data",
    ],
)
def test_a_setting_out_of_the_clone_is_left_out_before_any_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    file: str,
    config: bytes,
    entry: str,
) -> None:
    """The entry is named as written, no host file is, and no directory
    of the host (or the home directory) is listed."""
    host = _host_tree(tmp_path)
    monkeypatch.setenv("HOME", str(host))
    monkeypatch.setenv("USERPROFILE", str(host))
    root = tmp_path / "clone"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    (root / file).write_bytes(config.replace(b"HOST", host.as_posix().encode()))
    if file == "setup.cfg":
        (root / "setup.py").write_bytes(b"from setuptools import setup\nsetup()\n")
    entry = entry.replace("HOST", host.as_posix())
    listed: list[str] = []
    real_walk, real_scandir = os.walk, os.scandir

    def walk(top: Any, *args: Any, **kwargs: Any) -> Any:
        listed.append(os.fspath(top))
        return real_walk(top, *args, **kwargs)

    def scandir(path: Any = ".") -> Any:
        if not isinstance(path, int):  # a directory's descriptor names none
            listed.append(os.fspath(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "walk", walk)
    monkeypatch.setattr(os, "scandir", scandir)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with reading_remote_clone(str(root)):
            _root, files, _cleanup = get_wheel_files(root)
    assert [f.distribution_path for f in files] == ["demo/__init__.py"]
    assert not [p for p in listed if Path(os.path.abspath(p)).is_relative_to(host)]
    assert [r.getMessage() for r in _outside_records(caplog)] == [
        f"FILE={entry}: outside the downloaded repository; not read"
    ]
    assert "hostfile" not in caplog.text and "hostpkg/__init__" not in caplog.text


def _case_insensitive(where: Path) -> bool:
    (where / "Probe").mkdir()
    return (where / "probe").is_dir()


@pytest.mark.parametrize("spelled", [".git", ".GIT"], ids=["git", "case-variant"])
def test_the_clones_git_directory_is_left_out(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, spelled: str
) -> None:
    """``.git/config`` can hold the URL's user information: a setting naming
    it is left out, and so is a file of ``.git`` a backend lists, in another
    letter case too where the file system finds it so."""
    if spelled != ".git" and not _case_insensitive(tmp_path):
        pytest.skip("the file system tells cases apart")
    root = tmp_path / "clone"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_bytes(b"[remote]\n")
    (root / "pyproject.toml").write_bytes(
        _HB_FORCE + f'"{spelled}/config" = "demo/config"\n'.encode()
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with reading_remote_clone(str(root)):
            _root, files, _cleanup = get_wheel_files(root)
            kept = drop_outside_clone(
                [
                    IncludedFile(str(root / spelled / "config"), "demo/config"),
                    IncludedFile(
                        str(root / "demo" / "__init__.py"), "demo/__init__.py"
                    ),
                ],
                root,
            )
    assert [f.distribution_path for f in files] == ["demo/__init__.py"]
    assert [f.distribution_path for f in kept] == ["demo/__init__.py"]
    assert [r.getMessage() for r in _outside_records(caplog)] == [
        f"FILE={spelled}/config: outside the downloaded repository; not read",
        "listed files outside the downloaded repository; not read",
    ]


def test_a_file_a_build_extracted_is_kept_in_a_clone(tmp_path: Path) -> None:
    """A library caller may build in the clone itself (``--allow-build``
    within ``fetch_git_project()``): the wheel's files live in a temporary
    directory out of it, and are kept."""
    root = tmp_path / "clone"
    root.mkdir()
    built = tmp_path / "extracted" / "demo" / "__init__.py"
    built.parent.mkdir(parents=True)
    built.write_bytes(b"")
    with reading_remote_clone(str(root)):
        kept = drop_outside_clone(
            [IncludedFile(str(built), "demo/__init__.py", built=True)], root
        )
    assert [f.distribution_path for f in kept] == ["demo/__init__.py"]
