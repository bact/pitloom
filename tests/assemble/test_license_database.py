# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``licenseid`` database that fails after the matcher is built: one
``WARNING:``, lookups degrade, the next lookup builds the matcher again.

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
from licenseid import AggregatedLicenseMatcher, DatabaseNotReadyError, InvalidInputError

from pitloom.extract import _license
from pitloom.extract._license import canonicalize_license_id, detect_license_from_text

_MIT_TEXT = "Permission is hereby granted, free of charge, to any person " * 5


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.parametrize(
    ("error", "warned"),
    [
        (DatabaseNotReadyError("database: unreadable: x.db: no such table"), True),
        # an input licenseid rejects is no database failure
        (InvalidInputError("option: invalid: license_id: MIT OR X"), False),
    ],
    ids=["not-ready", "invalid-input"],
)
def test_a_database_failure_in_a_lookup_warns_once_and_rebuilds(
    error: Exception, warned: bool, caplog: pytest.LogCaptureFixture
) -> None:
    broken = MagicMock(spec=AggregatedLicenseMatcher)
    broken.match.side_effect = error
    with patch.object(
        _license, "AggregatedLicenseMatcher", return_value=broken
    ) as built:
        with caplog.at_level(logging.WARNING, logger=_license.__name__):
            results = [
                canonicalize_license_id("mit"),
                detect_license_from_text(_MIT_TEXT),
                canonicalize_license_id("apache-2.0"),
            ]

    assert results == ["mit", None, "apache-2.0"]
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


@pytest.mark.parametrize(
    ("damage", "id_after"),
    [
        ("delete", "mit"),
        ("truncate", "mit"),
        ("zero-header", "mit"),
        ("drop-table", "MIT"),
    ],
)
def test_a_real_database_broken_mid_run_warns_and_recovers(
    damage: str,
    id_after: str,
    licenseid_db_path: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``licenseid`` checks its database when the matcher is built; a file
    damaged afterwards fails the lookup with ``DatabaseNotReadyError``: one
    ``WARNING:``, no licence detected, and once the file is restored the
    next lookup works again (the cached matcher was dropped)."""
    db = tmp_path / "licenses.db"
    shutil.copyfile(licenseid_db_path, db)
    real = functools.partial(AggregatedLicenseMatcher, db_path=str(db))
    with patch.object(_license, "AggregatedLicenseMatcher", real):
        assert canonicalize_license_id("mit") == "MIT"  # the matcher is built
        _damage(db, damage)
        with caplog.at_level(logging.WARNING, logger=_license.__name__):
            assert canonicalize_license_id("mit") == id_after
            assert detect_license_from_text(_MIT_TEXT) is None
        # a lookup never creates the database file (licenseid >= 0.4.2)
        assert db.exists() is (damage != "delete")
        shutil.copyfile(licenseid_db_path, db)
        assert canonicalize_license_id("mit") == "MIT"

    (message,) = _warnings(caplog)
    assert "licenseid database cannot be used" in message


#: Inputs that reach licenseid's SQL and full-text search: none is a
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
    "Apache-" + "2" * 50_001 + "+",  # SQLite refuses so long a LIKE pattern
    "",
]


def test_hostile_input_is_never_a_database_failure(
    licenseid_db_path: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No input makes Pitloom report the database unusable or rebuild the
    matcher, and no lookup raises."""
    db = tmp_path / "licenses.db"
    shutil.copyfile(licenseid_db_path, db)
    built: list[AggregatedLicenseMatcher] = []

    def build() -> AggregatedLicenseMatcher:
        built.append(AggregatedLicenseMatcher(db_path=str(db)))
        return built[-1]

    with patch.object(_license, "AggregatedLicenseMatcher", build):
        with caplog.at_level(logging.WARNING, logger=_license.__name__):
            for text in _HOSTILE_TEXTS:
                found = detect_license_from_text(text, stated="MIT")
                assert found is None or isinstance(found, str)
            for raw in _HOSTILE_IDS:
                assert isinstance(canonicalize_license_id(raw), str)
            assert canonicalize_license_id("mit") == "MIT"  # still usable
            # padding does not count towards the length limit
            assert canonicalize_license_id(" " * 300 + "mit\n") == "MIT"

    assert not _warnings(caplog)
    assert len(built) == 1


_HUGE_ID = "A" * 50_001 + "+"


@pytest.mark.xfail(
    strict=True,
    reason="licenseid 0.4.2 reports SQLite's refusal of a LIKE pattern over "
    "50,000 bytes, built from a licence id in the text, as a database failure",
)
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
    real = functools.partial(AggregatedLicenseMatcher, db_path=str(db))
    with patch.object(_license, "AggregatedLicenseMatcher", real):
        with caplog.at_level(logging.WARNING, logger=_license.__name__):
            detect_license_from_text(text)
    assert not _warnings(caplog)
