# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.project.installed: discovery
(find_installed_metadata_candidate) and parsing (_parse_installed_metadata).

See also: test_installed_reconcile.py for reconcile_installed_metadata()
tests, and test_installed_integration.py for read_project()/
resolve_project_with_lockfile() end-to-end integration cases (fixture-dir
based, embed-wheel regression, peek/reread dedup, determinism).
"""

from __future__ import annotations

import email
import logging
from pathlib import Path

import pytest

from pitloom.extract.project.installed import (
    _discover_candidate,
    _parse_installed_metadata,
    find_installed_metadata_candidate,
    read_installed_metadata,
)

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "projects"


def _msg(text: str) -> email.message.Message:
    return email.message_from_string(text)


# --- _parse_installed_metadata ----------------------------------------------


def test_parse_installed_metadata_minimal() -> None:
    """Only Name/Version present -- every optional field stays unset, no
    provenance recorded for what wasn't declared."""
    msg = _msg("Metadata-Version: 2.1\nName: pkg\nVersion: 1.0.0\n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.name == "pkg"
    assert metadata.version == "1.0.0"
    assert metadata.description is None
    assert metadata.requires_python is None
    assert metadata.license_name is None
    assert metadata.keywords == []
    assert metadata.urls == {}
    assert set(metadata.provenance) == {"name", "version"}


def test_parse_installed_metadata_license_expression_preferred_over_legacy() -> None:
    """Spec 2.4+ makes License-Expression/License mutually exclusive, but a
    real, non-compliant file can carry both -- prefer License-Expression,
    never raise."""
    msg = _msg(
        "Name: pkg\nVersion: 1.0.0\nLicense-Expression: MIT\nLicense: Apache-2.0\n"
    )
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.license_name == "MIT"
    assert metadata.provenance["license"] == "Source: pkg.egg-info"


def test_parse_installed_metadata_legacy_license_fallback() -> None:
    msg = _msg("Name: pkg\nVersion: 1.0.0\nLicense: Apache-2.0\n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.license_name == "Apache-2.0"


def test_parse_installed_metadata_keywords_declared_empty() -> None:
    """An explicit `Keywords:` header with an empty value is a
    declared-empty, not absent -- provenance is still recorded."""
    msg = _msg("Name: pkg\nVersion: 1.0.0\nKeywords: \n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.keywords == []
    assert "keywords" in metadata.provenance


def test_parse_installed_metadata_keywords_absent() -> None:
    """No `Keywords:` header at all -- absent, not declared-empty."""
    msg = _msg("Name: pkg\nVersion: 1.0.0\n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.keywords == []
    assert "keywords" not in metadata.provenance


def test_parse_installed_metadata_keywords_csv_split() -> None:
    msg = _msg("Name: pkg\nVersion: 1.0.0\nKeywords: sbom,spdx,supply-chain\n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.keywords == ["sbom", "spdx", "supply-chain"]


def test_parse_installed_metadata_project_url_comma_in_url() -> None:
    """Split on the first comma only -- a URL's own query string can
    legally contain commas."""
    msg = _msg(
        "Name: pkg\nVersion: 1.0.0\n"
        "Project-URL: Tracker, https://example.com/issues?labels=a,b\n"
    )
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.urls == {"Tracker": "https://example.com/issues?labels=a,b"}


def test_parse_installed_metadata_homepage_fallback() -> None:
    """Legacy Home-page maps to key "Homepage" only when no Project-URL
    already used that key."""
    msg = _msg("Name: pkg\nVersion: 1.0.0\nHome-page: https://example.com\n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.urls == {"Homepage": "https://example.com"}


def test_parse_installed_metadata_homepage_does_not_override_project_url() -> None:
    msg = _msg(
        "Name: pkg\nVersion: 1.0.0\n"
        "Project-URL: Homepage, https://real.example.com\n"
        "Home-page: https://legacy.example.com\n"
    )
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.urls == {"Homepage": "https://real.example.com"}


def test_parse_installed_metadata_unicode_summary_and_keywords() -> None:
    msg = _msg(
        "Name: pkg\nVersion: 1.0.0\n"
        "Summary: A package for élégant 包管理\n"
        "Keywords: élégant,包\n"
    )
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert "élégant" in (metadata.description or "")
    assert metadata.keywords == ["élégant", "包"]


def test_parse_installed_metadata_no_name_header() -> None:
    """A marker file with no Name header at all -- name stays empty, no
    provenance recorded for it (used by discovery's own reject path)."""
    msg = _msg("Version: 1.0.0\n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.name == ""
    assert "name" not in metadata.provenance


# --- read_installed_metadata -------------------------------------------------


def test_read_installed_metadata_parses_marker_file(tmp_path: Path) -> None:
    marker = tmp_path / "PKG-INFO"
    marker.write_text("Name: pkg\nVersion: 1.0.0\n", encoding="utf-8")
    metadata = read_installed_metadata(marker, "Source: pkg.egg-info")
    assert metadata is not None
    assert metadata.name == "pkg"


def test_read_installed_metadata_missing_file_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    marker = tmp_path / "does-not-exist" / "PKG-INFO"
    with caplog.at_level(logging.WARNING):
        result = read_installed_metadata(marker, "Source: pkg.egg-info")
    assert result is None
    assert "could not be re-read" in caplog.text


def test_read_installed_metadata_quiet_suppresses_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    marker = tmp_path / "does-not-exist" / "PKG-INFO"
    with caplog.at_level(logging.WARNING):
        result = read_installed_metadata(marker, "Source: pkg.egg-info", quiet=True)
    assert result is None
    assert caplog.text == ""


def test_public_discovery_and_read_match_internal_discovery_and_parse() -> None:
    """Drift guard: find_installed_metadata_candidate() +
    read_installed_metadata() (the public API pair, unused by
    reader.py's own read_project() -- see _discover_candidate/
    _parse_installed_metadata in this module) must resolve to the exact
    same ProjectMetadata as reader.py's internal, message-reusing path
    for the same fixture. The two are separate implementations of "find
    then parse"; this test is the mechanical tie that catches one being
    fixed/changed without the other."""
    fixture = _FIXTURES / "installed-metadata-conflict"

    found = find_installed_metadata_candidate(
        fixture, "sampleproject-installed-conflict"
    )
    assert found is not None
    marker_path, label = found
    source_label = f"Source: {label} | File: {marker_path.name}"
    via_public_api = read_installed_metadata(marker_path, source_label)
    assert via_public_api is not None

    candidate = _discover_candidate(fixture, "sampleproject-installed-conflict")
    assert candidate is not None
    via_internal_path = _parse_installed_metadata(
        candidate.message,
        f"Source: {candidate.label} | File: {candidate.marker_path.name}",
    )

    assert via_public_api == via_internal_path


# --- find_installed_metadata_candidate (discovery) --------------------------


def test_find_installed_metadata_candidate_silent_when_none_found(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        result = find_installed_metadata_candidate(tmp_path, "pkg")
    assert result is None
    assert caplog.text == ""


def test_find_installed_metadata_candidate_marker_missing_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "pkg.egg-info").mkdir()
    with caplog.at_level(logging.WARNING):
        result = find_installed_metadata_candidate(tmp_path, "pkg")
    assert result is None
    assert "exists but has no PKG-INFO" in caplog.text


def test_find_installed_metadata_candidate_unreadable_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    egg_info = tmp_path / "pkg.egg-info"
    egg_info.mkdir()
    marker = egg_info / "PKG-INFO"
    marker.write_text("Name: pkg\nVersion: 1.0.0\n", encoding="utf-8")
    marker.chmod(0o000)
    try:
        with caplog.at_level(logging.WARNING):
            result = find_installed_metadata_candidate(tmp_path, "pkg")
    finally:
        marker.chmod(0o644)
    if result is None:
        assert "could not be read" in caplog.text
    else:
        pytest.skip("read permission not enforced for this user (e.g. root)")


def test_find_installed_metadata_candidate_name_mismatch_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    egg_info = tmp_path / "other.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text(
        "Name: other-pkg\nVersion: 1.0.0\n", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        result = find_installed_metadata_candidate(tmp_path, "pkg")
    assert result is None
    assert "does not match the resolved project name" in caplog.text


def test_find_installed_metadata_candidate_missing_name_header_rejected(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    egg_info = tmp_path / "pkg.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text("Version: 1.0.0\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = find_installed_metadata_candidate(tmp_path, "pkg")
    assert result is None
    assert "does not match the resolved project name" in caplog.text


def test_find_installed_metadata_candidate_name_canonicalization() -> None:
    """PEP 503 canonicalization: case-fold, -/_/. interchangeable."""
    result = find_installed_metadata_candidate(
        _FIXTURES / "installed-metadata-agree", "Sampleproject_Installed.Agree"
    )
    assert result is not None
    assert result[1] == "sampleproject_installed_agree.egg-info"


def test_find_installed_metadata_candidate_src_layout_real_setuptools_shape(
    tmp_path: Path,
) -> None:
    """Regression: the empirically-verified real shape -- setuptools'
    egg_info command writes `<name>.egg-info` directly under `src/` for a
    `package_dir={"": "src"}` project (one path segment, confirmed via a
    real `python setup.py egg_info` run), not nested inside an extra
    package-name directory."""
    egg_info = tmp_path / "src" / "pkg.egg-info"
    egg_info.mkdir(parents=True)
    (egg_info / "PKG-INFO").write_text("Name: pkg\nVersion: 1.0.0\n", encoding="utf-8")
    result = find_installed_metadata_candidate(tmp_path, "pkg")
    assert result is not None
    assert result[1] == "pkg.egg-info"


def test_find_installed_metadata_candidate_src_layout_nested_pkg_dir(
    tmp_path: Path,
) -> None:
    """The defensively-kept two-segment shape (nested inside an extra
    package-name directory) is still matched too, for a layout/backend
    not independently verified to write the one-segment shape."""
    egg_info = tmp_path / "src" / "pkg" / "pkg.egg-info"
    egg_info.mkdir(parents=True)
    (egg_info / "PKG-INFO").write_text("Name: pkg\nVersion: 1.0.0\n", encoding="utf-8")
    result = find_installed_metadata_candidate(tmp_path, "pkg")
    assert result is not None
    assert result[1] == "pkg.egg-info"


def test_find_installed_metadata_candidate_src_layout_too_deep_not_matched(
    tmp_path: Path,
) -> None:
    """Adversarial: the bounded-glob promise still holds after adding the
    one-segment src/*.egg-info pattern -- a marker three segments deep
    under src/ is not discovered, silently (the normal "nothing found"
    case)."""
    egg_info = tmp_path / "src" / "sub" / "deeper" / "pkg.egg-info"
    egg_info.mkdir(parents=True)
    (egg_info / "PKG-INFO").write_text("Name: pkg\nVersion: 1.0.0\n", encoding="utf-8")
    result = find_installed_metadata_candidate(tmp_path, "pkg")
    assert result is None


def test_find_installed_metadata_candidate_dist_info_beats_egg_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 10: two valid, name-matching candidates -- .dist-info wins,
    one WARNING names both and the winner."""
    with caplog.at_level(logging.WARNING):
        result = find_installed_metadata_candidate(
            _FIXTURES / "installed-metadata-tiebreak",
            "sampleproject-installed-tiebreak",
        )
    assert result is not None
    marker_path, label = result
    assert label.endswith(".dist-info")
    assert marker_path.name == "METADATA"
    assert "multiple installed-metadata candidates found" in caplog.text
    assert caplog.text.count("multiple installed-metadata candidates found") == 1


def test_find_installed_metadata_candidate_mismatched_sibling_no_tiebreak_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 11: only one of two egg-info dirs name-matches -- the
    mismatched one is rejected by the name filter (its own WARNING), and
    the "multiple candidates" tie-break WARNING must NOT also fire."""
    with caplog.at_level(logging.WARNING):
        result = find_installed_metadata_candidate(
            _FIXTURES / "installed-metadata-tiebreak-mismatch",
            "sampleproject-installed-tbm",
        )
    assert result is not None
    assert result[1] == "sampleproject_installed_tbm.egg-info"
    assert "does not match the resolved project name" in caplog.text
    assert "multiple installed-metadata candidates found" not in caplog.text


def test_find_installed_metadata_candidate_malformed_binary_rejected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 12: invalid UTF-8/binary PKG-INFO never raises; Name can't be
    recovered, so it's rejected as a mismatch with one WARNING."""
    with caplog.at_level(logging.WARNING):
        result = find_installed_metadata_candidate(
            _FIXTURES / "installed-metadata-malformed",
            "sampleproject-installed-malformed",
        )
    assert result is None
    assert "does not match the resolved project name" in caplog.text


def test_find_installed_metadata_candidate_missing_marker_dir(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 13: .egg-info directory exists, PKG-INFO missing."""
    with caplog.at_level(logging.WARNING):
        result = find_installed_metadata_candidate(
            _FIXTURES / "installed-metadata-missing-marker",
            "sampleproject-installed-nomarker",
        )
    assert result is None
    assert "exists but has no PKG-INFO" in caplog.text


def test_find_installed_metadata_candidate_bounded_glob_ignores_deep_decoy() -> None:
    """Case 18: a decoy vendor/somepkg.egg-info/PKG-INFO several levels
    deep is never matched -- only the fixed shallow glob patterns are
    searched, never a recursive walk."""
    result = find_installed_metadata_candidate(
        _FIXTURES / "installed-metadata-decoy-vendor", "sampleproject-installed-decoy"
    )
    assert result is None


def test_find_installed_metadata_candidate_alphabetical_tiebreak(
    tmp_path: Path,
) -> None:
    """Two same-format candidates (both .egg-info) -- alphabetical path
    is the final, deterministic tie-break."""
    for dirname in ("bbb.egg-info", "aaa.egg-info"):
        egg_info = tmp_path / dirname
        egg_info.mkdir()
        (egg_info / "PKG-INFO").write_text(
            "Name: pkg\nVersion: 1.0.0\n", encoding="utf-8"
        )
    result = find_installed_metadata_candidate(tmp_path, "pkg")
    assert result is not None
    assert result[1] == "aaa.egg-info"


def test_find_installed_metadata_candidate_empty_name_matching_dir_not_a_pkg(
    tmp_path: Path,
) -> None:
    """A non-directory match for the glob pattern (e.g. a stray file named
    like an egg-info dir) is silently skipped, not treated as a
    marker-missing candidate."""
    (tmp_path / "not-a-dir.egg-info").write_text("oops", encoding="utf-8")
    result = find_installed_metadata_candidate(tmp_path, "pkg")
    assert result is None


# --- quiet=True suppresses every discovery WARNING variant -----------------


def test_find_installed_metadata_candidate_quiet_suppresses_marker_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "pkg.egg-info").mkdir()
    with caplog.at_level(logging.WARNING):
        find_installed_metadata_candidate(tmp_path, "pkg", quiet=True)
    assert caplog.text == ""


def test_find_installed_metadata_candidate_quiet_suppresses_name_mismatch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    egg_info = tmp_path / "other.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text(
        "Name: other-pkg\nVersion: 1.0.0\n", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        find_installed_metadata_candidate(tmp_path, "pkg", quiet=True)
    assert caplog.text == ""


def test_find_installed_metadata_candidate_quiet_suppresses_tiebreak_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        find_installed_metadata_candidate(
            _FIXTURES / "installed-metadata-tiebreak",
            "sampleproject-installed-tiebreak",
            quiet=True,
        )
    assert caplog.text == ""


def test_find_installed_metadata_candidate_quiet_suppresses_unreadable_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    egg_info = tmp_path / "pkg.egg-info"
    egg_info.mkdir()
    marker = egg_info / "PKG-INFO"
    marker.write_text("Name: pkg\nVersion: 1.0.0\n", encoding="utf-8")
    marker.chmod(0o000)
    try:
        with caplog.at_level(logging.WARNING):
            result = find_installed_metadata_candidate(tmp_path, "pkg", quiet=True)
    finally:
        marker.chmod(0o644)
    if result is not None:
        pytest.skip("read permission not enforced for this user (e.g. root)")
    assert caplog.text == ""


# --- a few more _parse_installed_metadata branches --------------------------


def test_parse_installed_metadata_version_absent() -> None:
    msg = _msg("Name: pkg\n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.version is None
    assert "version" not in metadata.provenance


def test_parse_installed_metadata_project_url_entry_without_comma_skipped() -> None:
    """A malformed `Project-URL` entry with no comma at all is skipped,
    not raised on."""
    msg = _msg("Name: pkg\nVersion: 1.0.0\nProject-URL: no-comma-here\n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.urls == {}
    assert "urls" not in metadata.provenance


def test_parse_installed_metadata_version_declared_empty_becomes_none() -> None:
    """Regression: an explicit but empty `Version:` header must collapse
    to `version=None`, matching every static producer's convention
    (`str(x) if x else None`), not stay as the raw empty string --
    provenance still records it as declared either way."""
    msg = _msg("Name: pkg\nVersion: \n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.version is None
    assert "version" in metadata.provenance


def test_parse_installed_metadata_requires_python_empty_becomes_none() -> None:
    """Regression: an explicit but empty `Requires-Python:` header must
    collapse to `requires_python=None`, matching every static producer's
    "no constraint" convention (`str(x) if x else None`), not stay as the
    raw empty string -- provenance still records it as declared either
    way."""
    msg = _msg("Name: pkg\nVersion: 1.0.0\nRequires-Python: \n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.requires_python is None
    assert "requires_python" in metadata.provenance


def test_parse_installed_metadata_license_declared_empty_collapses_to_none() -> None:
    """Same convention for an explicit but empty `License:` header."""
    msg = _msg("Name: pkg\nVersion: 1.0.0\nLicense: \n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.license_name is None
    assert "license" in metadata.provenance


def test_parse_installed_metadata_license_expression_empty_becomes_none() -> None:
    """Same convention for an explicit but empty `License-Expression:`
    header."""
    msg = _msg("Name: pkg\nVersion: 1.0.0\nLicense-Expression: \n")
    metadata = _parse_installed_metadata(msg, "Source: pkg.egg-info")
    assert metadata.license_name is None
    assert "license" in metadata.provenance
