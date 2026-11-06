# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A LicenseID database that fails after the detector is built: one
``WARNING:``, text detection degrades, the next lookup builds the detector
again; a declared value is read all the while (it needs no database).

See also: :mod:`tests.assemble.test_license_detection` (a database that
cannot be used from the start).
"""

# pylint: disable=protected-access

from __future__ import annotations

import contextlib
import functools
import logging
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from licenseid import DatabaseNotReadyError, InvalidInputError, LicenseDetector

from pitloom.extract import _license_text_match
from pitloom.extract._license import resolve_declared_value
from pitloom.extract._license_text_match import detect_license_from_text

_MIT_TEXT = "Permission is hereby granted, free of charge, to any person " * 5
#: A real MIT licence file, detected as ``MIT`` with no licence stated.
_TEXTS = Path(__file__).parents[1] / "fixtures" / "license-texts"
_REAL_MIT = (_TEXTS / "RapidFuzz-3.14.5-LICENSE").read_text(encoding="utf-8")


def _declared(value: str) -> str | None:
    """The expression LicenseID reads in the declared *value*."""
    found = resolve_declared_value(value)
    return None if found is None else found["expression"]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.parametrize(
    ("error", "warned"),
    [
        (DatabaseNotReadyError("database: unreadable: x.db: no such table"), True),
        # an input LicenseID rejects is no database failure
        (InvalidInputError("option: invalid: license_id: MIT OR X"), False),
    ],
    ids=["not-ready", "invalid-input"],
)
def test_a_database_failure_in_a_lookup_warns_once_and_rebuilds(
    error: Exception, warned: bool, caplog: pytest.LogCaptureFixture
) -> None:
    broken = MagicMock(spec=LicenseDetector)
    broken.detect.side_effect = error
    with patch.object(
        _license_text_match, "LicenseDetector", return_value=broken
    ) as built:
        with caplog.at_level(logging.WARNING, logger=_license_text_match.__name__):
            results = [
                detect_license_from_text(_MIT_TEXT),
                _declared("mit"),
                detect_license_from_text(_MIT_TEXT),
                detect_license_from_text(_MIT_TEXT, stated="MIT"),
            ]

    assert results == [None, "MIT", None, None]
    assert built.call_count == (3 if warned else 1)
    messages = _warnings(caplog)
    assert len(messages) == (1 if warned else 0)
    if warned:
        assert "licenseid database cannot be used" in messages[0]


def _damage(db: Path, how: str) -> None:
    if how == "delete":
        db.unlink()
    elif how == "truncate":
        db.write_bytes(b"")
    elif how == "zero-header":
        with db.open("r+b") as handle:
            handle.write(b"\0" * 4096)
    else:  # one table gone: id lookups still work, text matching does not
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute("DROP TABLE license_index")
            conn.commit()


@pytest.mark.parametrize("damage", ["delete", "truncate", "zero-header", "drop-table"])
def test_a_real_database_broken_mid_run_warns_and_recovers(
    damage: str,
    licenseid_db_path: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """LicenseID checks its database when the detector is built; a file
    damaged afterwards fails the lookup with ``DatabaseNotReadyError``: one
    ``WARNING:``, no licence detected, a declared value still read, and once
    the file is restored the next lookup works again (the cached detector
    was dropped)."""
    db = tmp_path / "licenses.db"
    shutil.copyfile(licenseid_db_path, db)
    real = functools.partial(LicenseDetector, db_path=str(db))
    with patch.object(_license_text_match, "LicenseDetector", real):
        assert detect_license_from_text(_REAL_MIT) == "MIT"  # the detector is built
        _damage(db, damage)
        with caplog.at_level(logging.WARNING, logger=_license_text_match.__name__):
            assert detect_license_from_text(_REAL_MIT) is None
            assert detect_license_from_text(_MIT_TEXT) is None
            assert _declared("apache2") == "Apache-2.0"
        # a lookup never creates the database file (LicenseID >= 0.4.2)
        assert db.exists() is (damage != "delete")
        shutil.copyfile(licenseid_db_path, db)
        assert detect_license_from_text(_REAL_MIT) == "MIT"

    (message,) = _warnings(caplog)
    assert "licenseid database cannot be used" in message


#: Inputs that reach LicenseID's SQL and full-text search: none is a
#: database failure.
_HOSTILE_TEXTS = [
    'NEAR(MIT AND OR NOT * ^ : "quoted" -term column:x {a b}',
    "MIT License\0\0 Permission is hereby granted",
    "\ufffe\uffff" * 100 + " Permission is hereby granted",
    "(" * 5000 + "Permission is hereby granted",
    "Permission is hereby granted, free of charge " * 5000,
    "Permission \ud800 is hereby granted, free of charge " * 5,
]
_HOSTILE_IDS = [
    'MIT"',
    "%",
    "_",
    "MIT\0",
    "'; DROP TABLE licenses; --",
    "MIT OR",
    "()",
    "M" * 100_000,
    "Apache-" + "2" * 50_001 + "+",  # over SQLite's LIKE pattern limit
    "",
]


def test_hostile_input_is_never_a_database_failure(
    licenseid_db_path: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No input makes Pitloom report the database unusable or rebuild the
    detector, and no lookup raises: a hostile text through detection, a
    hostile id through detection (as a text stating it) and through the
    declared-value reading."""
    db = tmp_path / "licenses.db"
    shutil.copyfile(licenseid_db_path, db)
    built: list[LicenseDetector] = []

    def build() -> LicenseDetector:
        built.append(LicenseDetector(db_path=str(db)))
        return built[-1]

    with patch.object(_license_text_match, "LicenseDetector", build):
        with caplog.at_level(logging.WARNING, logger="pitloom"):
            for text in _HOSTILE_TEXTS:
                found = detect_license_from_text(text, stated="MIT")
                assert found is None or isinstance(found, str)
            for raw in _HOSTILE_IDS:
                assert detect_license_from_text(f"License: {raw}\n{_MIT_TEXT}") in (
                    None,
                    "MIT",
                )
                reading = resolve_declared_value(raw)
                assert reading is None or isinstance(reading["category"], str)
            assert detect_license_from_text(_REAL_MIT) == "MIT"  # still usable
            # padding is no part of the value
            assert _declared(" " * 300 + "mit\n") == "MIT"

    assert not _warnings(caplog)
    assert len(built) == 1


_HUGE_ID = "A" * 50_001 + "+"


@pytest.mark.parametrize(
    "text",
    [
        f"SPDX-License-Identifier: {_HUGE_ID}\n{_MIT_TEXT}",
        f"License: {_HUGE_ID}\n{_MIT_TEXT}",
        f'{{"license": "{_HUGE_ID}"}}',  # a JSON document as a whole
    ],
    ids=["spdx-tag", "license-field", "json-field"],
)
def test_a_huge_licence_id_in_a_text_is_no_database_failure(
    text: str,
    licenseid_db_path: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = tmp_path / "licenses.db"
    shutil.copyfile(licenseid_db_path, db)
    real = functools.partial(LicenseDetector, db_path=str(db))
    with patch.object(_license_text_match, "LicenseDetector", real):
        with caplog.at_level(logging.WARNING, logger=_license_text_match.__name__):
            detect_license_from_text(text)
            assert detect_license_from_text(_REAL_MIT) == "MIT"  # still usable
    assert not _warnings(caplog)
