# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A message about a project read from a Git URL names ``<checkout>``, not the
random temporary directory it was cloned into: two runs print the same text,
while a local project directory keeps its real path.

See also: tests/test_checkout_mask.py (the masking itself).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests._git_http_server import backend_available, make_repo, serve_git

pytestmark = [
    pytest.mark.loopback,
    pytest.mark.skipif(not backend_available(), reason="needs git http-backend"),
]

_SRC = str(Path(__file__).resolve().parents[3] / "src")
_DEMO = '[project]\nname = "demo"\nversion = "1.0"\n'
#: setuptools project whose ``MANIFEST.in`` pattern matches nothing: it says so
#: on stderr, which ``--debug`` relays.
_MANIFEST = {
    "pyproject.toml": _DEMO + '[tool.setuptools]\npackages = ["demo"]\n',
    "demo/__init__.py": "",
    "MANIFEST.in": "include *.js\n",
}
#: A ``setup.cfg`` with a ``%`` that setuptools cannot interpolate.
_BAD_CFG = {"setup.cfg": "[metadata]\nname = demo\ndescription = 50% faster\n"}


@pytest.fixture(name="base")
def _base(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "srv"
    make_repo(root, "g/manifest", {"main": _MANIFEST})
    make_repo(root, "g/cfg", {"main": _BAD_CFG})
    with serve_git(root, gitlab_style=True) as base:
        yield base


def _loom(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [_SRC, env.get("PYTHONPATH")]))
    return subprocess.run(  # nosec B603
        [sys.executable, "-m", "pitloom", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


@pytest.mark.parametrize("repo", ["g/manifest", "g/cfg"])
def test_a_url_run_names_no_temporary_directory(
    base: str, tmp_path: Path, repo: str
) -> None:
    runs = [
        _loom(
            ["--debug", "project", f"{base}/{repo}", "-o", str(tmp_path / f"{n}.json")],
            tmp_path,
        )
        for n in ("one", "two")
    ]

    for done in runs:
        assert "pitloom-git-" not in done.stderr, done.stderr
    # while the message about the checkout is there, so the test sees something
    assert "<checkout>" in runs[0].stderr, runs[0].stderr
    assert runs[0].stderr == runs[1].stderr


def test_a_local_directory_keeps_its_real_path(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    for name, text in _BAD_CFG.items():
        (project / name).write_text(text, encoding="utf-8")

    done = _loom(
        ["--debug", "project", str(project), "-o", str(tmp_path / "o.json")], tmp_path
    )

    assert str(project) in done.stderr, done.stderr
    assert "<checkout>" not in done.stderr
