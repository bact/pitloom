# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for license text detection utilities: SPDX id/expression
recognition, license-file discovery, CITATION.cff/codemeta.json readers,
candidate collection, and mocked (DB-absent) detection.

See also: test_license_normalization.py -- this module's sibling, split
from the original test_license.py; test_license_detection_ties.py (when a
match is decisive).
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract._license import (
    _COPYRIGHT_NOTICE_RE,
    _looks_like_spdx_license_expression,
    _looks_like_spdx_license_id,
    apply_in_package_license,
    canonicalize_license_id,
    collect_license_candidates,
    detect_license_for_project,
    detect_license_from_text,
    find_license_files,
)
from pitloom.extract._license_detect import (
    _license_from_citation_cff,
    _license_from_codemeta_json,
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
# _license_from_citation_cff / _license_from_codemeta_json (absent files:
# test_collect_candidates_empty_dir)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"cff-version: 1.2.0\nlicense: Apache-2.0\n", "Apache-2.0"),  # scalar
        (b'cff-version: 1.2.0\nlicense: "MIT"\n', "MIT"),  # quoted scalar
        (b"cff-version: 1.2.0\nlicense:\n  - MIT\n  - Apache-2.0\n", "MIT"),  # list
    ],
)
def test_citation_cff(raw: bytes, expected: str) -> None:
    """The ``license`` scalar, or a list's first item, is extracted."""
    assert _license_from_citation_cff(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b'{"license": "MIT"}', "MIT"),  # bare SPDX License ID
        (b'{"license": "https://spdx.org/licenses/Apache-2.0.html"}', "Apache-2.0"),
        (b'{"license": "proprietary license text here"}', None),  # not an id
    ],
)
def test_codemeta_json(raw: bytes, expected: str | None) -> None:
    """A bare id is kept, an SPDX URL reduced to its id, other text dropped."""
    assert _license_from_codemeta_json(raw) == expected


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
# canonicalize_license_id
# ---------------------------------------------------------------------------


def test_an_unusable_database_warns_once_and_degrades(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A matcher that cannot be built (a missing, corrupt or unreadable
    database) is one WARNING naming the cause, not a silent debug line;
    every lookup then degrades: the raw id, no detected licence. The build
    is retried, so a database fixed later in the process is used."""
    fixed = MagicMock()
    fixed.match.return_value = [{"license_id": "MIT"}]
    broken = RuntimeError("database: unreadable:\nx.db")
    with patch(
        "pitloom.extract._license.AggregatedLicenseMatcher",
        side_effect=[broken, broken, broken, fixed],
    ) as matcher_class:
        with caplog.at_level(logging.WARNING, logger="pitloom.extract._license"):
            results = [
                canonicalize_license_id("mit"),
                detect_license_from_text("MIT License " * 20),
                canonicalize_license_id("apache-2.0"),
                canonicalize_license_id("mit"),
            ]

    assert results == ["mit", None, "apache-2.0", "MIT"]
    assert matcher_class.call_count == 4
    (message,) = [r.getMessage() for r in caplog.records]
    assert "licenseid database cannot be used" in message
    assert "database: unreadable: x.db" in message


# ---------------------------------------------------------------------------
# detect_license_from_text -- DB absent / library missing
# ---------------------------------------------------------------------------


def test_detect_license_from_text_db_not_populated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Returns None gracefully when the licenseid database is not populated."""
    with patch(
        "licenseid.matcher.get_default_db_path",
        return_value=str(tmp_path / "empty.db"),
    ):
        result = detect_license_from_text("MIT License\n\nPermission is hereby granted")
        assert result is None
    assert "licenseid database cannot be used" in caplog.text


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
            mock_detect.assert_called_once_with(mit_text, stated=None)
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


_FILES = [("Apache-2.0", "Source: LICENSE")]


@pytest.mark.parametrize(
    ("stated", "candidates", "expected"),
    [
        ("MIT", _FILES, ("MIT", "Apache-2.0")),  # stated: files concluded
        ("UNKNOWN", _FILES, ("UNKNOWN", "Apache-2.0")),  # a placeholder states
        (None, _FILES, ("Apache-2.0", None)),  # silent: files declared
        ("", _FILES, ("Apache-2.0", None)),  # blank is silent
        (" \n", _FILES, ("Apache-2.0", None)),
        ("MIT", [], ("MIT", None)),  # nothing found: nothing changes
        (None, [], (None, None)),
    ],
)
def test_apply_in_package_license_is_one_rule_for_every_reader(
    stated: str | None,
    candidates: list[tuple[str, str]],
    expected: tuple[str | None, str | None],
) -> None:
    metadata = ProjectMetadata(name="p", license_name=stated)
    apply_in_package_license(metadata, candidates)
    assert (metadata.license_name, metadata.license_concluded) == expected
    field = "license_concluded" if expected[1] else "license"
    assert metadata.provenance.get(field) == ("Source: LICENSE" if candidates else None)


# ---------------------------------------------------------------------------
# What licenseid misses: a near-variant ranked first, a licence behind a
# copyright notice
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "is_notice"),
    [
        ("Copyright (c) 2017-2021 Ingy d\u00f6t Net", True),
        ("  Copyright 2006 Kirill Simonov", True),
        ("COPYRIGHT \u00a9 2020 Acme", True),
        ("(c) 2020 Acme", True),
        ("copyright notice and this permission notice shall be", False),
        ("Copyright holders may not", False),
        ("Copyright: (c) 2020 Acme", True),
        ("\ufeffCopyright (c) 2020 Acme", True),
    ],
)
def test_a_copyright_notice_line_is_told_from_licence_text(
    line: str, is_notice: bool
) -> None:
    assert bool(_COPYRIGHT_NOTICE_RE.fullmatch(line)) is is_notice


