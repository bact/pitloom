# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A project declaring no ``build-backend``: setuptools' file list, everywhere.

PEP 517 has a build frontend build such a project with
``setuptools.build_meta:__legacy__``, so its SBOM must list the files of
the wheel that backend builds (setuptools auto-discovery and
``[tool.setuptools]`` config), with no Hatchling fallback ``WARNING:``.
The ground truth is a real, offline build of a copy of each project.

Every surface scanning a project directory goes through
``get_wheel_files()``; the Hatchling build hook names its backend and is
not affected.

Setuptools' own deprecation banners on the target project's legacy
licence metadata, and its manifest step's ``warning: no files found
matching`` lines, are ``DEBUG`` lines, never untagged stderr.

See also: tests/extract/project/test_setuptools_cfg_backend.py
(``detect_build_backend()``),
tests/core/models_wheel/test_models_wheel_setuptools.py (the discoverer).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

import pitloom
from pitloom.assemble import generate, generate_project_sbom
from pitloom.embed import embed_wheel_sbom
from tests._setuptools_build import run_build
from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import run_cli

_BUILD = "import sys, setuptools.build_meta as b; b.__legacy__.build_wheel(sys.argv[1])"
_PROJECT = '[project]\nname = "demo"\nversion = "1.0.0"\n'
_REQUIRES = '[build-system]\nrequires = ["setuptools"]\n'
_FLAT = {
    "demo/__init__.py": "",
    "demo/a.py": "",
    "demo/data.txt": "x",
    "tests/test_demo.py": "",
    "docs/conf.py": "",
}
_SRC = {f"src/{name}": text for name, text in _FLAT.items() if name[:4] == "demo"}
_NAMESPACE = {
    "pyproject.toml": _PROJECT + '[tool.setuptools.packages.find]\nwhere = ["src"]\n',
    "src/ns/demo/__init__.py": "",
    "src/ns/demo/a.py": "",
}
_CASES: dict[str, dict[str, str]] = {
    "flat": {"pyproject.toml": _PROJECT, **_FLAT},
    "src": {"pyproject.toml": _PROJECT, **_SRC},
    "empty-table": {"pyproject.toml": "[build-system]\n" + _PROJECT, **_FLAT},
    "package-data": {
        "pyproject.toml": _REQUIRES
        + _PROJECT
        + '[tool.setuptools.package-data]\ndemo = ["*.txt"]\n',
        **_SRC,
    },
    "namespace": _NAMESPACE,
    "module": {"pyproject.toml": _PROJECT, "demo.py": "", "tests/test_demo.py": ""},
    "no-metadata": {"pyproject.toml": _REQUIRES, **_FLAT},
    "setup-py": {
        "setup.py": 'from setuptools import setup\nsetup(name="demo")\n',
        **_FLAT,
    },
}


def _project(tmp_path: Path, case: str) -> Path:
    root = tmp_path / "proj"
    for name, text in _CASES[case].items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _built_files(project: Path, tmp_path: Path) -> set[str]:
    """The payload of the wheel setuptools' legacy backend builds from a
    copy of *project* (building writes ``*.egg-info`` into it)."""
    copy = shutil.copytree(project, tmp_path / "copy")
    out = tmp_path / "wheel"
    out.mkdir()
    run_build(["-c", _BUILD, str(out)], cwd=copy)
    (wheel,) = out.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        return {n for n in archive.namelist() if ".dist-info/" not in n}


def _files(sbom_json: str) -> set[str]:
    return {
        str(element["name"])
        for element in json.loads(sbom_json)["@graph"]
        if element.get("type") == "software_File"
        and element.get("software_fileKind") == "file"
    }


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("case", sorted(_CASES))
def test_file_list_matches_the_legacy_backend_wheel(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, case: str
) -> None:
    project = _project(tmp_path, case)
    built = _built_files(project, tmp_path)
    assert built  # Not vacuous: the build packaged something.

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        listed = _files(generate_project_sbom(project, offline=True))

    assert listed == built
    assert not _warnings(caplog)


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


