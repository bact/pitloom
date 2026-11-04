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
from unittest.mock import patch

import pytest

import pitloom.extract._license as _license_module
from pitloom.extract import _license_detect
from pitloom.extract._license import (
    _with_tool_tag,
    detect_independent_license,
)
from pitloom.extract._license_detect import (
    _license_from_citation_cff,
    _license_from_codemeta_json,
    _looks_like_spdx_license_expression,
    collect_license_candidates,
    find_license_files,
)


def test_looks_like_spdx_license_expression_newlines_and_length() -> None:
    """_looks_like_spdx_license_expression rejects newlines and long strings."""
    assert not _looks_like_spdx_license_expression("MIT OR\nApache-2.0")
    assert not _looks_like_spdx_license_expression("MIT OR " + ("Apache-2.0 " * 30))


def test_tool_tag_without_a_version() -> None:
    """_with_tool_tag handles a None version gracefully."""
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

        with patch.object(
            _license_detect, "open_inside", side_effect=OSError("disk error")
        ):
            candidates = collect_license_candidates(p)
            assert len(candidates) == 0


def test_module_level_version_lookup_missing_packages() -> None:
    """_LICENSEID_VERSION falls back to None when the distribution is not
    installed (PackageNotFoundError)."""

    def _raise(_name: str) -> str:
        raise PackageNotFoundError(_name)

    # Restore each namespace, not reload it again: a reload makes new classes
    # (``ClassifiedLicense``), which do not equal instances other tests'
    # already-imported functions create.
    saved = [(m, dict(vars(m))) for m in (_license_module,)]
    try:
        with patch("importlib.metadata.version", side_effect=_raise):
            importlib.reload(_license_module)
            assert _license_module._LICENSEID_VERSION is None
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
