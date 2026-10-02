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
import time
import tracemalloc
import zipfile
from pathlib import Path

import pytest

from pitloom.assemble import generate_wheel_sbom
from pitloom.core import wheel_dist_info
from pitloom.core.wheel_dist_info import (
    MAX_METADATA_BYTES,
    MAX_METADATA_HEADERS,
    PROBLEM_NONE,
    PROBLEM_SEVERAL_MATCH,
    PROBLEM_SEVERAL_NONE_MATCH,
    resolve_own_dist_info,
)
from pitloom.core.wheel_dist_info import (
    PROBLEM_NOT_A_WHEEL_NAME as PROBLEM_NOT_A_WHEEL,
)
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from pitloom.extract.wheel import read_wheel
from tests._wheel_damage import (
    DAMAGE,
    METADATA,
    damaged_wheel,
)
from tests._wheel_damage import (
    WHEEL as _WHEEL,
)
from tests._wheel_models import safetensors_bytes

_REAL = "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\nSummary: real\n"
_EVIL = "Metadata-Version: 2.1\nName: evil\nVersion: 9.9\nSummary: evil\n"
#: The exception type each kind of damage raises, as the refusal names it.
_LABEL = {
    "deflate": "zlib.error",
    "crc": "zipfile.BadZipFile",
    "encrypted": "RuntimeError",
    "name": "UnicodeDecodeError",
}


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


def test_an_overlong_top_level_dist_info_is_not_split_at_every_dash(
    tmp_path: Path,
) -> None:
    """Over one path component, so never the wheel's own: and not tried at
    each of its dashes (quadratic: seconds for one, minutes for a few)."""
    wheel = _build(
        tmp_path / _WHEEL,
        [
            ("demo-1.0.dist-info/METADATA", _REAL),
            *((f"{'-' * 60_000}{i}.dist-info/METADATA", _EVIL) for i in range(3)),
        ],
    )

    started = time.monotonic()
    metadata, _ = read_wheel(wheel)

    assert time.monotonic() - started < 2.0  # seconds, not tens of them
    assert metadata.name == "demo"


@pytest.mark.parametrize(
    ("filename", "own", "name", "extra"),
    [
        # setuptools-shaped: a vendored dist-info that sorts after the real one.
        (_WHEEL, "demo-1.0", "demo", [("demo/_vendor/zipp-3.23.0.dist-info/M", _EVIL)]),
        # ... and one that sorts before it.
        (_WHEEL, "demo-1.0", "demo", [("a/_vendor/evil-9.9.dist-info/M", _EVIL)]),
        # A second top-level directory the file name does not name.
        (_WHEEL, "demo-1.0", "demo", [("evil-9.9.dist-info/M", _EVIL)]),
        (_WHEEL, "demo-1.0", "demo", [("zzz-9.9.dist-info/M", _EVIL)]),
        # PEP 503 name and PEP 440 version equivalence: the same directory.
        ("My.Pkg-1.0-py3-none-any.whl", "my_pkg-1.0.0", "my-pkg", []),
    ],
    ids=["nested-after", "nested-before", "top-level-before", "top-level-after", "pep"],
)
def test_a_foreign_dist_info_is_not_the_wheels_identity(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    filename: str,
    own: str,
    name: str,
    extra: list[tuple[str, str]],
) -> None:
    wheel = _build(
        tmp_path / filename,
        [
            (f"{own}.dist-info/METADATA", _REAL.replace("demo", name)),
            *((n.replace("/M", "/METADATA"), t) for n, t in extra),
            ("demo/__init__.py", ""),
        ],
    )

    metadata, files = read_wheel(wheel)

    assert metadata.name == name
    assert metadata.description == "real"
    # A foreign METADATA is still a listed, hashed file.
    for foreign, _ in extra:
        path = foreign.replace("/M", "/METADATA")
        assert any(f.distribution_path == path and f.digest_sha256 for f in files)
    assert not _warnings(caplog)


@pytest.mark.parametrize(
    ("filename", "dirs", "name", "problem"),
    [
        ("pkg.whl", ["demo-1.0.dist-info"], "demo", None),
        (_WHEEL, ["evil-9.9.dist-info"], "evil", "names no top-level"),
        (_WHEEL, [], "unknown", PROBLEM_NONE),
        (
            _WHEEL,
            ["a-1.dist-info", "b-1.dist-info"],
            "unknown",
            PROBLEM_SEVERAL_NONE_MATCH,
        ),
        ("pkg.whl", ["a-1.dist-info", "b-1.dist-info"], "unknown", PROBLEM_NOT_A_WHEEL),
        (
            _WHEEL,
            ["demo-1.0.dist-info", "Demo-1.0.dist-info"],
            "unknown",
            PROBLEM_SEVERAL_MATCH,
        ),
    ],
    ids=["renamed", "disagreement", "none", "several", "renamed-several", "twice"],
)
def test_a_file_name_that_does_not_name_the_dist_info(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    filename: str,
    dirs: list[str],
    name: str,
    problem: str | None,
) -> None:
    wheel = _build(
        tmp_path / filename,
        [(f"{d}/METADATA", _REAL.replace("demo", d.split("-")[0])) for d in dirs]
        + [("demo/__init__.py", "")],
    )

    metadata, files = read_wheel(wheel)

    assert metadata.name == name
    assert any(f.distribution_path == "demo/__init__.py" for f in files)
    warnings = _warnings(caplog)
    if problem is None:
        assert not warnings
    else:
        (warning,) = warnings
        assert problem in warning
        # Said once, and with its consequence only where nothing was chosen.
        assert warning.endswith("identity unknown") == (name == "unknown")
        assert "metadata not read" not in warning