def _lib_generate(project: Path, _tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate(project, offline=True)


def _lib_embed_wheel_sbom(project: Path, tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    wheel = _make_dummy_wheel(tmp / "dist", "demo", "1.0.0")
    return _wheel_sbom(embed_wheel_sbom(wheel, project_dir=project)[0])


_SURFACES: dict[str, Callable[[Path, Path, pytest.MonkeyPatch], str]] = {
    "cli-project": _cli_project,
    "cli-generate": _cli_generate,
    "cli-embed-wheel": _cli_embed_wheel,
    "lib-generate": _lib_generate,
    "lib-embed_wheel_sbom": _lib_embed_wheel_sbom,
}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_every_surface_reads_setuptools_files_quietly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    surface: str,
) -> None:
    """The namespace layout, which Hatchling's heuristic cannot find."""
    project = _project(tmp_path, "namespace")
    (tmp_path / "out").mkdir()

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        listed = _files(_SURFACES[surface](project, tmp_path / "out", monkeypatch))

    assert not _warnings(caplog)
    if "embed" not in surface:  # An embed lists the wheel's own files.
        assert listed == {"ns/demo/__init__.py", "ns/demo/a.py"}


_LEGACY_LICENCE = (
    '[project]\nname = "demo"\nversion = "1.0"\nlicense = {text = "MIT"}\n'
    'classifiers = ["License :: OSI Approved :: MIT License"]\n'
)
_TAGS = ("ERROR: ", "WARNING: ", "INFO: ", "DEBUG: ")


def _stderr_lines(argv: list[str], cwd: Path, *, debug: bool = False) -> list[str]:
    """Run ``python <argv>`` with the Pitloom under test, ``PITLOOM_DEBUG``
    set by *debug*; its stderr lines, decoded strictly (no lossy replacement
    hides a stray byte)."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONWARNINGS"}
    env["PITLOOM_DEBUG"] = "1" if debug else "0"
    # The pitloom under test, not whichever one the interpreter installs.
    source = str(Path(pitloom.__file__).parents[1])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [source, env.get("PYTHONPATH")]))
    result = subprocess.run(  # nosec B603
        [sys.executable, *argv],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        timeout=300,
    )
    return result.stderr.decode("utf-8").splitlines()


@pytest.mark.parametrize(
    "build_system",
    ["", '[build-system]\nbuild-backend = "setuptools.build_meta"\n'],
    ids=["no-backend", "setuptools-backend"],
)
def test_setuptools_banners_are_debug_lines(tmp_path: Path, build_system: str) -> None:
    """Setuptools' multi-line ``SetuptoolsDeprecationWarning`` banners (a
    ``project.license`` table, a ``License ::`` classifier) never reach stderr
    untagged. A real ``loom --debug project`` process (no pytest warning
    filter): every stderr line is tagged, each banner one ``DEBUG:`` line."""
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    pyproject = build_system + _LEGACY_LICENCE
    (project / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    argv = ["-m", "pitloom", "--debug", "project", str(project), "--offline"]
    lines = _stderr_lines([*argv, "-o", "out.json"], tmp_path)
    assert [line for line in lines if not line.startswith(_TAGS)] == []
    banners = [line for line in lines if "SetuptoolsDeprecationWarning: " in line]
    assert len(banners) == 2
    assert all(line.startswith("DEBUG: ") for line in banners)
    assert "`project.license` as a TOML table" in banners[0]


_LIB = "import sys; from pathlib import Path; from {0} import {1} as f; "
_MANIFEST_SURFACES: dict[str, list[str]] = {
    "cli-project": ["-m", "pitloom", "project", "{p}", "--offline", "-o", "o.json"],
    "cli-allow-build": [
        "-m",
        "pitloom",
        "project",
        "{p}",
        "--offline",
        "--allow-build",
        "--no-build-isolation",
        "-o",
        "o.json",
    ],
    "cli-embed-wheel": ["-m", "pitloom", "embed-wheel", "{w}", "--project-dir", "{p}"],
    "lib-generate": [
        "-c",
        _LIB.format("pitloom.assemble", "generate") + "f(sys.argv[1], offline=True)",
        "{p}",
    ],
    "lib-embed_wheel_sbom": [
        "-c",
        _LIB.format("pitloom.embed", "embed_wheel_sbom")
        + "f(sys.argv[2], project_dir=sys.argv[1])",
        "{p}",
        "{w}",
    ],
}
_MANIFEST_WARNINGS = (
    "warning: no files found matching '*.js'",
    "warning: no files found matching '*.css' under directory 'doc'",
    "warning: no previously-included files found matching 'gone.txt'",
    "no previously-included directories found matching 'nodir'",
)


@pytest.mark.parametrize(
    ("surface", "debug"),
    [*((name, True) for name in sorted(_MANIFEST_SURFACES)), ("cli-project", False)],
)
def test_manifest_step_lines_are_debug_lines(
    tmp_path: Path, surface: str, debug: bool
) -> None:
    """``MANIFEST.in`` patterns matching nothing make setuptools' manifest
    step (``include_package_data``) write bare ``warning: ...`` lines on
    stderr. Every surface that discovers a setuptools project's files,
    ``--allow-build`` included, relays each as one ``DEBUG:`` line, the text
    kept; without ``--debug`` stderr holds none of them."""
    project = tmp_path / "proj"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "src" / "demo" / "__init__.py").write_bytes(b"")
    (project / "pyproject.toml").write_bytes(
        (
            _REQUIRES
            + 'build-backend = "setuptools.build_meta"\n'
            + _PROJECT
            + '[tool.setuptools.packages.find]\nwhere = ["src"]\n'
        ).encode("utf-8")
    )
    manifest = b"include *.js\nrecursive-include doc *.css\nexclude gone.txt\n"
    (project / "MANIFEST.in").write_bytes(manifest + b"prune nodir\n")
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    argv = [arg.format(p=project, w=wheel) for arg in _MANIFEST_SURFACES[surface]]

    lines = _stderr_lines(argv, tmp_path, debug=debug)

    assert [line for line in lines if not line.startswith(_TAGS)] == []
    relayed = [line for line in lines if "setuptools stderr: " in line]
    if not debug:
        assert relayed == []
        return
    assert all(line.startswith("DEBUG: ") for line in relayed)
    assert sorted(line.split("setuptools stderr: ", 1)[1] for line in relayed) == (
        sorted(_MANIFEST_WARNINGS)
    )
