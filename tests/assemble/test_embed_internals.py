# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.embed internal helpers and edge cases: dist-info
prefix discovery, zip timestamp resolution, RECORD line updates, filename
derivation, and archive-rewriting error paths.

See also: test_embed_core.py, test_embed_cli.py -- this module's siblings,
split from the original test_embed.py.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest
from installer.sources import WheelFile

from pitloom.embed import (
    _derive_wheel_sbom_filename,
    _find_dist_info_prefix,
    _looks_like_pitloom_sbom,
    _resolve_zip_timestamp,
    _rewrite_wheel_archive,
    _update_record_lines,
    embed_sbom_in_wheel,
    embed_wheel_sbom,
)

from .conftest import _SAMPLE_SPDX3_JSON, _make_dummy_wheel


def test_find_dist_info_prefix_edge_cases(tmp_path: Path) -> None:
    """Test _find_dist_info_prefix with single, matching, and ambiguous dist-infos."""
    # 1. No dist-info
    p1 = tmp_path / "nodist-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p1, "w") as zf:
        zf.writestr("nodist/module.py", "# code")
    with zipfile.ZipFile(p1, "r") as zf:
        with pytest.raises(ValueError, match="no .dist-info directory found"):
            _find_dist_info_prefix(zf, p1)

    # 2. Multiple dist-info where one matches stem prefix
    p2 = tmp_path / "mypkg-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p2, "w") as zf:
        zf.writestr("mypkg-1.0.0.dist-info/METADATA", "Name: mypkg\nVersion: 1.0.0\n")
        zf.writestr("other-1.0.0.dist-info/METADATA", "Name: other\nVersion: 1.0.0\n")
    with zipfile.ZipFile(p2, "r") as zf:
        assert _find_dist_info_prefix(zf, p2) == "mypkg-1.0.0.dist-info/"

    # 3. Multiple dist-info where none or multiple match stem prefix
    p3 = tmp_path / "unmatched-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p3, "w") as zf:
        zf.writestr("pkg1-1.0.0.dist-info/METADATA", "Name: pkg1\n")
        zf.writestr("pkg2-1.0.0.dist-info/METADATA", "Name: pkg2\n")
    with zipfile.ZipFile(p3, "r") as zf:
        with pytest.raises(ValueError, match="multiple .dist-info directories found"):
            _find_dist_info_prefix(zf, p3)


