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

import functools
import logging
import shutil
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


@pytest.mark.parametrize("damage", ["delete", "truncate", "corrupt"])
def test_a_real_database_broken_mid_run_warns(
    damage: str,
    licenseid_db_path: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``licenseid`` checks its database when the matcher is built; a file
    damaged afterwards fails the lookup with ``DatabaseNotReadyError``."""
    db = tmp_path / "licenses.db"
    shutil.copyfile(licenseid_db_path, db)
    real = functools.partial(AggregatedLicenseMatcher, db_path=str(db))
    with patch.object(_license, "AggregatedLicenseMatcher", real):
        assert canonicalize_license_id("mit") == "MIT"  # the matcher is built
        if damage == "delete":
            db.unlink()
        elif damage == "truncate":
            db.write_bytes(b"")
        else:
            with db.open("r+b") as handle:
                handle.write(b"\0" * 4096)
        with caplog.at_level(logging.WARNING, logger=_license.__name__):
            assert canonicalize_license_id("mit") == "mit"
            assert detect_license_from_text(_MIT_TEXT) is None

    (message,) = _warnings(caplog)
    assert "licenseid database cannot be used" in message
