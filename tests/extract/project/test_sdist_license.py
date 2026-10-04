# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``read_sdist`` reads the project's own licence files as a directory
does: the root-level members of ``PKG-INFO``'s top directory only, one name
per case variant, each regular member up to the cap; and, with no
``PKG-INFO``, ``project.license`` and its classifiers from
``pyproject.toml``.

See also: tests/assemble/test_license_sdist_parity.py (every surface, one
value), tests/extract/project/test_sdist_member_names.py (member names).
"""

from __future__ import annotations

import io
import itertools
import logging
import tarfile
from pathlib import Path

import pytest

from pitloom.assemble.spdx3.provenance import (
    is_license_concluded,
    parse_provenance_value,
)
from pitloom.core.project import ProjectMetadata
from pitloom.extract._license_detect import LICENSE_FILE_MAX_BYTES
from pitloom.extract.project.pyproject import read_pyproject
from pitloom.extract.project.sdist import read_sdist
from tests._raw_archive import write_raw_tar, write_raw_zip
from tests.warning_helpers import logged_warnings

_TOP = "demo-1.0.0"
_PKG_INFO = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
_KINDS = ["tar", "zip"]


def _sdist(tmp: Path, members: dict[str, bytes], kind: str = "tar") -> Path:
    """An sdist of *members* (raw names, in this order)."""
    if kind == "zip":
        return write_raw_zip(tmp / f"{_TOP}.zip", members)
    return write_raw_tar(tmp / f"{_TOP}.tar.gz", members)


def _read(tmp: Path, members: dict[str, bytes], kind: str = "tar") -> ProjectMetadata:
    """The metadata of a silent ``PKG-INFO`` followed by *members*, names
    under the project's top directory."""
    raw = {f"{_TOP}/PKG-INFO": _PKG_INFO}
    raw.update({f"{_TOP}/{name}": data for name, data in members.items()})
    return read_sdist(_sdist(tmp, raw, kind), read_config=False).metadata


_CASE_VARIANTS = {"License": b"Apache-2.0\n", "license": b"MIT\n"}


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(
    ("names", "expected"),
    [
        *[(order, "Apache-2.0") for order in itertools.permutations(_CASE_VARIANTS)],
        *[
            (order, "BSD-3-Clause")
            for order in itertools.permutations([*_CASE_VARIANTS, "LICENSE"])
        ],
    ],
)
def test_one_name_per_case_variant_whatever_the_archive_order(
    tmp_path: Path, kind: str, names: tuple[str, ...], expected: str
) -> None:
    """The exact candidate spelling wins, else the first in ``str`` order."""
    data = {**_CASE_VARIANTS, "LICENSE": b"BSD-3-Clause\n"}
    metadata = _read(tmp_path, {name: data[name] for name in names}, kind)
    assert (metadata.license_name or "").strip() == expected


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f"{_TOP}/docs/LICENSE", None),
        ("other-1.0/LICENSE", None),
        ("LICENSE", None),
        (f"{_TOP}/../LICENSE", None),
        (f"/{_TOP}/LICENSE", None),
        (f"C:/{_TOP}/LICENSE", None),
        (f"C:{_TOP}/LICENSE", None),
        # Non-conforming but safe: the root member under its install name.
        (f"{_TOP}\\LICENSE", "Apache-2.0"),
        (f"./{_TOP}/LICENSE", "Apache-2.0"),
    ],
    ids=["nested", "other-top", "archive-root", "dotdot", "abs", "drive", "drive-rel"]
    + ["backslash", "dot-prefix"],
)
def test_only_the_project_roots_licence_files_are_read(
    tmp_path: Path, kind: str, raw: str, expected: str | None
) -> None:
    members = {f"{_TOP}/PKG-INFO": _PKG_INFO, raw: b"Apache-2.0\n"}
    metadata = read_sdist(_sdist(tmp_path, members, kind), read_config=False).metadata
    assert ((metadata.license_name or "").strip() or None) == expected


