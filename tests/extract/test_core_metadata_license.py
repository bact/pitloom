# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract._core_metadata.core_metadata_license`,
the one licence-header rule shared by the sdist, wheel, installed-project
and installed-dependency readers.
"""

from __future__ import annotations

import email
import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps_installed
from pitloom.assemble.spdx3.deps_installed import _enrich_from_installed
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract._core_metadata import core_metadata_license
from pitloom.extract.project.installed import _parse_installed_metadata
from pitloom.extract.project.sdist import _parse_pkg_info, read_sdist
from pitloom.extract.wheel import _populate_metadata_from_email
from tests.assemble.conftest import _FakeMetadata, _make_ci

_BASE = "Metadata-Version: 2.4\nName: pkg\nVersion: 1.0.0\n"

#: (extra headers, licence every reader must agree on; ``None`` = absent or
#: empty), one case per boundary of the rule.
_CASES = [
    pytest.param("License-Expression: MIT\n", "MIT", id="expression-only"),
    pytest.param(
        "License-Expression: MIT\nLicense: Apache-2.0\n", "MIT", id="expression-wins"
    ),
    pytest.param("License: Apache-2.0\n", "Apache-2.0", id="legacy-only"),
    pytest.param("", None, id="neither"),
    pytest.param("License-Expression: \n", None, id="empty-expression"),
    pytest.param("License: \n", None, id="empty-legacy"),
    pytest.param(
        "License-Expression: \nLicense: Apache-2.0\n",
        "Apache-2.0",
        id="empty-then-legacy",
    ),
]


def _msg(extra: str) -> email.message.Message:
    return email.message_from_string(_BASE + extra)


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ("License-Expression: MIT\n", "MIT"),
        ("License-Expression: MIT\nLicense: Apache-2.0\n", "MIT"),
        ("License: Apache-2.0\n", "Apache-2.0"),
        ("", None),
        ("License-Expression: \n", ""),
        ("License: \n", ""),
        ("License-Expression: \nLicense: Apache-2.0\n", "Apache-2.0"),
    ],
)
def test_core_metadata_license_is_tri_state(extra: str, expected: str | None) -> None:
    """Absent is ``None``; declared-but-empty is ``""``, not ``None``."""
    assert core_metadata_license(_msg(extra)) == expected


@pytest.mark.parametrize(("extra", "expected"), _CASES)
def test_sdist_pkg_info_reads_license_expression(
    extra: str, expected: str | None
) -> None:
    metadata = _parse_pkg_info(_BASE + extra, "Source: PKG-INFO")
    assert metadata.license_name == expected
    assert ("license" in metadata.provenance) is bool(expected)


@pytest.mark.parametrize("suffix", [".tar.gz", ".zip"])
def test_read_sdist_reads_license_expression(tmp_path: Path, suffix: str) -> None:
    """Both archive kinds, with both headers present: the expression wins."""
    pkg_info = _BASE + "License-Expression: MIT\nLicense: Apache-2.0\n"
    sdist = tmp_path / f"pkg-1.0.0{suffix}"
    if suffix == ".zip":
        with zipfile.ZipFile(sdist, "w") as zf:
            zf.writestr("pkg-1.0.0/PKG-INFO", pkg_info)
    else:
        data = pkg_info.encode()
        with tarfile.open(sdist, "w:gz") as tf:
            info = tarfile.TarInfo("pkg-1.0.0/PKG-INFO")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    metadata = read_sdist(sdist).metadata
    assert metadata.license_name == "MIT"
    assert "license" in metadata.provenance


def _wheel_license(msg: email.message.Message) -> str | None:
    metadata = ProjectMetadata(name="pkg")
    _populate_metadata_from_email(metadata, {}, msg, "Source: METADATA")
    return metadata.license_name


def _installed_dependency_license(
    extra: str, monkeypatch: pytest.MonkeyPatch
) -> str | None:
    seen: list[str | None] = []

    def spy(license_id: str | None, *_args: object, **_kwargs: object) -> bool:
        seen.append(license_id)
        return False

    fields = dict(
        line.split(": ", 1) for line in (_BASE + extra).splitlines() if ": " in line
    )
    monkeypatch.setattr(deps_installed, "_apply_license", spy)
    monkeypatch.setattr(
        deps_installed, "get_pkg_metadata", lambda name: _FakeMetadata(fields)
    )
    ci = _make_ci()
    package = spdx3.software_Package(
        spdxId="https://example.com/p", name="pkg", creationInfo=ci
    )
    _enrich_from_installed("pkg", package, ci, "doc", "uuid", Spdx3JsonExporter())
    assert len(seen) == 1
    return seen[0] or None


@pytest.mark.parametrize(("extra", "expected"), _CASES)
def test_license_readers_agree(
    extra: str, expected: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drift guard: sdist, wheel, installed-project and installed-dependency
    readers resolve one METADATA to the same licence."""
    msg = _msg(extra)
    sdist = _parse_pkg_info(_BASE + extra, "Source: PKG-INFO").license_name
    installed = _parse_installed_metadata(msg, "Source: x").license_name
    assert sdist == _wheel_license(msg) == installed == expected
    assert _installed_dependency_license(extra, monkeypatch) == expected
