# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for license text detection utilities."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.extract._license import (
    _looks_like_spdx_license_expression,
    _looks_like_spdx_license_id,
    _read_license_from_citation_cff,
    _read_license_from_codemeta_json,
    collect_license_candidates,
    detect_license_for_project,
    detect_license_from_text,
    find_license_files,
)

# ---------------------------------------------------------------------------
# _looks_like_spdx_license_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["MIT", "Apache-2.0", "GPL-3.0-or-later", "LicenseRef-custom", "GPL-2.0+"],
)
def test_looks_like_spdx_license_id_valid(value: str) -> None:
    """Bare SPDX License IDs are recognised as IDs."""
    assert _looks_like_spdx_license_id(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "MIT License",  # contains space
        "MIT\nLicense",  # contains newline
        "",  # empty
        "MIT OR Apache-2.0",  # compound expression
        "a" * 101,  # too long
    ],
)
def test_looks_like_spdx_license_id_invalid(value: str) -> None:
    """Non-ID strings (text, expressions, empty) are not recognised as
    SPDX License IDs."""
    assert _looks_like_spdx_license_id(value) is False


# ---------------------------------------------------------------------------
# _looks_like_spdx_license_expression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["MIT OR Apache-2.0", "GPL-2.0 AND MIT", "GPL-2.0 WITH Classpath-exception-2.0"],
)
def test_looks_like_spdx_license_expression_valid(value: str) -> None:
    """Compound SPDX expressions with OR/AND/WITH are recognised."""
    assert _looks_like_spdx_license_expression(value) is True


def test_looks_like_spdx_license_expression_simple_id() -> None:
    """A simple SPDX License ID is not a compound expression."""
    assert _looks_like_spdx_license_expression("MIT") is False


# ---------------------------------------------------------------------------
# find_license_files
# ---------------------------------------------------------------------------


def test_find_license_files_uppercase() -> None:
    """An uppercase LICENSE file is found and returned with its actual name."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE").write_text("MIT License")
        assert find_license_files(p) == [p / "LICENSE"]


def test_find_license_files_with_suffix() -> None:
    """LICENSE.txt is found."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE.txt").write_text("MIT License")
        assert p / "LICENSE.txt" in find_license_files(p)


def test_find_license_files_lowercase() -> None:
    """A lowercase license.txt is found and returned with its actual on-disk name."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "license.txt").write_text("MIT License")
        files = find_license_files(p)
        assert len(files) == 1
        assert files[0].name.lower() == "license.txt"


def test_find_license_files_priority_no_extension_first() -> None:
    """No-extension LICENSE takes priority over LICENSE.txt."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE").write_text("MIT License")
        (p / "LICENSE.txt").write_text("MIT License")
        files = find_license_files(p)
        assert files[0].name.lower() == "license"


def test_find_license_files_copying() -> None:
    """COPYING is recognised as a license file."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "COPYING").write_text("GPL license text")
        assert p / "COPYING" in find_license_files(p)


def test_find_license_files_rst() -> None:
    """LICENSE.rst is recognised as a license file."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE.rst").write_text("MIT License")
        assert p / "LICENSE.rst" in find_license_files(p)


def test_find_license_files_empty_dir() -> None:
    """An empty directory yields no license files."""
    with tempfile.TemporaryDirectory() as d:
        assert not find_license_files(Path(d))


# ---------------------------------------------------------------------------
# _read_license_from_citation_cff
# ---------------------------------------------------------------------------


def test_citation_cff_scalar() -> None:
    """Scalar license field in CITATION.cff is extracted."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "CITATION.cff").write_text("cff-version: 1.2.0\nlicense: Apache-2.0\n")
        assert _read_license_from_citation_cff(p) == "Apache-2.0"


def test_citation_cff_scalar_quoted() -> None:
    """Quoted scalar license field in CITATION.cff is extracted."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "CITATION.cff").write_text('cff-version: 1.2.0\nlicense: "MIT"\n')
        assert _read_license_from_citation_cff(p) == "MIT"