_BODY = "Permission is hereby granted, free of charge, to any person. " * 3
_NOTICE = "Copyright (c) 2020 Acme\n"


# pylint: disable-next=too-few-public-methods
class _FakeMatcher:
    """Scores the text as written and without its notice differently."""

    def __init__(self, raw: list[tuple[str, float]], bare: list[tuple[str, float]]):
        self._by_text = {_NOTICE + _BODY: raw, "\n" + _BODY: bare, _BODY: raw}

    def match(self, text: str = "", **kwargs: str) -> list[dict[str, object]]:
        if kwargs:  # the empty-database probe
            return [{"license_id": "MIT", "score": 1.0}]
        return [{"license_id": i, "score": s} for i, s in self._by_text[text]]


@pytest.mark.parametrize(
    ("text", "raw", "bare", "expected"),
    [
        (_BODY, [("MIT", 0.9)], [], "MIT"),  # no notice: one reading
        (_NOTICE + _BODY, [("Xnet", 0.9)], [("MIT", 1.0)], "MIT"),  # bare better
        (_NOTICE + _BODY, [("MIT", 0.93)], [("MirOS", 0.6)], "MIT"),  # raw better
        (_NOTICE + _BODY, [], [("MIT", 0.9)], "MIT"),  # only bare matches
        (_NOTICE + _BODY, [("X", 0.5)], [("Y", 0.6)], None),  # below threshold
        # the better reading is a tie: none, never the other reading's top
        (_NOTICE + _BODY, [("Xnet", 0.95)], [("JSON", 0.96), ("MIT", 0.955)], None),
    ],
)
def test_a_copyright_notice_is_read_both_ways(
    text: str,
    raw: list[tuple[str, float]],
    bare: list[tuple[str, float]],
    expected: str | None,
) -> None:
    with patch(
        "pitloom.extract._license._get_matcher", return_value=_FakeMatcher(raw, bare)
    ):
        assert detect_license_from_text(text) == expected


def test_a_stated_licence_is_looked_for_in_both_readings() -> None:
    """The reading without the notice scores higher, but only the reading as
    written has the stated licence in a near-tie."""
    fake = _FakeMatcher([("Pixar", 0.996), ("Apache-2.0", 0.992)], [("Pixar", 0.999)])
    with patch("pitloom.extract._license._get_matcher", return_value=fake):
        assert detect_license_from_text(_NOTICE + _BODY, stated="Apache-2.0") == (
            "Apache-2.0"
        )
