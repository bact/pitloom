# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hugging Face Hub entries: ``hub-revision-unpinned``,
``hub-response-invalid`` and ``target-ambiguous/hf-url`` (code, condition,
effect, actor, release, topic and the fields of each line); the Hub API
failure lines of the three shared families (``download-network-failed``,
``download-timeout``, ``offline-unusable``); each printed line trusted as its
entry and nothing else; and each field a Hub line writes under a hostile value
at the sink (a credential, a control character, a fake code).

See also: tests/extract/remote/test_hub_api.py (the classifier that picks the
entry), tests/extract/remote/test_hub_unpinned.py (when the unpinned line is
said) and tests/messages/test_sbom_target.py (the neighbouring targets).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from pitloom.logging_config import configure_logging
from pitloom.messages import FAMILY_TOPICS, MESSAGES, Line, Message, emit
from pitloom.messages import trusted_message as trusted
from pitloom.messages.network import (
    DOWNLOAD_FAILED,
    DOWNLOAD_FAILED_WARNING_LINE,
    DOWNLOAD_TIMEOUT,
    DOWNLOAD_TIMEOUT_WARNING_LINE,
    HUB_RESPONSE_INVALID,
    HUB_RESPONSE_LINE,
    HUB_REVISION_UNPINNED,
    HUB_UNPINNED_LINE,
    OFFLINE_UNUSABLE,
    OFFLINE_WARNING_LINE,
)
from pitloom.messages.targets import HF_URL_REWRITE_LINE, TARGET_AMBIGUOUS_HF_URL
from tests._message_drift import SAMPLES

pytestmark = pytest.mark.platform  # escapes in the printed line

_LOG = logging.getLogger("pitloom.test_hub")
_TOKEN = "hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGh"  # 34 letters

#: The three entries: code, condition, effect, actor, topic, line level and
#: the field names of its one line, spelt out here and not read from them.
_ENTRIES = [
    (
        HUB_REVISION_UNPINNED,
        ("hub-revision-unpinned", "unpinned", "weaker", "user", "network"),
        ("WARNING", {"url"}),
    ),
    (
        HUB_RESPONSE_INVALID,
        ("hub-response-invalid", "invalid", "thinner", "user", "network"),
        ("WARNING", {"url", "failure", "outcome"}),
    ),
    (
        TARGET_AMBIGUOUS_HF_URL,
        ("target-ambiguous/hf-url", "ambiguous", "none", "none", "targets"),
        ("INFO", {"url", "target"}),
    ),
]


@pytest.mark.parametrize(
    ("message", "facts", "shape"), _ENTRIES, ids=["unpinned", "invalid", "hf-url"]
)
def test_each_entry_says_what_the_plan_names(
    message: Message, facts: tuple[str, ...], shape: tuple[str, set[str]]
) -> None:
    code, condition, effect, actor, topic = facts
    assert (message.code, message.condition) == (code, condition)
    assert (message.effect, message.actor, message.since) == (effect, actor, "0.25.0")
    assert MESSAGES[code] is message and FAMILY_TOPICS[message.family] == topic
    level, names = shape
    (line,) = message.lines
    assert (line.level, set(line.fields)) == (level, names)


#: A Hub API request's WARNING line of each shared family: the line's
#: fields, which every Hub request names (the page, what is not recorded).
_SHARED = [
    (DOWNLOAD_FAILED, DOWNLOAD_FAILED_WARNING_LINE, {"url", "failure", "outcome"}),
    (DOWNLOAD_TIMEOUT, DOWNLOAD_TIMEOUT_WARNING_LINE, {"url", "duration", "outcome"}),
    (OFFLINE_UNUSABLE, OFFLINE_WARNING_LINE, {"url", "outcome"}),
]


@pytest.mark.parametrize(
    ("message", "line", "names"), _SHARED, ids=["failed", "timeout", "offline"]
)
def test_a_shared_family_has_a_warning_line_a_hub_request_can_say(
    message: Message, line: Line, names: set[str]
) -> None:
    assert line in message.lines
    assert (line.level, set(line.fields)) == ("WARNING", names)


@pytest.mark.parametrize(
    "message", [DOWNLOAD_FAILED, DOWNLOAD_TIMEOUT, OFFLINE_UNUSABLE]
)
def test_a_shared_family_names_the_hub_api_calls(message: Message) -> None:
    """The reader of the catalogue learns the family covers ``model_info()``
    and ``dataset_info()``, in what it says and what it did."""
    assert "model_info()" in message.summary
    assert "dataset_info()" in message.summary
    assert "Hub API" in message.did


def _text(line: Line, **overrides: object) -> str:
    values = {name: SAMPLES[name] for name in line.fields} | overrides
    return line.render(values)