def test_resolve_zip_timestamp_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _resolve_zip_timestamp under various invalid/fallback conditions."""
    # Invalid string in SOURCE_DATE_EPOCH
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-a-number")
    ts, floored = _resolve_zip_timestamp(fallback=(1990, 5, 1, 12, 0, 0))
    assert ts == (1990, 5, 1, 12, 0, 0)
    assert floored is False

    # Overflow in SOURCE_DATE_EPOCH
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "99999999999999999999999999999999999")
    ts_overflow, floored_overflow = _resolve_zip_timestamp(
        fallback=(1995, 1, 1, 0, 0, 0)
    )
    assert ts_overflow == (1995, 1, 1, 0, 0, 0)
    assert floored_overflow is False

    # Fallback with year < 1980 clamped to 1980
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    ts_clamped, floored_clamped = _resolve_zip_timestamp(fallback=(1970, 1, 1, 0, 0, 0))
    assert ts_clamped == (1980, 1, 1, 0, 0, 0)
    assert floored_clamped is True

    # Fallback None uses current time
    ts_now, floored_now = _resolve_zip_timestamp(fallback=None)
    assert ts_now[0] >= 2026
    assert floored_now is False

    # SOURCE_DATE_EPOCH itself before 1980 (e.g. SOURCE_DATE_EPOCH=0) is floored
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    ts_epoch_floored, floored_epoch = _resolve_zip_timestamp()
    assert ts_epoch_floored == (1980, 1, 1, 0, 0, 0)
    assert floored_epoch is True


def test_update_record_lines_empty_rows() -> None:
    """Test _update_record_lines skips empty rows in RECORD string."""
    raw_record = "pkg/__init__.py,sha256=abc,10\n\n\npkg-1.0.dist-info/RECORD,,\n"
    updated = _update_record_lines(
        raw_record,
        "pkg-1.0.dist-info/sboms/pkg.spdx3.json",
        "hash123",
        100,
        "pkg-1.0.dist-info/",
    )
    assert "pkg-1.0.dist-info/sboms/pkg.spdx3.json,sha256=hash123,100" in updated
    assert "pkg-1.0.dist-info/RECORD,," in updated


def test_embed_sbom_file_not_found(tmp_path: Path) -> None:
    """Test embed_sbom_in_wheel raises FileNotFoundError for missing wheel."""
    missing_wheel = tmp_path / "does_not_exist.whl"
    with pytest.raises(FileNotFoundError, match="Wheel file not found"):
        embed_sbom_in_wheel(missing_wheel, "{}")


def test_embed_sbom_in_wheel_corrupt_zip_raises_value_error(tmp_path: Path) -> None:
    """A wheel that isn't a valid ZIP -> ValueError, not zipfile.BadZipFile.

    embed_sbom_in_wheel shares _open_wheel_zip with find_embedded_sbom
    (see test_validate_wheel_corrupt_zip_errors), so it inherits the same
    BadZipFile -> ValueError normalization."""
    corrupt_wheel = tmp_path / "notazip-1.0.0-py3-none-any.whl"
    corrupt_wheel.write_bytes(b"not a zip file at all")
    with pytest.raises(ValueError, match="Invalid wheel archive"):
        embed_sbom_in_wheel(corrupt_wheel, "{}")


def test_embed_sbom_without_existing_record(tmp_path: Path) -> None:
    """Test embed_sbom_in_wheel handles a wheel archive with no RECORD entry."""
    wheel_path = tmp_path / "norec-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(
            "norec-1.0.0.dist-info/METADATA",
            "Name: norec\nVersion: 1.0.0\n",
        )
        zf.writestr("norec/__init__.py", "# empty\n")

    embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)

    with zipfile.ZipFile(wheel_path, "r") as zf:
        assert "norec-1.0.0.dist-info/sboms/norec-1.0.0.spdx3.json" in zf.namelist()
        assert "norec-1.0.0.dist-info/RECORD" in zf.namelist()
        rec_text = zf.read("norec-1.0.0.dist-info/RECORD").decode("utf-8")
        assert "norec-1.0.0.dist-info/sboms/norec-1.0.0.spdx3.json" in rec_text
        assert "norec-1.0.0.dist-info/RECORD,," in rec_text


def test_derive_wheel_sbom_filename_fallbacks(tmp_path: Path) -> None:
    """Test _derive_wheel_sbom_filename metadata missing/empty header fallbacks."""
    # 1. No METADATA in archive -> fall back to dist-info name prefix
    p1 = tmp_path / "nometa-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p1, "w") as zf:
        zf.writestr("nometa-1.0.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")
    with zipfile.ZipFile(p1, "r") as zf:
        fn1 = _derive_wheel_sbom_filename(zf, "nometa-1.0.0.dist-info/")
        assert fn1 == "nometa-1.0.0.spdx3.json"

    # 2. METADATA with no Name or Version headers -> fall back to dist-info prefix
    p2 = tmp_path / "emptyheaders-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p2, "w") as zf:
        zf.writestr(
            "emptyheaders-1.0.0.dist-info/METADATA",
            "Summary: A summary\nAuthor: Author\n",
        )
    with zipfile.ZipFile(p2, "r") as zf:
        fn2 = _derive_wheel_sbom_filename(zf, "emptyheaders-1.0.0.dist-info/")
        assert fn2 == "emptyheaders-1.0.0.spdx3.json"

    # 3. METADATA with blank line after Name (stops header scan)
    p3 = tmp_path / "blankheader-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p3, "w") as zf:
        zf.writestr(
            "blankheader-1.0.0.dist-info/METADATA",
            "Name: myname\n\nVersion: 2.0.0 in description body\n",
        )
    with zipfile.ZipFile(p3, "r") as zf:
        fn3 = _derive_wheel_sbom_filename(zf, "blankheader-1.0.0.dist-info/")
        assert fn3 == "blankheader-1.0.0.spdx3.json"

    # 4. Empty prefix fallback
    with zipfile.ZipFile(p1, "r") as zf:
        fn4 = _derive_wheel_sbom_filename(zf, ".dist-info/")
        assert fn4 == "sbom.spdx3.json"


def test_rewrite_wheel_archive_chmod_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test _rewrite_wheel_archive gracefully ignores OSError on os.chmod."""
    wheel_path = _make_dummy_wheel(tmp_path, "chmodpkg", "1.0.0")

    def _failing_chmod(path: Any, mode: int) -> None:
        raise OSError("Permission denied simulation")

    monkeypatch.setattr("pitloom._embed_wheel.os.chmod", _failing_chmod)
    # Should complete without error
    embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)


def test_rewrite_wheel_archive_temp_file_cleanup_on_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test temporary file is cleaned up if archive write fails midway."""
    wheel_path = _make_dummy_wheel(tmp_path, "cleanuppkg", "1.0.0")

    def _failing_writestr(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Disk write simulation failed")

    monkeypatch.setattr("zipfile.ZipFile.writestr", _failing_writestr)
    with pytest.raises(RuntimeError, match="Disk write simulation failed"):
        embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)

    # Verify no .tmp files remain in parent dir
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert not tmp_files


def test_embed_sbom_in_wheel_chmod_oserror(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that os.chmod raising OSError is gracefully ignored."""
    wheel_path = _make_dummy_wheel(tmp_path, "chmodpkg", "1.0.0")

    def _failing_chmod(*args: Any, **kwargs: Any) -> None:
        raise OSError("Simulated permission error on chmod")

    monkeypatch.setattr("os.chmod", _failing_chmod)

    # Should complete without error
    embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)
    assert wheel_path.exists()


