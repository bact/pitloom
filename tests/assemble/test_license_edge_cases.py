# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for license detection edge cases, tool tag formatting, and OS error handling.

See also:
- :mod:`tests.assemble.test_license_detection` for primary license detection suite.
- :mod:`tests.assemble.test_license_normalization` for expression normalization.
"""

# pylint: disable=protected-access

from __future__ import annotations

import importlib
import tempfile
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pitloom.extract._license as _license_module
import pitloom.extract._license_classify as _classify_module
from pitloom.extract._license import (
    _looks_like_spdx_license_expression,
    _with_tool_tag,
    canonicalize_license_id,
    detect_independent_license,
    detect_license_from_text,
    tag_license_normalization,
)
from pitloom.extract._license_detect import (
    _license_from_citation_cff,
    _license_from_codemeta_json,
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
    with patch("pitloom.extract._license_classify._PY_SPDX_LICENSE_VERSION", None):
        note = tag_license_normalization("Source: test", "mit", "MIT")
        assert "Normalized-From: mit" in note
        assert "Normalizer:" not in note

    with patch("pitloom.extract._license._LICENSEID_VERSION", None):
        res = _with_tool_tag("Source: test")
        assert res == "Source: test"


def test_find_license_files_oserror(tmp_path: Path) -> None:
    """find_license_files returns empty list on OSError."""
    nonexistent = tmp_path / "nonexistent_license_dir_12345"
    # pylint: disable-next=use-implicit-booleaness-not-comparison
    assert find_license_files(nonexistent) == []


@pytest.mark.parametrize(
    "raw",
    [b"title: My Project\nauthors:\n  - name: Arthit\n", b"\xff\xfe\x00\x00"],
    ids=["no-license-field", "not-utf8"],
)
def test_license_from_citation_cff_edge_cases(raw: bytes) -> None:
    """_license_from_citation_cff gives None without a field or for non-UTF-8."""
    assert _license_from_citation_cff(raw) is None


@pytest.mark.parametrize(
    "raw",
    [b'{"license": 12345}', b'{"license": unquoted', b'{"license": "\xff"}'],
    ids=["non-string", "malformed", "not-utf8"],
)
def test_license_from_codemeta_json_edge_cases(raw: bytes) -> None:
    """_license_from_codemeta_json handles non-string values and decode errors."""
    assert _license_from_codemeta_json(raw) is None


def test_collect_license_candidates_file_read_oserror() -> None:
    """collect_license_candidates handles OSError when reading license file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        lic = p / "LICENSE"
        lic.write_text("MIT License", encoding="utf-8")

        with patch.object(Path, "open", side_effect=OSError("disk error")):
            candidates = collect_license_candidates(p)
            assert len(candidates) == 0


def test_module_level_version_lookup_missing_packages() -> None:
    """_LICENSEID_VERSION/_PY_SPDX_LICENSE_VERSION fall back to None when the
    underlying distributions are not installed (PackageNotFoundError)."""

    def _raise(_name: str) -> str:
        raise PackageNotFoundError(_name)

    # Restore each namespace, not reload it again: a reload makes new classes
    # (``ClassifiedLicense``), which no longer equal instances other tests'
    # already-imported functions create.
    saved = [(m, dict(vars(m))) for m in (_classify_module, _license_module)]
    try:
        with patch("importlib.metadata.version", side_effect=_raise):
            importlib.reload(_classify_module)
            importlib.reload(_license_module)
            assert _license_module._LICENSEID_VERSION is None
            assert _classify_module._PY_SPDX_LICENSE_VERSION is None
    finally:
        for module, namespace in saved:
            vars(module).update(namespace)


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


def test_detect_license_from_text_empty_db_warns_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An empty database is warned about once per process, not per lookup."""
    empty = MagicMock()
    empty.match.return_value = []
    monkeypatch.setattr(_license_module, "_get_matcher", lambda: empty)
    _license_module._warn_empty_database.cache_clear()
    try:
        with caplog.at_level("WARNING", logger="pitloom.extract._license"):
            results = [
                _license_module.detect_license_from_text(text)
                for text in ("x" * 200, "y" * 200)
            ]
    finally:
        _license_module._warn_empty_database.cache_clear()

    assert results == [None, None]
    assert empty.match.call_count == 2
    assert sum("appears empty" in r.message for r in caplog.records) == 1
