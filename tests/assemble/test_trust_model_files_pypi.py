# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The reader gate of a file downloaded from a PyPI URL, on every surface.

A wheel's fastText model is listed without metadata by default, with one
``reader-unsafe/remote`` ``INFO:`` naming the downloaded file (a download is
remote input, as a Git URL's clone is), and read with
``--trust-model-files``. An sdist's models are not scanned at all, as for a
local sdist archive, so the flag warns once that it has no effect there.

See also: :mod:`tests.assemble.test_trust_model_files` (a local wheel) and
:mod:`tests.assemble.test_generate_git_project_gate` (a Git URL's gate).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pitloom.assemble import (
    _generators_git,
    generate,
    generate_git_project_sbom,
    generate_project_sbom,
    generate_pypi_sbom,
    generate_wheel_sbom,
)
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.remote.git import GitCheckout
from pitloom.extract.remote.pypi import SDIST
from pitloom.extract.scanner_wheel import WHEEL_GATED_FORMATS
from tests._fake_pypi_server import Dist
from tests._model_fixtures import (
    FORMATS,
    fixture_path,
    has_reader_library,
    remote_gate_infos,
    spy_readers,
    write_model_project,
)
from tests._wheel_models import write_model_wheel
from tests.assemble._pypi_dists import (
    SDIST_NAME,
    URL,
    VERSION,
    WHEEL_NAME,
    fake_pypi,
    publish_demo,
    sdist_bytes,
)
from tests.assemble.embed_surfaces_shared import run_cli
from tests.assemble.test_trust_model_files import _hyperparameters
from tests.extract.scanner.test_scanner_wheel_gate_formats import (
    FASTTEXT_DIR,
    gate_infos,
    spy_load_model,
)
from tests.warning_helpers import count_naming, logged_warnings

_FLAG = "--trust-model-files"
_MODEL = "demo/sentimentdemo.bin"
_Runner = Callable[[Path, pytest.MonkeyPatch, bool], str]  # -> SBOM json


def _publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, members: dict[str, bytes]
) -> Iterator[str]:
    """A fake PyPI whose release ``URL`` has a wheel and an sdist, each
    holding *members*."""
    wheel = write_model_wheel(tmp_path / "published", members)
    assert wheel.name == WHEEL_NAME
    sdist = sdist_bytes(extra=members)
    for fake, _temp in fake_pypi(monkeypatch, tmp_path):
        dists = [Dist(WHEEL_NAME, wheel.read_bytes()), Dist(SDIST_NAME, sdist)]
        publish_demo(fake, {VERSION: dists})
        yield URL


@pytest.fixture(name="pypi_url")
def _pypi_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[str]:
    data = (FASTTEXT_DIR / "sentimentdemo.bin").read_bytes()
    yield from _publish(monkeypatch, tmp_path, {_MODEL: data})


def _cli(command: str) -> _Runner:
    def _run(tmp: Path, mp: pytest.MonkeyPatch, trust: bool) -> str:
        tmp.mkdir()
        out = tmp / "out.json"
        run_cli([command, URL, "-o", str(out), *([_FLAG] if trust else [])], mp)
        return out.read_text(encoding="utf-8")

    return _run


_WHEEL_SURFACES: dict[str, _Runner] = {
    "cli-wheel": _cli("wheel"),
    "cli-generate": _cli("generate"),
    "lib-generate": lambda _t, _m, trust: generate(URL, trust_model_files=trust),
    "lib-generate_wheel_sbom": lambda _t, _m, trust: generate_wheel_sbom(
        URL, trust_model_files=trust
    ),
    "lib-generate_pypi_sbom": lambda _t, _m, trust: generate_pypi_sbom(
        URL, trust_model_files=trust
    ),
}
_SDIST_SURFACES: dict[str, _Runner] = {
    "cli-project": _cli("project"),
    # None, not False, when not given: an explicit False is an option given.
    "lib-generate_project_sbom": lambda _t, _m, trust: generate_project_sbom(
        URL, trust_model_files=trust or None
    ),
    "lib-generate_pypi_sbom": lambda _t, _m, trust: generate_pypi_sbom(
        URL, kind=SDIST, trust_model_files=trust or None
    ),
}


