# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What ``licenseid`` warns, relayed as tagged ``pitloom`` records
(:mod:`pitloom.extract._licenseid_relay`).

See also: tests/test_licence_db_missing_surfaces.py (the relay on the CLI,
library and hook surfaces), tests/core/test_warning_capture.py (the relay
and Pitloom's other warning blocks in threads).
"""

from __future__ import annotations

import logging
import threading
import warnings
from pathlib import Path

import pytest
from licenseid import get_default_db_path, resolve
from licenseid import warning as licenseid_warning

from pitloom.extract import _license
from pitloom.extract import _licenseid_relay as relay
from pitloom.extract._license import resolve_declared_value
from pitloom.extract._license_text_match import detect_license_from_text
from tests._licenseid_warn import as_licenseid, warn_from_pitloom

_LOGGER = relay.__name__
_OUTDATED = "database: build v2 outdated: current v3; run 'licenseid update'"
_GUESS = "licenseid: input: variant not stated"


def _said(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == _LOGGER]


def _outdated() -> None:
    """Warn as licenseid does, through its one emitter, for Pitloom."""
    warn_from_pitloom(
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
            warn_from_pitloom(*parts)
    assert _said(caplog) == [expected]


def test_a_block_that_raises_still_relays(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        with pytest.raises(RuntimeError, match="boom"):
            with relay.relay_licenseid_warnings():
                _outdated()
                raise RuntimeError("boom")
    assert _said(caplog) == [(logging.WARNING, f"licenseid: {_OUTDATED}")]


def test_another_warning_goes_on_to_python_when_given(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with warnings.catch_warnings(record=True) as outer:
        warnings.simplefilter("always")
        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            with relay.relay_licenseid_warnings():
                warnings.warn("not licenseid's", UserWarning, stacklevel=1)
                given = [str(w.message) for w in outer]
    assert given == ["not licenseid's"]
    assert [w.filename for w in outer] == [__file__]
    assert not _said(caplog)


def test_a_licenseid_warning_to_other_code_follows_the_host_filters() -> None:
    """Only a warning of a ``pitloom`` module is the relay's: one this test
    module is given stays under the suite's ``error`` filter."""
    with pytest.raises(licenseid_warning.LicenseIdWarning, match="outdated"):
        with relay.relay_licenseid_warnings():
            licenseid_warning.warn("database", "build v2 outdated")


def test_a_lookup_changes_the_filters_once() -> None:
    """The relay's filter stays first; a later lookup changes nothing, so a
    warning shown once per location (``default``) is not shown again per
    lookup (a change of the filters resets that record)."""
    with warnings.catch_warnings(record=True) as shown:
        warnings.simplefilter("default")
        before = list(warnings.filters)
        after: list[object] = []
        for _ in range(3):
            with relay.relay_licenseid_warnings():
                _outdated()
                warnings.warn("third-party deprecation", UserWarning, stacklevel=1)
            after.append(list(warnings.filters))
        # pylint: disable-next=protected-access
        assert after == [[relay._FILTER, *before]] * 3
    assert [str(w.message) for w in shown] == ["third-party deprecation"]


def test_a_warning_of_another_thread_is_not_taken(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only this thread's warnings are recorded; another thread's goes on to
    Python when given, and a ``licenseid`` one of it is not said."""

    def other() -> None:
        _outdated()
        warnings.warn("another thread's", UserWarning, stacklevel=1)

    with warnings.catch_warnings(record=True) as shown:
        warnings.simplefilter("always")
        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            with relay.relay_licenseid_warnings():
                thread = threading.Thread(target=other)
                thread.start()
                thread.join(timeout=30)
                given = sorted(str(w.message) for w in shown)
    assert given == ["another thread's", _OUTDATED]
    assert not _said(caplog)


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
        found = detect_license_from_text(text)
    assert found == "GPL-2.0-only"
    # the database the host has may say more (an older build)
    assert [line for line in _said(caplog) if line[1].startswith(_GUESS)] == [
        (
            logging.INFO,
            "licenseid: input: variant not stated: GPL-2.0; using GPL-2.0-only",
        )
    ]


def test_resolving_relays_what_resolve_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Resolving a declared value is inside the relay too: what
    ``resolve()`` warns is one tagged line, and the reading is kept."""
    real = resolve

    def warning_resolve(value: str, source: str) -> object:
        assert source == "packaged"
        _outdated()
        return real(value, source="packaged")

    monkeypatch.setattr(_license, "resolve", as_licenseid(warning_resolve))
    _license.clear_resolution_cache()
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        found = resolve_declared_value("Apache2")
    _license.clear_resolution_cache()
    assert found is not None and found["expression"] == "Apache-2.0"
    assert _said(caplog) == [(logging.WARNING, f"licenseid: {_OUTDATED}")]


def test_detection_relays_the_warning_of_building_the_detector(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Detector construction is inside the relay too (a database an older
    licenseid built warns there)."""

    # pylint: disable-next=too-few-public-methods
    class _Outdated:
        def __init__(self) -> None:
            _outdated()

        def detect(self, text: str) -> list[object]:
            del text
            return []

    monkeypatch.setattr(
        "pitloom.extract._license_text_match.LicenseDetector", _Outdated
    )
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert detect_license_from_text("Some licence words. " * 10) is None
    assert _said(caplog) == [(logging.WARNING, f"licenseid: {_OUTDATED}")]


def test_detection_relays_what_detect_itself_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A warning given while detecting (not while building the detector)
    is relayed, not raised out of the detection."""

    # pylint: disable-next=too-few-public-methods
    class _Guessing:
        def detect(self, text: str) -> list[object]:
            del text
            warn_from_pitloom(
                "input", "variant not stated", "GPL-2.0", "using GPL-2.0-only"
            )
            return [{"expression": "GPL-2.0-only", "score": 1.0}]

    monkeypatch.setattr(
        "pitloom.extract._license_text_match.LicenseDetector", _Guessing
    )
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        found = detect_license_from_text("Some licence words. " * 10)
    assert found == "GPL-2.0-only"
    assert _said(caplog) == [
        (
            logging.INFO,
            "licenseid: input: variant not stated: GPL-2.0; using GPL-2.0-only",
        )
    ]
