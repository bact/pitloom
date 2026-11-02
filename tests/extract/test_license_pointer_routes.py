# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Git LFS pointer named as the project's licence file is no licence text,
on every route that reads one: the CLI, the library, the Hatchling hook, an
sdist and a wheel. The file's name never stands in for it either.

A file that is not a whole pointer (empty, a look-alike that only opens like
one, a malformed one) is read as the file says.

See also: tests/extract/test_license_detect_lfs.py (the readers' own cases);
tests/extract/project/test_pyproject_license.py (the table reader).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.assemble._generators_wheel import generate_wheel_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.extract._license import stated_license
from tests._lfs import lfs_pointer_bytes
from tests._raw_archive import write_raw_tar, write_raw_zip
from tests.extract.conftest import make_hook, staged_sbom

_OPENING = b"version https://git-lfs.github.com/spec/v1\n"
_REAL = b"Acme custom terms: do as you please.\n"
#: The licence file, by kind; ``None`` is a file that does not exist.
_KINDS: dict[str, bytes | None] = {
    "pointer": lfs_pointer_bytes(_REAL, eol="\n"),
    "empty": b"",
    "missing": None,
    "real": _REAL,
    "look-alike": _OPENING + b"x" * 1024,
    "malformed": _OPENING + b"oid sha256:00\n",
}
#: The kinds read as the file says (a text element carries the file's text).
_READ = ("real", "look-alike", "malformed")
_PYPROJECT = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    '[project]\nname = "tiny"\nversion = "1.0"\nlicense = {file = "LICENSE"}\n'
    '[tool.hatch.build.targets.wheel]\npackages = ["tiny"]\n'
)
_PKG_INFO = b"Metadata-Version: 2.1\nName: tiny\nVersion: 1.0\n"
_DATE = "2026-01-01T00:00:00Z"


def _project(root: Path, data: bytes | None) -> Path:
    (root / "tiny").mkdir(parents=True)
    (root / "tiny" / "__init__.py").write_bytes(b"x = 1\n")
    (root / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    if data is not None:
        (root / "LICENSE").write_bytes(data)
    return root


def _cli(tmp_path: Path, data: bytes | None, monkeypatch: pytest.MonkeyPatch) -> str:
    root, out = _project(tmp_path / "p", data), tmp_path / "out.json"
    argv = ["loom", "project", str(root), "-o", str(out), "--offline"]
    monkeypatch.setattr(sys, "argv", [*argv, "--creation-datetime", _DATE])
    if main() != 0:
        raise ValueError("loom project failed")
    return out.read_text(encoding="utf-8")


def _library(tmp_path: Path, data: bytes | None, _mp: pytest.MonkeyPatch) -> str:
    return generate_project_sbom(
        _project(tmp_path / "p", data),
        creation_metadata=CreationMetadata(),
        offline=True,
    )


def _hook(tmp_path: Path, data: bytes | None, _mp: pytest.MonkeyPatch) -> str:
    root = _project(tmp_path / "p", data)
    hook = make_hook(str(root), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    try:
        staged = staged_sbom(build_data)
        assert staged is not None
        return staged.read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")


def _sdist(tmp_path: Path, data: bytes | None, _mp: pytest.MonkeyPatch) -> str:
    """An sdist with no ``PKG-INFO``, so its ``pyproject.toml`` is read."""
    members = {
        "tiny-1.0/pyproject.toml": _PYPROJECT.encode(),
        "tiny-1.0/tiny/__init__.py": b"x = 1\n",
        "tiny-1.0/setup.py": b"",
    }
    if data is not None:
        members["tiny-1.0/LICENSE"] = data
    path = write_raw_tar(tmp_path / "tiny-1.0.tar.gz", members)
    return generate_project_sbom(
        path, creation_metadata=CreationMetadata(), offline=True
    )


def _wheel(tmp_path: Path, data: bytes | None, _mp: pytest.MonkeyPatch) -> str:
    info = "tiny-1.0.dist-info/"
    members = {
        "tiny/__init__.py": b"x = 1\n",
        f"{info}METADATA": _PKG_INFO,
        f"{info}WHEEL": b"Wheel-Version: 1.0\n",
        f"{info}RECORD": b"",
    }
    if data is not None:
        members[f"{info}licenses/LICENSE"] = data
    path = write_raw_zip(tmp_path / "tiny-1.0-py3-none-any.whl", members)
    return generate_wheel_sbom(path, creation_metadata=CreationMetadata(), offline=True)


_Route = Callable[[Path, "bytes | None", pytest.MonkeyPatch], str]
_ROUTES: dict[str, _Route] = {
    "cli": _cli,
    "library": _library,
    "hook": _hook,
    "sdist": _sdist,
    "wheel": _wheel,
}
#: A directory whose ``pyproject.toml`` names a missing file fails the parse
#: (``pyproject-metadata``); the hook, an sdist and a wheel state no licence.
_MISSING_FAILS = ("cli", "library")


def _licence_texts(sbom: str) -> tuple[list[str], list[dict[str, Any]]]:
    """The text of each ``simplelicensing_*`` element, and the
    ``hasDeclaredLicense`` relationships, of *sbom*."""
    graph = json.loads(sbom)["@graph"]
    elements = [e for e in graph if e.get("type", "").startswith("simplelicensing_")]
    relationships = [
        e for e in graph if e.get("relationshipType") == "hasDeclaredLicense"
    ]
    return [e.get("simplelicensing_licenseText", "") for e in elements], relationships


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("route", _ROUTES)
def test_a_pointer_licence_file_is_no_licence_text_on_any_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str, kind: str
) -> None:
    data = _KINDS[kind]
    if kind == "missing" and route in _MISSING_FAILS:
        with pytest.raises(ValueError):
            _ROUTES[route](tmp_path, data, monkeypatch)
        return
    texts, relationships = _licence_texts(_ROUTES[route](tmp_path, data, monkeypatch))
    # Only a project reads its own licence file: a wheel states what its
    # METADATA does (nothing here), whatever its licence member holds.
    if kind in _READ and route != "wheel":
        assert data is not None
        assert [t.strip() for t in texts] == [data.decode().strip()]
        assert relationships
    else:
        assert texts == [] and relationships == []
    # Whatever the file held, its name is not a licence text.
    assert "LICENSE" not in texts


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        pytest.param(_KINDS["pointer"], None, id="pointer"),
        pytest.param(lfs_pointer_bytes(_REAL, eol="\r\n"), None, id="pointer-crlf"),
        pytest.param(_KINDS["look-alike"], "look-alike", id="look-alike"),
        pytest.param(_KINDS["malformed"], "malformed", id="malformed"),
        pytest.param(_REAL, "real", id="real"),
        pytest.param(b"  \n", None, id="blank"),
    ],
)
def test_stated_license_refuses_a_whole_pointer(
    hint: bytes | None, expected: str | None
) -> None:
    """The one helper every route states a licence through: a hint that is a
    whole pointer (a build backend read the unpulled file) states nothing;
    any other text is kept as written."""
    assert hint is not None
    text = hint.decode()
    assert stated_license(text, "Source: x") == (
        (None, None) if expected is None else (text, None)
    )