def _ai_packages(sbom: str) -> int:
    return sum(e["type"] == "ai_AIPackage" for e in json.loads(sbom)["@graph"])


@pytest.fixture(name="quiet_run")
def _quiet_run(pypi_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    del pypi_url
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.loopback
@pytest.mark.parametrize("surface", _WHEEL_SURFACES)
def test_a_downloaded_wheels_model_is_gated_as_remote_input(
    surface: str,
    quiet_run: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    spy = spy_load_model(monkeypatch)
    run = _WHEEL_SURFACES[surface]

    gated = run(quiet_run / "gated", monkeypatch, False)
    spy.assert_not_called()
    assert not _hyperparameters(gated)
    (line,) = remote_gate_infos(caplog)
    assert line.startswith(f"FILE={WHEEL_NAME}: ")
    assert ": fasttext; pass --trust-model-files for a release you trust" in line
    assert gate_infos(caplog) == []  # not the local wheel's line

    caplog.clear()
    trusted = run(quiet_run / "trusted", monkeypatch, True)
    spy.assert_called_once()
    assert _hyperparameters(trusted)
    assert remote_gate_infos(caplog) == []
    assert not [w for w in logged_warnings(caplog) if "has no effect" in w]


@pytest.mark.loopback
@pytest.mark.parametrize("surface", _SDIST_SURFACES)
def test_a_downloaded_sdists_model_is_not_read_and_the_flag_warns(
    surface: str,
    quiet_run: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    spy = spy_load_model(monkeypatch)
    run = _SDIST_SURFACES[surface]
    for trust in (False, True):
        caplog.clear()
        sbom = run(quiet_run / str(trust), monkeypatch, trust)
        assert _MODEL in sbom  # listed as a file of the sdist
        assert _ai_packages(sbom) == 0
        assert remote_gate_infos(caplog) == []
        warned = count_naming(logged_warnings(caplog), _FLAG)
        assert warned == (1 if trust else 0)
    spy.assert_not_called()


def _gated_and_read(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[[], str],
) -> tuple[list[str], list[str]]:
    """The formats *run*'s ``reader-unsafe/remote`` line names, and those
    whose reader it ran."""
    read = spy_readers(monkeypatch)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        run()
    (line,) = remote_gate_infos(caplog)
    named = re.search(r": ([a-z0-9_, ]+); pass --trust-model-files ", line)
    assert named is not None, line
    return named.group(1).split(", "), sorted({str(fmt) for fmt, _path in read})


@pytest.mark.loopback
def test_the_pypi_and_git_routes_gate_the_same_formats(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Drift guard: with one model of every format (gated or not) in a
    downloaded wheel and in a Git URL's clone, the line names the same
    formats and the same readers run: neither gate can grow or shrink
    alone."""
    models = [fixture_path(fmt) for fmt in FORMATS]
    folder = write_model_project(tmp_path / "clone", models)

    @contextmanager
    def fetch(url: str, **_kwargs: object) -> Iterator[GitCheckout]:
        yield GitCheckout(str(folder), url, "main", "c", "", True)

    monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
    git = _gated_and_read(
        caplog, monkeypatch, lambda: generate_git_project_sbom("https://h/o/r")
    )
    members = {f"demo/{model.name}": model.read_bytes() for model in models}
    pypi = [
        _gated_and_read(caplog, monkeypatch, lambda: generate_pypi_sbom(URL))
        for _url in _publish(monkeypatch, tmp_path / "pypi", members)
    ]
    assert pypi == [git]
    gated, read = git
    assert gated == sorted(str(f) for f in WHEEL_GATED_FORMATS)
    assert read == sorted(
        str(f)
        for f in FORMATS
        if f not in WHEEL_GATED_FORMATS and has_reader_library(f)
    )
    assert str(AiModelFormat.SAFETENSORS) in read  # a non-gated format is read
