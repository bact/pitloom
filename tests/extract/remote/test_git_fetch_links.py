# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The symbolic links of a clone that are not followed: one into its
``.git`` directory (whose ``config`` can hold the URL's user information)
and every link to a folder (two links to ``.`` make a file walk endless),
besides one out of the clone; a link to a file of the clone is kept. A
folder URL naming a link to ``.git`` names no folder.

See also: :mod:`tests.extract.remote.test_git_hardening` (links out of the
clone).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pitloom.extract.remote import RemoteSourceError, fetch_git_project, git_url
from pitloom.extract.remote._git_folder import checkout_folder

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="needs git"),
    pytest.mark.skipif(sys.platform == "win32", reason="symbolic links need POSIX"),
]

_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.org",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


@pytest.fixture(autouse=True)
def _local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_url, "ALLOWED_SCHEMES", frozenset({"file"}))
    for name, value in _ENV.items():
        monkeypatch.setenv(name, value)


def _repository(root: Path, links: dict[str, str]) -> str:
    """The ``file:`` URL of a repository at *root* holding ``real.py``,
    ``demo/__init__.py`` and the links *links* (name -> target)."""
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    (root / "real.py").write_bytes(b"x = 1\n")
    for name, target in links.items():
        (root / name).symlink_to(target)
    for args in (("init", "-q", "-b", "main"), ("add", "."), ("commit", "-qm", "x")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root.as_uri()


def _names(folder: Path) -> list[str]:
    return sorted(
        p.relative_to(folder).as_posix()
        for p in folder.rglob("*")
        if ".git" not in p.relative_to(folder).parts
    )


def test_links_into_git_and_to_folders_are_dropped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    url = _repository(
        tmp_path / "origin",
        {
            "inside.py": "real.py",
            "config": ".git/config",
            "head": "./demo/../.git/HEAD",
            "g": ".git",
            "demo/a": ".",
            "demo/b": "..",
            "pkg": "demo",
        },
    )
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with fetch_git_project(url) as checkout:
            names = _names(Path(checkout.folder))
    assert names == ["demo", "demo/__init__.py", "inside.py", "real.py"]
    assert "6 symbolic link(s) leading out of the repository" in caplog.text


@pytest.mark.parametrize("page", ["tree", "-/tree"], ids=["github", "gitlab"])
def test_a_folder_url_naming_a_link_to_git_names_no_folder(
    tmp_path: Path, page: str
) -> None:
    url = _repository(tmp_path / "origin", {"sub": ".git"})
    with pytest.raises(RemoteSourceError) as raised:
        with fetch_git_project(f"{url}/{page}/main/sub"):
            pytest.fail("not read")
    assert raised.value.code == "git.path-not-found"


def test_a_folder_of_the_checkout_never_resolves_into_git(tmp_path: Path) -> None:
    """Even with a link to ``.git`` left in place (a fetch drops it), the
    folder it names is no folder of the checkout."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "sub").symlink_to(".git")
    with pytest.raises(RemoteSourceError) as raised:
        checkout_folder(str(tmp_path), "sub")
    assert raised.value.code == "git.path-not-found"
