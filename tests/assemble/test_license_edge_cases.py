# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for license detection edge cases, tool tag formatting, and OS error handling.

See also:
- :mod:`tests.assemble.test_license_detection` for primary license detection suite.
- :mod:`tests.assemble.test_license_normalization` for expression normalization.
"""

from __future__ import annotations

import importlib
import tempfile
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pitloom.extract._license as _license_module
from pitloom.extract._license import (
    _looks_like_spdx_license_expression,
    _with_tool_tag,
    canonicalize_license_id,
    detect_independent_license,
    detect_license_from_text,
    resolve_license_file_entries,
    tag_license_normalization,
)
from pitloom.extract._license_detect import (
    _read_license_from_citation_cff,
    _read_license_from_codemeta_json,
    collect_license_candidates,
    find_license_files,
)


def test_looks_like_spdx_license_expression_newlines_and_length() -> None:
    """_looks_like_spdx_license_expression rejects newlines and long strings."""
    assert not _looks_like_spdx_license_expression("MIT OR\nApache-2.0")
    assert not _looks_like_spdx_license_expression("MIT OR " + ("Apache-2.0 " * 30))


def test_detect_license_from_text_exception_handling() -> None:
    """detect_license_from_text catches matcher exceptions and returns None."""
    with patch(
        "pitloom.extract._license.AggregatedLicenseMatcher",
        side_effect=RuntimeError("matcher error"),
    ):
        assert detect_license_from_text("some license text") is None


def test_canonicalize_license_id_match_and_exception() -> None:
    """canonicalize_license_id returns canonical ID or raw on match/exception."""
    mock_matcher = MagicMock()
    mock_matcher.match.return_value = [{"license_id": "MIT"}]
    with patch(
        "pitloom.extract._license.AggregatedLicenseMatcher",
        return_value=mock_matcher,
    ):
        assert canonicalize_license_id("mit") == "MIT"

    # Exception path returns raw. Clear the cache first, or _get_matcher's
    # lru_cache would still return the block above's mock_matcher.
    _license_module._get_matcher.cache_clear()
    mock_err_matcher = MagicMock()
    mock_err_matcher.match.side_effect = RuntimeError("fail")
    with patch(
        "pitloom.extract._license.AggregatedLicenseMatcher",
        return_value=mock_err_matcher,
    ):
        assert canonicalize_license_id("custom-raw") == "custom-raw"


def test_tag_license_normalization_and_tool_tags_without_versions() -> None:
    """tag_license_normalization and _with_tool_tag handle None version gracefully."""
    with patch("pitloom.extract._license._PY_SPDX_LICENSE_VERSION", None):
        note = tag_license_normalization("Source: test", "mit", "MIT")
        assert "Normalized-From: mit" in note
        assert "Normalizer:" not in note

    with patch("pitloom.extract._license._LICENSEID_VERSION", None):
        res = _with_tool_tag("Source: test")
        assert res == "Source: test"


def test_find_license_files_oserror(tmp_path: Path) -> None:
    """find_license_files returns empty list on OSError."""
    nonexistent = tmp_path / "nonexistent_license_dir_12345"
    assert find_license_files(nonexistent) == []


def test_read_license_from_citation_cff_edge_cases() -> None:
    """_read_license_from_citation_cff handles unparseable CFF and OS errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        cff = p / "CITATION.cff"
        cff.write_text(
            "title: My Project\nauthors:\n  - name: Arthit\n", encoding="utf-8"
        )
        assert _read_license_from_citation_cff(p) is None

        # Unicode decode error simulation
        cff.write_bytes(b"\xff\xfe\x00\x00")
        assert _read_license_from_citation_cff(p) is None


def test_read_license_from_codemeta_json_edge_cases() -> None:
    """_read_license_from_codemeta_json handles non-string values and decode errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        cm = p / "codemeta.json"
        cm.write_text('{"license": 12345}', encoding="utf-8")
        assert _read_license_from_codemeta_json(p) is None

        # Malformed JSON
        cm.write_text('{"license": unquoted', encoding="utf-8")
        assert _read_license_from_codemeta_json(p) is None


def test_collect_license_candidates_file_read_oserror() -> None:
    """collect_license_candidates handles OSError when reading license file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        lic = p / "LICENSE"
        lic.write_text("MIT License", encoding="utf-8")

        with patch.object(Path, "read_text", side_effect=OSError("disk error")):
            candidates = collect_license_candidates(p)
            assert len(candidates) == 0


