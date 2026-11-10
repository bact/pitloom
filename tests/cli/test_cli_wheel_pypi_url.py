# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom wheel <pypi-url>``, ``loom generate <pypi-url>`` and the refusals of
``loom model``/``--embed``: the wheel of a PyPI release is downloaded and read
as a local wheel is, against a local fake PyPI (``loopback``).

See also: tests/cli/test_cli_project_pypi_url.py (the sdist),
tests/cli/_pypi_cli.py (the helpers).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.assemble import generate_pypi_sbom
from pitloom.extract.remote import git as git_module
from tests._fake_pypi_server import FakePypi
from tests.assemble._pypi_dists import (
    URL,
    WHEEL_NAME,
    wheel_bytes,
)
from tests.cli._pypi_cli import CLI_CREATION, assert_clean_stderr, pinned_fake, run
from tests.kv_helpers import sbom_output_path

pytestmark = pytest.mark.loopback


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakePypi]:
    yield from pinned_fake(monkeypatch, tmp_path)


def _library() -> str:
    return generate_pypi_sbom(URL, creation_metadata=CLI_CREATION)


def _no_fetch(fake: FakePypi) -> None:
    assert not fake.seen


@pytest.mark.parametrize("command", ["wheel", "generate"])
def test_the_sbom_is_the_librarys(
    command: str,
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake
    out = tmp_path / "out" / "sbom.json"
    out.parent.mkdir()
    assert run(monkeypatch, tmp_path, command, URL, "-o", str(out)) == 0
    captured = capsys.readouterr()
    assert out.read_text(encoding="utf-8").strip() == _library().strip()
    assert sbom_output_path(captured.out) == str(out)
    assert_clean_stderr(captured.err)
    if command == "generate":
        assert "loom project" in captured.err


def test_the_default_name_is_the_wheel_filename_in_the_cwd(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake
    assert run(monkeypatch, tmp_path, "wheel", URL) == 0
    captured = capsys.readouterr()
    expected = tmp_path / f"{WHEEL_NAME}.spdx3.json"
    assert expected.is_file()
    assert Path(sbom_output_path(captured.out)) == expected
    assert_clean_stderr(captured.err)


@pytest.mark.parametrize("command", ["wheel", "generate"])
def test_stdout_is_the_sbom_alone_for_dash(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    del fake
    assert run(monkeypatch, tmp_path, command, URL, "-o", "-", "-v") == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["@graph"]
    assert captured.out.strip() == _library().strip()
    # -v reaches the PyPI route under both commands: no "has no effect".
    assert "PYPI_URL=" in captured.err
    assert "no effect" not in captured.err
    assert_clean_stderr(captured.err)
    assert not list(tmp_path.glob("*.spdx3.json"))


def test_embed_is_refused_without_a_fetch(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(monkeypatch, tmp_path, "wheel", URL, "--embed") == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR: ") and "--embed" in err
    assert_clean_stderr(err)
    _no_fetch(fake)


def test_a_signed_wheel_flag_without_embed_warns_once(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake
    assert run(monkeypatch, tmp_path, "wheel", URL, "--allow-signed-wheel") == 0
    err = capsys.readouterr().err
    assert err.count("--allow-signed-wheel") == 1
    assert_clean_stderr(err)


def test_model_refuses_a_pypi_url_without_a_fetch(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(monkeypatch, tmp_path, "model", URL) == 1
    err = capsys.readouterr().err
    assert "loom wheel" in err and "loom project" in err
    assert_clean_stderr(err)
    _no_fetch(fake)


@pytest.mark.parametrize("command", ["wheel", "project", "generate"])
def test_offline_refuses_the_fetch(
    command: str,
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    extra = ["-o", str(tmp_path / "o.json")] if command == "generate" else []
    assert run(monkeypatch, tmp_path, command, URL, "--offline", *extra) == 1
    err = capsys.readouterr().err
    assert "ERROR: " in err and "network access is forbidden" in err
    assert_clean_stderr(err)
    _no_fetch(fake)


def test_a_file_over_the_cap_is_refused_with_its_code(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake
    assert wheel_bytes()  # a wheel of more than one byte
    assert run(monkeypatch, tmp_path, "wheel", URL, "--max-download-bytes", "1") == 1
    err = capsys.readouterr().err
    assert "ERROR: " in err and "over-cap" in err and "max-download-bytes" in err
    assert_clean_stderr(err)
    assert not list(tmp_path.glob("*.spdx3.json"))


@pytest.mark.parametrize("value", ["0", "-1"])
def test_a_download_cap_that_is_not_positive_is_rejected(
    value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit) as exc:
        run(monkeypatch, tmp_path, "wheel", URL, "--max-download-bytes", value)
    assert exc.value.code == 2


def test_a_pypi_url_never_reaches_the_git_route(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del fake

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("the Git route was taken")

    monkeypatch.setattr(git_module, "fetch_git_project", boom)
    from pitloom.cli.commands import _remote  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(_remote, "fetch_git_project", boom)
    for command in ("wheel", "generate"):
        out = tmp_path / f"{command}.json"
        assert run(monkeypatch, tmp_path, command, URL, "-o", str(out)) == 0
