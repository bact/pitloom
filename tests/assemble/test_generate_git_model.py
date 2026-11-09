# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""``generate_git_sbom()`` and ``generate()`` on the Git URL of an AI model
file: the SBOM a local run of the file gives, for every format, whatever
temporary directory the clone is in; the fetch's own options reach the
fetch, an option a model cannot use warns once, and a downloaded file is
never read by a gated reader (fastText, GGUF, HDF5, ONNX, PyTorch).

The fetch is stood in for by a prepared directory; see
:mod:`tests.extract.remote.test_git_fetch_models` for real clones.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pitloom.assemble import (
    _generators_git,
    generate,
    generate_git_project_sbom,
    generate_git_sbom,
    generate_model_sbom,
)
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.creation import CreationMetadata
from pitloom.core.internal_error import InternalError
from pitloom.core.lfs_pointer import reading_remote_clone
from pitloom.core.project import ProjectMetadata
from pitloom.extract.remote import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout
from pitloom.extract.scanner_wheel import WHEEL_GATED_FORMATS
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import READER_UNSAFE_REMOTE
from tests._model_fixtures import (
    FORMATS,
    fixture_path,
    has_reader_library,
    spy_readers,
)
from tests.warning_helpers import count_naming, logged_warnings

_URL = "https://user:SECRET@git.example.org/o/r/-/blob/main/models/m"
_FIXED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")


def _copy(fmt: AiModelFormat, folder: Path) -> Path:
    """*fmt*'s fixture, alone in the new *folder*."""
    folder.mkdir(parents=True)
    return Path(shutil.copy(fixture_path(fmt), folder))


