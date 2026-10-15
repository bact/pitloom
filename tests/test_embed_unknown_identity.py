# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel whose ``METADATA`` has no ``Name`` embedded with
``loom embed-wheel`` / ``embed_wheel_sbom()``, with and without
``--project-dir``: not looked up in an ID registry, its document UUID seeded
by its file name, and one ``INFO:`` per batch.

See also: tests/test_wheel_unknown_identity_registry.py (``wheel``,
``generate``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.embed import EmbedFileCache, embed_wheel_sbom
from pitloom.id_registry import PACKAGE_TYPE
from tests.registry_helpers import make_registry

_PINNED = "https://example.org/pinned#Package-1"
_INFO = "package identity unknown"


def _wheel(root: Path, folder: str, stem: str) -> Path:
    path = root / folder / f"{stem}-1.0-py3-none-any.whl"
    path.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{stem}-1.0.dist-info/METADATA", "Version: 1.0\n")
        zf.writestr("pkg/__init__.py", "")
    return path


def _embedded(wheel: Path) -> dict[str, object]:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return dict(json.loads(archive.read(name)))


def _main(sbom: dict[str, object]) -> tuple[str, str]:
    """The main package's id and its document namespace."""
    graph = sbom["@graph"]
    assert isinstance(graph, list)
    (pkg,) = [e for e in graph if e["type"] == "software_Package"]
    spdx_id = str(pkg["spdxId"])
    return spdx_id, spdx_id.split("#", maxsplit=1)[0]


def _run(
    surface: str,
    wheels: list[Path],
    project: Path | None,
    reg: Path | None,
    mp: pytest.MonkeyPatch,
) -> None:
    if surface == "cli":
        argv = ["loom", "embed-wheel", *map(str, wheels)]
        if project is not None:
            argv += ["--project-dir", str(project)]
        if reg is not None:
            argv += ["--id-registry", str(reg)]
        mp.setattr(sys, "argv", argv)
        assert __main__.main() == 0
        return
    with EmbedFileCache() as cache:
        for wheel in wheels:
            embed_wheel_sbom(
                wheel, project_dir=project, id_registry=reg, file_cache=cache
            )


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


@pytest.mark.parametrize("surface", ["cli", "library"])
@pytest.mark.parametrize("with_project", [True, False], ids=["project", "standalone"])
@pytest.mark.parametrize("declared", [True, False], ids=["declared", "undeclared"])
def test_embed_of_nameless_wheels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    surface: str,
    with_project: bool,
    declared: bool,
) -> None:
    project = tmp_path / "pd"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "pd"\nversion = "1"\n', encoding="utf-8"
    )
    reg = tmp_path / "reg.json"
    if declared:
        make_registry({(PACKAGE_TYPE, "unknown"): (_PINNED, None)}, path=reg)
    wheels = [
        _wheel(tmp_path, "e3", "foo"),
        _wheel(tmp_path, "e4", "foo"),
        _wheel(tmp_path, "e3", "qux"),
    ]
    caplog.set_level(logging.INFO, logger="pitloom")
    _run(
        surface,
        wheels,
        project if with_project else None,
        reg if declared else None,
        monkeypatch,
    )
    foo3, foo4, qux = (_main(_embedded(w)) for w in wheels)
    assert _PINNED not in (foo3[0], foo4[0], qux[0])
    assert foo3 == foo4
    assert foo3[1] != qux[1]
    assert caplog.text.count(_INFO) == (1 if declared else 0)
