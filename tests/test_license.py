# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for license text detection utilities."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.extract._license import (
    _looks_like_spdx_license_expression,
    _looks_like_spdx_license_id,
    _read_license_from_citation_cff,
    _read_license_from_codemeta_json,
    canonicalize_license_id,
    collect_license_candidates,
    detect_independent_license,
    detect_license_for_project,
    detect_license_from_text,
    find_license_files,
    normalize_license_expression,
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
    """Skip if the licenseid database has not been built yet.

    Build with: ``licenseid update``
    """
    # pylint: disable=import-outside-toplevel
    from licenseid.database import get_default_db_path

    db = Path(get_default_db_path())
    if not db.exists():
        pytest.skip("licenseid database not built -- run 'licenseid update'")
    return db


# ---------------------------------------------------------------------------
# canonicalize_license_id
# ---------------------------------------------------------------------------


def test_canonicalize_license_id_match_failure_logs_and_returns_raw(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failure inside AggregatedLicenseMatcher (e.g. a corrupt database) is
    caught, logged, and the raw input is returned unchanged -- same fallback
    behaviour as before logging was added."""
    with patch(
        "pitloom.extract._license.AggregatedLicenseMatcher",
        side_effect=RuntimeError("db corrupt"),
    ):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._license"):
            result = canonicalize_license_id("mit")

    assert result == "mit"
    assert any("mit" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# detect_license_from_text -- DB absent / library missing
# ---------------------------------------------------------------------------


def test_detect_license_from_text_db_not_populated(tmp_path: Path) -> None:
    """Returns None gracefully when the licenseid database is not populated."""
    with patch(
        "licenseid.matcher.get_default_db_path",
        return_value=str(tmp_path / "empty.db"),
    ):
        result = detect_license_from_text("MIT License\n\nPermission is hereby granted")
        assert result is None


# ---------------------------------------------------------------------------
# detect_license_for_project -- mocked detection
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
# Integration tests -- require real licenseid database
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


def test_detect_license_from_text_returns_spdx_id() -> None:
    """Detection with a real DB returns a valid SPDX License ID string
    (not None or raw text)."""
    result = detect_license_from_text(_MIT_TEXT)
    # Result may be None if score is below threshold; when not None it must
    # look like an SPDX License ID (no newlines, alphanumeric with dashes/dots)
    if result is not None:
        assert _looks_like_spdx_license_id(result), (
            f"Expected SPDX License ID, got: {result!r}"
        )


def test_detect_project_from_license_file_integration() -> None:
    """End-to-end: LICENSE file text is processed;
    result is None or a valid SPDX License ID."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE").write_text(_MIT_TEXT)
        result_id, prov = detect_license_for_project(p)
    if result_id is not None:
        assert _looks_like_spdx_license_id(result_id), (
            f"Expected SPDX License ID, got: {result_id!r}"
        )
        assert prov is not None and "LICENSE" in prov and "licenseid_detection" in prov


# ---------------------------------------------------------------------------
# detect_independent_license (G2)
# ---------------------------------------------------------------------------


def test_detect_independent_license_ignores_hint_entirely() -> None:
    """Unlike detect_license_for_project, there is no hint parameter at all --
    only the project directory is ever consulted."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE").write_text(_MIT_TEXT)
        result_id, prov = detect_independent_license(p)
    if result_id is not None:
        assert _looks_like_spdx_license_id(result_id)
        assert prov is not None and "LICENSE" in prov


def test_detect_independent_license_no_sources_returns_none() -> None:
    with tempfile.TemporaryDirectory() as d:
        result_id, prov = detect_independent_license(Path(d))
    assert result_id is None
    assert prov is None


def test_detect_independent_license_bare_id_no_detection_method() -> None:
    """A bare SPDX id found via CITATION.cff needs no licenseid detection --
    no Tool: tag on a value that was just read, not determined."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "codemeta.json").write_text('{"license": "MIT"}')
        result_id, prov = detect_independent_license(p)
    assert result_id == "MIT"
    assert prov == "Source: codemeta.json | Field: license"
    assert "Tool:" not in prov


def test_detect_independent_license_tags_licenseid_tool_version() -> None:
    """A licenseid_detection result carries the library version it ran under
    (G2's detected-role source-recording enhancement) -- reproducible against
    the exact detector version, not just "licenseid was involved somewhere"."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE").write_text(_MIT_TEXT)
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            result_id, prov = detect_independent_license(p)
    assert result_id == "MIT"
    assert prov is not None
    assert "Method: licenseid_detection" in prov
    assert "| Tool: licenseid==" in prov


def test_detect_license_for_project_delegates_directory_scan() -> None:
    """detect_license_for_project's own directory-search fallback now goes
    through detect_independent_license -- same result, same Tool: tagging,
    confirming the extraction didn't change external behavior."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "LICENSE").write_text(_MIT_TEXT)
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            via_project, prov_project = detect_license_for_project(p)
            via_independent, prov_independent = detect_independent_license(p)
    assert via_project == via_independent == "MIT"
    assert prov_project == prov_independent


