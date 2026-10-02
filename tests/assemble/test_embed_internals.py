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
from types import SimpleNamespace
from typing import Any

import pytest
from installer.sources import WheelFile

from pitloom.core.wheel_dist_info import PROBLEM_NONE, PROBLEM_SEVERAL_NONE_MATCH
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
from pitloom.plugins.hatch import _default_sbom_basename

from .conftest import _SAMPLE_SPDX3_JSON, _make_dummy_wheel


def test_find_dist_info_prefix_edge_cases(tmp_path: Path) -> None:
    """Test _find_dist_info_prefix with single, matching, and ambiguous dist-infos."""
    # 1. No dist-info
    p1 = tmp_path / "nodist-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p1, "w") as zf:
        zf.writestr("nodist/module.py", "# code")
    with zipfile.ZipFile(p1, "r") as zf:
        with pytest.raises(ValueError, match=PROBLEM_NONE):
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
        with pytest.raises(ValueError, match=PROBLEM_SEVERAL_NONE_MATCH):
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


def test_embed_wheel_sbom_not_found(tmp_path: Path) -> None:
    """Test that embedding into a non-existent wheel
    raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        embed_wheel_sbom(tmp_path / "does_not_exist.whl")


def test_embed_sbom_in_wheel_corrupt_zip_raises_value_error(tmp_path: Path) -> None:
    """A wheel that isn't a valid ZIP -> ValueError, not zipfile.BadZipFile.

    embed_sbom_in_wheel shares open_wheel_zip with find_embedded_sbom
    (see test_validate_wheel_corrupt_zip_errors), so it inherits the same
    BadZipFile -> refusal normalization."""
    corrupt_wheel = tmp_path / "notazip-1.0.0-py3-none-any.whl"
    corrupt_wheel.write_bytes(b"not a zip file at all")
    with pytest.raises(ValueError, match="wheel refused"):
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


@pytest.mark.parametrize(
    ("name", "version", "expected"),
    [
        ("x\n", "1", "x_-1.spdx3.json"),
        ("ev\x1b[31mil\n x", "1.0", "ev_[31mil__x-1.0.spdx3.json"),
        ("my pkg", "1.0\x7f\u0085", "my_pkg-1.0__.spdx3.json"),
        ("a/b\\c:d", "1", "a_b_c_d-1.spdx3.json"),
        # Format characters (category Cf: bidi override, zero-width space).
        ("a\u202eb\u200bc", "1", "a_b_c-1.spdx3.json"),
        # Already safe: unchanged, as before escaping existed.
        ("my-pkg", "1.0+local", "my-pkg-1.0+local.spdx3.json"),
        # The longest name an installer accepts (255), and one more: the
        # directory's own name instead.
        ("a" * 242, "1", "a" * 242 + "-1.spdx3.json"),
        ("a" * 243, "1", "pkg-1.0.spdx3.json"),
        ("my-pkg", "1" * 5000, "pkg-1.0.spdx3.json"),
    ],
    ids=[
        "newline",
        "escape-and-folded",
        "space-del-c1",
        "separators",
        "format-characters",
        "safe",
        "name-255-chars",
        "name-256-chars",
        "version-5000-digits",
    ],
)
def test_the_default_sbom_name_replaces_only_what_is_unsafe_in_a_file_name(
    tmp_path: Path, name: str, version: str, expected: str
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "pkg", "1.0")

    _, arcname, _, _ = embed_sbom_in_wheel(wheel, b"{}", identity=(name, version))

    assert arcname == f"pkg-1.0.dist-info/sboms/{expected}"


def test_the_default_sbom_name_of_a_safe_name_is_the_hatchling_hooks(
    tmp_path: Path,
) -> None:
    hatch = SimpleNamespace(
        core=SimpleNamespace(raw_name="my-pkg"), version="1.0+local"
    )
    wheel = _make_dummy_wheel(tmp_path, "pkg", "1.0")

    arcname = embed_sbom_in_wheel(wheel, b"{}", identity=("my-pkg", "1.0+local"))[1]

    assert arcname.rsplit("/", 1)[1] == f"{_default_sbom_basename(hatch)}.spdx3.json"


@pytest.mark.parametrize(
    ("dist_info", "metadata", "expected"),
    [
        # A folded header value, and the fallback to the directory's own name
        # where METADATA names nothing: both escaped.
        ("pkg-1.0", "Name: ev\x1b[31mil\n x\nVersion: 1.0\n", "ev_[31mil__x-1.0"),
        ("ev\x1b[31mil one", "Summary: no name\n", "ev_[31mil_one"),
    ],
    ids=["folded-name", "fallback-prefix"],
)
def test_the_default_sbom_name_from_a_wheels_own_metadata_is_escaped(
    tmp_path: Path, dist_info: str, metadata: str, expected: str
) -> None:
    wheel = tmp_path / "pkg-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(f"{dist_info}.dist-info/METADATA", metadata)

    arcname = embed_sbom_in_wheel(wheel, b"{}")[1]

    assert arcname == f"{dist_info}.dist-info/sboms/{expected}.spdx3.json"


@pytest.mark.parametrize("unlink_fails", [False, True])
def test_an_interrupted_rewrite_leaves_no_temporary_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, unlink_fails: bool
) -> None:
    """The interrupt itself propagates, even where the cleanup fails."""
    wheel = _make_dummy_wheel(tmp_path, "intpkg", "1.0.0")
    before = wheel.read_bytes()

    def interrupted(*_args: Any) -> None:
        raise KeyboardInterrupt

    def unlink_refused(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("busy")

    monkeypatch.setattr("pitloom._embed_wheel.RefusingReader", interrupted)
    if unlink_fails:
        monkeypatch.setattr(Path, "unlink", unlink_refused)

    with pytest.raises(KeyboardInterrupt):
        embed_sbom_in_wheel(wheel, b"{}")

    assert wheel.read_bytes() == before
    assert unlink_fails or not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    ("target", "error"),
    [
        ("zipfile.ZipFile.writestr", RuntimeError("archive write failed")),
        # e.g. Windows: the wheel is in use.
        ("os.replace", PermissionError("file in use")),
    ],
    ids=["writestr", "replace"],
)
def test_a_failed_rewrite_leaves_no_temporary_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, target: str, error: Exception
) -> None:
    wheel_path = _make_dummy_wheel(tmp_path, "cleanuppkg", "1.0.0")

    def _fail(*_args: Any, **_kwargs: Any) -> None:
        raise error

    monkeypatch.setattr(target, _fail)
    with pytest.raises(type(error), match=str(error)):
        embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)

    assert not list(tmp_path.glob("*.tmp"))


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


@pytest.mark.parametrize(
    "content",
    [b"{not valid json", b'{"@graph": "not-a-list"}', b"{}"],
    ids=["invalid-json", "graph-not-a-list", "no-graph"],
)
def test_looks_like_pitloom_sbom_rejects(content: bytes) -> None:
    assert _looks_like_pitloom_sbom(content) is False


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
