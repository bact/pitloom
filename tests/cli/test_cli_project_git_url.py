# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""``loom project <url>`` and ``loom generate <url>``: the Git URL of a project
is fetched, then read as ``loom project`` reads a directory.

The fetch is stood in for by a prepared directory (the fetch itself is tested
in ``tests/extract/remote``), so these tests cover what the commands do with
what was fetched: the settings that apply, the flags that cannot, the
messages.

See also: tests/extract/remote/test_git_http_e2e.py for the same commands
against a real (local) Git server.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import project as mod_project
from pitloom.extract.remote import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout
from tests.kv_helpers import sbom_output_path

_URL = "https://gitlab.example.org/g/p/-/tree/main/svc"
_DEMO = '[project]\nname = "demo"\nversion = "1.0"\n'


@pytest.fixture(name="fetched")
def _fetched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Stand in for the fetch with a project directory; records what was
    asked of it."""
    folder = tmp_path / "checkout"
    folder.mkdir()
    (folder / "pyproject.toml").write_text(
        _DEMO + '[tool.pitloom]\npretty = true\nsbom-basename = "hostile"\n',
        encoding="utf-8",
    )
    asked: dict[str, object] = {}

    @contextmanager
    def fetch(url: str, *, offline: bool | None = None) -> Iterator[GitCheckout]:
        asked["url"], asked["offline"] = url, offline
        if offline:
            raise RemoteSourceError("git.offline", f"no network for {url}")
        yield GitCheckout(str(folder), url, "main", "c0ffee", "svc", False)

    monkeypatch.setattr(mod_project, "fetch_git_project", fetch)
    asked["folder"] = folder
    return asked


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *argv: str) -> int:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


@pytest.mark.parametrize("command", ["project", "generate"])
def test_a_git_url_is_fetched_and_read_as_a_project(
    command: str,
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The SBOM describes the fetched project; the repository's own
    ``[tool.pitloom]`` (compact output, a file name) is not obeyed; stdout
    carries the output path alone."""
    out = tmp_path / "sbom.json"
    assert _run(monkeypatch, tmp_path, command, _URL, "-o", str(out)) == 0
    assert fetched["url"] == _URL and fetched["offline"] is None
    captured = capsys.readouterr()
    assert sbom_output_path(captured.out) == str(out)
    assert "\n" not in out.read_text(encoding="utf-8").strip()
    assert "demo" in {
        e.get("name") for e in json.loads(out.read_text(encoding="utf-8"))["@graph"]
    }
    assert "the repository's own [tool.pitloom] settings are ignored" in captured.err


