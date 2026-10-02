# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``read_wheel`` takes a wheel's identity from its own top-level
``.dist-info`` only, warns instead of crashing on a member it cannot read,
and reads ``METADATA`` within a bound.

See also: tests/core/test_wheel_dist_info.py (the selector),
tests/test_wheel_identity_surfaces.py (every wheel surface).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import pytest

from pitloom.assemble import generate_wheel_sbom
from pitloom.core.wheel_dist_info import resolve_own_dist_info
from pitloom.extract import wheel as wheel_module
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from pitloom.extract.wheel import read_wheel
from tests._wheel_damage import DAMAGE, METADATA, damaged_wheel
from tests._wheel_models import safetensors_bytes

_REAL = "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\nSummary: real\n"
_EVIL = "Metadata-Version: 2.1\nName: evil\nVersion: 9.9\nSummary: evil\n"
_WHEEL = "demo-1.0-py3-none-any.whl"


@pytest.fixture(autouse=True)
def _fixed_creation_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def _build(path: Path, members: list[tuple[str, str]]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return path


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    "extra",
    [
        # setuptools-shaped: a vendored dist-info that sorts after the real one.
        [("demo/_vendor/zipp-3.23.0.dist-info/METADATA", _EVIL)],
        # ... and one that sorts before it.
        [("a/_vendor/evil-9.9.dist-info/METADATA", _EVIL)],
        # A second top-level directory the file name does not name.
        [("evil-9.9.dist-info/METADATA", _EVIL)],
        [("zzz-9.9.dist-info/METADATA", _EVIL)],
    ],
    ids=["nested-after", "nested-before", "top-level-before", "top-level-after"],
)
def test_a_foreign_dist_info_is_not_the_wheels_identity(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, extra: list[tuple[str, str]]
) -> None:
    wheel = _build(
        tmp_path / _WHEEL,
        [("demo-1.0.dist-info/METADATA", _REAL), *extra, ("demo/__init__.py", "")],
    )

    metadata, files = read_wheel(wheel)

    assert (metadata.name, metadata.version) == ("demo", "1.0")
    assert metadata.description == "real"
    # The foreign METADATA is still a listed, hashed file.
    foreign = extra[0][0]
    assert any(f.distribution_path == foreign and f.digest_sha256 for f in files)
    assert not _warnings(caplog)


def test_pep_503_and_440_equivalent_names_are_the_same_directory(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    wheel = _build(
        tmp_path / "My.Pkg-1.0-py3-none-any.whl",
        [("my_pkg-1.0.0.dist-info/METADATA", _REAL.replace("demo", "my-pkg"))],
    )

    metadata, _ = read_wheel(wheel)

    assert metadata.name == "my-pkg"
    assert not _warnings(caplog)


@pytest.mark.parametrize(
    ("filename", "dirs", "name", "warnings"),
    [
        ("pkg.whl", ["demo-1.0.dist-info"], "demo", 0),
        (_WHEEL, ["evil-9.9.dist-info"], "evil", 1),
        (_WHEEL, [], "unknown", 1),
        (_WHEEL, ["a-1.dist-info", "b-1.dist-info"], "unknown", 1),
    ],
    ids=["renamed", "disagreement", "none", "several"],
)
def test_a_file_name_that_does_not_name_the_dist_info(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    filename: str,
    dirs: list[str],
    name: str,
    warnings: int,
) -> None:
    wheel = _build(
        tmp_path / filename,
        [(f"{d}/METADATA", _REAL.replace("demo", d.split("-")[0])) for d in dirs]
        + [("demo/__init__.py", "")],
    )

    metadata, files = read_wheel(wheel)

    assert metadata.name == name
    assert len(_warnings(caplog)) == warnings
    assert any(f.distribution_path == "demo/__init__.py" for f in files)


@pytest.mark.parametrize(
    ("kind", "in_metadata"),
    [(k, False) for k in sorted(DAMAGE)]
    + [(k, True) for k in sorted(DAMAGE) if k != "name"],
    ids=str,
)
def test_a_member_that_cannot_be_read_refuses_the_wheel(
    tmp_path: Path, kind: str, in_metadata: bool
) -> None:
    wheel = damaged_wheel(tmp_path, kind, in_metadata=in_metadata)
    member = METADATA if in_metadata else DAMAGE[kind][0]

    with pytest.raises(ValueError, match="could not read") as excinfo:
        read_wheel(wheel)

    message = str(excinfo.value)
    assert f"ARCHIVE={_WHEEL!r}" in message
    assert f"ENTRY={member!r}" in message
    assert "\n" not in message


def test_a_metadata_over_the_cap_is_not_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wheel_module, "MAX_METADATA_BYTES", 100)
    wheel = _build(
        tmp_path / _WHEEL,
        [("demo-1.0.dist-info/METADATA", _REAL + "x" * 1000), ("demo/a.py", "")],
    )

    metadata, files = read_wheel(wheel)

    assert metadata.name == "unknown"
    assert {f.distribution_path for f in files} == {
        "demo-1.0.dist-info/METADATA",
        "demo/a.py",
    }
    (warning,) = _warnings(caplog)
    assert "100 bytes" in warning and "METADATA" in warning


def test_a_metadata_at_the_cap_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata_text = _REAL + "x" * 10
    monkeypatch.setattr(wheel_module, "MAX_METADATA_BYTES", len(metadata_text))
    wheel = _build(tmp_path / _WHEEL, [("demo-1.0.dist-info/METADATA", metadata_text)])

    assert read_wheel(wheel)[0].name == "demo"


def test_the_scanner_and_read_wheel_agree_on_the_own_dist_info(
    tmp_path: Path,
) -> None:
    """One selector: the directory ``read_wheel`` reads is the one the model
    scan leaves out; a foreign directory's model is scanned."""
    wheel = _build(
        tmp_path / _WHEEL,
        [
            ("demo-1.0.dist-info/METADATA", _REAL),
            ("evil-9.9.dist-info/METADATA", _EVIL),
        ],
    )
    models = {
        "demo-1.0.dist-info/m.safetensors": False,
        "evil-9.9.dist-info/m.safetensors": True,
    }
    with zipfile.ZipFile(wheel, "a") as zf:
        for name in models:
            zf.writestr(name, safetensors_bytes())
    with zipfile.ZipFile(wheel) as zf:
        own = resolve_own_dist_info(_WHEEL, zf.namelist()).prefix
    assert own == "demo-1.0.dist-info/"
    assert read_wheel(wheel)[0].name == "demo"

    scanned = {
        m.format_info.file_path_relative
        for m in scan_wheel_for_ai_models(
            wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=1 << 20
        )
    }

    assert scanned == {n for n, foreign in models.items() if foreign}


def test_member_order_does_not_change_the_sbom(tmp_path: Path) -> None:
    members = [
        ("demo-1.0.dist-info/METADATA", _REAL),
        ("evil-9.9.dist-info/METADATA", _EVIL),
        ("demo/_vendor/zipp-3.23.0.dist-info/METADATA", _EVIL),
        ("demo/__init__.py", ""),
        ("demo/mod.py", "x = 1\n"),
    ]
    outputs = set()
    for number, order in enumerate((members, members[::-1], members[2:] + members[:2])):
        folder = tmp_path / str(number)
        folder.mkdir()
        outputs.add(generate_wheel_sbom(_build(folder / _WHEEL, order), offline=True))

    assert len(outputs) == 1
