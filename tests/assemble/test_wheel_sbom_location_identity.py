# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which ``.dist-info`` verify and embed use, and their bounded, refusing
``METADATA`` read (:mod:`pitloom._wheel_sbom_location`).

See also: tests/assemble/test_embed_internals.py (the basic cases),
tests/core/test_wheel_dist_info.py (the selector),
tests/test_wheel_identity_surfaces.py (every surface).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom._wheel_sbom_location import (
    _find_dist_info_prefix,
    find_embedded_sbom,
    read_wheel_name_version,
    read_wheel_name_version_from_path,
)
from pitloom.core import wheel_dist_info
from pitloom.embed import embed_sbom_in_wheel, embed_wheel_sbom
from pitloom.extract.wheel import read_wheel
from tests._wheel_damage import REAL, WHEEL, damaged_wheel, raw_wheel

_EVIL = "Name: evil\nVersion: 9\n"
_DEMO_2 = "Name: demo\nVersion: 2.0\n"


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
        # Nested and vendored alone is no dist-info at all.
        ("foo-1.0-py3-none-any.whl", ["foo/_vendor/zipp-3.23.0.dist-info"], None),
    ],
    ids=["pep503", "no-startswith", "single-other", "none", "nested-alone"],
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


@pytest.mark.parametrize("dirs", [[], ["a-1.dist-info", "b-1.dist-info"]])
def test_the_error_quotes_the_file_name_escaped(
    tmp_path: Path, dirs: list[str]
) -> None:
    path = _wheel(tmp_path / "foo-1.0-py3-none-any.whl", dirs)
    forged = Path("x\nERROR: forged.whl")
    with zipfile.ZipFile(path) as zf, pytest.raises(ValueError) as excinfo:
        _find_dist_info_prefix(zf, forged)
    assert "\n" not in str(excinfo.value) and repr(forged.name) in str(excinfo.value)


def _declared(wheel: Path) -> tuple[str, str]:
    """What ``read_wheel`` says the wheel is."""
    metadata, _ = read_wheel(wheel)
    return metadata.name, str(metadata.version)


def _located(wheel: Path) -> tuple[str, str]:
    """What verify-wheel and embed's selector and read say it is."""
    with zipfile.ZipFile(wheel) as zf:
        prefix = _find_dist_info_prefix(zf, wheel)
        name, version = read_wheel_name_version(zf, prefix)
    return str(name), str(version)


def _embedded(wheel: Path) -> tuple[str, str]:
    """What the SBOM ``embed_wheel_sbom`` writes into the wheel is about."""
    embed_wheel_sbom(wheel)
    with zipfile.ZipFile(wheel) as zf:
        (arcname,) = [n for n in zf.namelist() if "/sboms/" in n]
        graph = json.loads(zf.read(arcname))["@graph"]
    (package,) = [e for e in graph if e["type"] == "software_Package"]
    return package["name"], package["software_packageVersion"]


# Each is the same wheel, read three ways. They must name one identity or the
# embed must refuse: never two answers (the old selectors disagreed on all).
@pytest.mark.parametrize(
    ("filename", "entries", "identity"),
    [
        # Renamed, with an empty ``.dist-info`` directory entry beside the
        # real one.
        (
            "x.whl",
            [("extra.dist-info/", ""), ("demo-1.0.dist-info/METADATA", REAL)],
            ("demo", "1.0"),
        ),
        # A directory entry alone is no dist-info: the file name does not
        # make one of it, and the only real one is the wheel's own.
        (
            WHEEL,
            [("demo-1.0.dist-info/", ""), ("evil-9.dist-info/METADATA", _EVIL)],
            ("evil", "9"),
        ),
        # Names no reader may take at face value: the identity is the same,
        # the embed cannot rewrite what it cannot name.
        (WHEEL, [("./demo-1.0.dist-info/METADATA", REAL)], None),
        (WHEEL, [("demo-2.0.dist-info\\METADATA", _DEMO_2)], None),
    ],
    ids=["dir-entry-beside", "dir-entry-alone", "dot-prefixed", "backslash-only"],
)
def test_every_reader_of_one_wheel_names_one_identity(
    tmp_path: Path,
    filename: str,
    entries: list[tuple[str, str]],
    identity: tuple[str, str] | None,
) -> None:
    wheel = raw_wheel(tmp_path / filename, entries)

    declared, located = _declared(wheel), _located(wheel)

    assert declared == located
    if identity is not None:
        assert declared == identity
        assert _embedded(wheel) == identity
    else:
        before = wheel.read_bytes()
        with pytest.raises(ValueError, match="non-conforming name"):
            embed_wheel_sbom(wheel)
        assert wheel.read_bytes() == before
        assert not list(tmp_path.glob("*.tmp"))


