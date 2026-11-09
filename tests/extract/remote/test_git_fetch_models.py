# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""What the SBOM of a Git URL describes, for every AI model format alike:
the model file a file page names (``blob``, ``raw``, at a branch or a
commit), a folder's one model file (``tree``, the bare repository), or the
folder's project, against a real local repository (``file://`` URLs, allowed
for these tests only).

See also: :mod:`tests.extract.remote.test_git_fetch` (the fetch itself) and
:mod:`tests.extract.test_model_target` (the same rule on a local folder).
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.model_target import AUTO, MODEL, PROJECT
from pitloom.extract.remote import RemoteSourceError, fetch_git_project, git_url
from pitloom.extract.remote.git_target import resolve_git_target
from pitloom.messages import (
    LFS_POINTER,
    MODEL_AMBIGUOUS,
    MODEL_WRONG_FORMAT,
    NO_SBOM_TARGET,
    CodedValueError,
    code_of,
)
from tests._git_http_server import git
from tests._model_fixtures import FORMATS, fixture_path

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="needs git"),
    pytest.mark.skipif(sys.platform == "win32", reason="file:// URLs of POSIX paths"),
]

_DEMO = '[project]\nname = "demo"\nversion = "1.0"\n'
_OID = "a" * 64
_POINTER = f"version https://git-lfs.github.com/spec/v1\noid sha256:{_OID}\nsize 9\n"


@pytest.fixture(autouse=True)
def _local_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow ``file:`` URLs, and isolate ``git`` from the user's own config."""
    monkeypatch.setattr(git_url, "ALLOWED_SCHEMES", frozenset({"file"}))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)


def _repo(
    root: Path,
    files: Mapping[str, str | bytes],
    links: Mapping[str, str] | None = None,
) -> str:
    """The ``file://`` URL of a new repository at *root* whose ``main`` holds
    *files* (path -> content) and the symbolic *links* (path -> target)."""
    root.mkdir(parents=True)
    git(root, "init", "-q")
    git(root, "checkout", "-q", "-b", "main")
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    for rel, target in (links or {}).items():
        (root / rel).symlink_to(target)
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "one")
    return f"file://{root}"


def _resolved(url: str, mode: str = AUTO) -> tuple[str, str, AiModelFormat | None]:
    """The kind, the model file's name in messages and its format."""
    with fetch_git_project(url) as checkout, checkout.reading():
        target = resolve_git_target(checkout, mode, url)
    model = target.model
    return (
        (target.kind, "", None)
        if model is None
        else (MODEL, model.shown, model.model_format)
    )