def test_module_level_version_lookup_missing_packages() -> None:
    """_LICENSEID_VERSION/_PY_SPDX_LICENSE_VERSION fall back to None when the
    underlying distributions are not installed (PackageNotFoundError)."""

    def _raise(_name: str) -> str:
        raise PackageNotFoundError(_name)

    try:
        with patch("importlib.metadata.version", side_effect=_raise):
            importlib.reload(_license_module)
            assert _license_module._LICENSEID_VERSION is None
            assert _license_module._PY_SPDX_LICENSE_VERSION is None
    finally:
        importlib.reload(_license_module)


def test_collect_license_candidates_skips_blank_file_and_continues() -> None:
    """collect_license_candidates skips a whitespace-only license file and keeps
    scanning subsequent license files instead of stopping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        (p / "LICENSE").write_text("   \n  \n", encoding="utf-8")
        (p / "COPYING").write_text("MIT License text", encoding="utf-8")

        candidates = collect_license_candidates(p)
        assert len(candidates) == 1
        assert candidates[0][0] == "MIT License text"


def test_resolve_license_file_entries_escapes_hyphenated_name(
    tmp_path: Path,
) -> None:
    """`distribution_path` must match real wheel dist-info naming: PEP 503
    normalize then replace ``-`` with ``_`` (the current Binary Distribution
    Format spec's escaping rule, which superseded PEP 427's on this point in
    2021) -- not PEP 503 normalization alone, which would leave the hyphen
    in place and never match a real wheel's `.dist-info/` directory name.
    Regression test: verified against the real published wheel filename for
    `pytest-asyncio` (`pytest_asyncio-1.4.0.dist-info/...`)."""
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")

    entries = resolve_license_file_entries(
        tmp_path, "pytest-asyncio", "1.4.0", ["LICENSE"]
    )

    assert len(entries) == 1
    assert entries[0].distribution_path == (
        "pytest_asyncio-1.4.0.dist-info/licenses/LICENSE"
    )


def test_resolve_license_file_entries_uppercase_name_lowercased(
    tmp_path: Path,
) -> None:
    """A mixed-case declared name (e.g. `MarkupSafe`) must lowercase in the
    dist-info path, matching the real published wheel
    (`markupsafe-3.0.3.dist-info/...`, not `MarkupSafe-3.0.3.dist-info/...`)."""
    (tmp_path / "LICENSE.txt").write_text("BSD-3-Clause", encoding="utf-8")

    entries = resolve_license_file_entries(
        tmp_path, "MarkupSafe", "3.0.3", ["LICENSE.txt"]
    )

    assert len(entries) == 1
    assert entries[0].distribution_path == (
        "markupsafe-3.0.3.dist-info/licenses/LICENSE.txt"
    )


def test_resolve_license_file_entries_unresolved_version_skips_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An unresolved (``None``) version has no real wheel filename to derive
    a `.dist-info/` path from -- every declared entry must be skipped with a
    `WARNING:`, never fabricated (e.g. as a placeholder version)."""
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")

    with caplog.at_level("WARNING", logger="pitloom.extract._license"):
        entries = resolve_license_file_entries(tmp_path, "pkg", None, ["LICENSE"])

    assert entries == []
    assert "pkg" in caplog.text
    assert "version could not be resolved" in caplog.text


def test_resolve_license_file_entries_dedups_repeated_path(
    tmp_path: Path,
) -> None:
    """A ``license_files`` list with the same path declared twice (e.g. two
    overlapping glob patterns both matching ``LICENSE``) must produce exactly
    one ``ProjectFile``, not a duplicate ``software_File`` element downstream."""
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")

    entries = resolve_license_file_entries(
        tmp_path, "pkg", "1.0.0", ["LICENSE", "LICENSE"]
    )

    assert len(entries) == 1
    assert entries[0].physical_path == "LICENSE"


def test_resolve_license_file_entries_unreadable_file_skips_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A declared entry that can't be read (e.g. it's a directory, not a
    file) must be skipped with a `WARNING:` naming the entry, and must not
    stop the remaining entries from being processed."""
    (tmp_path / "LICENSE").mkdir()
    (tmp_path / "NOTICE").write_text("Copyright notice", encoding="utf-8")

    with caplog.at_level("WARNING", logger="pitloom.extract._license"):
        entries = resolve_license_file_entries(
            tmp_path, "pkg", "1.0.0", ["LICENSE", "NOTICE"]
        )

    assert len(entries) == 1
    assert entries[0].physical_path == "NOTICE"
    assert "LICENSE" in caplog.text
    assert "could not read declared license-files entry" in caplog.text


def test_detect_independent_license_loop_continuation() -> None:
    """detect_independent_license skips unrecognized text candidates until match."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        lic1 = p / "LICENSE"
        lic1.write_text("Some random non-license text", encoding="utf-8")

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value=None,
        ):
            detected, prov = detect_independent_license(p)
            assert detected is None
            assert prov is None
