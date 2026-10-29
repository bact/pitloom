# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A hostile name or licence text read from a project, a wheel or an sdist
cannot forge a provenance segment.

A provenance string is split on ``|``; a file named ``a | Evidence:
not_measured | Reason: over-cap`` would otherwise add the ``Evidence`` and
``Reason`` keys a merge acts on. Each surface runs once with a benign name
and once with a hostile one over the same content: every provenance entry
keeps the key set the benign run has, and the hostile text is written
escaped (``|`` as ``/``, display controls as ``\\uXXXX``).

The pipe and the line break cannot be in a file name on Windows
(``_POSIX``); the rows that need such a file are skipped there. The rows
that read the text from a file's content or a function argument run
everywhere.

See also: tests/provenance_helpers.py (the readers of the SBOM) and
tests/core/test_provenance_builders.py (the builders).
"""

from __future__ import annotations

import io
import json
import sys
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.core.provenance import ProvenanceConfig, sanitize_provenance_text
from pitloom.extract import _license_resolve
from pitloom.extract._license_classify import tag_license_normalization
from pitloom.extract._license_detect import license_candidates_from_members
from pitloom.extract._license_resolve import DeclaredResolution, resolution_notes
from pitloom.extract.copyright_notices import copyright_from_members
from tests.provenance_helpers import (
    assert_escaped,
    keys_of,
    provenance_shape,
    provenance_texts,
)

#: A pipe or a line break cannot be in a file name on Windows.
_POSIX = sys.platform != "win32"

_PIPE = "a | Evidence: not_measured | Reason: over-cap"
_SEMI = "a; Field: b"
_LINE_BREAK = "a\nb"
_RLO = "a\u202eb"
_FULL = ProvenanceConfig(detail="full")
_FIXED = (1980, 1, 1, 0, 0, 0)
_MIT = (
    b"MIT License\n\nCopyright (c) 2020 Jane Doe\n\n"
    b"Permission is hereby granted, free of charge, to any person obtaining "
    b"a copy of this software.\n"
)
_PKG_INFO = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
_PYPROJECT = '[project]\nname = "demo"\nversion = "1.0.0"\n'


def _rows(*texts: str, file_name: bool = False) -> list[object]:
    """The hostile *texts* as rows: those with a pipe or a line break (and,
    for a *file_name*, a colon) skipped on Windows, which cannot name a file
    so."""
    skip = pytest.mark.skipif(
        not _POSIX, reason="no pipe, colon or newline in a Windows file name"
    )
    return [
        pytest.param(
            text,
            id=name,
            marks=[skip]
            if ("|" in text or "\n" in text or (file_name and ":" in text))
            else [],
        )
        for text, name in ((t, _ID[t]) for t in texts)
    ]


_ID = {_PIPE: "pipe", _SEMI: "semicolon", _LINE_BREAK: "newline", _RLO: "rlo"}
#: A file name; a setup.cfg value cannot hold a line break.
_NAMES = _rows(_PIPE, _SEMI, _LINE_BREAK, _RLO, file_name=True)
_CFG_NAMES = _rows(_PIPE, _SEMI, _RLO)


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(zipfile.ZipInfo(name, _FIXED), data)
    return path


def _toml(text: str) -> str:
    """*text* as a TOML basic string."""
    return json.dumps(text)


def _project(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    for name, content in files.items():
        (root / name).parent.mkdir(exist_ok=True)
        (root / name).write_bytes(content.encode("utf-8"))
    return root


def _from_project(root: Path) -> str:
    return generate_project_sbom(root, offline=True, provenance=_FULL)


# Each surface builds an SBOM with the token in one name or text.


def _wheel(root: Path, token: str) -> str:
    root.mkdir()
    wheel = _zip(
        root / f"demo-1.0.0-py3-none-{token}.whl",
        {
            "demo-1.0.0.dist-info/METADATA": (
                b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
                b"License-File: LICENSE\n"
            ),
            "demo-1.0.0.dist-info/RECORD": b"",
            "demo-1.0.0.dist-info/licenses/LICENSE": _MIT,
            "demo/__init__.py": b"",
        },
    )
    return generate_wheel_sbom(wheel, offline=True, provenance=_FULL)


def _sdist(root: Path, token: str) -> str:
    root.mkdir()
    sdist = _zip(
        root / f"demo-1.0.0-{token}.zip",
        {
            "demo-1.0.0/PKG-INFO": _PKG_INFO,
            "demo-1.0.0/pyproject.toml": _PYPROJECT.encode(),
            "demo-1.0.0/LICENSE": _MIT,
            "demo-1.0.0/demo/__init__.py": b"",
        },
    )
    return generate_project_sbom(sdist, offline=True, provenance=_FULL)


def _sdist_tar(root: Path, token: str) -> str:
    root.mkdir()
    path = root / f"demo-1.0.0-{token}.tar.gz"
    members = {
        "demo-1.0.0/PKG-INFO": _PKG_INFO,
        "demo-1.0.0/LICENSE": _MIT,
        "demo-1.0.0/demo/__init__.py": b"",
    }
    with tarfile.open(path, "w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return generate_project_sbom(path, offline=True, provenance=_FULL)


def _dist_info(root: Path, token: str) -> str:
    # A name-matching in-tree dist-info fills the description the project
    # leaves out.
    _project(
        root,
        {
            "pyproject.toml": _PYPROJECT,
            f"demo_{token}.dist-info/METADATA": (
                "Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\nSummary: Filled\n"
            ),
        },
    )
    return _from_project(root)


def _license_file(root: Path, token: str) -> str:
    # A file with text is read by pyproject-metadata into ``license.text``;
    # an empty one is the file Pitloom names as the source.
    name = f"LIC-{token}.txt"
    _project(
        root,
        {
            "pyproject.toml": f"{_PYPROJECT}license = {{file = {_toml(name)}}}\n",
            name: "",
        },
    )
    return _from_project(root)


def _cfg_file(root: Path, token: str) -> str:
    _project(
        root,
        {
            "setup.cfg": f"[metadata]\nname = demo\nversion = file: VER-{token}\n",
            f"VER-{token}": "1.2.3\n",
        },
    )
    return _from_project(root)


def _cfg_attr(root: Path, token: str) -> str:
    _project(
        root,
        {
            "setup.cfg": (
                f"[metadata]\nname = demo\nversion = attr: m_{token}.VERSION\n"
            ),
            f"m_{token}.py": 'VERSION = "1.2.3"\n',
        },
    )
    return _from_project(root)


def _hatch_version(root: Path, token: str) -> str:
    name = f"v-{token}.py"
    _project(
        root,
        {
            "pyproject.toml": (
                '[project]\nname = "demo"\ndynamic = ["version"]\n'
                f"[tool.hatch.version]\npath = {_toml(name)}\n"
            ),
            name: '__version__ = "1.2.3"\n',
        },
    )
    return _from_project(root)


#: surface -> (builder, a field whose provenance names the token).
_NAME_SURFACES: dict[str, tuple[Callable[[Path, str], str], str]] = {
    "wheel-file": (_wheel, "copyright_text"),
    "sdist-zip": (_sdist, "copyright_text"),
    "sdist-tar": (_sdist_tar, "copyright_text"),
    "dist-info-dir": (_dist_info, "description"),
    "license-file": (_license_file, "license"),
    "hatch-version-path": (_hatch_version, "version"),
}
_CFG_SURFACES: dict[str, tuple[Callable[[Path, str], str], str]] = {
    "cfg-file-directive": (_cfg_file, "version"),
    "cfg-attr-directive": (_cfg_attr, "version"),
}


def _check(
    tmp_path: Path, build: Callable[[Path, str], str], field: str, hostile: str
) -> None:
    benign = build(tmp_path / "benign", "ok")
    sbom = build(tmp_path / "hostile", hostile)
    shape = provenance_shape(benign)
    assert any(entry[1] == field for entry in shape), (field, shape)
    # The hostile run adds no key to any entry, and loses none.
    assert provenance_shape(sbom) == shape
    assert_escaped(provenance_texts(sbom), sanitize_provenance_text(hostile))


@pytest.mark.parametrize("hostile", _NAMES)
@pytest.mark.parametrize("surface", sorted(_NAME_SURFACES))
def test_hostile_file_name_keeps_the_keys(
    tmp_path: Path, surface: str, hostile: str
) -> None:
    build, field = _NAME_SURFACES[surface]
    _check(tmp_path, build, field, hostile)


@pytest.mark.parametrize("hostile", _CFG_NAMES)
@pytest.mark.parametrize("surface", sorted(_CFG_SURFACES))
def test_hostile_setup_cfg_directive_keeps_the_keys(
    tmp_path: Path, surface: str, hostile: str
) -> None:
    build, field = _CFG_SURFACES[surface]
    _check(tmp_path, build, field, hostile)


# Name-free: the text is a function argument or the content of a file.


@pytest.mark.parametrize("hostile", [_PIPE, _SEMI, _LINE_BREAK, _RLO], ids=_ID.get)
def test_hostile_archive_name_in_licence_and_copyright_sources(hostile: str) -> None:
    members = {
        "CITATION.cff": b"license: MIT\n",
        "codemeta.json": b'{"license": "https://spdx.org/licenses/MIT"}',
        "LICENSE": _MIT,
    }

    def sources(archive: str) -> list[str]:
        found = [
            source for _, source in license_candidates_from_members(members, archive)
        ]
        copyright_ = copyright_from_members(members, archive)
        assert copyright_ is not None
        return [*found, copyright_[1]]

    benign = sources("ok")
    hostile_sources = sources(hostile)
    assert len(benign) == 4
    assert keys_of(hostile_sources) == keys_of(benign)
    assert_escaped(hostile_sources, sanitize_provenance_text(hostile))


@pytest.mark.parametrize("hostile", [_PIPE, _SEMI, _LINE_BREAK, _RLO], ids=_ID.get)
def test_hostile_licence_text_in_normalized_from(hostile: str) -> None:
    base = "Source: pyproject.toml | Field: project.license"
    benign = tag_license_normalization(base, "mit", "MIT")
    note = tag_license_normalization(base, f"mit {hostile}", "MIT")
    assert keys_of([note]) == keys_of([benign])
    assert "normalized-from" in keys_of([note])[0]
    assert_escaped([note], sanitize_provenance_text(f"mit {hostile}"))


@pytest.mark.parametrize("hostile", [_PIPE, _SEMI, _LINE_BREAK, _RLO], ids=_ID.get)
def test_hostile_licence_text_in_resolution_keys(
    monkeypatch: pytest.MonkeyPatch, hostile: str
) -> None:
    # The resolver reads only plain spellings, so it is stood in for: the
    # keys are written whatever it answers.
    answer = DeclaredResolution(
        expression="Apache-2.0",
        category="separator",
        steps=("separator", hostile),
        expansions=(hostile,),
    )
    monkeypatch.setattr(_license_resolve, "resolve_value", lambda _value: answer)
    notes = resolution_notes(f"Apache2 {hostile}", "Apache-2.0")
    benign_answer = DeclaredResolution(
        "Apache-2.0", "separator", ("separator",), ("x",)
    )
    monkeypatch.setattr(_license_resolve, "resolve_value", lambda _value: benign_answer)
    benign = resolution_notes("Apache2", "Apache-2.0")
    assert keys_of([f"Source: x{notes}"]) == keys_of([f"Source: x{benign}"])
    assert "resolution-1" in keys_of([f"Source: x{notes}"])[0]
    assert_escaped([notes], sanitize_provenance_text(f"Apache2 {hostile}"))


@pytest.mark.parametrize("hostile", [_PIPE, _SEMI, _LINE_BREAK, _RLO], ids=_ID.get)
def test_hostile_pyproject_licence_string(tmp_path: Path, hostile: str) -> None:
    def build(root: Path, text: str) -> str:
        _project(root, {"pyproject.toml": f"{_PYPROJECT}license = {_toml(text)}\n"})
        return _from_project(root)

    sbom = build(tmp_path / "hostile", f"MIT {hostile}")
    assert provenance_shape(sbom) == provenance_shape(build(tmp_path / "ok", "MIT"))
    assert not any("not_measured" in text for text in provenance_texts(sbom))
