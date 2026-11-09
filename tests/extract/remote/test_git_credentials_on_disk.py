# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The user information of a Git URL stays off the disk of its clone: git
writes the URL it is given to ``.git/config``, which Pitloom rewrites
without it right after the checkout, by a clone and by a pinned fetch. A
repository naming ``.git/config`` as its licence or readme reads nothing of
it either.

The server is on ``127.0.0.1`` (`loopback`); the credential is fake.

See also: :mod:`tests.extract.remote.test_git_http_e2e` (the server).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.assemble import generate_git_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.extract.remote import fetch_git_project
from tests._git_http_server import backend_available, make_repo, serve_git

_WINDOWS = sys.platform == "win32"

pytestmark = [
    pytest.mark.loopback,
    pytest.mark.skipif(_WINDOWS, reason="git http-backend CGI server is POSIX-only"),
    pytest.mark.skipif(
        not _WINDOWS and not backend_available(), reason="needs git http-backend"
    ),
]

_SECRET = b"SECRETTOKEN"
_HB = '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
_PROJECT = {
    "pyproject.toml": _HB + '[project]\nname = "demo"\nversion = "1"\n'
    'license = {file = ".git/config"}\n',
    "demo/__init__.py": "",
}


@pytest.fixture(name="served")
def _served(tmp_path: Path) -> Iterator[tuple[str, str]]:
    """The address of a server holding ``g/p`` with a password in it, and
    the commit of its ``main``."""
    root = tmp_path / "srv"
    bare = make_repo(root, "g/p", {"main": _PROJECT})
    commit = subprocess.run(
        ["git", "-C", str(bare), "rev-parse", "main"],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull},
    ).stdout.strip()
    with serve_git(root, gitlab_style=True) as base:
        yield base.replace("://", "://alice:SECRETTOKEN@", 1), commit


def _holding_secret(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and _SECRET in path.read_bytes()
    )


@pytest.mark.parametrize("pinned", [False, True], ids=["clone", "pinned-fetch"])
def test_no_file_of_the_clone_holds_the_urls_credentials(
    served: tuple[str, str], pinned: bool
) -> None:
    base, commit = served
    url = f"{base}/g/p" + (f"/-/tree/{commit}" if pinned else ".git")
    with fetch_git_project(url) as checkout:
        root = Path(checkout.root)
        assert (root / ".git" / "config").is_file()
        assert _holding_secret(root) == []
        remote = subprocess.run(
            ["git", "-C", str(root), "config", "remote.origin.url"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    assert remote == base.replace("alice:SECRETTOKEN@", "") + "/g/p.git"


def test_a_licence_file_in_the_clones_git_directory_is_not_read(
    served: tuple[str, str], capfd: pytest.CaptureFixture[str]
) -> None:
    base, _commit = served
    sbom = generate_git_sbom(
        f"{base}/g/p.git",
        sbom_kind="project",
        creation_metadata=CreationMetadata(creation_datetime="2026-01-01T00:00:00Z"),
    )
    err = capfd.readouterr().err
    assert "repositoryformatversion" not in sbom
    assert "SECRETTOKEN" not in sbom + err
    assert "FILE=.git/config" in err
