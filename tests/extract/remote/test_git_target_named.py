# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The file a Git URL names is read only when it is a regular file of the
folder read, inside the clone: a name that leads out of it (``..``, a
decoded ``%2F``) is never opened or sniffed, under any mode and whatever
its suffix; a link is refused as one; a name spelled in another case is
not found, as on a case-sensitive file system.

See also: :mod:`tests.extract.remote.test_git_fetch_models` (the rule on
real clones) and :mod:`tests.extract.remote.test_git_url_encoded` (the URL
check that comes first).
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import _generators_git, generate_git_sbom
from pitloom.core import path_confine
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.clone_mark import reading_remote_clone
from pitloom.core.creation import CreationMetadata
from pitloom.extract import scanner_project
from pitloom.extract.ai_model import read_ai_model_header
from pitloom.extract.model_target import AUTO, MODEL, PROJECT, resolve_sbom_target
from pitloom.extract.remote import (
    RemoteSourceError,
    _git_folder,
    fetch_git_project,
    git_target,
    git_url,
)
from pitloom.extract.remote._git_folder import checkout_folder, checkout_has_file
from pitloom.extract.remote.git import GitCheckout
from pitloom.extract.remote.git_target import resolve_git_target
from pitloom.messages import (
    CodedValueError,
    code_of,
)
from pitloom.messages.targets import NO_SBOM_TARGET
from tests._git_http_server import git
from tests._model_fixtures import fixture_path, spy_readers

#: ``git`` and ``file://`` URLs of POSIX paths: not on Windows.
_NO_GIT = sys.platform == "win32" or shutil.which("git") is None

_DEMO = b'[project]\nname = "demo"\nversion = "1.0"\n'
_FIXED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
#: A format whose reader runs on a clone's file, and one only sniffed.
_HOST_FORMATS = (AiModelFormat.SAFETENSORS, AiModelFormat.GGUF)


@pytest.fixture(name="sniffed")
def _sniffed(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every path whose header a model candidate reads."""
    seen: list[Path] = []
    real = read_ai_model_header

    def spy(path: Path) -> bytes:
        seen.append(Path(path))
        return real(path)

    monkeypatch.setattr(scanner_project, "read_ai_model_header", spy)
    return seen


def _host(tmp_path: Path, fmt: AiModelFormat, name: str) -> tuple[Path, str]:
    """A model of *fmt* outside the clone, at ``host/<name>``, and its
    SHA-256."""
    host = tmp_path / "host" / name
    host.parent.mkdir(parents=True)
    host.write_bytes(fixture_path(fmt).read_bytes())
    return host, hashlib.sha256(host.read_bytes()).hexdigest()


def _clone(tmp_path: Path, project: bool = True) -> Path:
    """A clone's folder ``clone/models``, with a project config or not."""
    folder = tmp_path / "clone" / "models"
    folder.mkdir(parents=True)
    (folder / "README.md").write_bytes(b"r\n")
    if project:
        (folder / "pyproject.toml").write_bytes(_DEMO)
    return folder


def _checkout(folder: Path, file: str) -> GitCheckout:
    return GitCheckout(
        str(folder), "https://h.example/o/r", "main", "c", "models", False, file
    )


@pytest.mark.parametrize("fmt", _HOST_FORMATS, ids=[f.value for f in _HOST_FORMATS])
@pytest.mark.parametrize("name", ["blob", "m.gguf"], ids=["no-suffix", "suffix"])
@pytest.mark.parametrize("mode", [AUTO, MODEL])
def test_a_named_file_out_of_the_clone_is_never_sniffed(
    tmp_path: Path, sniffed: list[Path], fmt: AiModelFormat, name: str, mode: str
) -> None:
    """Under a model only, or with a model suffix: ``git.path-not-found``;
    under auto, any other name reads the folder, as a missing one does."""
    host, _digest = _host(tmp_path, fmt, name)
    checkout = _checkout(_clone(tmp_path), f"../../host/{name}")
    with checkout.reading():
        if mode == AUTO and name == "blob":
            assert resolve_git_target(checkout, mode, "u").kind == PROJECT
        else:
            with pytest.raises(RemoteSourceError) as excinfo:
                resolve_git_target(checkout, mode, "u")
            assert excinfo.value.code == "git.path-not-found"
    assert host.exists() and host not in sniffed


@pytest.mark.parametrize("fmt", _HOST_FORMATS, ids=[f.value for f in _HOST_FORMATS])
@pytest.mark.parametrize("mode", [AUTO, MODEL])
def test_the_sbom_of_a_name_out_of_the_clone_holds_nothing_of_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sniffed: list[Path],
    fmt: AiModelFormat,
    mode: str,
) -> None:
    """End to end: no reader runs on the host file and neither its hash nor
    its path is in the SBOM or the error."""
    host, digest = _host(tmp_path, fmt, "blob")
    folder = _clone(tmp_path, project=False)
    shutil.copy(fixture_path(AiModelFormat.NUMPY), folder / "own.npy")

    @contextmanager
    def fetch(_url: str, **_options: object) -> Iterator[GitCheckout]:
        yield _checkout(folder, "../../host/blob")

    monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
    read = spy_readers(monkeypatch)
    try:
        text = generate_git_sbom(
            "https://h.example/o/r", sbom_kind=mode, creation_metadata=_FIXED
        )
    except RemoteSourceError as exc:
        assert mode == MODEL and exc.code == "git.path-not-found"
        text = str(exc)
    else:
        assert mode == AUTO and "own.npy" in text
    assert digest not in text and str(host.parent) not in text
    assert host not in sniffed and all(path != host for _fmt, path in read)


