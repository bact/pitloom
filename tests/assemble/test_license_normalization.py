# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration tests against the real licenseid database, plus tests for
G2 license canonicalization (``detect_independent_license``,
``normalize_license_expression``) and its provenance tagging.

See also: test_license_detection.py -- this module's sibling, split from
the original test_license.py.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.extract._license import (
    _PY_SPDX_LICENSE_VERSION,
    _looks_like_spdx_license_id,
    canonicalize_license_id,
    detect_independent_license,
    detect_license_for_project,
    detect_license_from_text,
    normalize_license_expression,
    tag_license_normalization,
)

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


def test_detect_license_from_text_rejects_short_label() -> None:
    """Regression: a short license *label* (not a real license body) must
    not be fuzzy-matched at all -- found via real-world validation
    against pipenv 2026.8.0, whose ``[project.license].text = "MIT
    License (MIT)"`` (18 characters) previously scored a false-positive
    match against an unrelated SPDX ID ("AML") purely by coincidental
    short-string similarity. Real SPDX license texts are always much
    longer than this, so the length guard in
    ``detect_license_from_text()`` only ever excludes non-license-body
    input like this."""
    assert detect_license_from_text("MIT License (MIT)") is None


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


@pytest.mark.parametrize("malformed", [")", ")(", "A)", ")A", "))"])
def test_normalize_license_expression_unbalanced_close_paren_falls_back(
    malformed: str,
) -> None:
    """A ")" with no matching "(" before it must not raise, even though
    py-spdx-license itself raises IndexError (not its own ParseError) for
    this specific shape -- found by fuzzing (fuzz/fuzz_license_expression.py)
    within seconds of random input. This function's contract is "never
    raises for any string," so any parser failure, documented or not,
    takes the same graceful fallback as the "((unbalanced" case above."""
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


# ---------------------------------------------------------------------------
# tag_license_normalization
# ---------------------------------------------------------------------------


def test_tag_license_normalization_noop_when_unchanged() -> None:
    """No normalization happened (raw already canonical): provenance is
    returned unchanged, nothing to flag."""
    prov = "Source: pyproject.toml | Field: project.license"
    assert tag_license_normalization(prov, "MIT", "MIT") == prov


def test_tag_license_normalization_flags_casing_change() -> None:
    """A casing-only rewrite ("mit" -> "MIT") is flagged with the raw value
    and, when the library is installed, the py-spdx-license version that
    did the rewrite -- wiring the previously-dead _PY_SPDX_LICENSE_VERSION
    into actual output."""
    prov = "Source: pyproject.toml | Field: project.license"
    tagged = tag_license_normalization(prov, "mit", "MIT")
    assert tagged.startswith(prov)
    assert "Normalized-From: mit" in tagged
    if _PY_SPDX_LICENSE_VERSION is not None:
        assert f"Normalizer: py-spdx-license=={_PY_SPDX_LICENSE_VERSION}" in tagged


def test_tag_license_normalization_flags_compound_dedup() -> None:
    """A compound-expression dedup ("MIT AND MIT" -> "MIT") is flagged the
    same way as a bare casing change -- any value rewrite counts."""
    prov = "Source: LICENSE | Method: licenseid_detection"
    tagged = tag_license_normalization(prov, "MIT AND MIT", "MIT")
    assert "Normalized-From: MIT AND MIT" in tagged


def test_tag_license_normalization_strips_raw_whitespace() -> None:
    """*raw* is compared and recorded stripped, matching how callers pass
    already-``.strip()``-able values (e.g. ``license_id.strip()`` at the
    deps.py call site)."""
    prov = "Source: pyproject.toml | Field: project.license"
    assert tag_license_normalization(prov, "MIT", "MIT") == prov
    tagged = tag_license_normalization(prov, "  mit  ", "MIT")
    assert "Normalized-From: mit" in tagged
