# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One unreadable project file: every surface warns once and keeps the rest.

Every surface that scans a project directory's files goes through
``get_wheel_files()``: ``loom project``, ``loom generate``, ``loom
embed-wheel --project-dir``, the library's ``generate_project_sbom()``/
``generate()``/``embed_wheel_sbom(project_dir=...)``, and the Hatchling
build hook; ``loom enrich --project-dir`` hashes the same file set for its
document identity. Each must log exactly one ``WARNING:`` naming the unreadable
file and keep every other file's scan result (here: a readable file's
copyright header). A generating surface drops the unreadable file from
its ``software_File`` set; an embed keeps it, as the wheel's own file set
is the truth there and the project scan only adds header data.

A directory discovery cannot list (``chmod 000``) likewise gets one
``DIR=`` warning on every surface; the names under it are never seen.

See also: tests/core/models_wheel/test_models_wheel_unreadable.py for the
scan itself, tests/_unreadable.py for the deny modes.
"""

from __future__ import annotations

import json
import logging
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate, generate_project_sbom
from pitloom.embed import embed_wheel_sbom
from tests._unreadable import ALL_MODES, POSIX_NON_ROOT, deny, unlistable
from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import run_cli
from tests.assemble.enrich_identity_shared import (
    enrich_base_namespace,
    sbom_namespace,
)
from tests.extract.conftest import make_hook

_READABLE = "demo/__init__.py"
_SECRET = "demo/locked/secret.txt"
_COPYRIGHT = "2026 Demo Author"
_EMBED_SURFACES = ("cli-embed-wheel", "lib-embed_wheel_sbom")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "demo" / "locked").mkdir(parents=True)
    (root / _READABLE).write_text(
        f"# SPDX-FileCopyrightText: {_COPYRIGHT}\nx = 1\n", encoding="utf-8"
    )
    (root / _SECRET).write_text("secret\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "demo"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    return root


def _wheel_sbom(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


def _cli_project(project: Path, tmp: Path, mp: pytest.MonkeyPatch) -> str:
    output = tmp / "out.spdx3.json"
    run_cli(["project", str(project), "-o", str(output)], mp)
    return output.read_text(encoding="utf-8")


def _cli_generate(project: Path, tmp: Path, mp: pytest.MonkeyPatch) -> str:
    output = tmp / "out.spdx3.json"
    run_cli(["generate", str(project), "-o", str(output)], mp)
    return output.read_text(encoding="utf-8")


def _cli_embed_wheel(project: Path, tmp: Path, mp: pytest.MonkeyPatch) -> str:
    wheel = _make_dummy_wheel(tmp / "dist", "demo", "1.0.0")
    run_cli(["embed-wheel", str(wheel), "--project-dir", str(project)], mp)
    return _wheel_sbom(wheel)


def _lib_generate_project_sbom(
    project: Path, _tmp: Path, _mp: pytest.MonkeyPatch
) -> str:
    return generate_project_sbom(project, offline=True)


def _lib_generate(project: Path, _tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate(project, offline=True)


def _lib_embed_wheel_sbom(project: Path, tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    wheel = _make_dummy_wheel(tmp / "dist", "demo", "1.0.0")
    output = embed_wheel_sbom(wheel, project_dir=project)[0]
    return _wheel_sbom(output)


def _hatchling_hook(project: Path, _tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    try:
        (staged,) = build_data["sbom_files"]
        return Path(staged).read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")


_SURFACES: dict[str, Callable[[Path, Path, pytest.MonkeyPatch], str]] = {
    "cli-project": _cli_project,
    "cli-generate": _cli_generate,
    "cli-embed-wheel": _cli_embed_wheel,
    "lib-generate_project_sbom": _lib_generate_project_sbom,
    "lib-generate": _lib_generate,
    "lib-embed_wheel_sbom": _lib_embed_wheel_sbom,
    "hatchling-hook": _hatchling_hook,
}


def _files(sbom_json: str) -> dict[str, dict[str, Any]]:
    return {
        str(element["name"]): element
        for element in json.loads(sbom_json)["@graph"]
        if element.get("type") == "software_File"
    }


def _assert_readable_scanned(files: dict[str, dict[str, Any]]) -> None:
    assert files[_READABLE].get("software_copyrightText") == _COPYRIGHT


@pytest.mark.parametrize("mode", ALL_MODES)
@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_unreadable_file_is_skipped_with_one_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    surface: str,
    mode: str,
) -> None:
    run = _SURFACES[surface]
    embed = surface in _EMBED_SURFACES
    project = _project(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    # Not vacuous: readable, the file is in a generating surface's SBOM.
    files = _files(run(project, tmp_path / "a", monkeypatch))
    _assert_readable_scanned(files)
    assert embed or _SECRET in files

    with (
        deny(project / _SECRET, mode, monkeypatch),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        files = _files(run(project, tmp_path / "b", monkeypatch))

    _assert_readable_scanned(files)
    assert _SECRET not in files
    about_secret = [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and _SECRET in r.getMessage()
    ]
    assert len(about_secret) == 1
    assert about_secret[0].startswith(f"FILE={_SECRET}: could not read")


@pytest.mark.parametrize("mode", ALL_MODES)
def test_enrich_identity_matches_the_sbom_with_an_unreadable_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mode: str,
) -> None:
    """``loom enrich --project-dir`` must name the document the project SBOM
    has: both skip the same file, so the Merkle root and doc UUID agree."""
    project = _project(tmp_path)
    readable = enrich_base_namespace(project, tmp_path / "model")

    with (
        deny(project / _SECRET, mode, monkeypatch),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        sbom_json = generate_project_sbom(project, offline=True)
        caplog.clear()
        namespace = enrich_base_namespace(project, tmp_path / "model")

    assert namespace == sbom_namespace(sbom_json)
    # Not vacuous: the skipped file changes the identity.
    assert namespace != readable
    about_secret = [r for r in caplog.records if _SECRET in r.getMessage()]
    assert len(about_secret) == 1


_LOCKED_DIR = "demo/locked"


def _dir_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith("DIR=")
    ]


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX permissions, non-root")
@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_unlistable_dir_is_skipped_with_one_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    surface: str,
) -> None:
    project = _project(tmp_path)
    (tmp_path / "out").mkdir()
    with (
        unlistable(project / _LOCKED_DIR),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        files = _files(_SURFACES[surface](project, tmp_path / "out", monkeypatch))

    _assert_readable_scanned(files)
    assert _SECRET not in files
    (message,) = _dir_warnings(caplog)
    assert message.startswith(f"DIR={_LOCKED_DIR}: could not list")


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX permissions, non-root")
def test_enrich_identity_matches_the_sbom_with_an_unlistable_dir(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path)
    readable = enrich_base_namespace(project, tmp_path / "model")
    with (
        unlistable(project / _LOCKED_DIR),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        sbom_json = generate_project_sbom(project, offline=True)
        caplog.clear()
        namespace = enrich_base_namespace(project, tmp_path / "model")
    assert namespace == sbom_namespace(sbom_json)
    # Not vacuous: the unlisted file changes the identity.
    assert namespace != readable
    assert len(_dir_warnings(caplog)) == 1