@pytest.fixture(name="fetched")
def _fetched(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Stand in for the fetch: it yields the folder set in ``["folder"]``
    (subfolder ``models`` of the repository) and its file ``["file"]``, and
    records what it was asked."""
    seen: dict[str, object] = {}

    @contextmanager
    def fetch(
        url: str,
        *,
        check_url: object = None,
        offline: bool | None = None,
        max_bytes: int | None = None,
    ) -> Iterator[GitCheckout]:
        seen.update(url=url, check_url=check_url, offline=offline, max_bytes=max_bytes)
        folder, file = seen["folder"], seen.get("file", "")
        yield GitCheckout(
            folder=str(folder),
            repo_url=url,
            ref="main",
            commit="c",
            subdir="models",
            whole_repository=False,
            file=str(file),
        )

    monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
    return seen


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records]


@pytest.mark.parametrize("fmt", FORMATS, ids=[f.value for f in FORMATS])
def test_a_model_file_url_gives_the_local_files_sbom(
    fmt: AiModelFormat,
    fetched: dict[str, object],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Byte for byte the SBOM of the same file read locally (in a clone, for
    the gate), from two clones in different directories; no message and no
    field names a clone's directory."""
    local = _copy(fmt, tmp_path / "local")
    with reading_remote_clone():
        expected = generate_model_sbom(local, creation_metadata=_FIXED)
    caplog.clear()
    runs = []
    for clone in ("clone-a", "clone-bb"):
        model = _copy(fmt, tmp_path / clone / "models")
        fetched.update(folder=model.parent, file=model.name)
        with caplog.at_level(logging.DEBUG):
            runs.append(generate_git_sbom(_URL, creation_metadata=_FIXED))
        texts = [*_messages(caplog), runs[-1]]
        assert not [t for t in texts if str(tmp_path) in t]
        caplog.clear()
    assert runs == [expected, expected]
    assert "SECRET" not in runs[0]


@pytest.mark.parametrize("fmt", FORMATS, ids=[f.value for f in FORMATS])
def test_a_native_library_reader_never_runs_on_a_downloaded_file(
    fmt: AiModelFormat,
    fetched: dict[str, object],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gated formats' reader is never called: the format-only entry and
    one ``reader-unsafe/remote`` ``INFO:``; every other format is read as a
    local file outside a clone is. A spy on the reader decides, not the
    SBOM: without its optional library a local read is a stub too."""
    local = _copy(fmt, tmp_path / "local")
    outside = generate_model_sbom(local, creation_metadata=_FIXED)
    model = _copy(fmt, tmp_path / "clone" / "models")
    fetched.update(folder=model.parent, file="")
    read = spy_readers(monkeypatch, (fmt,))
    with caplog.at_level(logging.INFO):
        sbom = generate_git_sbom(_URL, creation_metadata=_FIXED)
    notes = [
        r
        for r in caplog.records
        if getattr(r, CODE_ATTR, None) == READER_UNSAFE_REMOTE.code
    ]
    gated = fmt in WHEEL_GATED_FORMATS
    assert len(notes) == int(gated)
    assert read == ([] if gated or not has_reader_library(fmt) else [(fmt, model)])
    if not gated:
        assert sbom == outside
    assert f"FILE=models/{model.name}" in caplog.text  # the folder's one model


def test_the_fetchs_own_options_reach_it_on_the_model_route(
    fetched: dict[str, object], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``check_url``, ``offline`` and ``max_clone_bytes`` reach the fetch;
    ``offline`` is the fetch's alone, so a model read never says it has no
    effect."""
    model = _copy(AiModelFormat.KERAS, tmp_path / "c" / "models")
    fetched.update(folder=model.parent, file=model.name)

    def check(_url: str) -> None:
        """A caller's address check."""

    with caplog.at_level(logging.WARNING):
        generate_git_sbom(_URL, check_url=check, offline=False, max_clone_bytes=77)
        generate(_URL, check_url=check, offline=False)
    assert fetched["check_url"] is check and fetched["offline"] is False
    assert not logged_warnings(caplog)
    generate_git_sbom(_URL, max_clone_bytes=77)
    assert fetched["max_bytes"] == 77


def test_an_option_a_model_cannot_use_warns_once_with_the_models_reason(
    fetched: dict[str, object], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Each is one ``WARNING:`` naming the URL without credentials, in the
    words of the Git model target, never the clone."""
    model = _copy(AiModelFormat.NUMPY, tmp_path / "c" / "models")
    fetched.update(folder=model.parent, file=model.name)
    with caplog.at_level(logging.WARNING):
        generate_git_sbom(
            _URL,
            content_type=True,
            scan_model_usage=True,
            use_lockfile=False,
            update_id_registry=True,
            project_metadata=ProjectMetadata(name="p", version="1"),
        )
    warnings = logged_warnings(caplog)
    for flag in (
        "--content-type",
        "--scan-model-usage",
        "--use-lockfile",
        "--update-id-registry",
    ):
        assert count_naming(warnings, flag) == 1, flag
    assert sum("project_metadata has no effect" in w for w in warnings) == 1
    assert any("for a model target (there are no Python files" in w for w in warnings)
    assert all("SECRET" not in w and str(tmp_path) not in w for w in warnings)
    # The five option lines; a missing optional library adds its own warning.
    assert sum("Options: " in w for w in warnings) == 5


def test_a_project_only_of_a_model_folder_is_refused_with_a_hint(
    fetched: dict[str, object], tmp_path: Path
) -> None:
    """``generate_git_project_sbom()`` stays project-only: a folder of model
    files and no project is ``git.no-project`` naming ``loom model``."""
    model = _copy(AiModelFormat.NUMPY, tmp_path / "c" / "models")
    fetched.update(folder=model.parent, file=model.name)
    with pytest.raises(RemoteSourceError) as excinfo:
        generate_git_project_sbom(_URL)
    assert excinfo.value.code == "git.no-project"
    assert model.name in str(excinfo.value) and "loom model" in str(excinfo.value)


def test_an_unknown_sbom_kind_is_refused_before_the_fetch(
    fetched: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        _generators_git, "configure_logging", lambda: calls.append("configure")
    )
    with pytest.raises(InternalError, match="sbom_kind"):
        generate_git_sbom(_URL, sbom_kind="dataset")
    assert calls == ["configure"] and "url" not in fetched


def test_a_reader_warning_names_the_file_by_its_path_in_the_repository(
    fetched: dict[str, object], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A model file the reader cannot read: its ``WARNING:`` (the reader's
    own text included) and the SBOM name ``models/<file>``, never the
    clone's directory."""
    folder = tmp_path / "clone" / "models"
    folder.mkdir(parents=True)
    keras = fixture_path(AiModelFormat.KERAS).read_bytes()
    (folder / "cut.keras").write_bytes(keras[:4000])
    fetched.update(folder=folder, file="cut.keras")
    with caplog.at_level(logging.INFO):
        sbom = generate_git_sbom(_URL, creation_metadata=_FIXED)
    warned = logged_warnings(caplog)
    assert len(warned) == 1 and "FILE=models/cut.keras" in warned[0]
    assert "'models/cut.keras'" in warned[0]
    assert str(tmp_path) not in caplog.text + sbom