_DUPLICATE_ENTRIES = [
    [("demo-1.0.dist-info/METADATA", REAL), ("demo-1.0.dist-info/METADATA", _EVIL)],
    # The hijack: one install location under two names.
    [("demo-1.0.dist-info/METADATA", REAL), ("demo-1.0.dist-info\\METADATA", _EVIL)],
]


def _call_find_prefix(wheel: Path) -> Any:
    with zipfile.ZipFile(wheel) as zf:
        return _find_dist_info_prefix(zf, wheel)


def _call_embed(wheel: Path) -> Any:
    return embed_sbom_in_wheel(wheel, b"{}")


@pytest.mark.parametrize(
    "call",
    [
        _call_find_prefix,
        read_wheel_name_version_from_path,
        find_embedded_sbom,
        _call_embed,
        embed_wheel_sbom,
    ],
    ids=lambda f: f.__name__,
)
@pytest.mark.parametrize("entries", _DUPLICATE_ENTRIES, ids=["exact", "backslash"])
def test_a_wheel_holding_one_name_twice_is_refused_by_every_reader(
    tmp_path: Path,
    entries: list[tuple[str, str]],
    call: Callable[[Path], Any],
) -> None:
    wheel = raw_wheel(tmp_path / WHEEL, entries)
    before = wheel.read_bytes()

    with pytest.raises(ValueError, match="duplicate member name -- wheel refused"):
        call(wheel)

    assert wheel.read_bytes() == before


@pytest.mark.parametrize("sbom_filename", [None, "demo-1.0.spdx3.json"])
def test_an_embedded_sbom_is_found_under_its_normalised_name(
    tmp_path: Path, sbom_filename: str | None
) -> None:
    """The same member list as the ``.dist-info`` is chosen from: an SBOM
    stored under ``\\`` is at the location an installer would write it."""
    wheel = raw_wheel(
        tmp_path / WHEEL,
        [
            ("demo-1.0.dist-info/METADATA", REAL),
            ("demo-1.0.dist-info\\sboms\\demo-1.0.spdx3.json", "{}"),
        ],
    )

    found = find_embedded_sbom(wheel, sbom_filename)

    assert found is not None
    assert found.arcname == "demo-1.0.dist-info/sboms/demo-1.0.spdx3.json"
    assert found.data == b"{}"


def test_a_damaged_metadata_refuses_the_wheel(tmp_path: Path) -> None:
    path = damaged_wheel(tmp_path, "deflate", in_metadata=True)

    with pytest.raises(ValueError, match="could not read"):
        read_wheel_name_version_from_path(path)


@pytest.mark.parametrize(
    ("cap", "value", "warning"),
    [
        ("MAX_METADATA_BYTES", 10, "over 10 bytes"),
        ("MAX_METADATA_HEADERS", 1, "over 1 headers"),
    ],
)
def test_a_metadata_over_a_cap_is_not_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    cap: str,
    value: int,
    warning: str,
) -> None:
    monkeypatch.setattr(wheel_dist_info, cap, value)
    path = _wheel(tmp_path / "foo-1.0-py3-none-any.whl", ["foo-1.0.dist-info"])

    with zipfile.ZipFile(path) as zf:
        assert read_wheel_name_version(zf, "foo-1.0.dist-info/") == (None, None)

    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "ENTRY='foo-1.0.dist-info/METADATA'" in record.getMessage()
    assert warning in record.getMessage()


def test_an_own_dist_info_without_metadata_is_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = raw_wheel(tmp_path / WHEEL, [("demo-1.0.dist-info/WHEEL", "x")])

    with zipfile.ZipFile(path) as zf:
        assert read_wheel_name_version(zf, "demo-1.0.dist-info/") == (None, None)

    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert record.getMessage().endswith("identity unknown")


@pytest.mark.parametrize("report", [False, True])
def test_the_dist_info_problem_is_said_only_when_asked(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, report: bool
) -> None:
    """A caller that has already read the wheel (``read_wheel`` warns) is not
    told twice; verify-wheel, which has not, asks."""
    path = raw_wheel(tmp_path / WHEEL, [("evil-9.dist-info/METADATA", _EVIL)])

    assert read_wheel_name_version_from_path(path, report=report) == ("evil", "9")

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == int(report)
    assert all("names no top-level .dist-info" in w for w in warnings)