def test_a_name_out_of_the_clone_never_reaches_the_model_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first layer: under auto the folder is read with no named file,
    so the model rule's own check is never what keeps it out."""
    _host(tmp_path, AiModelFormat.SAFETENSORS, "blob")
    asked: list[str] = []
    real = resolve_sbom_target

    def spy(folder: str, **kwargs: Any) -> Any:
        asked.append(kwargs["file"])
        return real(folder, **kwargs)

    monkeypatch.setattr(git_target, "resolve_sbom_target", spy)
    checkout = _checkout(_clone(tmp_path), "../../host/blob")
    with checkout.reading():
        assert resolve_git_target(checkout, AUTO, "u").kind == PROJECT
    assert asked == [""]


@pytest.mark.parametrize("absolute", [False, True], ids=["dotdot", "absolute"])
@pytest.mark.parametrize("mode", [AUTO, MODEL])
def test_the_model_rule_in_a_clone_refuses_a_name_out_of_its_folder(
    tmp_path: Path, sniffed: list[Path], mode: str, absolute: bool
) -> None:
    """Defence in depth: :func:`resolve_sbom_target` in a clone opens no
    named file whose real path is out of the folder, whoever calls it."""
    host, _digest = _host(tmp_path, AiModelFormat.SAFETENSORS, "blob")
    folder = _clone(tmp_path, project=False)
    name = str(host) if absolute else "../../host/blob"
    with (
        reading_remote_clone(),
        pytest.raises((CodedValueError, FileNotFoundError)) as excinfo,
    ):
        resolve_sbom_target(folder, subject="u", file=name, mode=mode)
    expected = "input-not-found" if mode == MODEL else NO_SBOM_TARGET.code
    assert code_of(excinfo.value) == expected
    assert host not in sniffed


# --- real clones -----------------------------------------------------------


@pytest.fixture(name="local_git")
def _local_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow ``file:`` URLs, and isolate ``git`` from the user's config."""
    monkeypatch.setattr(git_url, "ALLOWED_SCHEMES", frozenset({"file"}))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)


def _repo(
    root: Path, files: dict[str, bytes], links: dict[str, str] | None = None
) -> str:
    """The ``file://`` URL of a new repository at *root* on ``main``."""
    root.mkdir(parents=True)
    git(root, "init", "-q")
    git(root, "checkout", "-q", "-b", "main")
    for rel, content in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(content)
    for rel, target in (links or {}).items():
        (root / rel).symlink_to(target)
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "one")
    return f"file://{root}"


def _kind(url: str, mode: str = AUTO) -> tuple[str, str]:
    with fetch_git_project(url) as checkout, checkout.reading():
        target = resolve_git_target(checkout, mode, url)
    return target.kind, "" if target.model is None else target.model.shown


@pytest.mark.skipif(_NO_GIT, reason="needs git and POSIX file:// URLs")
@pytest.mark.usefixtures("local_git")
@pytest.mark.parametrize("mode", [AUTO, MODEL])
def test_a_url_whose_decoded_name_leaves_the_clone_is_refused_unread(
    tmp_path: Path, sniffed: list[Path], caplog: pytest.LogCaptureFixture, mode: str
) -> None:
    """``.git%2F..%2F..`` to a host file with model magic: ``git.url-invalid``
    before the clone, logged as a ``WARNING:``; the host file is not read."""
    host, digest = _host(tmp_path, AiModelFormat.GGUF, "blob")
    url = _repo(tmp_path / "o", {"README.md": b"r\n"})
    escape = "%2F".join([".git"] + [".."] * 40 + [str(host).lstrip("/")])
    escape = escape.replace("/", "%2F")
    with (
        caplog.at_level(logging.WARNING, logger="pitloom"),
        pytest.raises(RemoteSourceError) as excinfo,
    ):
        _kind(f"{url}/blob/main/{escape}", mode)
    assert excinfo.value.code == "git.url-invalid"
    assert "WARNING" in caplog.text and digest not in caplog.text
    assert host not in sniffed


