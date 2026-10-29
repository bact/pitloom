# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Git LFS pointer bytes for tests, with a real ``oid`` and ``size``, and
one project tree of pointers and other files every route reads (built
on call, so a missing fixture skips only the tests that read it).

See also: ``tests/fixtures/lfs-pointers/`` (real pointers from the Hub);
``tests/test_lfs_pointer_surfaces.py`` (the routes :func:`tree` feeds).
"""

from __future__ import annotations

import functools
import hashlib
import os
from pathlib import Path

import pytest

from pitloom.core.lfs_pointer import LfsPointer, parse_lfs_pointer

#: The spec URL git-lfs writes today.
LFS_SPEC_URL = "https://git-lfs.github.com/spec/v1"


def lfs_pointer_bytes(
    content: bytes = b"x",
    *,
    eol: str = "\n",
    url: str = LFS_SPEC_URL,
    trailing_newline: bool = True,
) -> bytes:
    """The pointer git-lfs would write for *content* (its SHA-256 and
    length), with lines ending in *eol*, under the spec *url*."""
    lines = [
        f"version {url}",
        f"oid sha256:{hashlib.sha256(content).hexdigest()}",
        f"size {len(content)}",
    ]
    return (eol.join(lines) + (eol if trailing_newline else "")).encode("ascii")


_REPO = Path(__file__).resolve().parents[1]
_FIXTURES = Path(__file__).parent / "fixtures" / "lfs-pointers"


def in_git_checkout(root: Path) -> bool:
    """Whether *root* or a parent holds a ``.git`` entry (a directory, or
    the file of a worktree), as a sdist's unpacked tree does not."""
    return any(os.path.lexists(d / ".git") for d in (root, *root.parents))


def pointer_fixture(name: str) -> Path:
    """The real pointer fixture *name*. Absent: the test fails in a Git
    checkout (the directory was deleted), and is skipped elsewhere
    (Pitloom's published sdist leaves ``tests/fixtures/lfs-pointers/`` out).
    Call it from a test or a fixture, never at import: a skip there would
    take the whole importing module with it."""
    path = _FIXTURES / name
    if not path.is_file():
        if in_git_checkout(_REPO):
            pytest.fail(f"pointer fixture missing from the checkout: {path}")
        pytest.skip("pointer fixtures not present (excluded from the sdist)")
    return path


_PYPROJECT = (
    b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    b'[project]\nname = "demo"\nversion = "1.0"\n'
    b'[tool.hatch.build.targets.wheel]\npackages = ["demo"]\n'
)
_OPENING = b"version https://git-lfs.github.com/spec/v1\n"


@functools.cache
def _tree() -> dict[str, bytes]:
    return {
        "demo/__init__.py": b"x = 1\n",
        "demo/data/humaneval-test.parquet": pointer_fixture(
            "humaneval-test.parquet"
        ).read_bytes(),
        "demo/static/main.js": pointer_fixture("static-js-app-main.js").read_bytes(),
        "demo/pytorch_model.bin": pointer_fixture(
            "bert-tiny-pytorch-model.bin"
        ).read_bytes(),
        "demo/crlf.dat": lfs_pointer_bytes(b"crlf", eol="\r\n"),
        "demo/hawser.dat": lfs_pointer_bytes(
            b"old", url="https://hawser.github.com/spec/v1", trailing_newline=False
        ),
        "demo/long.dat": _OPENING + b"x" * 1024,
    }


def tree() -> dict[str, bytes]:
    """The package's files, name to bytes: real Hub pointers, built variants,
    and files that are not pointers (one only opens like one). A fresh dict
    on each call; skips or fails like :func:`pointer_fixture`."""
    return dict(_tree())


def pointers() -> dict[str, LfsPointer]:
    """The pointers among :func:`tree`, by name."""
    return {
        name: pointer
        for name, data in tree().items()
        if (pointer := parse_lfs_pointer(data)) is not None
    }


def write_project(root: Path, files: dict[str, bytes]) -> Path:
    """A Hatchling project at *root* whose package holds *files*."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_bytes(_PYPROJECT)
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    return root