@pytest.mark.parametrize(
    ("kind", "in_metadata", "label"),
    [(k, False, _LABEL[k]) for k in sorted(DAMAGE)]
    + [(k, True, _LABEL[k]) for k in sorted(DAMAGE) if k != "name"],
    ids=lambda v: str(v),
)
def test_a_member_that_cannot_be_read_refuses_the_wheel(
    tmp_path: Path, kind: str, in_metadata: bool, label: str
) -> None:
    wheel = damaged_wheel(tmp_path, kind, in_metadata=in_metadata)
    member = METADATA if in_metadata else DAMAGE[kind][0]

    with pytest.raises(ValueError, match="could not read") as excinfo:
        read_wheel(wheel)

    message = str(excinfo.value)
    assert f"ARCHIVE={_WHEEL!r}" in message
    assert f"ENTRY={member!r}" in message
    assert f"({label})" in message
    assert "\n" not in message


@pytest.mark.parametrize(
    ("text", "limits", "name", "warning"),
    [
        (_REAL, {"MAX_METADATA_BYTES": len(_REAL) - 1}, "unknown", "bytes"),
        # A description after the headers may be any size.
        (_REAL + "\n" + "x" * 1000, {"MAX_METADATA_BYTES": 100}, "demo", None),
    ],
    ids=["bytes-over", "big-body"],
)
def test_a_metadata_header_block_over_a_cap_is_not_read(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    limits: dict[str, int],
    name: str,
    warning: str | None,
) -> None:
    for cap, value in limits.items():
        monkeypatch.setattr(wheel_dist_info, cap, value)
    wheel = _build(
        tmp_path / _WHEEL, [("demo-1.0.dist-info/METADATA", text), ("demo/a.py", "")]
    )

    metadata, files = read_wheel(wheel)

    assert metadata.name == name
    assert {f.distribution_path for f in files} == {
        "demo-1.0.dist-info/METADATA",
        "demo/a.py",
    }
    warnings = _warnings(caplog)
    if warning is None:
        assert not warnings
    else:
        (message,) = warnings
        assert f"over {limits.popitem()[1]} {warning}" in message
        assert "METADATA" in message and message.endswith("identity unknown")


def test_an_own_dist_info_without_metadata_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    wheel = _build(tmp_path / _WHEEL, [("demo-1.0.dist-info/WHEEL", "x"), ("a.py", "")])

    metadata, _ = read_wheel(wheel)

    assert metadata.name == "unknown"
    (warning,) = _warnings(caplog)
    assert "no demo-1.0.dist-info/METADATA" in warning
    assert warning.endswith("identity unknown")


def test_sixteen_mebibytes_of_short_headers_do_not_cost_hundreds_of_megabytes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A 28 KB wheel whose ``METADATA`` inflates to 16 MiB of ``X-A: b``
    lines: 2.4 million headers once parsed, about 700 MB resident. The header
    count stops the read, so memory stays small."""
    lines = "X-A: b\n" * (MAX_METADATA_BYTES // 7)
    wheel = _build(tmp_path / _WHEEL, [("demo-1.0.dist-info/METADATA", _REAL + lines)])
    assert wheel.stat().st_size < 100_000  # the attack is cheap to ship

    # Tracing may already be on (PYTHONTRACEMALLOC): measure from where it is.
    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()
    tracemalloc.reset_peak()
    baseline = tracemalloc.get_traced_memory()[0]
    try:
        metadata, _ = read_wheel(wheel)
        peak = tracemalloc.get_traced_memory()[1] - baseline
    finally:
        if not was_tracing:
            tracemalloc.stop()

    assert metadata.name == "unknown"
    assert peak < 32 * 1024 * 1024
    (warning,) = _warnings(caplog)
    assert f"over {MAX_METADATA_HEADERS} headers" in warning


@pytest.mark.parametrize(
    ("dist_infos", "own", "name", "scanned"),
    [
        pytest.param(
            ["demo-1.0.dist-info", "evil-9.9.dist-info"],
            "demo-1.0.dist-info/",
            "demo",
            {"evil-9.9.dist-info"},
            id="one-matches",
        ),
        pytest.param(
            ["demo-1.0.dist-info", "Demo-1.0.0.dist-info"],
            None,
            "unknown",
            {"demo-1.0.dist-info", "Demo-1.0.0.dist-info"},
            id="two-match",
        ),
    ],
)
def test_the_scanner_and_read_wheel_agree_on_the_own_dist_info(
    tmp_path: Path,
    dist_infos: list[str],
    own: str | None,
    name: str,
    scanned: set[str],
) -> None:
    """One selector: the directory ``read_wheel`` reads is the one the model
    scan leaves out, and where it reads none the scan leaves out none."""
    wheel = _build(
        tmp_path / _WHEEL,
        [
            (f"{d}/METADATA", _EVIL if d.startswith("evil") else _REAL)
            for d in dist_infos
        ],
    )
    with zipfile.ZipFile(wheel, "a") as zf:
        for directory in dist_infos:
            zf.writestr(f"{directory}/m.safetensors", safetensors_bytes())
    with zipfile.ZipFile(wheel) as zf:
        assert resolve_own_dist_info(_WHEEL, zf.namelist()).prefix == own
    assert read_wheel(wheel)[0].name == name

    found = {
        m.format_info.file_path_relative
        for m in scan_wheel_for_ai_models(
            wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=1 << 20
        )
    }

    assert found == {f"{d}/m.safetensors" for d in scanned}


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
