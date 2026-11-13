# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""``loom model``, ``loom generate`` and ``loom project`` on the Git URL of
an AI model file or folder, and ``loom model`` on a local folder: the model
is fetched, then read as ``loom model`` reads a file; the output goes to the
current directory, never into the clone.

The fetch is stood in for by a prepared directory (the fetch itself is
tested in ``tests/extract/remote``).

See also: tests/cli/test_cli_project_git_url.py (a project at a Git URL).
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import _remote
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout
from tests._model_fixtures import fixture_path
from tests.kv_helpers import info_kv, sbom_output_path

_URL = "https://gitlab.example.org/g/p/-/blob/main/models/example-model.keras"
_NAME = "example-model.keras"
_AT = ["--creation-datetime", "2026-01-01T00:00:00Z"]


@pytest.fixture(name="fetched")
def _fetched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Stand in for the fetch with a clone whose folder ``models`` holds the
    Keras fixture; records what was asked of it. ``["file"]`` is the file
    the URL names (default: the fixture)."""
    folder = tmp_path / "clone" / "models"
    folder.mkdir(parents=True)
    shutil.copy(fixture_path(AiModelFormat.KERAS), folder)
    asked: dict[str, object] = {"folder": folder, "file": _NAME}

    @contextmanager
    def fetch(
        url: str,
        *,
        policy: RemoteFetchPolicy = RemoteFetchPolicy(),
        trust_model_files: bool = False,
    ) -> Iterator[GitCheckout]:
        asked.update(
            url=url,
            offline=policy.offline,
            max_bytes=policy.max_bytes,
            trust_model_files=trust_model_files,
        )
        if policy.offline:
            raise RemoteSourceError("git.offline", "network access is forbidden")
        file = str(asked["file"])
        yield GitCheckout(
            str(folder),
            url,
            "main",
            "c",
            "models",
            False,
            file,
            trust_model_files=trust_model_files,
        )

    monkeypatch.setattr(_remote, "fetch_git_project", fetch)
    return asked


def _run(monkeypatch: pytest.MonkeyPatch, cwd: Path, *argv: str) -> int:
    cwd.mkdir(exist_ok=True)
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def _ai_names(sbom: str) -> list[str]:
    graph = json.loads(sbom)["@graph"]
    return [e["name"] for e in graph if e.get("type") == "ai_AIPackage"]


@pytest.mark.parametrize(
    "url",
    [
        "https://huggingface.co/spaces/o/app",
        "https://gitlab.com/g/p/-/tree/main/svc",
        "https://user:SECRET@github.com/o/r",
    ],
)
def test_model_command_given_a_git_url_fetches_it(
    url: str,
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A Git URL (a Hugging Face Space too) is fetched and its model read.
    The rule was reversed: ``loom model`` used to refuse a Git URL and name
    ``loom project``; it now reads the model file the URL names, or the
    folder's one model file."""
    fetched["file"] = ""
    out = tmp_path / "work"
    assert _run(monkeypatch, out, "model", url) == 0
    captured = capsys.readouterr()
    assert fetched["url"] == url.strip() and fetched["offline"] is False
    assert sbom_output_path(captured.out) == str(out / f"{_NAME}.spdx3.json")
    assert "SECRET" not in captured.err + captured.out
    assert f"FILE=models/{_NAME}" in captured.err


def test_model_command_writes_the_models_sbom_in_the_current_directory(
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Named after the model file, in the current directory, not the clone;
    ``-v`` names the file by its path in the repository; stderr never names
    the clone's directory; ``--offline`` is the fetch's alone."""
    cwd = tmp_path / "work"
    assert _run(monkeypatch, cwd, "model", _URL, "-v", "--no-offline", *_AT) == 0
    captured = capsys.readouterr()
    written = cwd / f"{_NAME}.spdx3.json"
    assert sbom_output_path(captured.out) == str(written)
    assert _ai_names(written.read_text(encoding="utf-8")) == ["Binary_Classifier_v1"]
    assert info_kv(captured.err)["MODEL_FILE"] == f"models/{_NAME}"
    assert not list(Path(str(fetched["folder"])).glob("*.json"))
    assert str(tmp_path / "clone") not in captured.err
    assert "has no effect" not in captured.err


def test_model_command_offline_fetches_nothing(
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(monkeypatch, tmp_path / "w", "model", _URL, "--offline") == 1
    assert fetched["offline"] is True
    assert "ERROR: loom model: network access" in capsys.readouterr().err


def test_an_option_a_git_model_cannot_use_names_the_url(
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One ``WARNING:`` against the URL, in the Git model target's words."""
    assert _run(monkeypatch, tmp_path / "w", "model", _URL, "--content-type") == 0
    err = capsys.readouterr().err
    assert err.count(f"Options: {_URL}: --content-type/--no-content-type") == 1
    assert fetched["url"] == _URL


@pytest.mark.parametrize("output", ["x.json", "-"])
def test_generate_reads_a_model_file_url(
    output: str,
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom generate <url>`` gives the model SBOM; with ``-o -`` stdout is
    that SBOM alone."""
    cwd = tmp_path / "w"
    assert _run(monkeypatch, cwd, "generate", _URL, "-o", output, *_AT) == 0
    out = capsys.readouterr().out
    if output == "-":
        assert _ai_names(out) == ["Binary_Classifier_v1"]
    else:
        assert sbom_output_path(out) == output
        sbom = (cwd / output).read_text(encoding="utf-8")
        assert _ai_names(sbom) == ["Binary_Classifier_v1"]
    assert fetched["url"] == _URL


def test_project_command_on_a_model_folder_says_to_use_loom_model(
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom project`` stays project-only: one ``ERROR:`` with the hint,
    exit 1, nothing written."""
    cwd = tmp_path / "w"
    assert _run(monkeypatch, cwd, "project", _URL) == 1
    err = capsys.readouterr().err
    errors = [line for line in err.splitlines() if line.startswith("ERROR:")]
    assert len(errors) == 1 and "use 'loom model <url>'" in errors[0]
    assert _NAME in errors[0]
    assert not list(cwd.iterdir())
    assert fetched["url"] == _URL


def test_model_command_on_a_local_folder_reads_its_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The output is named after the model file, not the folder."""
    folder = tmp_path / "models"
    folder.mkdir()
    shutil.copy(fixture_path(AiModelFormat.KERAS), folder)
    (folder / "README.md").write_text("r\n", encoding="utf-8")
    assert _run(monkeypatch, tmp_path, "model", "models") == 0
    out = capsys.readouterr().out
    assert sbom_output_path(out) == str(tmp_path / f"{_NAME}.spdx3.json")


def test_model_command_on_a_folder_of_two_models_names_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "models"
    folder.mkdir()
    shutil.copy(fixture_path(AiModelFormat.KERAS), folder)
    shutil.copy(fixture_path(AiModelFormat.NUMPY), folder)
    assert _run(monkeypatch, tmp_path, "model", "models") == 1
    err = capsys.readouterr().err
    assert err.count("one of several AI model files") == 2
    assert "[model-ambiguous]" in err.splitlines()[-1]


@pytest.mark.parametrize("given", [True, False])
def test_trust_model_files_reaches_the_fetch_of_a_model_url(
    given: bool,
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The flag is the fetch's, not the model delegate's: it reaches the
    fetch only when given, and never warns "has no effect"."""
    fetched["file"] = ""
    flags = ["--trust-model-files"] if given else []
    assert _run(monkeypatch, tmp_path / "work", "model", _URL, *flags) == 0
    assert fetched["trust_model_files"] is given
    assert "has no effect" not in capsys.readouterr().err