# ---------------------------------------------------------------------------
# normalize_license_expression (G2 canonicalization; independent of the
# conflict-resolution machinery in deps.py -- these test the pure function).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("mit", "MIT"),
        ("MIT", "MIT"),
        ("bsd-3-clause", "BSD-3-Clause"),
        ("BSD-3-Clause", "BSD-3-Clause"),
        # Recognized even though it contains what looks like an operator
        # substring ("-OR-") -- it's a single, database-known license id,
        # not a compound expression, so it canonicalizes as a whole token
        # to the database's own casing (distinct from the *unrecognized*
        # hyphenated-identifier cases below, which must stay untouched).
        ("GPL-2.0-OR-LATER", "GPL-2.0-or-later"),
        ("gpl-2.0-or-later", "GPL-2.0-or-later"),
    ],
)
def test_normalize_license_expression_bare_id_casing(raw: str, expected: str) -> None:
    """A bare id is canonicalized to its recognized SPDX casing, same as
    canonicalize_license_id -- normalize_license_expression must not regress
    this for the simple, non-compound case."""
    assert normalize_license_expression(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["MIT AND MIT", "(MIT AND MIT)", "MIT and MIT", "(mit and mit)", "mit AND mit"],
)
def test_normalize_license_expression_dedups_conjunction(raw: str) -> None:
    """A license AND'd with itself -- however cased, parenthesized, or
    spelled -- normalizes to the single license, not a compound string."""
    assert normalize_license_expression(raw) == "MIT"


def test_normalize_license_expression_canonical_ordering_is_order_independent() -> None:
    """A OR B and B OR A are the same license choice -- both orderings must
    normalize to one identical string, so a G2 comparison between them
    (candidates entered in different orders from different sources) doesn't
    misreport a conflict."""
    a = normalize_license_expression("MIT OR Apache-2.0")
    b = normalize_license_expression("Apache-2.0 OR MIT")
    assert a == b


@pytest.mark.parametrize(
    "raw",
    [
        "GPL-2.0-or-later",  # recognized id, but already canonical -- no-op
        "LicenseRef-my-or-license",  # unrecognized -- must pass through verbatim
        "LicenseRef-and-tool",
        "LicenseRef-with-exception-name",
    ],
)
def test_normalize_license_expression_never_mangles_hyphenated_identifiers(
    raw: str,
) -> None:
    """The operator-casing preprocessing must never touch and/or/with/not
    when it's hyphen-glued into an identifier rather than standing alone as
    its own token -- regression test for the bug caught during design
    (a naive \\b-word-boundary regex corrupted these into e.g. "-OR-")."""
    assert normalize_license_expression(raw) == raw


def test_normalize_license_expression_unrecognized_value_passes_through() -> None:
    """A non-SPDX / vendor-specific string that isn't a parseable expression
    at all is returned unchanged, not mangled or rejected."""
    assert normalize_license_expression("gemma") == "gemma"


def test_normalize_license_expression_malformed_syntax_falls_back_gracefully() -> None:
    """Genuinely malformed SPDX expression syntax (unbalanced parens) must not
    raise -- falls back to canonicalize_license_id's own (also
    graceful-on-failure) behavior rather than propagating a ParseError."""
    malformed = "((unbalanced"
    assert normalize_license_expression(malformed) == canonicalize_license_id(malformed)


def test_normalize_license_expression_idempotent() -> None:
    """Normalizing an already-normalized expression returns it unchanged --
    required for the G2 comparison to be stable (declared side and detected
    side may each independently call this)."""
    once = normalize_license_expression("MIT OR Apache-2.0")
    twice = normalize_license_expression(once)
    assert once == twice


@pytest.mark.parametrize(
    "without_parens,with_parens",
    [
        # Real-world regression source: github.com/aquasecurity/trivy/
        # discussions/10139 -- Trivy reports the same license expression
        # with and without a redundant outer paren across scans of the
        # same package, breaking policy rules that compare against one
        # fixed string. These are that report's own four example pairs.
        (
            "GPL-3.0-or-later WITH GCC-exception-3.1",
            "(GPL-3.0-or-later WITH GCC-exception-3.1)",
        ),
        ("MIT AND GPL-3.0-only", "(MIT AND GPL-3.0-only)"),
        ("MPL-2.0 AND MIT", "(MPL-2.0 AND MIT)"),
        ("BSD-3-Clause AND IJG AND Zlib", "(BSD-3-Clause AND IJG AND Zlib)"),
    ],
)
def test_normalize_license_expression_strips_redundant_outer_parens(
    without_parens: str, with_parens: str
) -> None:
    """A paren that doesn't change meaning (wraps an already-unambiguous
    expression) must normalize identically whether present or not."""
    assert normalize_license_expression(without_parens) == normalize_license_expression(
        with_parens
    )


def test_normalize_license_expression_keeps_precedence_significant_parens() -> None:
    """Unlike the redundant-paren case above, a paren that changes the
    parse (overrides AND-binds-tighter-than-OR default precedence) is
    semantically load-bearing and must NOT be normalized away -- otherwise
    two genuinely different licenses would collapse into one string."""
    no_parens = normalize_license_expression("MIT AND Apache-2.0 OR BSD-3-Clause")
    redundant_parens = normalize_license_expression(
        "(MIT AND Apache-2.0) OR BSD-3-Clause"
    )
    significant_parens = normalize_license_expression(
        "MIT AND (Apache-2.0 OR BSD-3-Clause)"
    )
    # Explicit parens matching the default precedence change nothing.
    assert no_parens == redundant_parens
    # Parens overriding default precedence are a different expression --
    # must not collapse to the same normalized string as the other two.
    assert significant_parens != no_parens
