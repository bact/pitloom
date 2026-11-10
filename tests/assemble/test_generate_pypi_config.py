# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The download cap and the options of a PyPI URL target: the
``max-download-bytes`` cascade (argument > explicit config > 512 MiB), its
validation on every surface, the options a downloaded file cannot use, and
the PyPI JSON URL a dependency lookup shares with the target.

See also: tests/assemble/test_generate_pypi.py (the surfaces),
tests/core/test_config.py (the config key's reader).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import (
    _generators_pypi,
    generate,
    generate_git_sbom,
    generate_project_sbom,
    generate_pypi_sbom,
    generate_wheel_sbom,
)
from pitloom.assemble.spdx3 import deps_pypi
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import load_config_file
from pitloom.core.inert_options import GIT, forward_options
from pitloom.core.model_extract_limit import DEFAULT_MAX_DOWNLOAD_BYTES
from pitloom.extract.remote import pypi
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.pypi import SDIST
from tests._fake_pypi_server import FakePypi
from tests.assemble._pypi_dists import (
    CREATION,
    URL,
    WHEEL_NAME,
    fake_pypi,
    publish_demo,
    wheel_bytes,
)

_SIZE = len(wheel_bytes())
#: The real lookup, before tests/conftest.py stubs it out for every test.
_real_lookup = deps_pypi._fetch_pypi_release_info  # pylint: disable=protected-access


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakePypi]:
    for fake, _temp in fake_pypi(monkeypatch, tmp_path):
        publish_demo(fake)
        yield fake


@pytest.fixture(name="caps")
def _caps(monkeypatch: pytest.MonkeyPatch) -> list[int | None]:
    """The cap each fetch is given."""
    seen: list[int | None] = []
    real = pypi.fetch_pypi_file

    def _spy(url: str, **kwargs: Any) -> AbstractContextManager[pypi.PypiDownload]:
        seen.append(kwargs["max_bytes"])
        return real(url, **kwargs)

    monkeypatch.setattr(_generators_pypi, "fetch_pypi_file", _spy)
    return seen


def _config_file(tmp_path: Path, cap: int) -> PitloomConfig:
    path = tmp_path / "pitloom.toml"
    path.write_text(f"[tool.pitloom]\nmax-download-bytes = {cap}\n", encoding="utf-8")
    return load_config_file(path)


# --- the cascade ----------------------------------------------------------


@pytest.mark.loopback
@pytest.mark.parametrize(
    ("argument", "configured", "expected"),
    [
        (None, None, DEFAULT_MAX_DOWNLOAD_BYTES),
        (None, 1000, 1000),
        (2000, 1000, 2000),
        (2000, None, 2000),
    ],
    ids=["default", "config", "argument-beats-config", "argument"],
)
def test_the_cap_cascades(
    fake: FakePypi,
    caps: list[int | None],
    tmp_path: Path,
    argument: int | None,
    configured: int | None,
    expected: int,
) -> None:
    del fake
    config = None if configured is None else _config_file(tmp_path, configured)
    generate_pypi_sbom(
        URL,
        max_download_bytes=argument,
        pitloom_config=config,
        creation_metadata=CREATION,
    )
    assert caps == [expected]


@pytest.mark.loopback
@pytest.mark.parametrize(
    "call",
    [
        lambda tmp: generate_pypi_sbom(URL, max_download_bytes=_SIZE - 1),
        lambda tmp: generate_wheel_sbom(URL, max_download_bytes=_SIZE - 1),
        lambda tmp: generate(URL, max_download_bytes=_SIZE - 1),
        lambda tmp: generate_pypi_sbom(
            URL, pitloom_config=_config_file(tmp, _SIZE - 1)
        ),
    ],
    ids=["pypi", "wheel", "generate", "config-file"],
)
def test_a_file_over_the_cap_is_refused(
    fake: FakePypi, tmp_path: Path, call: Callable[[Path], str]
) -> None:
    with pytest.raises(RemoteSourceError) as exc:
        call(tmp_path)
    assert exc.value.code == "pypi.too-large"
    assert f"/files/{WHEEL_NAME}" in fake.seen


@pytest.mark.loopback
def test_a_file_at_the_cap_is_read(fake: FakePypi) -> None:
    del fake
    assert generate_pypi_sbom(URL, max_download_bytes=_SIZE, creation_metadata=CREATION)


_BAD = [0, -1, True, 1.5, "8"]


@pytest.mark.loopback
@pytest.mark.parametrize("bad", _BAD, ids=repr)
@pytest.mark.parametrize(
    "call",
    [
        lambda bad: generate_pypi_sbom(URL, max_download_bytes=bad),
        lambda bad: generate_project_sbom(URL, max_download_bytes=bad),
        lambda bad: generate(URL, max_download_bytes=bad),
        lambda bad: generate_pypi_sbom(
            URL, pitloom_config=PitloomConfig(max_download_bytes=bad)
        ),
    ],
    ids=["pypi", "project", "generate", "config"],
)
def test_an_invalid_cap_is_refused_before_any_request(
    fake: FakePypi, call: Callable[[object], str], bad: object
) -> None:
    with pytest.raises(ValueError, match="max.download.bytes"):
        call(bad)
    assert not fake.seen


def _local_wheel(tmp_path: Path) -> Path:
    wheel = tmp_path / WHEEL_NAME
    wheel.write_bytes(wheel_bytes())
    return wheel