def test_the_default_output_name_ignores_the_repositorys_basename(
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom project <url>`` names its file from the project, not from the
    ``sbom-basename`` the downloaded repository asked for."""
    assert _run(monkeypatch, tmp_path, "project", _URL) == 0
    assert Path(sbom_output_path(capsys.readouterr().out)).name == "demo-1.0.spdx3.json"
    assert fetched["folder"]


def test_an_explicit_config_applies_to_a_fetched_project(
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--config FILE`` is the user's own, so it is obeyed; no notice that a
    repository's settings are ignored is needed then."""
    config = tmp_path / "mine.toml"
    config.write_text("[tool.pitloom]\npretty = true\n", encoding="utf-8")
    out = tmp_path / "o.json"
    assert (
        _run(
            monkeypatch,
            tmp_path,
            "project",
            _URL,
            "--config",
            str(config),
            "-o",
            str(out),
        )
        == 0
    )
    assert out.read_text(encoding="utf-8").count("\n") > 10
    assert "settings are ignored" not in capsys.readouterr().err
    assert fetched["offline"] is False  # the config's own setting


@pytest.mark.parametrize(
    ("flags", "config", "offline"),
    [
        (["--offline"], None, True),
        ([], "offline = true", True),
        (["--no-offline"], "offline = true", False),
    ],
    ids=["flag", "config", "flag-beats-config"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_offline_forbids_the_fetch(
    flags: list[str],
    config: str | None,
    offline: bool,
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--offline``, or ``offline`` in ``--config``, is passed on; the flag
    wins; a refusal is one ``ERROR:`` and exit 1."""
    args = ["project", _URL, "-o", str(tmp_path / "o.json"), *flags]
    if config:
        cfg = tmp_path / "c.toml"
        cfg.write_text(f"[tool.pitloom]\n{config}\n", encoding="utf-8")
        args += ["--config", str(cfg)]
    code = _run(monkeypatch, tmp_path, *args)
    assert fetched["offline"] is offline
    assert code == (1 if offline else 0)
    assert (
        "ERROR: SBOM generation failed: no network" in capsys.readouterr().err
    ) == offline


def test_a_build_flag_has_no_effect_and_is_said_once(
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The build backend of a downloaded repository never runs."""
    assert (
        _run(
            monkeypatch,
            tmp_path,
            "project",
            _URL,
            "--allow-build",
            "-o",
            str(tmp_path / "o.json"),
        )
        == 0
    )
    err = capsys.readouterr().err
    assert err.count("--allow-build has no effect for a remote repository") == 1
    assert fetched["url"] == _URL


def test_a_failure_to_read_the_fetched_project_names_the_projects_below(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A checkout with no project but one below it: ``ERROR:`` with the hint."""
    folder = tmp_path / "checkout"
    (folder / "services" / "a").mkdir(parents=True)
    (folder / "services" / "a" / "setup.py").write_text("", encoding="utf-8")

    @contextmanager
    def fetch(url: str, *, offline: bool | None = None) -> Iterator[GitCheckout]:
        _ = offline
        yield GitCheckout(str(folder), url, None, "c", "", True)

    monkeypatch.setattr(mod_project, "fetch_git_project", fetch)
    assert (
        _run(monkeypatch, tmp_path, "project", _URL, "-o", str(tmp_path / "o.json"))
        == 1
    )
    assert "services/a" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["project", "generate"])
@pytest.mark.parametrize("address", ["ssh://git@host/o/r.git", "git@host:o/r.git"])
def test_a_remote_address_that_is_not_fetched_is_refused_aloud(
    command: str,
    address: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Not a "directory not found": a ``WARNING:`` and an ``ERROR:`` saying
    only http and https URLs are fetched."""
    assert (
        _run(monkeypatch, tmp_path, command, address, "-o", str(tmp_path / "o.json"))
        == 1
    )
    err = capsys.readouterr().err
    assert "WARNING: Git source: Cannot fetch" in err
    assert "ERROR: SBOM generation failed: Cannot fetch" in err
    assert "only http and https URLs are fetched" in err


@pytest.mark.skipif(
    sys.platform == "win32", reason="a colon is not valid in a Windows file name"
)
def test_a_local_path_that_looks_like_an_address_is_still_a_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory that exists is never read as a remote address."""
    project = tmp_path / "a@b:proj"
    project.mkdir()
    (project / "pyproject.toml").write_text(_DEMO, encoding="utf-8")
    assert (
        _run(
            monkeypatch,
            tmp_path,
            "project",
            str(project),
            "-o",
            str(tmp_path / "o.json"),
        )
        == 0
    )
    assert "Git source" not in capsys.readouterr().err


@pytest.mark.parametrize("command", ["project", "generate"])
@pytest.mark.parametrize(
    "url",
    [
        "https://huggingface.co/spaces/o/app",
        "https://huggingface.co/spaces/o/app/tree/main/src",
        "https://huggingface.co/datasets/o/data",
    ],
)
def test_a_hugging_face_space_or_dataset_is_fetched_as_a_git_repository(
    command: str,
    url: str,
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _run(monkeypatch, tmp_path, command, url, "-o", str(tmp_path / "o.json")) == 0
    )
    assert fetched["url"] == url


@pytest.mark.parametrize(
    "url",
    ["https://huggingface.co/o/m", "https://hf.co/o/m/tree/main"],
)
def test_a_hugging_face_model_is_no_project(
    url: str,
    fetched: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One ``ERROR:`` line naming ``loom model``, not a missing directory; the
    address is not fetched as a repository."""
    assert _run(monkeypatch, tmp_path, "project", url) == 1
    lines = capsys.readouterr().err.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("ERROR: ")
    assert "is a Hugging Face model, not a project: use 'loom model'" in lines[0]
    assert "url" not in fetched
