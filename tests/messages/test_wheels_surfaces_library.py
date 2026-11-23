# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The wheel and embedded-SBOM lines on the surfaces that are not the
commands: the library (``pitloom.embed.embed_wheel_sbom``,
``embed_sbom_in_wheel``, ``find_embedded_sbom``: the ``pitloom_code`` of each
raised exception and of each record, ``WheelRefused`` still a
``ValueError``), the Hatchling hook (``sbom-name-conflict``,
``library-unusable/hatchling``: one ``ERROR:`` with the hook's frame and the
code) and the build route (``Build: `` frame, ``; not copied``).

See also: tests/messages/test_wheels_surfaces.py and
tests/messages/test_wheels_surfaces_sboms.py (the commands) and
tests/messages/test_wheels_core.py (the helpers).
"""

# pylint: disable=protected-access

from __future__ import annotations

import codecs
import logging
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from pitloom.assemble import find_embedded_sbom
from pitloom.core._models_wheel_build_and_read import _extract_wheel_to_included_files
from pitloom.embed import embed_wheel_sbom
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    BUILD_FRAME,
    GIT_FRAME,
    MESSAGES,
    CodedValueError,
    code_of,
)
from pitloom.messages import trusted_message as trusted
from pitloom.messages.wheels import WheelRefused
from tests._wheel_fixtures import (
    DIST_INFO,
    WHEEL_FILE,
    make_wheel,
    metadata,
    patch_member_name,
    spdx3_sbom,
    write_wheel,
)
from tests.extract.conftest import make_hook

pytestmark = pytest.mark.platform  # ZIP archives, member names, stderr lines


@pytest.fixture(autouse=True, name="_pinned")
def pinned_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    monkeypatch.chdir(tmp_path)


def _records(caplog: pytest.LogCaptureFixture) -> list[tuple[str, str, str | None]]:
    """Each record as its level, text and code."""
    return [
        (r.levelname, r.getMessage(), getattr(r, CODE_ATTR, None))
        for r in caplog.records
    ]


# -- the library: every refusal is a ValueError that carries its code ----------


def _unreadable(directory: Path) -> Path:
    path = directory / WHEEL_FILE
    path.write_bytes(b"not a zip")
    return path


def _nul(directory: Path) -> Path:
    wheel = make_wheel(directory)
    patch_member_name(wheel, "demo/__init__.py", b"demo/__\x00nit__.py")
    return wheel


def _duplicate(directory: Path) -> Path:
    members = {f"{DIST_INFO}/METADATA": metadata(), "d/M": b"1", "d\\M": b"2"}
    return write_wheel(directory / WHEEL_FILE, members)


def _no_dist_info(directory: Path) -> Path:
    return write_wheel(directory / WHEEL_FILE, {"demo/a.py": b""})


def _signed(directory: Path) -> Path:
    return make_wheel(directory, extra={f"{DIST_INFO}/RECORD.p7s": b"{}"})


def _non_conforming(directory: Path) -> Path:
    members = {f"{DIST_INFO}\\METADATA": metadata(), f"{DIST_INFO}/WHEEL": b"x"}
    return write_wheel(directory / WHEEL_FILE, members)


_REFUSALS: dict[str, tuple[Callable[[Path], Path], str]] = {
    "unreadable": (_unreadable, "wheel-unreadable"),
    "nul": (_nul, "wheel-invalid"),
    "duplicate": (_duplicate, "wheel-invalid"),
    "no-dist-info": (_no_dist_info, "dist-info-missing"),
    "signed": (_signed, "wheel-unusable/signed"),
    "non-conforming": (_non_conforming, "wheel-unusable"),
}


@pytest.mark.parametrize("cause", sorted(_REFUSALS))
def test_embed_wheel_sbom_raises_a_coded_wheel_refusal_and_leaves_the_wheel(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, cause: str
) -> None:
    build, code = _REFUSALS[cause]
    wheel = build(tmp_path)
    before = wheel.read_bytes()
    with caplog.at_level(logging.INFO), pytest.raises(ValueError) as raised:
        embed_wheel_sbom(wheel)
    assert isinstance(raised.value, WheelRefused)  # and a ValueError, as before
    assert code_of(raised.value) == code
    assert getattr(raised.value, CODE_ATTR) == code
    text = str(raised.value)
    assert text.startswith(f"ARCHIVE='{WHEEL_FILE}'") and text.endswith(
        "; wheel refused"
    )
    assert "\n" not in text and str(tmp_path) not in text
    assert trusted(f"ERROR: {text} [{code}]") is MESSAGES[code]
    assert wheel.read_bytes() == before
    assert not [c for _, _, c in _records(caplog) if c == code]  # raised, not logged


def test_the_library_returns_a_removed_signature_and_a_date_floor_not_a_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The commands say them (``wheel-unusable/signed`` and
    ``datetime-not-recordable`` as ``INFO:``); the library hands them over."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    wheel = _signed(tmp_path)
    with caplog.at_level(logging.INFO):
        _, _, removed, floored = embed_wheel_sbom(wheel, allow_signed_wheel=True)[1:]
    assert removed == (f"{DIST_INFO}/RECORD.p7s",) and floored is True
    assert not _records(caplog)


def test_find_embedded_sbom_returns_none_for_none_and_raises_for_several(
    tmp_path: Path,
) -> None:
    assert find_embedded_sbom(make_wheel(tmp_path / "none")) is None
    sboms = {"a.spdx3.json": spdx3_sbom(), "b.spdx3.json": spdx3_sbom()}
    several = make_wheel(tmp_path / "several", sboms=sboms)
    with pytest.raises(ValueError, match="pass --sbom-filename") as raised:
        find_embedded_sbom(several)
    assert code_of(raised.value) == "wheel-sbom-ambiguous"
    assert find_embedded_sbom(several, "a.spdx3.json") is not None  # one named
    with pytest.raises(WheelRefused) as refused:
        find_embedded_sbom(_no_dist_info(tmp_path / "bare"))
    assert code_of(refused.value) == "dist-info-missing"


def test_a_mismatch_logs_each_part_but_the_last_and_raises_the_last(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sbom = tmp_path / "given.json"
    sbom.write_bytes(spdx3_sbom("other", "2.0"))
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError) as raised:
        embed_wheel_sbom(make_wheel(tmp_path / "w"), sbom_path=sbom)
    assert code_of(raised.value) == "wheel-sbom-conflict"
    assert isinstance(raised.value, CodedValueError)
    assert [(lv, c) for lv, _, c in _records(caplog)] == [
        ("ERROR", "wheel-sbom-conflict")
    ]
    assert "name 'other' differs" in caplog.records[0].getMessage()
    assert str(raised.value).endswith(
        "SBOM version '2.0' differs from the wheel's METADATA '1.0'"
    )


def test_a_given_sbom_with_a_byte_order_mark_is_one_coded_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sbom = tmp_path / "bom.json"
    sbom.write_bytes(codecs.BOM_UTF8 + spdx3_sbom())
    with caplog.at_level(logging.WARNING):
        embed_wheel_sbom(make_wheel(tmp_path / "w"), sbom_path=sbom)
    ((level, text, code),) = _records(caplog)
    assert (level, code) == ("WARNING", "json-malformed/bom")
    assert text.startswith("FILE=") and "byte order mark" in text


def test_the_library_says_a_member_it_leaves_out_with_its_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    wheel = write_wheel(
        tmp_path / WHEEL_FILE, {f"{DIST_INFO}/METADATA": metadata(), "/abs.py": b""}
    )
    with caplog.at_level(logging.WARNING):
        embed_wheel_sbom(wheel)
    assert _records(caplog) == [
        (
            "WARNING",
            f"ARCHIVE='{WHEEL_FILE}' ENTRY='/abs.py': no safe install location; "
            "not listed",
            "archive-member-unsafe",
        )
    ]


# -- the Hatchling hook --------------------------------------------------------


def _project(root: Path, extra: str = "") -> Path:
    project = root / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
        '\n[project]\nname = "demo"\nversion = "1.0.0"\n'
        f"{extra}",
        encoding="utf-8",
    )
    return project


def _error_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [ln for ln in capsys.readouterr().err.splitlines() if ln.strip()]


def test_the_hook_says_an_sbom_name_clash_once_with_its_frame_and_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, '\n[tool.pitloom]\nsbom-basename = "mine"\n')
    hook = make_hook(str(project), {})
    cast(Any, hook.build_config).sbom_files.append("dist/MINE.Spdx3.JSON")
    build_data: dict[str, Any] = {}
    with pytest.raises(ValueError) as raised:
        hook.initialize("standard", build_data)
    assert code_of(raised.value) == "sbom-name-conflict"
    assert not build_data  # nothing staged
    (line,) = _error_lines(capsys)
    assert line.startswith("ERROR: ") and line.endswith("[sbom-name-conflict]")
    assert (
        "FILE=mine.spdx3.json: also the name, ignoring case, of sbom-files entry"
        in line
    )
    assert "'dist/MINE.Spdx3.JSON'" in line
    assert trusted(line) is MESSAGES["sbom-name-conflict"]


@pytest.mark.parametrize(
    ("patched", "said"),
    [
        (
            {"return_value": "1.28.0"},
            "Hatchling 1.28.0 cannot embed an SBOM (PEP 770 needs 1.29.0 or later); "
            "upgrade Hatchling",
        ),
        (
            {"side_effect": PackageNotFoundError("hatchling")},
            "Hatchling version unknown (no package metadata found); PEP 770 needs "
            "1.29.0 or later, reinstall Hatchling",
        ),
    ],
    ids=["too-old", "unknown"],
)
def test_the_hook_says_an_unusable_hatchling_once_as_a_coded_value_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    patched: dict[str, Any],
    said: str,
) -> None:
    hook = make_hook(str(_project(tmp_path)), {})
    with patch("pitloom.plugins.hatch._pkg_version", **patched):
        with pytest.raises(ValueError) as raised:  # no longer a RuntimeError
            hook.initialize("standard", {})
    assert not isinstance(raised.value, RuntimeError)
    assert code_of(raised.value) == "library-unusable/hatchling"
    (line,) = _error_lines(capsys)
    assert line.startswith("ERROR: ") and said in line
    assert line.endswith("[library-unusable/hatchling]")
    assert trusted(line) is MESSAGES["library-unusable/hatchling"]


# -- the build route -----------------------------------------------------------


def test_the_build_route_says_not_copied_behind_its_frame(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    wheel = write_wheel(
        tmp_path / WHEEL_FILE,
        {"pkg/__init__.py": b"", "../evil.py": b"x", "pkg\\a.py": b"y"},
    )
    out = tmp_path / "out"
    out.mkdir()
    with caplog.at_level(logging.WARNING):
        files = _extract_wheel_to_included_files(wheel, out)
    assert sorted(f.distribution_path for f in files) == ["pkg/__init__.py", "pkg/a.py"]
    assert not (tmp_path / "evil.py").exists()
    frame = BUILD_FRAME.render({})
    assert list(_records(caplog)) == [
        (
            "WARNING",
            f"{frame}ARCHIVE='{WHEEL_FILE}' ENTRY='../evil.py': no safe install "
            "location; not copied",
            "archive-member-unsafe",
        ),
        (
            "WARNING",
            f"{frame}ARCHIVE='{WHEEL_FILE}' ENTRY='pkg\\a.py': non-conforming name; "
            "copied as 'pkg/a.py'",
            "archive-member-invalid",
        ),
    ]
    assert not any("skipped" in text for _, text, _ in _records(caplog))
    assert all(trusted(f"{lv}: {text} [{c}]") for lv, text, c in _records(caplog))


_BODIES = {
    "archive-member-unsafe": "ENTRY='/a': no safe install location; not copied",
    "archive-member-conflict": "ENTRY='/a': also a directory of other entries; "
    "not copied",
    "archive-member-invalid": "ENTRY='/a': non-conforming name; copied as 'a'",
}


@pytest.mark.parametrize(
    ("prefix", "carries"),
    [
        (BUILD_FRAME.render({}), True),
        ("", True),
        (GIT_FRAME.render({}), False),
        ("Nowhere: ", False),
    ],
    ids=["build-frame", "no-frame", "git-frame", "unknown-frame"],
)
@pytest.mark.parametrize("code", sorted(_BODIES))
def test_only_a_frame_that_carries_the_member_codes_trusts_them(
    prefix: str, carries: bool, code: str
) -> None:
    line = f"WARNING: {prefix}ARCHIVE='{WHEEL_FILE}' {_BODIES[code]} [{code}]"
    assert (trusted(line) is MESSAGES[code]) is carries