@pytest.mark.skipif(_NO_GIT, reason="needs git and POSIX file:// URLs")
@pytest.mark.usefixtures("local_git")
@pytest.mark.parametrize(
    "page", ["models/sub/m.keras", "models%2Fsub%2Fm.keras"], ids=["plain", "encoded"]
)
def test_a_nested_model_path_is_read(tmp_path: Path, page: str) -> None:
    keras = fixture_path(AiModelFormat.KERAS).read_bytes()
    url = _repo(tmp_path / "o", {"pyproject.toml": _DEMO, "models/sub/m.keras": keras})
    assert _kind(f"{url}/blob/main/{page}") == ("model", "models/sub/m.keras")


@pytest.mark.skipif(_NO_GIT, reason="needs git and POSIX file:// URLs")
@pytest.mark.usefixtures("local_git")
def test_a_named_link_is_refused_as_a_link(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A link in the repository is said to be one, not to be missing; under
    auto a name no model has reads the folder."""
    keras = fixture_path(AiModelFormat.KERAS).read_bytes()
    links = {"m.keras": "real/m.keras", "m.dat": "real/m.keras"}
    url = _repo(tmp_path / "o", {"pyproject.toml": _DEMO, "real/m.keras": keras}, links)
    for mode in (AUTO, MODEL):
        with pytest.raises(RemoteSourceError) as excinfo:
            _kind(f"{url}/blob/main/m.keras", mode)
        assert excinfo.value.code == "git.path-not-found"
        assert str(excinfo.value) == (
            "File 'm.keras' in the repository at that branch is a symbolic link; "
            "links are not followed."
        )
    with caplog.at_level(logging.INFO, logger="pitloom"):
        assert _kind(f"{url}/blob/main/m.dat") == (PROJECT, "")
    assert "FILE=m.dat: not an AI model file; reading its folder" in caplog.text


@pytest.mark.skipif(_NO_GIT, reason="needs git and POSIX file:// URLs")
@pytest.mark.usefixtures("local_git")
@pytest.mark.parametrize("page", ["Models/m.keras", "models/M.keras"])
def test_a_name_in_another_case_is_not_found(tmp_path: Path, page: str) -> None:
    keras = fixture_path(AiModelFormat.KERAS).read_bytes()
    url = _repo(tmp_path / "o", {"models/m.keras": keras})
    with pytest.raises(RemoteSourceError) as excinfo:
        _kind(f"{url}/blob/main/{page}", MODEL)
    assert excinfo.value.code == "git.path-not-found"


def _fold(path: str) -> str:
    """*path* (absolute) as a case-insensitive file system finds it."""
    here = Path(path).anchor
    for part in Path(path).parts[1:]:
        try:
            names = os.listdir(here)
        except OSError:
            return os.path.join(here, *Path(path).parts[len(Path(here).parts) :])
        match = next((n for n in names if n.casefold() == part.casefold()), part)
        here = os.path.join(here, match)
    return here


@pytest.fixture(name="case_insensitive")
def _case_insensitive(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Emulate a case-insensitive file system (macOS, Windows) for the
    clone's path checks: a file or folder is found in any case, and
    ``realpath`` keeps the spelling typed."""
    fake_path = types.SimpleNamespace(**vars(os.path))
    fake_path.isfile = lambda p: os.path.isfile(_fold(os.path.abspath(p)))
    fake_path.isdir = lambda p: os.path.isdir(_fold(os.path.abspath(p)))
    fake_os = types.SimpleNamespace(**vars(os))
    fake_os.path = fake_path
    monkeypatch.setattr(_git_folder, "os", fake_os)
    monkeypatch.setattr(path_confine, "os", fake_os)
    return fake_os


def test_a_case_insensitive_file_system_agrees_with_a_case_sensitive_one(
    tmp_path: Path, case_insensitive: types.SimpleNamespace
) -> None:
    """``Models/M.gguf`` for ``models/m.gguf`` is found by the file system,
    and refused as on Linux: only the spelling on disk is that file."""
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "m.gguf").write_bytes(b"x")
    root = str(tmp_path)
    assert case_insensitive.path.isfile(os.path.join(root, "Models", "M.GGUF"))
    assert checkout_has_file(root, "models/m.gguf")
    for wrong in ("models/M.GGUF", "Models/m.gguf"):
        assert not checkout_has_file(root, wrong)
    assert checkout_folder(root, "models") == os.path.realpath(tmp_path / "models")
    with pytest.raises(RemoteSourceError) as excinfo:
        checkout_folder(root, "Models")
    assert excinfo.value.code == "git.path-not-found"
