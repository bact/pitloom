# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The kind an uncoded record carries
(:data:`pitloom.logging_config.KIND_ATTR`): each writer of a summary, a
``-v`` detail and a relay sets it, the printed line reads back as the same
kind (:func:`pitloom.messages.line_kind`), and each relay module's own
prefix is one of :data:`pitloom.messages.RELAY_PREFIXES`.

See also: tests/messages/test_line_kind.py (the classifier),
tests/extract/test_reader_relay.py (a reader's relay said again).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import logging_config
from pitloom.cli.kv_output import log_kv
from pitloom.core import _models_wheel_setuptools_relay as setuptools_relay
from pitloom.extract import _licenseid_relay
from pitloom.extract.ai_model import pytorch
from pitloom.logging_config import CODE_ATTR, KIND_ATTR, print_error
from pitloom.messages import (
    RELAY_EXTRA,
    RELAY_PREFIXES,
    SUMMARIES,
    line_kind,
    say_summary,
)
from pitloom.messages._sbom_input import VALIDATOR_PREFIX

_LOG = logging.getLogger("pitloom.test_record_kinds")


def _said(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    (record,) = [r for r in caplog.records if r.name.startswith("pitloom")]
    return record


def _summary() -> None:
    (merged,) = [s for s in SUMMARIES if s.template.startswith("merge: ")]
    say_summary(_LOG, merged, number=3)


def _detail() -> None:
    log_kv(OUTPUT_PATH="sbom.json")


def _licenseid() -> None:
    # A text of its own: the relay says each text once per process.
    _licenseid_relay.say("test_record_kinds: a warning", logging.INFO)


def _setuptools() -> None:
    setuptools_relay.relay_stderr_text(Path("p"), "error: x")


def _fickling() -> None:
    # pylint: disable-next=protected-access
    pytorch._relay_fickling_stderr("its own words")


@pytest.mark.parametrize(
    ("say", "kind"),
    [
        (_summary, "summary"),
        (_detail, "detail"),
        (_licenseid, "relay"),
        (_setuptools, "relay"),
        (_fickling, "relay"),
    ],
    ids=["summary", "detail", "licenseid", "setuptools", "fickling"],
)
def test_each_uncoded_writer_marks_its_record_s_kind(
    caplog: pytest.LogCaptureFixture, say: Callable[[], None], kind: str
) -> None:
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        say()
    record = _said(caplog)
    assert getattr(record, KIND_ATTR) == kind
    assert getattr(record, CODE_ATTR, None) is None
    assert line_kind(f"{record.levelname}: {record.getMessage()}") == kind


def test_each_relay_module_s_prefix_is_declared() -> None:
    """A relay module keeps its prefix as a module constant (the message
    inventory's shape); the classifier reads :data:`RELAY_PREFIXES`."""
    own = {
        _licenseid_relay.PREFIX,
        # pylint: disable-next=protected-access
        setuptools_relay._PREFIX,
        pytorch.FICKLING_PREFIX,
        VALIDATOR_PREFIX,
    }
    assert own == set(RELAY_PREFIXES)
    assert len(RELAY_PREFIXES) == len(own)


def test_the_relay_extra_is_read_only() -> None:
    assert dict(RELAY_EXTRA) == {KIND_ATTR: "relay"}
    with pytest.raises(TypeError):
        RELAY_EXTRA[KIND_ATTR] = "summary"  # type: ignore[index]


def test_print_error_writes_through_its_one_seam(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every ``ERROR:`` line :func:`print_error` writes passes
    ``_write_error_line``, looked up at each call: a wrapper sees it."""
    seen: list[str] = []
    monkeypatch.setattr(logging_config, "_write_error_line", seen.append)
    print_error(VALIDATOR_PREFIX + "a finding", frame="loom generate: ")
    print_error("boom", code="lfs-pointer", frame="")
    assert seen == [
        "ERROR: loom generate: spdx3-validate: a finding",
        "ERROR: boom [lfs-pointer]",
    ]
    assert capsys.readouterr().err == ""
    assert [line_kind(line) for line in seen] == ["relay", "uncoded"]


def test_the_seam_writes_one_line_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_error("boom", frame="")
    assert capsys.readouterr().err == "ERROR: boom\n"
