# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration tests against the real licenseid database, plus tests for
G2 license detection (``detect_independent_license``) and its provenance
tagging; expression normalisation is in ``tests/extract/test_license_classify.py``.

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
    detect_independent_license,
    detect_license_for_project,
    detect_license_from_text,
    tag_deprecated_license_ids,
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
# tag_license_normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "note"),
    [
        ("GPL-2.0", "GPL-2.0 (GPL-2.0-only or GPL-2.0-or-later)"),
        (
            "GPL-2.0 AND LGPL-2.1 AND GPL-2.0",
            "GPL-2.0 (GPL-2.0-only or GPL-2.0-or-later); "
            "LGPL-2.1 (LGPL-2.1-only or LGPL-2.1-or-later)",
        ),
        (
            "GPL-2.0 WITH Classpath-exception-2.0",
            "GPL-2.0 (GPL-2.0-only or GPL-2.0-or-later)",
        ),
    ],
)
def test_tag_deprecated_license_ids_notes_each_ambiguous_id_once(
    expression: str, note: str
) -> None:
    prov = "Source: pyproject.toml | Field: project.license"
    assert tag_deprecated_license_ids(prov, expression) == (
        f"{prov} | Deprecated-License-Id: {note}"
    )


@pytest.mark.parametrize(
    "expression",
    [
        "MIT",  # not deprecated
        "GPL-2.0-only",  # current
        "GPL-2.0-or-later AND MIT",
        "eCos-2.0",  # deprecated, but no -only/-or-later pair to choose from
        "LicenseRef-x",
    ],
)
def test_tag_deprecated_license_ids_leaves_the_rest_alone(expression: str) -> None:
    assert tag_deprecated_license_ids("Source: x", expression) == "Source: x"


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
