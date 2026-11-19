# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The configuration lines the Hatchling hook says: its own table's refusals
(``enabled``, unknown keys, moved keys), which name no file (the table may come
from ``hatch.toml``), the project file shown relative, a bad
``SOURCE_DATE_EPOCH`` and the ``datetime-unpinned`` note.

See also: tests/messages/test_config_surfaces.py (the same lines from the
readers) and tests/extract/project/test_hatch_hook_validate.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.plugins._hatch_config import _MOVED_KEYS
from tests._code_records import coded, has_parts
from tests.extract.conftest import MINIMAL_PYPROJECT, make_hook, write_pyproject

pytestmark = pytest.mark.platform

# --- the Hatchling hook: its table may come from hatch.toml, so no file -------


def _hook_error(
    tmp_path: Path, config: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> tuple[str | None, str]:
    """``(code, message)`` of the one ERROR the hook said, and that it raised."""
    write_pyproject(tmp_path)
    hook = make_hook(str(tmp_path), config)
    with caplog.at_level(logging.INFO), pytest.raises(ValueError):
        hook.initialize("standard", {})
    (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    return coded(caplog)[caplog.records.index(record)]


@pytest.mark.parametrize(
    ("config", "code", "tail"),
    [
        pytest.param(
            {"enabled": "yes"},
            "config-invalid",
            "[tool.hatch.build.hooks.pitloom] enabled: must be true or false, "
            "got a string 'yes'",
            id="enabled",
        ),
        pytest.param(
            {"zeta": 1, "alpha": 2},
            "config-unknown-key",
            "[tool.hatch.build.hooks.pitloom]: unknown keys alpha, zeta; only "
            "enabled and Hatchling's own hook keys go here, other settings go "
            "in [tool.pitloom]",
            id="unknown-sorted",
        ),
        pytest.param(
            {"enable-by-default": False, "typo": 1},
            "config-unknown-key",
            "[tool.hatch.build.hooks.pitloom]: unknown keys typo; only ",
            id="unknown-beside-hatchling-key",
        ),
        pytest.param(
            {"a\nb": 1},
            "config-unknown-key",
            r"unknown keys 'a\nb'; only ",
            id="unknown-escaped",
        ),
        pytest.param(
            {"creator-name": "x", "typo": 1},
            "config-moved",
            "[tool.hatch.build.hooks.pitloom] creator-name: moved to "
            "[[tool.pitloom.creator]] name",
            id="moved-before-unknown",
        ),
    ],
)
def test_the_hook_says_its_own_table_and_no_file(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    config: dict[str, Any],
    code: str,
    tail: str,
) -> None:
    got_code, message = _hook_error(tmp_path, config, caplog)
    assert got_code == code
    assert message.startswith("Pitloom build hook: ")
    assert "FILE=" not in message and "\n" not in message
    assert tail in message


@pytest.mark.parametrize(("key", "destination"), sorted(_MOVED_KEYS.items()))
def test_a_moved_hook_key_names_where_it_went(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, key: str, destination: str
) -> None:
    code, message = _hook_error(tmp_path, {key: "x"}, caplog)
    assert code == "config-moved"
    assert message.endswith(
        f"[tool.hatch.build.hooks.pitloom] {key}: moved to {destination}"
    )


def test_a_hook_project_file_is_shown_relative(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The build tree is a temporary directory under pip: ``FILE=`` is the
    name Hatchling's user knows."""
    write_pyproject(tmp_path, MINIMAL_PYPROJECT + '\n[tool.pitloom]\npretty = "yes"\n')
    hook = make_hook(str(tmp_path), {})
    with caplog.at_level(logging.INFO), pytest.raises(ValueError):
        hook.initialize("standard", {})
    (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert record.getMessage() == (
        "Pitloom build hook: FILE=pyproject.toml: [tool.pitloom] pretty: "
        "must be true or false, got a string 'yes'"
    )
    assert str(tmp_path) not in record.getMessage()


@pytest.mark.parametrize(
    ("env", "tail", "unpinned"),
    [
        pytest.param({}, "", True, id="neither"),
        pytest.param({"SOURCE_DATE_EPOCH": "1767225600"}, "", False, id="epoch"),
        pytest.param(
            {},
            '[tool.pitloom.creation]\ncreation-datetime = "2026-01-01T00:00:00Z"\n',
            False,
            id="pinned",
        ),
        pytest.param(
            {"SOURCE_DATE_EPOCH": "1767225600"},
            '[tool.pitloom.creation]\ncreation-datetime = "2026-01-01T00:00:00Z"\n',
            False,
            id="both",
        ),
    ],
)
def test_the_hook_says_when_the_time_is_the_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    env: dict[str, str],
    tail: str,
    unpinned: bool,
) -> None:
    """One ``INFO:`` when neither the config nor ``SOURCE_DATE_EPOCH`` pins
    the time; nothing when either does."""
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    write_pyproject(tmp_path, MINIMAL_PYPROJECT + "\n" + tail)
    hook = make_hook(str(tmp_path), {})
    with caplog.at_level(logging.INFO):
        hook.initialize("standard", {})
    said = [
        (r.levelno, m)
        for r, (c, m) in zip(caplog.records, coded(caplog), strict=True)
        if c == "datetime-unpinned"
    ]
    if unpinned:
        ((level, message),) = said
        assert level == logging.INFO
        assert has_parts(message, "from the clock", "SOURCE_DATE_EPOCH")
        assert "creation-datetime" in message
    else:
        assert not said


@pytest.mark.parametrize(
    ("value", "tail"),
    [
        ("abc", "SOURCE_DATE_EPOCH=abc: not an integer"),
        ("99999999999999999", "SOURCE_DATE_EPOCH=99999999999999999: out of range"),
        ("1\n2", r"SOURCE_DATE_EPOCH='1\n2': not an integer"),
    ],
    ids=["text", "range", "newline"],
)
def test_a_bad_source_date_epoch_fails_the_hook_on_one_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    value: str,
    tail: str,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", value)
    code, message = _hook_error(tmp_path, {}, caplog)
    assert code == "source-date-epoch-invalid"
    assert tail in message and "\n" not in message
