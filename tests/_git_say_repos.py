# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The repositories the Git source message tests fetch from a local smart-HTTP
server (:mod:`tests._git_http_server`), and the lines a fetch printed, read
back as a script would read them.

See also: tests/extract/remote/test_git_say.py,
tests/extract/remote/test_git_say_errors.py,
tests/extract/remote/test_git_say_redirect.py and
tests/messages/test_git_surfaces.py (the tests that use it).
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

import pytest

from pitloom.logging_config import CODE_ATTR, escape_controls
from pitloom.messages import Message, trusted_message
from tests._git_http_server import backend_available, git, make_repo

__all__ = [
    "DEMO",
    "SERVER_MARKS",
    "Repos",
    "build_repos",
    "printed",
    "trusted_codes",
]

#: The stand-in server runs ``git http-backend`` as a POSIX CGI program.
_WINDOWS = sys.platform == "win32"

#: What a test that fetches from the local server carries.
SERVER_MARKS = [
    pytest.mark.loopback,
    pytest.mark.skipif(_WINDOWS, reason="git http-backend CGI server is POSIX-only"),
    pytest.mark.skipif(
        not _WINDOWS and not backend_available(), reason="needs git http-backend"
    ),
]

DEMO = '[project]\nname = "demo"\nversion = "1.0"\n'
_SUB = '[project]\nname = "svc-a"\nversion = "2"\n'
_MAIN: dict[str, str | bytes] = {
    "pyproject.toml": DEMO,
    "README.md": "readme\n",
    "svc/a/pyproject.toml": _SUB,
    "svc/a/README.md": "a\n",
}


class Repos(NamedTuple):
    """What :func:`build_repos` made: the commit of ``main`` of ``g/p``."""

    main_commit: str


def _link_repo(root: Path, name: str, links: dict[str, str]) -> None:
    """The bare repository ``<root>/<name>.git``: one commit holding a
    project, a file ``real.txt`` and the symbolic *links* (name -> target)."""
    bare = root / f"{name}.git"
    bare.parent.mkdir(parents=True, exist_ok=True)
    work = root / f".work-{name.replace('/', '-')}"
    work.mkdir(parents=True)
    git(work, "init", "-q")
    git(work, "checkout", "-q", "--orphan", "main")
    (work / "pyproject.toml").write_text(DEMO, encoding="utf-8")
    (work / "real.txt").write_text("x\n", encoding="utf-8")
    (work / "sub").mkdir()
    (work / "sub" / "f.txt").write_text("y\n", encoding="utf-8")
    for link, target in links.items():
        os.symlink(target, work / link)
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "main")
    git(root, "clone", "-q", "--bare", str(work), str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/main")


#: Symbolic links by what they do: one leaves the repository, one goes into
#: ``.git``, one to a folder, one to a file of the repository (kept).
LINKS: dict[str, dict[str, str]] = {
    "g/links-out": {"leak": "../../outside.txt"},
    "g/links-git": {"into-git": ".git/config"},
    "g/links-dir": {"to-folder": "sub"},
    "g/links-two": {"leak": "../../outside.txt", "to-folder": "sub"},
    "g/links-kept": {"ok": "real.txt"},
}


def build_repos(root: Path) -> Repos:
    """Create the bare repositories under *root*.

    ``g/p`` (and ``g/_git/p``, an Azure DevOps address) holds a project, a
    monorepo folder ``svc/a``, a branch ``feat/x`` with a slash and the tag
    ``v1``; ``a/b/src/p`` a project under a group called ``src``; ``g/mono``
    projects below a root with none, ``g/mono2`` below a folder with none and
    ``g/many`` six of them; ``g/empty`` no commit; ``g/links-*`` symbolic
    links (:data:`LINKS`).
    """
    tree: dict[str, Mapping[str, str | bytes]] = {
        "main": _MAIN,
        "feat/x": {"pyproject.toml": DEMO, "x.txt": "x\n"},
    }
    for name in ("g/p", "g/_git/p"):
        bare = make_repo(root, name, tree)
        git(bare, "tag", "v1", "main")
    make_repo(root, "a/b/src/p", {"main": {"pyproject.toml": DEMO}})
    make_repo(
        root,
        "g/mono",
        {"main": {"one/pyproject.toml": DEMO, "two/setup.py": "x = 1\n"}},
    )
    make_repo(
        root,
        "g/mono2",
        {"main": {"apps/one/pyproject.toml": DEMO, "apps/two/setup.py": "x = 1\n"}},
    )
    make_repo(
        root,
        "g/many",
        {"main": {f"{n}/pyproject.toml": DEMO for n in "abcdef"}},
    )
    empty = root / "g" / "empty.git"
    empty.parent.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "--bare", str(empty))
    if not _WINDOWS:
        for name, links in LINKS.items():
            _link_repo(root, name, links)
    return Repos(git(root / "g" / "p.git", "rev-parse", "main"))


def printed(caplog: pytest.LogCaptureFixture, *codes: str) -> list[str]:
    """The ``LEVEL: text [code]`` of each coded record *caplog* holds (of
    those *codes* only, when named), as the command line prints it."""
    lines = []
    for record in caplog.records:
        code = getattr(record, CODE_ATTR, None)
        if code is None or (codes and code not in codes):
            continue
        text = escape_controls(record.getMessage())
        lines.append(f"{logging.getLevelName(record.levelno)}: {text} [{code}]")
    return lines


def trusted_codes(lines: list[str]) -> list[str]:
    """The code of each of *lines* that :func:`trusted_message` trusts; a
    line it does not trust fails the caller's assertion on the count."""
    found: list[Message | None] = [trusted_message(line) for line in lines]
    return [m.code for m in found if m is not None]
