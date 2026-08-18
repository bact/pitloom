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

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from pitloom.extract._license import (
    _looks_like_spdx_license_expression,
    _with_tool_tag,
    canonicalize_license_id,
    detect_independent_license,
    detect_license_from_text,
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

    # Exception path returns raw
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


def test_find_license_files_oserror() -> None:
    """find_license_files returns empty list on OSError."""
    nonexistent = Path("/tmp/nonexistent_license_dir_12345")
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
