# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared builders for the author surface tests.

See also: tests/test_author_surfaces.py,
tests/test_author_split_surfaces.py and tests/test_author_split_warnings.py
(the users).
"""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3.deps_originator import _resolve_author_or_maintainer
from pitloom.assemble.spdx3.deps_pypi import _extract_pypi_originator
from pitloom.core.creation import CreationMetadata
from pitloom.extract.authors import dependency_author_splits
from pitloom.extract.project import read_project
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.wheel import read_wheel
from tests.assemble.conftest import _FakeMetadata, _make_sdist
from tests.extract.conftest import make_hook

CREATED = CreationMetadata(creation_datetime="2024-05-01T00:00:00Z")
#: In every author split ``WARNING:``, a name or an address field's, and
#: in no other line.
SPLIT_MARK = "on ',' / ';'"
#: The ``INFO:`` for a project's name field read as one author that may
#: list several: the field's excerpt, then the route's hint.
ONE_AUTHOR_LINE = (
    "AUTHOR={}: read as one author; it may list several"
    " ('Doe, Jane' and 'Ann and Bob' cannot be told from lists){}"
)
#: The hint of a route reading core metadata.
CORE_HINT = (
    " -- a project directory or an sdist with pyproject.toml keeps the declared authors"
)
#: The hint ending :data:`ONE_AUTHOR_LINE` per surface reading a project's
#: own free-text ``author``; any other surface gives none.
ONE_AUTHOR_HINTS = {
    "setup-cfg": "",
    "setup-py": "",
    "wheel-metadata": CORE_HINT,
    "sdist-pkg-info": CORE_HINT,
}
#: Reads (author, author_email) through one surface: its authors.
Surface = Callable[[Path, str | None, str | None], list[dict[str, str]]]


def one_author_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    """The ``INFO:`` lines of a name field read as one author."""
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.INFO and ": read as one author;" in r.getMessage()
    ]


def core_headers(author: str | None, email_: str | None) -> str:
    """A ``demo`` core-metadata text with these ``Author`` and
    ``Author-email`` headers, each left out when ``None``."""
    text = "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n"
    text += f"Author: {author}\n" if author is not None else ""
    return text + (f"Author-email: {email_}\n" if email_ is not None else "")


def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No ``[tool.pitloom]`` borrowed from the current directory; a fixed
    creation time (:data:`CREATED`) for the CLI."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1714521600")  # 2024-05-01


def write_wheel(
    tmp_path: Path,
    metadata: str,
    version: str = "1.0",
    dist_info: dict[str, bytes] | None = None,
) -> Path:
    """A ``demo`` wheel with *metadata* as its ``METADATA`` and the
    *dist_info* files (path under the ``.dist-info`` to bytes)."""
    wheel = tmp_path / f"demo-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(f"demo-{version}.dist-info/METADATA", metadata)
        for name, data in (dist_info or {}).items():
            zf.writestr(f"demo-{version}.dist-info/{name}", data)
        zf.writestr("demo/__init__.py", "")
    return wheel


def hook_sbom(project: Path) -> str:
    """The SBOM the Hatchling build hook stages for *project*'s wheel: the
    real ``PitloomBuildHook.initialize()``, not just its metadata step."""
    hook = make_hook(str(project), {})
    build_data: dict[str, list[str]] = {}
    hook.initialize("standard", build_data)
    try:
        (staged,) = build_data["sbom_files"]
        return Path(staged).read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")


def read_dir(tmp_path: Path) -> list[dict[str, str]]:
    """The authors the directory route reads from *tmp_path*."""
    return read_project(
        tmp_path, include_locked_dependencies=False, include_installed_metadata=False
    )[0].authors


def _setup_cfg(tmp_path: Path, author: str | None, email_: str | None) -> Any:
    fields = {"author": author, "author_email": email_}
    stated = "".join(f"{k} = {v}\n" for k, v in fields.items() if v is not None)
    (tmp_path / "setup.cfg").write_text(
        f"[metadata]\nname = demo\nversion = 1.0\n{stated}", encoding="utf-8"
    )
    return read_dir(tmp_path)


def _setup_py(tmp_path: Path, author: str | None, email_: str | None) -> Any:
    fields = {"author": author, "author_email": email_}
    stated = "".join(f", {k}={v!r}" for k, v in fields.items() if v is not None)
    (tmp_path / "setup.py").write_text(
        f"from setuptools import setup\nsetup(name='demo', version='1.0'{stated})\n",
        encoding="utf-8",
    )
    return read_dir(tmp_path)


def _wheel(tmp_path: Path, author: str | None, email_: str | None) -> Any:
    return read_wheel(write_wheel(tmp_path, core_headers(author, email_)))[0].authors


def _sdist(tmp_path: Path, author: str | None, email_: str | None) -> Any:
    members: dict[str, bytes | None] = {
        "PKG-INFO": core_headers(author, email_).encode(),
        "pyproject.toml": None,
    }
    return read_sdist(_make_sdist(tmp_path, members=members)).metadata.authors


def _as_dicts(pairs: list[tuple[str | None, str | None]]) -> list[dict[str, str]]:
    return [
        {k: v for k, v in (("name", name), ("email", addr)) if v}
        for name, addr in pairs
    ]


def _dep_installed(_tmp: Path, author: str | None, email_: str | None) -> Any:
    named = {"Author": author, "Author-email": email_}
    fields = {k: v for k, v in named.items() if v is not None}
    with dependency_author_splits():
        return _as_dicts(_resolve_author_or_maintainer(_FakeMetadata(fields), "dep"))


def _dep_pypi(_tmp: Path, author: str | None, email_: str | None) -> Any:
    with dependency_author_splits():
        info = {"author": author, "author_email": email_}
        return _as_dicts(_extract_pypi_originator(info, "dep"))


SURFACES: dict[str, Surface] = {
    "setup-cfg": _setup_cfg,
    "setup-py": _setup_py,
    "wheel-metadata": _wheel,
    "sdist-pkg-info": _sdist,
    "dependency-installed": _dep_installed,
    "dependency-pypi": _dep_pypi,
}
