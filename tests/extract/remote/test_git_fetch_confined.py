# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""Code run within ``with fetch_git_project(url) as checkout:`` reads the
checkout as a downloaded repository, with or without
``checkout.reading()``: no file out of it is read, and the model readers a
wheel scan does not run are not run. The mark is the block's alone: off on
every exit, and never seen by another thread.

See also: :mod:`tests.extract.remote.test_git_fetch` (the fetch itself).
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.clone_mark import in_remote_clone, remote_clone_root
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.extract.remote import fetch_git_project, git_url
from pitloom.logging_config import CODE_ATTR
from tests._model_fixtures import fixture_path, spy_readers

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="needs git"),
]

_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.org",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}
_FIXED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={**os.environ, **_ENV},
    )


@pytest.fixture(autouse=True)
def _local_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_url, "ALLOWED_SCHEMES", frozenset({"file"}))
    for name, value in _ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(name="hostile")
def _hostile(tmp_path: Path) -> tuple[str, Path]:
    """The URL of a repository whose build configuration names a host file
    by its absolute path and whose package holds an HDF5 model, and that
    host file."""
    secret = tmp_path / "host" / "secret.py"
    secret.parent.mkdir()
    secret.write_bytes(b"# SPDX-FileCopyrightText: 2026 HOSTSECRET\n")
    root = tmp_path / "origin"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    shutil.copy(fixture_path(AiModelFormat.HDF5), root / "demo" / "m.h5")
    (root / "pyproject.toml").write_bytes(
        b'[build-system]\nrequires = ["hatchling"]\n'
        b'build-backend = "hatchling.build"\n'
        b'[project]\nname = "demo"\nversion = "1"\n'
        b"[tool.hatch.build.targets.wheel.force-include]\n"
        + f'"{secret.as_posix()}" = "demo/s.py"\n'.encode()
    )
    _git(root, "init", "-q")
    _git(root, "checkout", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "x")
    return root.as_uri(), secret


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [str(getattr(r, CODE_ATTR, "")) for r in caplog.records]


@pytest.mark.parametrize("nested", [False, True], ids=["fetch", "and-reading"])
def test_a_library_caller_reads_the_checkout_confined(
    hostile: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    nested: bool,
) -> None:
    url, secret = hostile
    read = spy_readers(monkeypatch)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with fetch_git_project(url) as checkout:
            assert in_remote_clone() and remote_clone_root() == checkout.root
            if nested:
                with checkout.reading():
                    assert remote_clone_root() == checkout.root
                    text = generate_project_sbom(
                        Path(checkout.folder),
                        creation_metadata=_FIXED,
                        pitloom_config=PitloomConfig(),
                        extract_file_header=True,
                    )
                assert in_remote_clone()
            else:
                text = generate_project_sbom(
                    Path(checkout.folder),
                    creation_metadata=_FIXED,
                    pitloom_config=PitloomConfig(),
                    extract_file_header=True,
                )
    assert not in_remote_clone() and remote_clone_root() is None
    assert hashlib.sha256(secret.read_bytes()).hexdigest() not in text
    assert "HOSTSECRET" not in text and "demo/m.h5" in text
    assert not read
    codes = _codes(caplog)
    assert codes.count("file-unreadable/outside-repository") == 1
    assert codes.count("reader-unsafe/remote") == 1


def test_the_mark_is_off_after_the_block_raises(hostile: tuple[str, Path]) -> None:
    url, _secret = hostile
    with pytest.raises(LookupError, match="inside"):
        with fetch_git_project(url):
            assert in_remote_clone()
            raise LookupError("inside")
    assert not in_remote_clone() and remote_clone_root() is None


def test_the_mark_is_off_after_the_generator_is_closed(
    hostile: tuple[str, Path],
) -> None:
    url, _secret = hostile
    manager = fetch_git_project(url)
    manager.__enter__()  # pylint: disable=unnecessary-dunder-call
    assert in_remote_clone()
    # pylint: disable-next=no-member
    manager.gen.close()  # GeneratorExit at the yield
    assert not in_remote_clone() and remote_clone_root() is None


def test_another_thread_never_sees_the_mark(hostile: tuple[str, Path]) -> None:
    """A second caller, in its own thread, before, during and after the
    first's block, reads outside any clone."""
    url, _secret = hostile
    inside, done = threading.Event(), threading.Event()
    seen: list[bool] = []

    def other() -> None:
        seen.append(in_remote_clone())
        assert inside.wait(timeout=60)
        seen.append(in_remote_clone() or remote_clone_root() is not None)
        done.set()

    thread = threading.Thread(target=other)
    thread.start()
    with fetch_git_project(url):
        inside.set()
        assert done.wait(timeout=60)
        assert in_remote_clone()
    thread.join(timeout=60)
    assert seen == [False, False]
    with fetch_git_project(url) as checkout:  # a second, sequential caller
        assert remote_clone_root() == checkout.root
    assert not in_remote_clone()
