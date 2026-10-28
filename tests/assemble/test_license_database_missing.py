# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A missing licenseid database costs a stated licence only the licence-file
check: said once at ``INFO:``. Any other case still warns.

See also: :mod:`tests.assemble.test_license_database` (a database that
fails after the matcher is built).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from licenseid import AggregatedLicenseMatcher

from pitloom.extract import _license
from pitloom.extract._license import (
    canonicalize_license_id,
    detect_license_from_text,
    resolve_declared_value,
)

_TEXT = "Permission is hereby granted, free of charge, to any person " * 5
_INFO = "licenseid database not found: "


def _lines(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records]


@pytest.fixture(name="missing")
def _missing(tmp_path: Path) -> Iterator[None]:
    real = functools.partial(
        AggregatedLicenseMatcher, db_path=str(tmp_path / "none.db")
    )
    with patch.object(_license, "AggregatedLicenseMatcher", real):
        yield


@pytest.mark.parametrize("stated", ["MIT", "Apache-2.0 OR MIT"])
@pytest.mark.usefixtures("missing")
def test_a_missing_database_with_a_stated_licence_is_info_once(
    stated: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=_license.__name__):
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
    with caplog.at_level(logging.INFO, logger=_license.__name__):
        assert detect_license_from_text(_TEXT, stated=stated) is None

    (level, message) = _lines(caplog)[0]
    assert level == logging.WARNING
    assert "licenseid database cannot be used" in message


@pytest.mark.usefixtures("missing")
def test_a_declared_value_needing_the_reading_still_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger=_license.__name__):
        assert detect_license_from_text(_TEXT, stated="Apache2") is None
        assert resolve_declared_value("Apache2") is None
        assert canonicalize_license_id("mit") == "mit"

    levels = [level for level, _ in _lines(caplog)]
    assert levels == [logging.INFO, logging.WARNING]
    assert "cannot be used" in _lines(caplog)[1][1]


def test_an_unusable_database_with_a_stated_licence_still_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"")
    real = functools.partial(AggregatedLicenseMatcher, db_path=str(broken))
    with patch.object(_license, "AggregatedLicenseMatcher", real):
        with caplog.at_level(logging.INFO, logger=_license.__name__):
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
    with caplog.at_level(logging.INFO, logger=_license.__name__):
        for path in (tmp_path / "none.db", broken):
            real = functools.partial(AggregatedLicenseMatcher, db_path=str(path))
            with patch.object(_license, "AggregatedLicenseMatcher", real):
                detect_license_from_text(_TEXT, stated="MIT")

    levels_and_lines = _lines(caplog)
    assert [level for level, _ in levels_and_lines] == [logging.INFO, logging.WARNING]
    for _, line in levels_and_lines:
        assert line.startswith("licenseid database ")
        assert line.count(" -- ") == 1
