# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A direct-reference dependency (``name @ URL``) is said, as one ``INFO:``
line ``[dependency-name-ambiguous]``, not to be looked up on PyPI: once per
package and document, on every route that looks names up online (the
library, ``loom generate``, the Hatchling hook), never offline, never for a
registry requirement, and never with the URL.

See also: tests/test_direct_reference_surfaces.py (the lookup itself) and
tests/messages/test_dependency_name_ambiguous.py (the helper).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import deps, deps_pypi
from pitloom.assemble.spdx3.document import build
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from tests._author_routes import CREATED, hook_sbom, isolate
from tests._code_records import coded
from tests.assemble.embed_surfaces_shared import run_cli

pytestmark = pytest.mark.platform

_CODE = "dependency-name-ambiguous"
_URL = "https://example.com/secret/impostor.git"
_DIRECT = f"Impostor_Pkg @ git+{_URL}@v1"
_HEAD = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    '[project]\nname = "demo"\nversion = "1.0"\n'
)
_HATCH = "[tool.hatch.metadata]\nallow-direct-references = true\n"


def _pyproject(
    dependencies: list[str], extras: dict[str, list[str]] | None = None
) -> str:
    text = f"{_HEAD}dependencies = {json.dumps(dependencies)}\n"
    if extras:
        text += "[project.optional-dependencies]\n"
        text += "".join(f"{k} = {json.dumps(v)}\n" for k, v in extras.items())
    return text


@pytest.fixture(name="network", autouse=True)
def network_fixture(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A PyPI that knows no package: the lookups made, never the network."""
    seen: list[str] = []

    def fetch(name: str, _version: str | None) -> None:
        seen.append(name)

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", fetch)
    monkeypatch.setattr(deps, "_fetch_pypi_release_info", fetch)
    return seen


def _project(tmp_path: Path, pyproject: str) -> Path:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return tmp_path


def _info(caplog: pytest.LogCaptureFixture) -> list[str]:
    """The messages of the ``dependency-name-ambiguous`` lines."""
    return [message for code, message in coded(caplog) if code == _CODE]


def _library(
    tmp_path: Path, pyproject: str, caplog: pytest.LogCaptureFixture, **kwargs: Any
) -> None:
    with caplog.at_level(logging.INFO):
        generate_project_sbom(
            _project(tmp_path, pyproject), creation_metadata=CREATED, **kwargs
        )


def test_a_direct_reference_is_said_once_online_without_its_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    isolate(tmp_path, monkeypatch)
    _library(tmp_path, _pyproject([_DIRECT, "plain-pkg==1.0"]), caplog)
    (message,) = _info(caplog)
    assert message.startswith("PACKAGE=")
    assert "mpostor" in message
    assert "not looked up on PyPI" in message
    assert "secret" not in caplog.text
    assert [r.levelno for r in caplog.records if r.getMessage() == message] == [
        logging.INFO
    ]


@pytest.mark.parametrize(
    "extras",
    [
        {"x": ["impostor-pkg @ https://example.com/other.whl"]},
        {"x": ["impostor-pkg==2.0"]},
    ],
    ids=["extra-direct", "extra-registry"],
)
def test_the_same_package_in_an_extra_is_still_said_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    extras: dict[str, list[str]],
) -> None:
    isolate(tmp_path, monkeypatch)
    _library(tmp_path, _pyproject([_DIRECT], extras), caplog)
    assert len(_info(caplog)) == 1


def test_no_line_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    network: list[str],
) -> None:
    """Only a run that would look the name up says it was not."""
    isolate(tmp_path, monkeypatch)
    _library(tmp_path, _pyproject([_DIRECT, "plain-pkg==1.0"]), caplog, offline=True)
    assert not network
    assert not _info(caplog)


def test_a_registry_requirement_is_not_said(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    network: list[str],
) -> None:
    """Counter-example: ``flask>=2`` is looked up, so nothing is said."""
    isolate(tmp_path, monkeypatch)
    _library(tmp_path, _pyproject(["flask>=2", "plain-pkg==1.0"]), caplog)
    assert network
    assert not _info(caplog)


def test_the_hook_says_it_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    isolate(tmp_path, monkeypatch)
    project = _project(tmp_path, _pyproject([_DIRECT, "plain-pkg==1.0"]) + _HATCH)
    with caplog.at_level(logging.INFO):
        hook_sbom(project)
    assert len(_info(caplog)) == 1
    assert "secret" not in caplog.text


def test_the_cli_says_it_on_stderr_and_nothing_on_stdout_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    isolate(tmp_path, monkeypatch)
    project = _project(tmp_path, _pyproject([_DIRECT, "plain-pkg==1.0"]))
    run_cli(["generate", str(project), "-o", str(tmp_path / "sbom.json")], monkeypatch)
    captured = capsys.readouterr()
    lines = [ln for ln in captured.err.splitlines() if f"[{_CODE}]" in ln]
    assert len(lines) == 1
    assert lines[0].startswith("INFO: PACKAGE=")
    assert "secret" not in captured.err
    assert _CODE not in captured.out


def _document(name: str) -> DocumentModel:
    """A document whose dependencies hold *name* as a direct reference twice
    (as a dependency and as an extra's) and, locked, a registry release."""
    url = f"{name} @ https://example.invalid/{name}-1.0.whl"
    return DocumentModel(
        project=ProjectMetadata(
            name="main",
            version="1.0",
            dependencies=[url, f'{url}; extra == "x"'],
            locked_dependencies=["other==1.0"],
        ),
        creation_metadata=CreationMetadata(creation_datetime="2024-05-01T00:00:00Z"),
    )


@pytest.mark.parametrize("offline", [False, True], ids=["online", "offline"])
def test_one_assembly_says_a_package_once_and_never_offline(
    caplog: pytest.LogCaptureFixture, offline: bool
) -> None:
    """Both spellings of the direct reference are one package: one line
    online, none offline."""
    with caplog.at_level(logging.INFO):
        build(_document("impostor"), offline=offline)
    assert len(_info(caplog)) == (0 if offline else 1)


def test_a_new_document_says_it_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Per document, never per process."""
    isolate(tmp_path, monkeypatch)
    project = _project(tmp_path, _pyproject([_DIRECT]))
    with caplog.at_level(logging.INFO):
        for _ in range(2):
            generate_project_sbom(project, creation_metadata=CREATED)
    assert len(_info(caplog)) == 2
