# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A missing LicenseID database costs a stated licence only the licence-file
check: said once at ``INFO:``. A text too short to be a licence body never
looks the database up. Any other case still warns.

See also: :mod:`tests.assemble.test_license_database` (a database that
fails after the detector is built).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from licenseid import DatabaseNotReadyError, LicenseDetector

from pitloom.extract import _license_text_match
from pitloom.extract._license import resolve_declared_value, stated_license
from pitloom.extract._license_text_match import (
    _get_detector,
    detect_license_from_text,
)

_TEXT = "Permission is hereby granted, free of charge, to any person " * 5
_INFO = "licenseid database not found: "


def _lines(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records]


@pytest.fixture(name="missing")
def _missing(tmp_path: Path) -> Iterator[None]:
    real = functools.partial(LicenseDetector, db_path=str(tmp_path / "none.db"))
    with patch.object(_license_text_match, "LicenseDetector", real):
        yield


@pytest.mark.parametrize("stated", ["MIT", "Apache-2.0 OR MIT"])
@pytest.mark.usefixtures("missing")
def test_a_missing_database_with_a_stated_licence_is_info_once(
    stated: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=_license_text_match.__name__):
        first = detect_license_from_text(_TEXT, stated=stated)
        second = detect_license_from_text(_TEXT, stated=stated)

    assert (first, second) == (None, None)
    (level, message) = _lines(caplog)[0]
    assert level == logging.INFO
    assert message.startswith(_INFO)
    assert "none.db" in message  # names where it looked
    assert "license text detection skipped" in message
    assert "licenseid update --source packaged" in message
    assert [line for line in _lines(caplog) if line[0] == logging.INFO] == [
        (level, message)
    ]
    assert not [line for line in _lines(caplog) if line[0] >= logging.WARNING]


@pytest.mark.parametrize("stated", [None, "", "  \n"], ids=["none", "empty", "blank"])
@pytest.mark.usefixtures("missing")
def test_a_missing_database_with_no_stated_licence_warns(
    stated: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=_license_text_match.__name__):
        assert detect_license_from_text(_TEXT, stated=stated) is None

    (level, message) = _lines(caplog)[0]
    assert level == logging.WARNING
    assert "licenseid database cannot be used" in message


@pytest.mark.parametrize(
    ("detail", "level"),
    [
        ("licenses.db", logging.INFO),
        (None, logging.WARNING),
        ("no home directory", logging.WARNING),
    ],
    ids=["path", "no-detail", "no-home"],
)
def test_only_a_named_missing_file_is_info(
    detail: str | None, level: int, caplog: pytest.LogCaptureFixture
) -> None:
    """``not found`` naming a path is a database to build; with no path, or
    for an account with no home directory (a setup problem), it warns."""
    error = DatabaseNotReadyError(f"database: not found: {detail}", "not found", detail)

    def refused() -> None:
        raise error

    with patch.object(_license_text_match, "LicenseDetector", refused):
        with caplog.at_level(logging.INFO, logger=_license_text_match.__name__):
            assert detect_license_from_text(_TEXT, stated="MIT") is None
    assert [line[0] for line in _lines(caplog)] == [level]


@pytest.mark.usefixtures("missing")
def test_a_declared_value_is_read_with_no_database(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The reading of a declared value uses the packaged SPDX License List:
    a missing database costs it nothing and says nothing more."""
    with caplog.at_level(logging.INFO, logger="pitloom"):
        assert detect_license_from_text(_TEXT, stated="Apache2") is None
        found = resolve_declared_value("Apache2")
        assert found is not None and found["expression"] == "Apache-2.0"

    levels = [level for level, _ in _lines(caplog)]
    assert levels == [logging.INFO]
    assert not any("cannot be used" in line for _, line in _lines(caplog))


def test_an_unusable_database_with_a_stated_licence_still_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"")
    real = functools.partial(LicenseDetector, db_path=str(broken))
    with patch.object(_license_text_match, "LicenseDetector", real):
        with caplog.at_level(logging.INFO, logger=_license_text_match.__name__):
            assert detect_license_from_text(_TEXT, stated="MIT") is None

    (level, message) = _lines(caplog)[0]
    assert level == logging.WARNING
    assert "cannot be used" in message


def test_the_info_and_warning_lines_share_one_grammar(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Sibling lines keep the ``licenseid database`` sub-prefix and one
    `` -- `` before the consequence."""
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"")
    with caplog.at_level(logging.INFO, logger=_license_text_match.__name__):
        for path in (tmp_path / "none.db", broken):
            real = functools.partial(LicenseDetector, db_path=str(path))
            with patch.object(_license_text_match, "LicenseDetector", real):
                detect_license_from_text(_TEXT, stated="MIT")

    levels_and_lines = _lines(caplog)
    assert [level for level, _ in levels_and_lines] == [logging.INFO, logging.WARNING]
    for _, line in levels_and_lines:
        assert line.startswith("licenseid database ")
        assert line.count(" -- ") == 1


@pytest.fixture(name="spy")
def _spy() -> Iterator[MagicMock]:
    """Records every lookup of the shared detector."""
    with patch.object(_license_text_match, "_get_detector", wraps=_get_detector) as spy:
        yield spy


@pytest.mark.parametrize(
    "value",
    ["New BSD", "CC0 1.0 Universal", "Some in-house licence, see the website"],
    ids=["alias", "title", "label"],
)
@pytest.mark.usefixtures("missing")
def test_a_short_value_never_looks_the_database_up(
    value: str, spy: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """A declared value under a licence body's length is no text to detect:
    a missing database is not looked up, nor said."""
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        assert detect_license_from_text(value) is None
        assert stated_license(value, "Source: x") == (value, None)

    assert spy.call_count == 0
    assert not [line for line in _lines(caplog) if "licenseid database" in line[1]]
    assert not [line for line in _lines(caplog) if line[0] >= logging.WARNING]


@pytest.mark.usefixtures("missing")
def test_a_long_text_with_no_database_warns_once(
    spy: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Detection needs the database and nothing is declared: one warning,
    though asked twice."""
    with caplog.at_level(logging.INFO, logger="pitloom"):
        assert detect_license_from_text(_TEXT) is None
        assert detect_license_from_text(_TEXT) is None

    assert spy.call_count == 2
    warned = [line for line in _lines(caplog) if line[0] >= logging.WARNING]
    assert len(warned) == 1
    assert "licenseid database cannot be used" in warned[0][1]


@pytest.mark.usefixtures("missing")
def test_a_declared_long_text_with_no_database_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The declared licence is a text only the database can read: kept as
    written, and the database it could not use warned about."""
    with caplog.at_level(logging.INFO, logger="pitloom"):
        assert stated_license(_TEXT, "Source: x") == (_TEXT, None)

    (level, message) = _lines(caplog)[0]
    assert level == logging.WARNING
    assert message.startswith("licenseid database cannot be used: ")
    assert not [line for line in _lines(caplog) if _INFO in line[1]]
