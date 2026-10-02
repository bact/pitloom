# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which ``.dist-info`` verify and embed use, and their bounded, refusing
``METADATA`` read (:mod:`pitloom._wheel_sbom_location`).

See also: tests/assemble/test_embed_internals.py (the basic cases),
tests/core/test_wheel_dist_info.py (the selector).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import pytest

from pitloom import _wheel_sbom_location
from pitloom._wheel_sbom_location import (
    _find_dist_info_prefix,
    read_wheel_name_version,
    read_wheel_name_version_from_path,
)
from tests._wheel_damage import damaged_wheel


def _wheel(path: Path, dirs: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for d in dirs:
            zf.writestr(f"{d}/METADATA", f"Name: {d.split('-')[0]}\nVersion: 1\n")
    return path


@pytest.mark.parametrize(
    ("wheel", "dirs", "expected"),
    [
        # PEP 503/440: the old raw prefix test raised here.
        (
            "My.Pkg-1.0-py3-none-any.whl",
            ["my_pkg-1.0.0.dist-info", "x-1.dist-info"],
            "my_pkg-1.0.0.dist-info/",
        ),
        # The old raw prefix test picked foo-bar-2.0 for foo-1.0.
        ("foo-1.0-py3-none-any.whl", ["foo-bar-2.0.dist-info", "o-1.dist-info"], None),
        (
            "foo-1.0-py3-none-any.whl",
            ["foo-bar-2.0.dist-info"],
            "foo-bar-2.0.dist-info/",
        ),
        ("foo-1.0-py3-none-any.whl", [], None),
    ],
    ids=["pep503", "no-startswith", "single-other", "none"],
)
def test_the_prefix_is_chosen_by_the_shared_selector(
    tmp_path: Path, wheel: str, dirs: list[str], expected: str | None
) -> None:
    path = _wheel(tmp_path / wheel, dirs)
    with zipfile.ZipFile(path) as zf:
        if expected is None:
            with pytest.raises(ValueError, match=r"\.dist-info"):
                _find_dist_info_prefix(zf, path)
        else:
            assert _find_dist_info_prefix(zf, path) == expected


def test_a_nested_dist_info_alone_is_no_dist_info(tmp_path: Path) -> None:
    path = tmp_path / "foo-1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("foo/_vendor/zipp-3.23.0.dist-info/METADATA", "Name: zipp\n")
    with zipfile.ZipFile(path) as zf, pytest.raises(ValueError, match="no .dist-info"):
        _find_dist_info_prefix(zf, path)


def test_a_damaged_metadata_refuses_the_wheel(tmp_path: Path) -> None:
    path = damaged_wheel(tmp_path, "deflate", in_metadata=True)

    with pytest.raises(ValueError, match="could not read"):
        read_wheel_name_version_from_path(path)


def test_a_metadata_over_the_cap_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(_wheel_sbom_location, "MAX_METADATA_BYTES", 10)
    path = _wheel(tmp_path / "foo-1.0-py3-none-any.whl", ["foo-1.0.dist-info"])

    with zipfile.ZipFile(path) as zf:
        assert read_wheel_name_version(zf, "foo-1.0.dist-info/") == (None, None)

    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "ENTRY='foo-1.0.dist-info/METADATA'" in record.getMessage()