def test_embed_wheel_sbom_not_found(tmp_path: Path) -> None:
    """Test that embedding into a non-existent wheel
    raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        embed_wheel_sbom(tmp_path / "does_not_exist.whl")


def test_embed_sbom_in_wheel_replace_error_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that temp_path is cleaned up if os.replace fails
    (e.g., Windows PermissionError)."""
    wheel_path = _make_dummy_wheel(tmp_path, "replacepkg", "1.0.0")

    def _failing_replace(src: str | Path, dst: str | Path) -> None:
        raise PermissionError("Simulated file in use error")

    monkeypatch.setattr("os.replace", _failing_replace)

    with pytest.raises(PermissionError, match="Simulated file in use error"):
        embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)

    # Verify no .tmp files remain in parent dir
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert not tmp_files


def test_embed_sbom_drops_stale_sboms_from_archive(tmp_path: Path) -> None:
    """Test re-embedding drops prior SBOM from archive & RECORD."""
    wheel_path = _make_dummy_wheel(tmp_path, "stalepkg", "1.0.0")

    # 1. Embed initial SBOM under custom name 'first.spdx3.json'
    embed_sbom_in_wheel(
        wheel_path,
        _SAMPLE_SPDX3_JSON,
        sbom_filename="first.spdx3.json",
    )
    with zipfile.ZipFile(wheel_path, "r") as zf:
        assert "stalepkg-1.0.0.dist-info/sboms/first.spdx3.json" in zf.namelist()

    # 2. Embed second SBOM under custom name 'second.spdx3.json'
    embed_sbom_in_wheel(
        wheel_path,
        _SAMPLE_SPDX3_JSON,
        sbom_filename="second.spdx3.json",
    )
    with zipfile.ZipFile(wheel_path, "r") as zf:
        namelist = zf.namelist()
        assert "stalepkg-1.0.0.dist-info/sboms/second.spdx3.json" in namelist
        assert "stalepkg-1.0.0.dist-info/sboms/first.spdx3.json" not in namelist

        record_text = zf.read("stalepkg-1.0.0.dist-info/RECORD").decode("utf-8")
        assert "stalepkg-1.0.0.dist-info/sboms/second.spdx3.json" in record_text
        assert "stalepkg-1.0.0.dist-info/sboms/first.spdx3.json" not in record_text

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()


def test_looks_like_pitloom_sbom_invalid_json_returns_false() -> None:
    """Test _looks_like_pitloom_sbom returns False when content isn't valid JSON."""
    assert _looks_like_pitloom_sbom(b"{not valid json") is False


def test_looks_like_pitloom_sbom_non_list_graph_returns_false() -> None:
    """Test _looks_like_pitloom_sbom returns False when @graph isn't a list."""
    assert _looks_like_pitloom_sbom(b'{"@graph": "not-a-list"}') is False
    assert _looks_like_pitloom_sbom(b"{}") is False


def test_embed_sbom_orig_mode_none_skips_chmod(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that a wheel_obj.exists() False on the orig_mode check leaves
    orig_mode as None and skips the chmod block entirely."""
    wheel_path = _make_dummy_wheel(tmp_path, "origmodenone", "1.0.0")
    real_exists = Path.exists
    call_count = {"n": 0}

    def fake_exists(self: Path) -> bool:
        call_count["n"] += 1
        if call_count["n"] == 2:
            return False
        return real_exists(self)

    def _chmod_should_not_be_called(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("os.chmod should not be called when orig_mode is None")

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr("pitloom._embed_wheel.os.chmod", _chmod_should_not_be_called)

    embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)


def test_rewrite_wheel_archive_exception_when_temp_already_gone(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test the except-block's cleanup guard when temp_path no longer exists
    by the time an exception is raised mid-write."""
    wheel_path = _make_dummy_wheel(tmp_path, "vanishtemp", "1.0.0")

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("copy failed")

    with zipfile.ZipFile(wheel_path, "r") as original_zf:
        monkeypatch.setattr("pitloom._embed_wheel.shutil.copyfileobj", _boom)
        monkeypatch.setattr(Path, "exists", lambda self: False)
        with pytest.raises(RuntimeError, match="copy failed"):
            _rewrite_wheel_archive(
                wheel_path,
                original_zf,
                "vanishtemp-1.0.0.dist-info/sboms/x.spdx3.json",
                b"{}",
                "vanishtemp-1.0.0.dist-info/RECORD",
                b"",
                (2020, 1, 1, 0, 0, 0),
            )


def test_rewrite_wheel_archive_orig_mode_none(tmp_path: Path) -> None:
    """Test _rewrite_wheel_archive handles non-existent wheel path without error."""

    source_wheel = _make_dummy_wheel(tmp_path, "orig_mode_pkg", "1.0.0")
    target_wheel = tmp_path / "new_target.whl"

    with zipfile.ZipFile(source_wheel, "r") as original_zf:
        temp_path = _rewrite_wheel_archive(
            target_wheel,
            original_zf,
            "orig_mode_pkg-1.0.0.dist-info/sboms/sbom.spdx3.json",
            b"{}",
            "orig_mode_pkg-1.0.0.dist-info/RECORD",
            b"",
            (2026, 1, 1, 0, 0, 0),
        )
    assert temp_path.exists()
    temp_path.unlink()