@pytest.mark.parametrize("kind", _KINDS)
def test_the_top_directory_is_the_first_pkg_info_s(tmp_path: Path, kind: str) -> None:
    """Two top directories: ``PKG-INFO`` and its licence come from the
    first in archive order, never a mix (the other's exact ``LICENSE``
    spelling does not hide this one's ``License``); an earlier
    ``pyproject.toml`` elsewhere does not choose it."""
    members = {
        "src-0/pyproject.toml": b"",
        "src-0/LICENSE": b"BSD-3-Clause\n",
        "other-1.0/PKG-INFO": _PKG_INFO,
        "other-1.0/License": b"MIT\n",
        f"{_TOP}/PKG-INFO": _PKG_INFO,
        f"{_TOP}/LICENSE": b"Apache-2.0\n",
    }
    metadata = read_sdist(_sdist(tmp_path, members, kind), read_config=False).metadata
    assert (metadata.license_name or "").strip() == "MIT"


@pytest.mark.parametrize(
    "link", [tarfile.SYMTYPE, tarfile.LNKTYPE], ids=["sym", "hard"]
)
def test_a_licence_link_member_is_not_read(tmp_path: Path, link: bytes) -> None:
    path = tmp_path / f"{_TOP}.tar.gz"
    with tarfile.open(path, "w:gz") as tf:
        for name, data in (
            (f"{_TOP}/PKG-INFO", _PKG_INFO),
            (f"{_TOP}/docs/LIC", b"Apache-2.0\n"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        info = tarfile.TarInfo(f"{_TOP}/LICENSE")
        info.type = link
        info.linkname = f"{_TOP}/docs/LIC" if link == tarfile.LNKTYPE else "docs/LIC"
        tf.addfile(info)
    assert read_sdist(path, read_config=False).metadata.license_name is None


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("over", [0, 1], ids=["at-cap", "over-cap"])
def test_a_licence_member_over_the_cap_is_skipped_with_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, kind: str, over: int
) -> None:
    data = b"Apache-2.0\n".ljust(LICENSE_FILE_MAX_BYTES + over, b" ")
    with caplog.at_level(logging.WARNING):
        metadata = _read(tmp_path, {"LICENSE": data}, kind)
    warned = [w for w in logged_warnings(caplog) if f"{_TOP}/LICENSE" in w]
    if over:
        assert metadata.license_name is None
        assert len(warned) == 1 and str(LICENSE_FILE_MAX_BYTES) in warned[0]
    else:
        assert (metadata.license_name or "").strip() == "Apache-2.0"
        assert not warned


@pytest.mark.parametrize(
    ("members", "expected", "source"),
    [
        ({"LICENSE": b""}, None, None),
        ({"LICENSE": b" \n\t\n"}, None, None),
        ({"LICENSE": b"", "LICENSE.txt": b"MIT\n"}, "MIT", "LICENSE.txt"),
        (
            {"CITATION.cff": b"license: MIT\n", "LICENSE": b"Apache-2.0\n"},
            "MIT",
            "CITATION.cff",
        ),
        (
            {"codemeta.json": b'{"license": "https://spdx.org/licenses/MIT"}'},
            "MIT",
            "codemeta.json",
        ),
        ({"codemeta.json": b"[]", "LICENSE": b"Apache-2.0\n"}, "Apache-2.0", "LICENSE"),
        ({"CITATION.cff": b"license: \xff\n", "LICENSE": b"MIT\n"}, "MIT", "LICENSE"),
    ],
    ids=["empty", "blank", "empty-then-txt", "cff", "codemeta", "codemeta-array"]
    + ["cff-not-utf8"],
)
def test_licence_sources_as_a_directory_reads_them(
    tmp_path: Path,
    members: dict[str, bytes],
    expected: str | None,
    source: str | None,
) -> None:
    """Declared from the first source that gives a licence; the provenance
    names the member and the archive, and is the project's own statement."""
    metadata = _read(tmp_path, members)
    assert ((metadata.license_name or "").strip() or None) == expected
    provenance = metadata.provenance.get("license")
    if source is None:
        assert provenance is None
        return
    assert provenance is not None
    entry = parse_provenance_value(provenance)
    assert entry["source"] == source and entry["file"] == f"{_TOP}.tar.gz"
    assert not is_license_concluded(entry)


def test_a_stated_licence_gets_the_files_as_concluded(tmp_path: Path) -> None:
    pkg_info = _PKG_INFO + b"License-Expression: MIT\n"
    members = {f"{_TOP}/PKG-INFO": pkg_info, f"{_TOP}/LICENSE": b"Apache-2.0\n"}
    metadata = read_sdist(_sdist(tmp_path, members), read_config=False).metadata
    assert metadata.license_name == "MIT"
    assert (metadata.license_concluded or "").strip() == "Apache-2.0"
    concluded = parse_provenance_value(metadata.provenance["license_concluded"])
    assert concluded["source"] == "LICENSE"


_MIT_LATIN1 = (
    "MIT License\n\nCopyright \xa9 2026 Ren\xe9\n\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy "
    'of this software and associated documentation files (the "Software"), to '
    "deal in the Software without restriction, including without limitation the "
    "rights to use, copy, modify, merge, publish, distribute, sublicense, and/or "
    "sell copies of the Software, and to permit persons to whom the Software is "
    "furnished to do so, subject to the following conditions:\n\n"
    "The above copyright notice and this permission notice shall be included in "
    "all copies or substantial portions of the Software.\n\n"
    'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR '
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, "
    "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE "
    "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER "
    "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING "
    "FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER "
    "DEALINGS IN THE SOFTWARE.\n"
).encode("latin-1")


def _dir_and_sdist(
    tmp_path: Path, tail: str, members: dict[str, bytes]
) -> tuple[ProjectMetadata, ProjectMetadata]:
    """The same project, as a directory and as an sdist with no PKG-INFO."""
    pyproject = f'[project]\nname = "demo"\nversion = "1.0.0"\n{tail}'.encode()
    root = tmp_path / "d"
    root.mkdir()
    for name, data in {"pyproject.toml": pyproject, **members}.items():
        (root / name).write_bytes(data)
    raw = {
        f"{_TOP}/{n}": d for n, d in {"pyproject.toml": pyproject, **members}.items()
    }
    sdist = read_sdist(_sdist(tmp_path, raw), read_config=False).metadata
    return read_pyproject(root / "pyproject.toml")[0], sdist


_MIT_CLASSIFIER = '"License :: OSI Approved :: MIT License"'


def _without_file(provenance: str | None) -> str | None:
    if provenance is None:
        return None
    return " | ".join(p for p in provenance.split(" | ") if not p.startswith("File:"))


@pytest.mark.parametrize(
    ("tail", "members"),
    [
        ('license = "MIT"\n', {"LICENSE": b"Apache-2.0\n"}),
        ('license = {text = "Apache-2.0"}\n', {}),
        ('license = {file = "LICENSE"}\n', {"LICENSE": b"BSD-3-Clause\n"}),
        (f"classifiers = [{_MIT_CLASSIFIER}]\n", {}),
        (f'license = "UNKNOWN"\nclassifiers = [{_MIT_CLASSIFIER}]\n', {}),
        ('license = ""\n', {"LICENSE": b"Apache-2.0\n"}),
        ("", {"LICENSE": _MIT_LATIN1}),
    ],
    ids=["string", "text", "file", "classifier", "weak", "blank", "not-utf8"],
)
def test_no_pkg_info_reads_the_licence_as_the_directory(
    tmp_path: Path, tail: str, members: dict[str, bytes]
) -> None:
    """With no ``PKG-INFO``, ``pyproject.toml``'s licence and the licence
    files give what the unpacked directory gives."""
    directory, sdist = _dir_and_sdist(tmp_path, tail, members)
    for field in ("license_name", "license_concluded"):
        assert getattr(sdist, field) == getattr(directory, field), field
    # The same provenance, the sdist's naming the archive too.
    assert _without_file(sdist.provenance.get("license")) == (
        directory.provenance.get("license")
    )
    assert directory.license_name or not tail


@pytest.mark.parametrize(
    "tail",
    [
        "license = 3\n",
        'license = {text = "MIT", file = "LICENSE"}\n',
        "license = {}\n",
        'license = {file = "NOT-THERE"}\n',
        "classifiers = 3\n",
    ],
    ids=["int", "both", "empty-table", "missing-file", "classifiers-int"],
)
def test_no_pkg_info_an_unusable_licence_field_states_nothing(
    tmp_path: Path, tail: str
) -> None:
    pyproject = f'[project]\nname = "demo"\nversion = "1.0.0"\n{tail}'.encode()
    members = {f"{_TOP}/pyproject.toml": pyproject, f"{_TOP}/LICENSE": b"MIT\n"}
    metadata = read_sdist(_sdist(tmp_path, members), read_config=False).metadata
    # Silent: the LICENSE file is the declared licence.
    assert (metadata.license_name or "").strip() == "MIT"
    assert metadata.license_concluded is None
