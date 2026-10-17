# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The main package's ``copyrightText`` on every route: directory, sdist,
bare wheel (PEP 639 ``licenses/`` and an older wheel's ``.dist-info``
root), ``embed-wheel --project-dir`` (CLI and library) and the Hatchling
build hook.

Each gives the notices found in the project's own licence files, the same
text from the same files, else ``NOASSERTION`` with no provenance; never
text made from the authors.

See also: tests/extract/test_copyright_notices.py (what a notice line is),
tests/test_author_surfaces.py (the same routes for the authors).
"""

# pylint: disable=missing-function-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

from __future__ import annotations

import json
import os
import shutil
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.embed import embed_wheel_sbom
from pitloom.extract._license_detect import LICENSE_FILE_MAX_BYTES
from pitloom.extract.project.reader import read_project
from tests._author_routes import CREATED, hook_sbom, isolate, write_wheel
from tests._spdx3_validate import assert_spdx3_valid
from tests.assemble.conftest import _make_sdist

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"
authors = [{name = "Ann", email = "ann@example.com"}]
"""
_METADATA = (
    "Metadata-Version: 2.4\nName: demo\nVersion: 1.0.0\n"
    "Author-email: Ann <ann@example.com>\n"
)
_BSD = (
    "BSD 3-Clause License\n\nCopyright (c) 2019, Brett Cannon\n"
    "All rights reserved.\n\nRedistributions of source code must retain the "
    "above copyright notice.\nTHIS SOFTWARE IS PROVIDED BY THE COPYRIGHT "
    'HOLDERS AND CONTRIBUTORS "AS IS"\n'
)
_APACHE_TEMPLATE = "Apache License\n\n   Copyright [yyyy] [name of copyright owner]\n"
_OVER_CAP = "Copyright (c) 2024 Big\n" + "x" * LICENSE_FILE_MAX_BYTES

#: case -> (licence files, copyrightText, the files its provenance names)
_CASES: dict[str, tuple[dict[str, str], str, str | None]] = {
    "single": ({"LICENSE": _BSD}, "Copyright (c) 2019, Brett Cannon", "LICENSE"),
    "several": (
        {
            "COPYING": "Copyright \u00a9 2020-2024 Bob\r\nCopyright (c) 2019 Ann\r\n",
            "LICENSE.txt": "\ufeffCopyright (c) 2019 Ann\n",
        },
        "Copyright (c) 2019 Ann\nCopyright \u00a9 2020-2024 Bob",
        "LICENSE.txt, COPYING",
    ),
    "none": ({}, "NOASSERTION", None),
    "template-only": ({"LICENSE": _APACHE_TEMPLATE}, "NOASSERTION", None),
    "over-cap": ({"LICENSE": _OVER_CAP}, "NOASSERTION", None),
}

#: Builds a route's SBOM from the project's licence files; the archive
#: its provenance names (``| File:``), if any.
_Route = Callable[[Path, pytest.MonkeyPatch, dict[str, bytes]], str]


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


def _project(tmp_path: Path, files: dict[str, bytes]) -> Path:
    project = tmp_path / "demo"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    for name, data in files.items():
        (project / name).write_bytes(data)
    return project


def _wheel(tmp_path: Path, files: dict[str, bytes], folder: str) -> Path:
    licences = {f"{folder}{name}": data for name, data in files.items()}
    return write_wheel(tmp_path, _METADATA, "1.0.0", licences)


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


def _directory(tmp_path: Path, _mp: pytest.MonkeyPatch, files: dict[str, bytes]) -> str:
    return generate_project_sbom(
        _project(tmp_path, files), creation_metadata=CREATED, offline=True
    )


def _sdist(tmp_path: Path, _mp: pytest.MonkeyPatch, files: dict[str, bytes]) -> str:
    sdist = _make_sdist(tmp_path, members=dict(files))
    return generate_project_sbom(sdist, creation_metadata=CREATED, offline=True)


def _bare_wheel(folder: str) -> _Route:
    def run(tmp_path: Path, _mp: pytest.MonkeyPatch, files: dict[str, bytes]) -> str:
        wheel = _wheel(tmp_path, files, folder)
        return generate_wheel_sbom(wheel, creation_metadata=CREATED)

    return run


def _cli_embed(tmp_path: Path, mp: pytest.MonkeyPatch, files: dict[str, bytes]) -> str:
    wheel = _wheel(tmp_path, files, "licenses/")
    project = _project(tmp_path, files)
    mp.setattr(
        sys, "argv", ["loom", "embed-wheel", str(wheel), "--project-dir", str(project)]
    )
    assert __main__.main() == 0
    return _embedded(wheel)


def _lib_embed(tmp_path: Path, _mp: pytest.MonkeyPatch, files: dict[str, bytes]) -> str:
    wheel = embed_wheel_sbom(
        _wheel(tmp_path, files, "licenses/"),
        project_dir=_project(tmp_path, files),
        creation_metadata=CREATED,
    )[0]
    return _embedded(wheel)


