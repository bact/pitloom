# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""In a Git URL's clone, ``get_wheel_files()`` reads no file the build
backend lists outside the downloaded repository (a ``force-include`` of an
absolute or ``..`` path, a link out): left out, unread, said in one
``file-unreadable/outside-repository`` ``WARNING:``. A local project keeps
them, as its backend would.

See also: :mod:`tests.assemble.test_generate_git_project_outside` (the
SBOM of such a project) and
:mod:`tests.core.models_wheel.test_models_wheel_unreadable` (a file that
cannot be read).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core import _models_wheel
from pitloom.core.lfs_pointer import reading_remote_clone
from pitloom.core.models import get_wheel_files
from pitloom.logging_config import CODE_ATTR
from tests._symlink import CAN_SYMLINK

_OUTSIDE = "file-unreadable/outside-repository"
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
    [record] = _outside_records(caplog)
    first, count = ("demo/link.txt", 3) if link else ("demo/secret.py", 2)
    assert record.levelno == logging.WARNING
    assert record.getMessage() == (
        f"FILE={first}: outside the downloaded repository ({count} files); not read"
    )


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
