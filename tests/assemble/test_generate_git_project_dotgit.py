# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The SBOM and the messages of a Git URL's project hold nothing of the
clone's ``.git`` directory, whose ``config`` can hold the URL's user
information: a licence, readme, version or requirements file naming it, or
a link to it, is not read, and a build backend's failure says its type, not
its text (which can quote a file it read). The same project read locally
reads as before.

The fetch is stood in for by a prepared directory, its links kept (a real
fetch drops links into ``.git``), as in
:mod:`tests.assemble.test_generate_git_project_outside`.

See also: :mod:`tests.extract.remote.test_git_credentials_on_disk` (the
credential itself is not on disk).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pitloom.assemble import _generators_git, generate_git_project_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.extract.remote.git import GitCheckout
from tests._symlink import CAN_SYMLINK

_FIXED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_CONFIG = (
    b'[core]\n\trepositoryformatversion = 0\n[remote "origin"]\n\turl = SECRETTOKEN\n'
)
_HB = b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
_ST = (
    b'[build-system]\nrequires = ["setuptools"]\n'
    b'build-backend = "setuptools.build_meta"\n'
)
_SETUP_PY = b"from setuptools import setup\nsetup()\n"
_LINK = ("link", ".git/config")

_VARIANTS: dict[str, dict[str, object]] = {
    "license-direct": {
        "pyproject.toml": _HB + b'[project]\nname = "demo"\nversion = "1"\n'
        b'license = {file = ".git/config"}\n'
    },
    "license-link": {
        "pyproject.toml": _HB + b'[project]\nname = "demo"\nversion = "1"\n'
        b'license = {file = "L"}\n',
        "L": _LINK,
    },
    "cfg-version-link": {
        "setup.cfg": b"[metadata]\nname = demo\nversion = file: V\n"
        b"[options]\npackages = demo\n",
        "setup.py": _SETUP_PY,
        "V": _LINK,
    },
    "pp-version-direct": {
        "pyproject.toml": _ST + b'[project]\nname = "demo"\ndynamic = ["version"]\n'
        b'[tool.setuptools]\npackages = ["demo"]\n'
        b'[tool.setuptools.dynamic]\nversion = {file = [".git/config"]}\n'
    },
    "cfg-reqs-link": {
        "setup.cfg": b"[metadata]\nname = demo\nversion = 1\n"
        b"[options]\npackages = demo\ninstall_requires = file: V\n",
        "setup.py": _SETUP_PY,
        "V": _LINK,
    },
    "cfg-global-src-root": {
        "setup.cfg": b"[global]\nsrc_root = .git\n[metadata]\nname = demo\n"
        b"version = file: config\n[options]\npy_modules =\n",
        "setup.py": _SETUP_PY,
    },
}
_NEEDS_LINK = {name for name, files in _VARIANTS.items() if _LINK in files.values()}


def _clone(folder: Path, files: dict[str, object]) -> Path:
    (folder / "demo").mkdir(parents=True)
    (folder / "demo" / "__init__.py").write_bytes(b"")
    (folder / ".git").mkdir()
    (folder / ".git" / "config").write_bytes(_CONFIG)
    for name, content in files.items():
        if isinstance(content, tuple):
            (folder / name).symlink_to(content[1])
        else:
            assert isinstance(content, bytes)
            (folder / name).write_bytes(content)
    return folder


@pytest.mark.parametrize("variant", sorted(_VARIANTS))
def test_nothing_of_the_clones_git_directory_is_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    variant: str,
) -> None:
    if variant in _NEEDS_LINK and not CAN_SYMLINK:
        pytest.skip("needs a symlink")
    folder = _clone(tmp_path / "clone", _VARIANTS[variant])

    @contextmanager
    def fetch(url: str, **_options: object) -> Iterator[GitCheckout]:
        yield GitCheckout(str(folder), url, "main", "c", "", True)

    monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        try:
            sbom = generate_git_project_sbom(
                "https://h/o/r", creation_metadata=_FIXED, extract_file_header=True
            )
        except ValueError as exc:
            sbom = str(exc)
    said = caplog.text + capsys.readouterr().err
    assert "SECRETTOKEN" not in sbom + said
    assert "repositoryformatversion" not in sbom + said