def _hook(tmp_path: Path, _mp: pytest.MonkeyPatch, files: dict[str, bytes]) -> str:
    return hook_sbom(_project(tmp_path, files))


_WHEEL = " | File: demo-1.0.0-py3-none-any.whl"
#: route -> (build the SBOM, the ``| File:`` part of its provenance)
_ROUTES: dict[str, tuple[_Route, str]] = {
    "directory": (_directory, ""),
    "sdist": (_sdist, " | File: demo-1.0.0.tar.gz"),
    "bare-wheel": (_bare_wheel("licenses/"), _WHEEL),
    "bare-wheel-dist-info-root": (_bare_wheel(""), _WHEEL),
    "cli-embed-wheel-project-dir": (_cli_embed, _WHEEL),
    "lib-embed-wheel-project-dir": (_lib_embed, _WHEEL),
    "hatchling-hook": (_hook, ""),
}


def _main_copyright(sbom: str) -> tuple[str, str | None]:
    """The main package's ``copyrightText`` and its provenance, as
    ``Source: ... | Method: ...``, or ``None``."""
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    main = next(
        e for e in graph if e["type"] == "software_Package" and e["name"] == "demo"
    )
    provenance = None
    for element in graph:
        if element["type"] == "Annotation" and element["subject"] == main["spdxId"]:
            entry = json.loads(element["statement"]).get("fields", {})
            if "copyright_text" in entry:
                found = entry["copyright_text"]
                within = f" | File: {found['file']}" if "file" in found else ""
                provenance = (
                    f"Source: {found['source']}{within} | Method: {found['method']}"
                )
    return main["software_copyrightText"], provenance


@pytest.mark.parametrize("case", sorted(_CASES))
@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_copyright_text_on_every_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    route: str,
    case: str,
) -> None:
    files, text, names = _CASES[case]
    run, within = _ROUTES[route]
    sbom = run(tmp_path, monkeypatch, {n: t.encode("utf-8") for n, t in files.items()})
    method = "copyright_notice_lines"
    provenance = f"Source: {names}{within} | Method: {method}" if names else None
    assert _main_copyright(sbom) == (text, provenance)
    over_cap = "LICENSE: larger than the 262144-byte license-detection cap"
    # The hook route logs unconfigured (caplog), the others on stderr.
    logged = capsys.readouterr().err + caplog.text
    assert (over_cap in logged) is (case == "over-cap")


#: Neither on Windows (no POSIX mode bits) nor as root (reads anyway).
_CANNOT_DENY_READ = sys.platform == "win32" or os.geteuid() == 0


@pytest.mark.skipif(_CANNOT_DENY_READ, reason="needs POSIX permissions, not root")
def test_unreadable_licence_file_is_warned_and_no_assertion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, {"LICENSE": _BSD.encode("utf-8")})
    licence = project / "LICENSE"
    licence.chmod(0)
    try:
        sbom = generate_project_sbom(project, creation_metadata=CREATED, offline=True)
    finally:
        licence.chmod(0o644)
    assert _main_copyright(sbom) == ("NOASSERTION", None)
    err = capsys.readouterr().err.splitlines()
    [warning] = [line for line in err if "LICENSE" in line]
    assert warning.startswith(f"WARNING: FILE={licence}: could not read ")


_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    ("project", "text"),
    [
        (
            "real-world-extras/flit/mousebender-2025.1",
            "Copyright (c) 2019, Brett Cannon",
        ),
        (
            "real-world-extras/hatchling/dparse-0.6.4",
            "Copyright (c) 2017, Jannis Gebauer",
        ),
        (
            "real-world-extras/flit/flit-4.1.0",
            "Copyright (c) 2015, Thomas Kluyver and contributors",
        ),
        (
            "real-world-extras/poetry/cachy-0.3.0",
            "Copyright (c) 2015 Sébastien Eustace",
        ),
        (
            "real-world-extras/setuptools/dinglehopper-0.11.0",
            "Copyright 2019-2025 Staatsbibliothek zu Berlin\u2009\u2014\u2009SPK",
        ),
        ("real-world-extras/flit/etils-1.14.0", None),
    ],
    ids=["mousebender", "dparse", "flit", "cachy", "dinglehopper", "etils"],
)
def test_real_world_licence_notices(
    tmp_path: Path, project: str, text: str | None
) -> None:
    """The notice a real project's licence file holds; an Apache 2.0 text
    with only its appendix template (etils) holds none."""
    copy = shutil.copytree(_FIXTURES / project, tmp_path / "p")
    metadata, _, _ = read_project(
        copy,
        include_locked_dependencies=False,
        include_installed_metadata=False,
        quiet=True,
        read_config=False,
    )
    assert metadata.copyright_text == text


@pytest.mark.parametrize("case", ["single", "none"])
def test_copyright_text_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    files = {n: t.encode("utf-8") for n, t in _CASES[case][0].items()}
    sbom = tmp_path / "sbom.json"
    sbom.write_text(_directory(tmp_path, monkeypatch, files), encoding="utf-8")
    assert_spdx3_valid(sbom)