@pytest.mark.parametrize(
    ("message", "line"),
    [
        (HUB_REVISION_UNPINNED, HUB_UNPINNED_LINE),
        (HUB_RESPONSE_INVALID, HUB_RESPONSE_LINE),
        (TARGET_AMBIGUOUS_HF_URL, HF_URL_REWRITE_LINE),
        (DOWNLOAD_FAILED, DOWNLOAD_FAILED_WARNING_LINE),
        (DOWNLOAD_TIMEOUT, DOWNLOAD_TIMEOUT_WARNING_LINE),
        (OFFLINE_UNUSABLE, OFFLINE_WARNING_LINE),
    ],
    ids=["unpinned", "invalid", "hf-url", "failed", "timeout", "offline"],
)
def test_a_printed_line_is_trusted_as_its_entry_only_at_its_level(
    message: Message, line: Line
) -> None:
    text = _text(line)
    assert trusted(f"{line.level}: {text} [{message.code}]") is message
    other = "ERROR" if line.level != "ERROR" else "WARNING"
    assert trusted(f"{other}: {text} [{message.code}]") is None
    # Another entry's code does not make the line that entry's.
    assert trusted(f"{line.level}: {text} [url-unsafe]") is None


def test_the_hub_lines_read_as_the_plan_names_them() -> None:
    assert _text(HUB_UNPINNED_LINE, url="https://huggingface.co/o/m") == (
        "URL=https://huggingface.co/o/m: the Hub stated no revision; files "
        "are read at the default branch as it is now"
    )
    assert _text(
        HUB_RESPONSE_LINE,
        url="https://huggingface.co/datasets/o/d",
        failure=ValueError("Expecting value"),
        outcome="licence, description, keywords, version and creator not recorded",
    ) == (
        "URL=https://huggingface.co/datasets/o/d: the Hub's answer could not "
        "be read (Expecting value); licence, description, keywords, version "
        "and creator not recorded"
    )
    assert _text(
        HF_URL_REWRITE_LINE,
        url="http://hf.co/o/m",
        target="https://huggingface.co/o/m",
    ) == ("URL=http://hf.co/o/m: read as Hugging Face model https://huggingface.co/o/m")


def test_the_unpinned_advice_does_not_ask_the_user_for_a_value_they_cannot_give() -> (
    None
):
    """The user passes Pitloom no ``hub_info['sha']``: the advice must not
    name it."""
    assert "hub_info" not in HUB_REVISION_UNPINNED.advice
    assert "hub_info" not in HUB_UNPINNED_LINE.template


# -- a hostile value at the sink -------------------------------------------------


def _said(
    capsys: pytest.CaptureFixture[str],
    message: Message,
    level: int,
    **values: Any,
) -> str:
    configure_logging()
    emit(_LOG, message, level, **values)
    return capsys.readouterr().err


_HOSTILE_FAILURES = [
    ("bad\nWARNING: forged [over-cap]", "bad WARNING: forged [over-cap]"),
    ("\x1b[31mred\x1b[0m", "'\\x1b[31mred\\x1b[0m'"),
    ("tail [over-cap]", "tail [over-cap]"),
    (f"Bearer {_TOKEN}", "Bearer hf_***"),
    (f"ok\t{_TOKEN}", "ok hf_***"),
    ("see https://u:s3cret@h/x now", "see https://***:***@h/x now"),
]


@pytest.mark.parametrize(
    ("hostile", "shown"),
    _HOSTILE_FAILURES,
    ids=["newline", "escape", "fake-code", "bearer", "tab", "url-user"],
)
def test_a_hostile_failure_is_one_masked_line_with_its_own_code(
    capsys: pytest.CaptureFixture[str], hostile: str, shown: str
) -> None:
    err = _said(
        capsys,
        HUB_RESPONSE_INVALID,
        logging.WARNING,
        url="https://huggingface.co/o/m",
        failure=ValueError(hostile),
        outcome="x not recorded",
    )
    (line,) = err.splitlines()
    assert f"could not be read ({shown}); x not recorded [" in line
    assert line.endswith(" [hub-response-invalid]")
    assert trusted(line) is HUB_RESPONSE_INVALID
    assert "s3cret" not in err and _TOKEN not in err and "\x1b" not in err


@pytest.mark.parametrize(
    ("hostile", "shown"),
    [
        ("https://u:s3cret@h/o\nm", "'https://***:***@h/o\\nm'"),
        ("https://h/\x1b[2J", "'https://h/\\x1b[2J'"),
        (f"https://h/o/m?token={_TOKEN}", "https://h/o/m?token=***"),
        ("https://h/o/m [over-cap]", "https://h/o/m [over-cap]"),
    ],
    ids=["url-user", "escape", "token", "fake-code"],
)
def test_a_hostile_url_is_one_masked_line_in_every_hub_line(
    capsys: pytest.CaptureFixture[str], hostile: str, shown: str
) -> None:
    """The ``url`` of the unpinned line and of the invalid-answer line, and
    the ``url`` and ``target`` of the rewrite line."""
    said = [
        _said(capsys, HUB_REVISION_UNPINNED, logging.WARNING, url=hostile),
        _said(
            capsys,
            HUB_RESPONSE_INVALID,
            logging.WARNING,
            url=hostile,
            failure=ValueError("x"),
            outcome="y",
        ),
        _said(
            capsys,
            TARGET_AMBIGUOUS_HF_URL,
            logging.INFO,
            url=hostile,
            target=hostile,
        ),
    ]
    for err in said:
        (line,) = err.splitlines()
        assert f"URL={shown}: " in line
        assert "s3cret" not in err and _TOKEN not in err and "\x1b" not in err
        assert trusted(line) is not None
    assert said[2].count(shown) == 2
