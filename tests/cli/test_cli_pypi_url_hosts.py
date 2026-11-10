# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The hosts of the PyPI family on the command line: ``pypi.org`` with a
trailing dot is read as ``pypi.org``; another index and PyPI's old address
are refused with ``[pypi-url-invalid]`` by ``loom wheel``, ``loom project``
and ``loom generate`` (``--offline`` too: the URL is read first), and with
``[pypi-url-unusable]`` by ``loom model``. Nothing is fetched or cloned.

See also: tests/assemble/test_generate_pypi_hosts.py (the library),
tests/cli/_pypi_cli.py (the helpers).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.extract.remote import git, pypi
from pitloom.extract.remote._git_run import GitRunner
from pitloom.messages import (
    MODEL_URL_LINE,
    PYPI_URL_INVALID,
    PYPI_URL_UNUSABLE,
    Line,
)
from tests._fake_pypi_server import FakePypi
from tests.assemble._pypi_dists import DOTTED, REFUSED, REFUSED_IDS, URL
from tests.cli._pypi_cli import assert_clean_stderr, pinned_fake, run

pytestmark = pytest.mark.loopback


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakePypi]:
    yield from pinned_fake(monkeypatch, tmp_path)


@pytest.fixture(name="no_fetch")
def _no_fetch(monkeypatch: pytest.MonkeyPatch, fake: FakePypi) -> Iterator[None]:
    """Fail on any download, Git command or Git redirect probe; and assert
    the fake PyPI was never asked."""

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fetched")

    monkeypatch.setattr(pypi, "_download", boom)
    monkeypatch.setattr(git, "_resolve", boom)
    monkeypatch.setattr(GitRunner, "run", boom)
    yield
    assert not fake.seen


@pytest.mark.parametrize("offline", [[], ["--offline"]], ids=["online", "offline"])
@pytest.mark.parametrize("case", REFUSED, ids=REFUSED_IDS)
@pytest.mark.parametrize("command", ["wheel", "project", "generate", "model"])
@pytest.mark.usefixtures("no_fetch")
def test_a_command_refuses_another_pypi_host(
    command: str,
    case: tuple[str, Line],
    offline: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, line = case
    extra = ["-o", str(tmp_path / "o.json")] if command == "generate" else []
    assert run(monkeypatch, tmp_path, command, url, *offline, *extra) == 1
    err = capsys.readouterr().err
    if command == "model":
        line, code = MODEL_URL_LINE, PYPI_URL_UNUSABLE.code
    else:
        code = PYPI_URL_INVALID.code
    errors = [e for e in err.splitlines() if e.startswith("ERROR: ")]
    assert len(errors) == 1
    assert errors[0].endswith(f"{line.render({'url': url})} [{code}]")
    assert "network access is forbidden" not in err
    assert_clean_stderr(err)
    assert not list(tmp_path.glob("*.spdx3.json"))


@pytest.mark.parametrize("command", ["wheel", "project", "generate"])
def test_a_trailing_dot_reads_pypi_org(
    command: str,
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sboms: list[bytes] = []
    for url in (DOTTED, URL):
        out = tmp_path / f"out{len(sboms)}.json"
        assert run(monkeypatch, tmp_path, command, url, "-o", str(out)) == 0
        sboms.append(out.read_bytes())
    assert fake.seen
    assert sboms[0] == sboms[1]