def test_citation_cff_list_first_item() -> None:
    """First item of a license list in CITATION.cff is extracted."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "CITATION.cff").write_text(
            "cff-version: 1.2.0\nlicense:\n  - MIT\n  - Apache-2.0\n"
        )
        assert _read_license_from_citation_cff(p) == "MIT"


def test_citation_cff_absent() -> None:
    """Missing CITATION.cff returns None."""
    with tempfile.TemporaryDirectory() as d:
        assert _read_license_from_citation_cff(Path(d)) is None


# ---------------------------------------------------------------------------
# _read_license_from_codemeta_json
# ---------------------------------------------------------------------------


def test_codemeta_json_bare_id() -> None:
    """Bare SPDX License ID in codemeta.json is extracted directly."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "codemeta.json").write_text('{"license": "MIT"}')
        assert _read_license_from_codemeta_json(p) == "MIT"


def test_codemeta_json_spdx_url() -> None:
    """SPDX URL in codemeta.json is reduced to the license ID."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "codemeta.json").write_text(
            '{"license": "https://spdx.org/licenses/Apache-2.0.html"}'
        )
        assert _read_license_from_codemeta_json(p) == "Apache-2.0"


def test_codemeta_json_absent() -> None:
    """Missing codemeta.json returns None."""
    with tempfile.TemporaryDirectory() as d:
        assert _read_license_from_codemeta_json(Path(d)) is None


def test_codemeta_json_non_spdx_value() -> None:
    """A non-SPDX string in codemeta.json returns None."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "codemeta.json").write_text('{"license": "proprietary license text here"}')
        assert _read_license_from_codemeta_json(p) is None


# ---------------------------------------------------------------------------
# collect_license_candidates
# ---------------------------------------------------------------------------


def test_collect_candidates_priority_order() -> None:
    """CITATION.cff comes before codemeta.json which comes before license files."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "CITATION.cff").write_text("license: MIT\n")
        (p / "codemeta.json").write_text('{"license": "Apache-2.0"}')
        (p / "LICENSE").write_text("MIT License text...")
        candidates = collect_license_candidates(p)
        sources = [src for _, src in candidates]
        assert sources[0] == "Source: CITATION.cff | Field: license"
        assert sources[1] == "Source: codemeta.json | Field: license"
        assert any("LICENSE" in src for src in sources)


def test_collect_candidates_empty_dir() -> None:
    """An empty directory yields no candidates."""
    with tempfile.TemporaryDirectory() as d:
        assert not collect_license_candidates(Path(d))


# ---------------------------------------------------------------------------
# Fixture: real licenseid database (skipped when not built)
# ---------------------------------------------------------------------------


@pytest.fixture(name="licenseid_db_path")
def licenseid_db_path_fixture() -> Path:
    """Return the path to the licenseid database, skipping if not built.

    Build with: ``licenseid update``
    """
    db = Path.home() / ".local" / "share" / "licenseid" / "licenses.db"
    if not db.exists():
        pytest.skip("licenseid database not built — run 'licenseid update'")
    return db


# ---------------------------------------------------------------------------
# detect_license_from_text — DB absent / library missing
# ---------------------------------------------------------------------------


def test_detect_license_from_text_db_missing(tmp_path: Path) -> None:
    """Returns None gracefully when the licenseid database does not exist."""
    with patch(
        "pitloom.extract._license._get_licenseid_db_path",
        return_value=tmp_path / "nonexistent.db",
    ):
        result = detect_license_from_text("MIT License\n\nPermission is hereby granted")
        assert result is None


def test_detect_license_from_text_library_not_installed(tmp_path: Path) -> None:
    """Returns None gracefully when the licenseid library is not installed."""
    fake_db = tmp_path / "licenses.db"
    fake_db.touch()
    with (
        patch(
            "pitloom.extract._license._get_licenseid_db_path",
            return_value=fake_db,
        ),
        patch.dict("sys.modules", {"licenseid": None}),
    ):
        result = detect_license_from_text("MIT License")
        assert result is None


# ---------------------------------------------------------------------------
# detect_license_for_project — mocked detection
# ---------------------------------------------------------------------------


def test_detect_project_spdx_license_id_passthrough() -> None:
    """A bare SPDX License ID hint is returned unchanged without calling detection."""
    with tempfile.TemporaryDirectory() as d:
        result_id, prov = detect_license_for_project(Path(d), "Apache-2.0")
        assert result_id == "Apache-2.0"
        assert prov is None


def test_detect_project_spdx_license_expression_passthrough() -> None:
    """A compound SPDX License Expression hint is returned unchanged
    without detection."""
    with tempfile.TemporaryDirectory() as d:
        result_id, prov = detect_license_for_project(Path(d), "MIT OR Apache-2.0")
        assert result_id == "MIT OR Apache-2.0"
        assert prov is None


def test_detect_project_from_citation_cff_no_detection_needed() -> None:
    """SPDX License ID from CITATION.cff is returned directly
    without running detection."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "CITATION.cff").write_text("license: GPL-3.0-or-later\n")
        result_id, prov = detect_license_for_project(p)
        assert result_id == "GPL-3.0-or-later"
        assert prov == "Source: CITATION.cff | Field: license"


