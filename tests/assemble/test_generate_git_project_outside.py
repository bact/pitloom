# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The SBOM of a Git URL's project holds nothing of a file its build
configuration lists outside the downloaded repository (``force-include`` of
an absolute or ``..`` path): no hash, no header text, no model metadata,
and one ``file-unreadable/outside-repository`` ``WARNING:``; the same
project read locally keeps the file.

The fetch is stood in for by a prepared directory, as in
:mod:`tests.assemble.test_generate_git_project_gate`.

See also: :mod:`tests.core.models_wheel.test_models_wheel_outside_clone`.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pitloom.assemble import (
    _generators_git,
    generate_git_project_sbom,
    generate_project_sbom,
)
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.extract.remote.git import GitCheckout
from pitloom.logging_config import CODE_ATTR
from tests._model_fixtures import fixture_path, spy_readers

_FIXED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_HEADER = b"# SPDX-FileCopyrightText: 2026 HOSTSECRET-COPY\nx = 1\n"


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """The clone (a project whose ``force-include`` names a host source file
    by its absolute path and a host model by ``..``), stood in for the
    fetch, and the host folder."""
    host = tmp_path / "host"
    host.mkdir()
    (host / "secret.py").write_bytes(_HEADER)
    shutil.copy(fixture_path(AiModelFormat.SAFETENSORS), host / "p.safetensors")
    folder = tmp_path / "clone"
    (folder / "demo").mkdir(parents=True)
    (folder / "demo" / "__init__.py").write_bytes(b"")
    (folder / "pyproject.toml").write_bytes(
        b'[build-system]\nrequires = ["hatchling"]\n'
        b'build-backend = "hatchling.build"\n'
        b'[project]\nname = "demo"\nversion = "1.0"\n'
        b"[tool.hatch.build.targets.wheel.force-include]\n"
        + f'"{(host / "secret.py").as_posix()}" = "demo/secret.py"\n'.encode()
        + b'"../host/p.safetensors" = "demo/p.safetensors"\n'
    )

    @contextmanager
    def fetch(url: str, **_options: object) -> Iterator[GitCheckout]:
        yield GitCheckout(str(folder), url, "main", "c", "", True)

    monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
    return folder, host


def _digests(host: Path) -> list[str]:
    return [
        hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(host.iterdir())
    ]


def test_the_sbom_holds_nothing_of_a_file_out_of_the_repository(
    project: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    folder, host = project
    read = spy_readers(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        text = generate_git_project_sbom(
            "https://h.example/o/r",
            creation_metadata=_FIXED,
            extract_file_header=True,
        )
    assert "demo/__init__.py" in text
    assert all(digest not in text for digest in _digests(host))
    assert "HOSTSECRET-COPY" not in text and "demo/secret.py" not in text
    assert not read
    codes = [getattr(r, CODE_ATTR, None) for r in caplog.records]
    assert codes.count("file-unreadable/outside-repository") == 1
    assert str(host) not in caplog.text and str(folder) not in caplog.text


def test_the_same_project_read_locally_keeps_the_file(
    project: tuple[Path, Path],
) -> None:
    folder, host = project
    text = generate_project_sbom(
        folder,
        creation_metadata=_FIXED,
        pitloom_config=PitloomConfig(),
        extract_file_header=True,
    )
    assert all(digest in text for digest in _digests(host))
    assert "HOSTSECRET-COPY" in text


def test_a_monorepo_projects_file_elsewhere_in_the_repository_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The bound is the repository's root, not the folder the URL names: a
    ``..`` to a file of the repository is read."""
    clone = tmp_path / "clone"
    folder = clone / "pkgs" / "a"
    (folder / "demo").mkdir(parents=True)
    (folder / "demo" / "__init__.py").write_bytes(b"")
    (clone / "NOTICE.txt").write_bytes(b"notice\n")
    (folder / "pyproject.toml").write_bytes(
        b'[build-system]\nrequires = ["hatchling"]\n'
        b'build-backend = "hatchling.build"\n'
        b'[project]\nname = "demo"\nversion = "1.0"\n'
        b"[tool.hatch.build.targets.wheel.force-include]\n"
        b'"../../NOTICE.txt" = "demo/NOTICE.txt"\n'
    )

    @contextmanager
    def fetch(url: str, **_options: object) -> Iterator[GitCheckout]:
        yield GitCheckout(str(folder), url, "main", "c", "pkgs/a", False)

    monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        text = generate_git_project_sbom(
            "https://h.example/o/r", creation_metadata=_FIXED
        )
    assert hashlib.sha256(b"notice\n").hexdigest() in text
    assert "outside-repository" not in caplog.text
