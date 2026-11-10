# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom project <pypi-url>``: the sdist of a PyPI release is downloaded and
read as a local sdist is, against a local fake PyPI (``loopback``).

See also: tests/cli/test_cli_wheel_pypi_url.py (the wheel and the shared
refusals), tests/cli/_pypi_cli.py (the helpers).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.assemble import PypiSbom, generate_pypi_sbom
from pitloom.cli.commands._remote_pypi import _default_output, run_pypi
from pitloom.core import temp_dirs
from pitloom.core.config import PitloomConfig
from pitloom.core.internal_error import InternalError
from pitloom.core.project import ProjectMetadata
from pitloom.extract.remote.pypi import SDIST, PypiDownload
from tests._fake_pypi_server import FakePypi
from tests.assemble._pypi_dists import NAME, URL, VERSION
from tests.cli._pypi_cli import CLI_CREATION, assert_clean_stderr, pinned_fake, run
from tests.kv_helpers import sbom_output_path

pytestmark = pytest.mark.loopback


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakePypi]:
    yield from pinned_fake(monkeypatch, tmp_path)


def _library() -> str:
    return generate_pypi_sbom(URL, kind=SDIST, creation_metadata=CLI_CREATION)


def test_the_sbom_is_the_librarys_and_named_by_metadata(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake
    assert run(monkeypatch, tmp_path, "project", URL) == 0
    captured = capsys.readouterr()
    expected = tmp_path / f"{NAME}-{VERSION}.spdx3.json"
    assert Path(sbom_output_path(captured.out)) == Path(expected.name)
    assert expected.read_text(encoding="utf-8").strip() == _library().strip()
    assert_clean_stderr(captured.err)


def test_stdout_is_the_sbom_alone_for_dash(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake
    assert run(monkeypatch, tmp_path, "project", URL, "-o", "-") == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["@graph"]
    assert_clean_stderr(captured.err)
    assert not list(tmp_path.glob("*.spdx3.json"))


def test_an_unusable_flag_warns_and_a_build_flag_is_not_run(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake
    assert run(monkeypatch, tmp_path, "project", URL, "--allow-build") == 0
    err = capsys.readouterr().err
    assert "--allow-build" in err
    assert_clean_stderr(err)


def test_an_unreachable_project_page_is_a_coded_error(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake
    url = "https://pypi.org/project/no-such-demo/"
    assert run(monkeypatch, tmp_path, "project", url) == 1
    err = capsys.readouterr().err
    assert "ERROR: " in err and "[release-not-found]" in err
    assert_clean_stderr(err)


def test_the_default_name_comes_from_the_sdists_metadata() -> None:
    """As a local sdist's: ``<name>-<version>``, ``<name>`` without a
    version, ``--config`` ``sbom-basename`` first; ``-o`` wins."""
    download = PypiDownload(
        path=Path("gone"),
        filename=f"{NAME}-{VERSION}.tar.gz",
        kind=SDIST,
        name=NAME,
        version=VERSION,
        project_url=URL,
        file_url="https://files.pythonhosted.org/x.tar.gz",
        sha256="a" * 64,
        size=1,
    )
    result = PypiSbom(
        sbom="{}", download=download, metadata=ProjectMetadata(name="Demo_X")
    )
    assert _default_output(result, None, None) == Path("Demo_X.spdx3.json")
    versioned = dataclasses.replace(
        result, metadata=ProjectMetadata(name="Demo_X", version="2.0")
    )
    assert _default_output(versioned, None, None) == Path("Demo_X-2.0.spdx3.json")
    named = PitloomConfig(sbom_basename="mine")
    assert _default_output(versioned, named, None) == Path("mine.spdx3.json")
    assert _default_output(versioned, named, Path("o.json")) == Path("o.json")


def test_a_download_dir_left_behind_is_a_warning_not_a_failure(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A directory that cannot be removed (a file held open on Windows)
    leaves the SBOM written, as the library returns it."""
    del fake
    monkeypatch.setattr(temp_dirs, "rmtree_quietly", lambda _path, _prefix: None)
    assert run(monkeypatch, tmp_path, "project", URL) == 0
    captured = capsys.readouterr()
    assert (tmp_path / f"{NAME}-{VERSION}.spdx3.json").is_file()
    warnings = [e for e in captured.err.splitlines() if e.startswith("WARNING: ")]
    assert len(warnings) == 1
    assert warnings[0].startswith(
        "WARNING: PyPI source: could not fully remove temporary directory "
    )


def test_run_pypi_refuses_an_unknown_kind() -> None:
    """The CLI route reads a wheel or an sdist only; any other kind is a
    programming error, raised before the arguments are read."""
    with pytest.raises(InternalError, match="kind must be"):
        run_pypi(argparse.Namespace(), URL, "model")
