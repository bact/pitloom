# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a re-embed removes from ``.dist-info/sboms/``: a Pitloom SBOM of type
build or analyzed for the same name and version, and nothing else.

See also: test_embed_internals.py (the archive rewrite itself).
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import pytest
from installer.sources import WheelFile

from pitloom import _embed_wheel
from pitloom._embed_wheel import embed_sbom_in_wheel

from .conftest import _SAMPLE_SPDX3_JSON, _make_dummy_wheel, _spdx3_json_with_subject

_DIST = "stalepkg-1.0.0.dist-info/sboms/"
_NEW = _spdx3_json_with_subject("stalepkg", "1.0.0", pitloom_sbom_types=["build"])


@pytest.mark.parametrize(
    ("name", "version", "types", "removed"),
    [
        ("stalepkg", "1.0.0", ["build"], True),
        ("stalepkg", "1.0.0", ["analyzed", "deployed"], True),
        ("StalePkg", "1.0", ["build"], True),
        ("stalepkg", "1.0.0", ["design"], False),
        ("stalepkg", "1.0.0", [], False),
        ("otherpkg", "1.0.0", ["build"], False),
        ("stalepkg", "2.0.0", ["build"], False),
        ("stalepkg", None, ["build"], False),
    ],
    ids=[
        "build",
        "analyzed",
        "name-and-version-spelt-otherwise",
        "design",
        "no-type",
        "other-name",
        "other-version",
        "no-version",
    ],
)
def test_only_a_build_or_analyzed_sbom_of_the_wheel_is_replaced(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    name: str,
    version: str | None,
    types: list[str],
    removed: bool,
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "stalepkg", "1.0.0")
    old = _spdx3_json_with_subject(name, version, pitloom_sbom_types=types)
    embed_sbom_in_wheel(wheel, old, sbom_filename="first.spdx3.json")
    with caplog.at_level(logging.WARNING):
        embed_sbom_in_wheel(wheel, _NEW, sbom_filename="second.spdx3.json")
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        record = zf.read("stalepkg-1.0.0.dist-info/RECORD").decode("utf-8")
    assert f"{_DIST}second.spdx3.json" in names
    assert (f"{_DIST}first.spdx3.json" not in names) is removed
    assert (f"{_DIST}first.spdx3.json" in record) is not removed
    assert len(caplog.messages) == (0 if removed else 1)
    if not removed:
        assert f"{_DIST}first.spdx3.json: kept" in caplog.messages[0]
    with WheelFile.open(wheel) as wf:
        wf.validate_record()


def test_a_sbom_not_made_by_pitloom_stays_silently(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "stalepkg", "1.0.0")
    foreign = _spdx3_json_with_subject("stalepkg", "1.0.0").replace("Pitloom", "x")
    embed_sbom_in_wheel(wheel, foreign, sbom_filename="first.spdx3.json")
    with caplog.at_level(logging.WARNING):
        embed_sbom_in_wheel(wheel, _NEW, sbom_filename="second.spdx3.json")
    with zipfile.ZipFile(wheel) as zf:
        assert f"{_DIST}first.spdx3.json" in zf.namelist()
    assert not caplog.messages


def test_the_sample_sbom_without_an_sbom_node_stays(tmp_path: Path) -> None:
    """The sample has a Pitloom agent but no ``software_Sbom``: no type, so
    it is not a build SBOM to replace."""
    wheel = _make_dummy_wheel(tmp_path, "stalepkg", "1.0.0")
    embed_sbom_in_wheel(wheel, _SAMPLE_SPDX3_JSON, sbom_filename="first.spdx3.json")
    embed_sbom_in_wheel(wheel, _NEW, sbom_filename="second.spdx3.json")
    with zipfile.ZipFile(wheel) as zf:
        assert f"{_DIST}first.spdx3.json" in zf.namelist()


def test_a_failed_chmod_is_one_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "stalepkg", "1.0.0")

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(_embed_wheel, "chmod", refuse)
    with caplog.at_level(logging.WARNING):
        embed_sbom_in_wheel(wheel, _NEW)
    assert caplog.messages == [f"{wheel.name}: file mode not restored: denied"]