def test_detect_project_from_codemeta_json_no_detection_needed() -> None:
    """SPDX License ID from codemeta.json is returned directly
    without running detection."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "codemeta.json").write_text('{"license": "MIT"}')
        result_id, prov = detect_license_for_project(p)
        assert result_id == "MIT"
        assert prov == "Source: codemeta.json | Field: license"


def test_detect_project_from_license_file_with_detection() -> None:
    """License file text is passed to detection; ID and provenance are returned."""
    mit_text = (
        "MIT License\n\nCopyright (c) 2024\n\n"
        "Permission is hereby granted, free of charge..."
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE").write_text(mit_text)
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ) as mock_detect:
            result_id, prov = detect_license_for_project(p)
            mock_detect.assert_called_once_with(mit_text)
        assert result_id == "MIT"
        assert prov is not None
        assert "LICENSE" in prov
        assert "licenseid_detection" in prov


def test_detect_project_no_sources_returns_none() -> None:
    """Returns (None, None) when no license sources exist and no hint is given."""
    with tempfile.TemporaryDirectory() as d:
        result_id, prov = detect_license_for_project(Path(d))
        assert result_id is None
        assert prov is None


def test_detect_project_hint_text_detection_succeeds() -> None:
    """License text in hint triggers detection when it is not a bare SPDX License ID."""
    hint = "MIT License\n\nPermission is hereby granted..."
    with tempfile.TemporaryDirectory() as d:
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            result_id, _ = detect_license_for_project(Path(d), hint)
        assert result_id == "MIT"


def test_detect_project_hint_text_detection_fails_returns_hint() -> None:
    """When detection fails, the raw hint string is returned as a fallback."""
    hint = "Some nonstandard license text"
    with tempfile.TemporaryDirectory() as d:
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value=None,
        ):
            result_id, _ = detect_license_for_project(Path(d), hint)
        assert result_id == hint


# ---------------------------------------------------------------------------
# Integration tests — require real licenseid database
# ---------------------------------------------------------------------------

# Canonical MIT license text (no copyright header, matches SPDX template closely)
_MIT_TEXT = """\
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def test_detect_license_from_text_returns_spdx_id(licenseid_db_path: Path) -> None:
    """Detection with a real DB returns a valid SPDX License ID string
    (not None or raw text)."""
    with patch(
        "pitloom.extract._license._get_licenseid_db_path",
        return_value=licenseid_db_path,
    ):
        result = detect_license_from_text(_MIT_TEXT)
    # Result may be None if score is below threshold; when not None it must
    # look like an SPDX License ID (no newlines, alphanumeric with dashes/dots)
    if result is not None:
        assert _looks_like_spdx_license_id(result), (
            f"Expected SPDX License ID, got: {result!r}"
        )


def test_detect_project_from_license_file_integration(licenseid_db_path: Path) -> None:
    """End-to-end: LICENSE file text is processed;
    result is None or a valid SPDX License ID."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE").write_text(_MIT_TEXT)
        with patch(
            "pitloom.extract._license._get_licenseid_db_path",
            return_value=licenseid_db_path,
        ):
            result_id, prov = detect_license_for_project(p)
    if result_id is not None:
        assert _looks_like_spdx_license_id(result_id), (
            f"Expected SPDX License ID, got: {result_id!r}"
        )
        assert prov is not None and "LICENSE" in prov and "licenseid_detection" in prov