def _local_project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "proj"\nversion = "1.0"\n', encoding="utf-8"
    )
    return project


def _model_file(tmp_path: Path) -> Path:
    """A model file (by its suffix), which the cap's check comes before."""
    model = tmp_path / "m.safetensors"
    model.write_bytes(b"\0")
    return model


_LOCAL: list[tuple[str, Callable[..., str], Callable[[Path], Path]]] = [
    ("wheel", generate_wheel_sbom, _local_wheel),
    ("project", generate_project_sbom, _local_project),
    ("generate-wheel", generate, _local_wheel),
    ("generate-project", generate, _local_project),
]
_INVALID_ANYWHERE = [*_LOCAL, ("generate-model", generate, _model_file)]


@pytest.mark.parametrize(
    ("call", "make"),
    [c[1:] for c in _INVALID_ANYWHERE],
    ids=[c[0] for c in _INVALID_ANYWHERE],
)
def test_a_local_target_refuses_an_invalid_cap_all_the_same(
    tmp_path: Path, call: Callable[..., str], make: Callable[[Path], Path]
) -> None:
    with pytest.raises(ValueError, match="max_download_bytes"):
        call(make(tmp_path), max_download_bytes=0)


@pytest.mark.parametrize(
    ("call", "make"), [c[1:] for c in _LOCAL], ids=[c[0] for c in _LOCAL]
)
def test_a_local_target_warns_the_cap_has_no_effect_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    call: Callable[..., str],
    make: Callable[[Path], Path],
) -> None:
    call(make(tmp_path), max_download_bytes=5, creation_metadata=CREATION)
    lines = [
        line
        for line in capsys.readouterr().err.splitlines()
        if "--max-download-bytes has no effect" in line
    ]
    assert len(lines) == 1 and lines[0].startswith("WARNING: Options: ")
    assert "only a PyPI URL target downloads a file" in lines[0]


def test_a_git_url_declares_the_cap_inert(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        forwarded = forward_options(
            GIT,
            "https://example.invalid/r",
            generate_git_sbom,
            {"max_download_bytes": 5},
        )
    assert not forwarded
    assert len(caplog.records) == 1


# --- options a download cannot use ----------------------------------------


def _warned(err: str, flag: str) -> list[str]:
    """The lines saying *flag* (either spelling) has no effect."""
    said = re.compile(rf": {re.escape(flag)}(/--no-\S+)? has no effect ")
    return [line for line in err.splitlines() if said.search(line)]


@pytest.mark.loopback
@pytest.mark.parametrize(
    ("kind", "options", "flags"),
    [
        (
            "wheel",
            {"enrich": True, "project_dir": "p", "use_lockfile": False},
            ["--enrich", "--project-dir", "--use-lockfile"],
        ),
        (
            SDIST,
            {
                "scan_model_usage": True,
                "max_model_extract_bytes": 5,
                "project_dir": "p",
            },
            ["--scan-model-usage", "--max-model-extract-bytes", "--project-dir"],
        ),
    ],
)
def test_each_inert_option_warns_once_against_the_url(
    fake: FakePypi,
    capsys: pytest.CaptureFixture[str],
    kind: str,
    options: dict[str, Any],
    flags: list[str],
) -> None:
    del fake
    generate_pypi_sbom(
        URL,
        kind=kind,
        creation_metadata=CREATION,
        build_options=BuildOptions(allow=True),
        **options,
    )
    err = capsys.readouterr().err
    for flag in flags:
        (line,) = _warned(err, flag)
        assert line.startswith(f"WARNING: Options: {URL}: ")
    (build,) = _warned(err, "--allow-build")
    assert build.startswith(f"WARNING: Build: {URL}: ")
    assert "for a PyPI URL target" in build


@pytest.mark.loopback
def test_project_metadata_has_no_effect_for_a_url(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    del fake
    # pylint: disable-next=import-outside-toplevel
    from pitloom.core.project import ProjectMetadata

    with caplog.at_level(logging.WARNING):
        sbom = generate_project_sbom(
            URL,
            project_metadata=ProjectMetadata(name="other", version="9"),
            creation_metadata=CREATION,
        )
    assert '"name":"demo"' in sbom
    (warned,) = [
        r for r in caplog.records if "project_metadata has no effect" in r.message
    ]
    assert URL in warned.message


# --- deps_pypi shares the JSON URL builder --------------------------------


@pytest.mark.parametrize(
    ("name", "version", "expected"),
    [
        ("a/b", "1/2", "https://pypi.org/pypi/a%2Fb/1%2F2/json"),
        ("demo", None, "https://pypi.org/pypi/demo/json"),
        ("demo", "", "https://pypi.org/pypi/demo/json"),
        ("demo", "1.0", "https://pypi.org/pypi/demo/1.0/json"),
    ],
)
def test_a_dependency_lookup_escapes_each_segment(
    monkeypatch: pytest.MonkeyPatch, name: str, version: str | None, expected: str
) -> None:
    asked: list[str] = []

    def _fetch(url: str, **kwargs: object) -> dict[str, Any]:
        del kwargs
        asked.append(url)
        return {}

    monkeypatch.setattr(deps_pypi, "fetch_json", _fetch)
    _real_lookup(name, version)
    assert asked == [expected]
