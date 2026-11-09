# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The project of a Git URL: a model file in its build file list is never
read by a gated reader (fastText, GGUF, HDF5, ONNX, PyTorch), on every
library route to it (``generate_git_sbom(sbom_kind="project")``,
``generate_git_project_sbom()``, ``generate()``); it keeps a format-only
entry, and one ``reader-unsafe/remote`` ``INFO:`` per SBOM names the
formats. Every other format is read as in the same project read locally,
and a local project reads every format.

The fetch is stood in for by a prepared directory, as in
:mod:`tests.assemble.test_generate_git_model` (the model route).

See also: :mod:`tests.extract.scanner.test_scanner_wheel_gate_formats` (the
scan) and :mod:`tests.cli.test_cli_project_git_url` (``loom project <url>``).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import textwrap
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import (
    _generators_git,
    generate,
    generate_git_project_sbom,
    generate_git_sbom,
    generate_project_sbom,
)
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.extract.remote.git import GitCheckout
from pitloom.extract.scanner_wheel import WHEEL_GATED_FORMATS
from tests._model_fixtures import (
    FORMATS,
    fixture_path,
    has_reader_library,
    remote_gate_infos,
    spy_readers,
    write_model_project,
)

_URL = "https://git.example.org/o/r/-/tree/main/proj"
_FIXED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_GATED_NAMES = sorted(str(f) for f in WHEEL_GATED_FORMATS)
_HOSTILE = Path(__file__).parents[1] / "fixtures" / "aimodels" / "hostile"


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with one fixture of each format, as the fetch's clone."""
    folder = write_model_project(tmp_path / "clone", [fixture_path(f) for f in FORMATS])

    @contextmanager
    def fetch(
        url: str,
        *,
        check_url: object = None,
        offline: bool | None = None,
        max_bytes: int | None = None,
    ) -> Iterator[GitCheckout]:
        del check_url, offline, max_bytes  # the fetch's own; not this test's
        yield GitCheckout(
            folder=str(folder),
            repo_url=url,
            ref="main",
            commit="c",
            subdir="proj",
            whole_repository=False,
        )

    monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
    return folder


def _local(folder: Path) -> str:
    """The SBOM of *folder* read as a local project, with the settings a
    Git URL's project is read with."""
    return generate_project_sbom(
        folder, creation_metadata=_FIXED, pitloom_config=PitloomConfig()
    )


#: Each library route to a Git URL's project.
_ROUTES: dict[str, Callable[[], str]] = {
    "git-sbom": lambda: generate_git_sbom(
        _URL, sbom_kind="project", creation_metadata=_FIXED
    ),
    "git-project": lambda: generate_git_project_sbom(_URL, creation_metadata=_FIXED),
    "generate": lambda: generate(_URL, creation_metadata=_FIXED),
}


def _models_by_file(sbom: str) -> dict[str, object]:
    """Each AI package of *sbom* by its file name, every element id in it
    replaced by that element's name (so that numbering does not decide)."""
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    names = {e["spdxId"]: e.get("name") for e in graph if "spdxId" in e}

    def named(value: object) -> object:
        if isinstance(value, dict):
            return {k: named(v) for k, v in value.items()}
        if isinstance(value, list):
            return [named(v) for v in value]
        return names.get(value, value) if isinstance(value, str) else value

    return {
        e["software_packageUrl"].split("/")[1].split("?")[0]: named(e)
        for e in graph
        if e.get("type") == "ai_AIPackage"
    }


@pytest.mark.parametrize("route", list(_ROUTES), ids=list(_ROUTES))
def test_a_gated_reader_never_runs_on_a_git_urls_project(
    route: str,
    project: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spy on the readers decides, not the SBOM: without its optional
    library a local read is a format-only entry too."""
    local = _models_by_file(_local(project))
    read = spy_readers(monkeypatch)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        remote = _models_by_file(_ROUTES[route]())
    assert not {fmt for fmt, _ in read} & WHEEL_GATED_FORMATS
    assert sorted(fmt for fmt, _ in read) == [
        f for f in FORMATS if f not in WHEEL_GATED_FORMATS and has_reader_library(f)
    ]
    (note,) = remote_gate_infos(caplog)  # five gated models, one line
    assert f": {', '.join(_GATED_NAMES)}; " in note
    assert set(remote) == set(local) == {fixture_path(f).name for f in FORMATS}
    for fmt in FORMATS:
        name = fixture_path(fmt).name
        if fmt in WHEEL_GATED_FORMATS:
            entry = json.dumps(remote[name])
            assert "Method: file_name_stem" in entry
            assert "Field:" not in entry, fmt  # format-only
            if has_reader_library(fmt):  # read in full outside a clone
                assert "Field:" in json.dumps(local[name]), fmt
        else:
            assert remote[name] == local[name], fmt


def test_a_local_project_reads_every_format(
    project: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside a Git URL's clone (``loom project <dir>``, the library) the
    gated readers run, and nothing says ``reader-unsafe/remote``."""
    read = spy_readers(monkeypatch)
    with caplog.at_level(logging.INFO):
        _local(project)
    expected = [f for f in FORMATS if has_reader_library(f)]
    if not set(expected) & WHEEL_GATED_FORMATS:
        pytest.skip("no gated format's library is installed")
    assert sorted(fmt for fmt, _ in read) == expected
    assert not remote_gate_infos(caplog)


def test_a_project_without_a_gated_model_says_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The ``INFO:`` names the gated models met; none met, no line."""
    folder = write_model_project(
        tmp_path / "clone", [fixture_path(AiModelFormat.SAFETENSORS)]
    )

    @contextmanager
    def fetch(url: str, **_options: object) -> Iterator[GitCheckout]:
        yield GitCheckout(
            folder=str(folder),
            repo_url=url,
            ref="main",
            commit="c",
            subdir="proj",
            whole_repository=False,
        )

    monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
    with caplog.at_level(logging.INFO):
        assert generate_git_project_sbom(_URL, creation_metadata=_FIXED) == _local(
            folder
        )
    assert not remote_gate_infos(caplog)


@pytest.mark.parametrize("hostile", ["hdf5-hang.h5", "hdf5-segfault.h5"])
def test_a_hostile_hdf5_in_a_git_urls_project_is_listed_not_opened(
    hostile: str, tmp_path: Path
) -> None:
    """Run in a subprocess under a timeout: were the gate broken, libhdf5
    would kill or hang the interpreter this test runs in."""
    if not (_HOSTILE / hostile).is_file():
        pytest.skip(f"{hostile} is not in this checkout")
    folder = write_model_project(tmp_path / "clone", [_HOSTILE / hostile])
    code = textwrap.dedent(
        """
        import json, sys
        from contextlib import contextmanager
        from pitloom.assemble import _generators_git, generate_git_project_sbom
        from pitloom.extract.remote.git import GitCheckout

        @contextmanager
        def fetch(url, **_options):
            yield GitCheckout(
                folder=sys.argv[1],
                repo_url=url,
                ref="main",
                commit="c",
                subdir="proj",
                whole_repository=False,
            )

        _generators_git.fetch_git_project = fetch
        sbom = generate_git_project_sbom("https://git.example.org/o/r")
        print(sorted(
            e["name"] for e in json.loads(sbom)["@graph"]
            if e.get("type") == "ai_AIPackage"
        ))
        """
    )
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, str(folder)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == repr([Path(hostile).stem])
    assert "[reader-unsafe/remote]" in done.stderr