@pytest.fixture(name="format_repos", scope="module")
def _format_repos(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[AiModelFormat, tuple[str, str]]:
    """Per format, a repository holding its fixture at the root and in
    ``models/`` beside a README: its URL and its commit."""
    repos: dict[AiModelFormat, tuple[str, str]] = {}
    for fmt in FORMATS:
        fixture = fixture_path(fmt)
        data = fixture.read_bytes()
        root = tmp_path_factory.mktemp("repos") / fmt.value
        url = _repo(
            root,
            {fixture.name: data, f"models/{fixture.name}": data, "README.md": "r\n"},
        )
        repos[fmt] = (url, git(root, "rev-parse", "HEAD"))
    return repos


_FORMS = {
    "blob-root": ("/blob/main/{name}", "{name}"),
    "raw-root": ("/raw/main/{name}", "{name}"),
    "bare": ("", "{name}"),
    "blob-folder": ("/blob/main/models/{name}", "models/{name}"),
    "raw-folder": ("/raw/main/models/{name}", "models/{name}"),
    "tree-folder": ("/tree/main/models", "models/{name}"),
    "commit-blob": ("/blob/{commit}/models/{name}", "models/{name}"),
}


@pytest.mark.parametrize("form", list(_FORMS))
@pytest.mark.parametrize("fmt", FORMATS, ids=[f.value for f in FORMATS])
def test_every_format_is_the_model_of_every_url_form(
    format_repos: dict[AiModelFormat, tuple[str, str]],
    fmt: AiModelFormat,
    form: str,
) -> None:
    """A file page (at a branch or a commit), a raw file, a folder and the
    bare repository each give the model file, named by its path in the
    repository, by its content: no format differs."""
    url, commit = format_repos[fmt]
    page, shown = _FORMS[form]
    name = fixture_path(fmt).name
    found = _resolved(url + page.format(name=name, commit=commit))
    assert found == (MODEL, shown.format(name=name), fmt)


def test_a_model_file_page_wins_over_the_folders_project(tmp_path: Path) -> None:
    """Under auto a named model file is the model, though the folder has a
    project; for a project only, the folder's project; a named
    ``pyproject.toml`` reads the folder; the bare repository is its project,
    or for a model only its one model file."""
    keras = fixture_path(AiModelFormat.KERAS)
    url = _repo(
        tmp_path / "o", {"pyproject.toml": _DEMO, "m.keras": keras.read_bytes()}
    )
    blob = url + "/blob/main/m.keras"
    assert _resolved(blob) == (MODEL, "m.keras", AiModelFormat.KERAS)
    assert _resolved(blob, PROJECT)[0] == PROJECT
    assert _resolved(url + "/blob/main/pyproject.toml")[0] == PROJECT
    assert _resolved(url)[0] == PROJECT
    assert _resolved(url, MODEL) == (MODEL, "m.keras", AiModelFormat.KERAS)


@pytest.mark.parametrize("mode", [AUTO, MODEL])
@pytest.mark.parametrize(
    "links", [None, {"link.keras": "real/m.keras"}], ids=["missing", "link"]
)
def test_a_named_file_that_is_no_file_of_the_folder_is_path_not_found(
    tmp_path: Path, mode: str, links: dict[str, str] | None
) -> None:
    """A file page whose file is gone, or is a link (not followed in a
    clone), is ``git.path-not-found`` naming its path; for a project only
    the folder is read as before."""
    keras = fixture_path(AiModelFormat.KERAS).read_bytes()
    url = _repo(tmp_path / "o", {"pyproject.toml": _DEMO, "real/m.keras": keras}, links)
    page = url + "/blob/main/" + ("link.keras" if links else "nope.keras")
    with pytest.raises(RemoteSourceError) as excinfo:
        _resolved(page, mode)
    assert excinfo.value.code == "git.path-not-found"
    assert ("'link.keras'" if links else "'nope.keras'") in str(excinfo.value)
    assert _resolved(page, PROJECT)[0] == PROJECT


@pytest.mark.parametrize(
    "links", [None, {"README.md": "docs/README.md"}], ids=["missing", "link"]
)
def test_a_named_non_model_file_that_is_no_file_reads_the_folder(
    tmp_path: Path, links: dict[str, str] | None, caplog: pytest.LogCaptureFixture
) -> None:
    """Under auto a file page of a name no model has (``README.md``), gone
    or a link, reads the folder as a file that is not a model does; for a
    model only it is ``git.path-not-found``."""
    files = {"pyproject.toml": _DEMO, "docs/README.md": "r\n"}
    url = _repo(tmp_path / "o", files, links)
    page = url + "/blob/main/README.md"
    with caplog.at_level(logging.INFO, logger="pitloom"):
        assert _resolved(page)[0] == PROJECT
    assert "FILE=README.md: not an AI model file; reading its folder" in caplog.text
    with pytest.raises(RemoteSourceError) as excinfo:
        _resolved(page, MODEL)
    assert excinfo.value.code == "git.path-not-found"


@pytest.mark.parametrize("name", ["e.gguf", "t.onnx", "x.bin"])
def test_a_named_file_with_a_model_suffix_that_is_no_model_is_refused(
    tmp_path: Path, name: str
) -> None:
    """Under auto, as for a model only and as a local file named on its own:
    a file whose name says model (empty, or of no format) is refused, not
    passed over for the folder's project; a name no model has is not."""
    files: dict[str, str | bytes] = {
        "pyproject.toml": _DEMO,
        name: b"",
        "notes.txt": b"hello",
    }
    url = _repo(tmp_path / "o", files)
    for mode in (AUTO, MODEL):
        with pytest.raises(CodedValueError) as excinfo:
            _resolved(url + f"/blob/main/{name}", mode)
        assert code_of(excinfo.value) == MODEL_WRONG_FORMAT.code
        assert f"'{name}'" in str(excinfo.value)
    assert _resolved(url + "/blob/main/notes.txt")[0] == PROJECT


def test_a_linked_model_in_the_folder_is_not_followed(tmp_path: Path) -> None:
    """A folder whose only model-named file is a link to a model elsewhere
    in the clone has no model file of its own."""
    keras = fixture_path(AiModelFormat.KERAS).read_bytes()
    url = _repo(tmp_path / "o", {"real/m.keras": keras}, {"link.keras": "real/m.keras"})
    with pytest.raises(CodedValueError) as excinfo:
        _resolved(url)
    assert code_of(excinfo.value) == NO_SBOM_TARGET.code


def test_two_models_in_the_folder_are_ambiguous(tmp_path: Path) -> None:
    keras = fixture_path(AiModelFormat.KERAS).read_bytes()
    npy = fixture_path(AiModelFormat.NUMPY).read_bytes()
    url = _repo(tmp_path / "o", {"d/a.keras": keras, "d/b.npy": npy})
    with pytest.raises(CodedValueError) as excinfo:
        _resolved(url + "/tree/main/d")
    assert code_of(excinfo.value) == MODEL_AMBIGUOUS.code


@pytest.mark.parametrize(
    ("mode", "code"),
    [(AUTO, NO_SBOM_TARGET.code), (MODEL, MODEL_WRONG_FORMAT.code)],
)
def test_a_folder_with_neither_is_refused(tmp_path: Path, mode: str, code: str) -> None:
    """No project, no model: ``project-or-model-not-found`` naming the URL
    (no credentials); for a model only, ``model-wrong-format``."""
    url = _repo(tmp_path / "o", {"README.md": "r\n"})
    secret = url.replace("file://", "file://user:SECRET@")
    with pytest.raises(CodedValueError) as excinfo:
        with fetch_git_project(url) as checkout, checkout.reading():
            resolve_git_target(checkout, mode, secret)
    assert code_of(excinfo.value) == code
    assert "SECRET" not in str(excinfo.value)


def test_neither_with_projects_below_names_them(tmp_path: Path) -> None:
    """``git.no-project`` with the monorepo hint, keeping the catalogued
    code of the condition."""
    url = _repo(tmp_path / "o", {"README.md": "r\n", "svc/a/setup.py": ""})
    with pytest.raises(RemoteSourceError) as excinfo:
        _resolved(url)
    assert excinfo.value.code == "git.no-project"
    assert excinfo.value.pitloom_code == NO_SBOM_TARGET.code
    assert "svc/a" in str(excinfo.value)


def test_a_project_only_of_a_model_folder_says_to_ask_for_a_model(
    tmp_path: Path,
) -> None:
    """``loom project`` on a folder of model files: ``git.no-project`` naming
    the files (escaped, at most five) and ``loom model``."""
    names = [f"m{i}.keras" for i in range(6)] + ["a\nb.npy"]
    url = _repo(tmp_path / "o", dict.fromkeys(names, b"x"))
    with pytest.raises(RemoteSourceError) as excinfo:
        _resolved(url, PROJECT)
    text = str(excinfo.value)
    assert excinfo.value.code == "git.no-project"
    assert "'a\\nb.npy', m0.keras" in text and "and 2 more" in text
    assert "loom model <url>" in text and "\n" not in text


@pytest.mark.parametrize(
    ("count", "tail"), [(5, ""), (6, " and 1 more")], ids=["five", "six"]
)
def test_a_model_folder_lists_at_most_five_names(
    tmp_path: Path, count: int, tail: str
) -> None:
    """The boundary of the listing: five names are all shown, a sixth is
    counted ("and 1 more"), never named."""
    names = [f"m{i}.keras" for i in range(count)]
    url = _repo(tmp_path / "o", dict.fromkeys(names, b"x"))
    with pytest.raises(RemoteSourceError) as excinfo:
        _resolved(url, PROJECT)
    text = str(excinfo.value)
    assert f"({', '.join(names[:5])}{tail})" in text
    assert ("more" in text) == bool(tail)
    assert "m5.keras" not in text


def test_a_project_only_of_a_model_folder_with_projects_below_reads_it(
    tmp_path: Path,
) -> None:
    """With projects in folders below, the folder is read as a project: its
    failure names them (the monorepo hint), not ``loom model``."""
    url = _repo(tmp_path / "o", {"m.keras": b"x", "svc/a/setup.py": ""})
    assert _resolved(url, PROJECT)[0] == PROJECT


@pytest.mark.parametrize("page", ["/blob/main/model.onnx", ""], ids=["named", "folder"])
def test_an_lfs_pointer_says_to_clone_with_lfs(tmp_path: Path, page: str) -> None:
    """A pointer in place of a model, named or alone in its folder:
    ``lfs-pointer`` with the clone's advice, not ``git lfs pull``."""
    url = _repo(tmp_path / "o", {"model.onnx": _POINTER})
    with pytest.raises(CodedValueError) as excinfo:
        _resolved(url + page)
    assert code_of(excinfo.value) == LFS_POINTER.code
    assert "clone with git lfs" in str(excinfo.value)
    assert "git lfs pull" not in str(excinfo.value)
    assert "pitloom-git-" not in str(excinfo.value)
