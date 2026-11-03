# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What ``licenseid`` warns, relayed as tagged ``pitloom`` records
(:mod:`pitloom.extract._licenseid_relay`).

See also: tests/test_licence_db_missing_surfaces.py (the relay on the CLI,
library and hook surfaces).
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import pytest
from licenseid import LicenseDetector, get_default_db_path, resolve
from licenseid import warning as licenseid_warning

from pitloom.extract import _licenseid_relay as relay
from pitloom.extract._license import detect_license_from_text

_LOGGER = relay.__name__
_OUTDATED = "database: build v2 outdated: current v3; run 'licenseid update'"


def _said(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == _LOGGER]


def _outdated() -> None:
    """Warn as licenseid does, through its one emitter."""
    licenseid_warning.warn(
        "database", "build v2 outdated", "current v3", "run 'licenseid update'"
    )


def test_a_warning_is_one_line_said_once_and_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The suite turns warnings into errors (``filterwarnings``): relayed, a
    licenseid warning neither raises nor reaches Python's own output."""
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        for _ in range(2):
            with relay.relay_licenseid_warnings():
                _outdated()
    assert _said(caplog) == [
        (logging.WARNING, f"licenseid: {_OUTDATED}"),
        (logging.DEBUG, f"licenseid: {_OUTDATED}"),
    ]


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (
            ("input", "variant not stated", "GPL-2.0", "using GPL-2.0-only"),
            (
                logging.INFO,
                "licenseid: input: variant not stated: GPL-2.0; using GPL-2.0-only",
            ),
        ),
        (
            ("database", "unreadable", "a\nWARNING: forged", None),
            (logging.WARNING, "licenseid: database: unreadable: a WARNING: forged"),
        ),
        (
            ("input", "binary file", "\x1b[31m", None),
            # quoted and escaped whole, as loggable() does
            (logging.WARNING, "licenseid: 'input: binary file: \\x1b[31m'"),
        ),
    ],
    ids=["guess-info", "newline", "control"],
)
def test_the_level_and_the_escaping(
    parts: tuple[str, str, str, str | None],
    expected: tuple[int, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        with relay.relay_licenseid_warnings():
            licenseid_warning.warn(*parts)
    assert _said(caplog) == [expected]


def test_a_block_that_raises_still_relays(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        with pytest.raises(RuntimeError, match="boom"):
            with relay.relay_licenseid_warnings():
                _outdated()
                raise RuntimeError("boom")
    assert _said(caplog) == [(logging.WARNING, f"licenseid: {_OUTDATED}")]


def test_another_warning_is_given_again_not_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with warnings.catch_warnings(record=True) as outer:
        warnings.simplefilter("always")
        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            with relay.relay_licenseid_warnings():
                warnings.warn("not licenseid's", UserWarning, stacklevel=1)
    assert [str(w.message) for w in outer] == ["not licenseid's"]
    assert [w.filename for w in outer] == [__file__]
    assert not _said(caplog)


def test_the_filters_are_restored() -> None:
    before = list(warnings.filters)
    with relay.relay_licenseid_warnings():
        _outdated()
    assert warnings.filters == before


def test_resolving_on_the_packaged_list_warns_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The declared-value reading gives no warning on any value (none here
    is an unknown id, a guess or a refusal of the input)."""
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        with relay.relay_licenseid_warnings():
            for value in ("MIT", "GPL-2.0", "Apache2", "Acme2", "", "MIT\x1f"):
                resolve(value, source="packaged")
    assert not _said(caplog)


def test_a_real_guess_of_the_detector_is_said_at_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bare ``GPL-2.0`` tag: licenseid reads ``GPL-2.0-only`` and says so."""
    db = Path(get_default_db_path())
    if not db.exists():
        pytest.skip("licenseid database not built -- run 'licenseid update'")
    text = "SPDX-License-Identifier: GPL-2.0\n" + "Some licence words. " * 10
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        with relay.relay_licenseid_warnings():
            found = LicenseDetector(str(db)).detect(text)
    assert found and found[0]["expression"] == "GPL-2.0-only"
    assert _said(caplog) == [
        (
            logging.INFO,
            "licenseid: input: variant not stated: GPL-2.0; using GPL-2.0-only",
        )
    ]


def test_detection_relays_the_warning_of_building_the_detector(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Detector construction is inside the relay too (a database an older
    licenseid built warns there)."""

    class _Outdated:
        def __init__(self) -> None:
            _outdated()

        def detect(self, text: str) -> list[object]:
            del text
            return []

    monkeypatch.setattr("pitloom.extract._license.LicenseDetector", _Outdated)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert detect_license_from_text("Some licence words. " * 10) is None
    assert _said(caplog) == [(logging.WARNING, f"licenseid: {_OUTDATED}")]
