# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Git URL families: each entry's code, level, condition, effect, actor,
release and fields; the lines a fetch says after ``Git source: `` (trusted),
the ones it never says after it (``ERROR``, other families); the closed
``ref_kind``; the ERROR templates that must not hold the words a retry reads
in git's own text; and each new or widened field under a hostile value at the
sink (a credential, a control character, a fake code).

See also: tests/messages/test_frames_codes.py (the frames),
tests/messages/test_git_surfaces.py (the command line and the library) and
tests/extract/remote/test_git_say.py (what a fetch says).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR, configure_logging
from pitloom.messages import (
    FAMILY_TOPICS,
    FIELDS,
    GIT_FRAME,
    GIT_PREFIX,
    MESSAGES,
    REF_KINDS,
    Line,
    Message,
    emit,
    say_summary,
    trusted_message,
)
from pitloom.messages.files import OVER_CAP
from pitloom.messages.git import (
    GIT_COMMAND,
    GIT_FAILED_LINE,
    GIT_FILTER_UNUSABLE,
    GIT_LINK_UNSAFE,
    GIT_MISSING,
    GIT_REDIRECT_UNUSABLE,
    GIT_REF_NOT_FOUND,
    GIT_REPOSITORY_EMPTY,
    GIT_REPOSITORY_UNUSABLE,
    GIT_URL_INVALID,
)
from pitloom.messages.models import LFS_POINTER
from pitloom.messages.network import (
    DOWNLOAD_FAILED,
    DOWNLOAD_TIMEOUT,
    GIT_NETWORK_FAILED_LINE,
    GIT_REDIRECT_OUTCOME,
    GIT_TIMEOUT_LINE,
    QUERY_NO_EFFECT,
    REDIRECT_REFUSED_WARNING_LINE,
    TOO_MANY_REDIRECTS_LINE,
    URL_MOVED,
    URL_REFUSED,
    VERSION_IGNORED_LINE,
)
from pitloom.messages.targets import (
    CONFIG_UNSAFE,
    NO_SBOM_TARGET,
    PROJECT_NOT_FOUND,
    TARGET_AMBIGUOUS_GIT_PAGE,
)
from tests._message_drift import SAMPLES

_LOG = logging.getLogger("pitloom.test_git")
_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

_Shape = tuple[str, frozenset[str]]


def _shapes(*lines: tuple[str, str]) -> list[_Shape]:
    """``(level, "a b")`` pairs as ``(level, {"a", "b"})`` pairs, sorted."""
    return sorted((lv, frozenset(names.split())) for lv, names in lines)


#: Each entry: its code, condition, effect, actor and the (level, fields) of
#: each of its lines, spelt out here and not read from the entry.
_ENTRIES = [
    (
        GIT_URL_INVALID,
        ("git-url-invalid", "invalid", "not-written", "user"),
        _shapes(*[("ERROR", "url")] * 4),
    ),
    (
        GIT_REF_NOT_FOUND,
        ("git-ref-not-found", "not-found", "not-written", "user"),
        _shapes(("ERROR", "url ref")),
    ),
    (
        GIT_MISSING,
        ("git-missing", "missing", "not-written", "user"),
        _shapes(("ERROR", "")),
    ),
    (
        GIT_REPOSITORY_UNUSABLE,
        ("git-repository-unusable", "unusable", "not-written", "user"),
        _shapes(("ERROR", "command error")),
    ),
    (
        GIT_REPOSITORY_EMPTY,
        ("git-repository-unusable/empty", "unusable", "not-written", "user"),
        _shapes(("ERROR", "url")),
    ),
    (
        GIT_REDIRECT_UNUSABLE,
        ("git-redirect-unusable", "unusable", "none", "none"),
        _shapes(("INFO", "url why")),
    ),
    (
        GIT_FILTER_UNUSABLE,
        ("git-filter-unusable", "unusable", "none", "none"),
        _shapes(("INFO", "url")),
    ),
    (
        GIT_LINK_UNSAFE,
        ("git-link-unsafe", "unsafe", "thinner", "none"),
        _shapes(("INFO", "url number")),
    ),
    (
        TARGET_AMBIGUOUS_GIT_PAGE,
        ("target-ambiguous/git-page", "ambiguous", "none", "none"),
        _shapes(
            ("INFO", "url target"),
            ("INFO", "url target ref_kind ref"),
            ("INFO", "url target path"),
            ("INFO", "url target ref_kind ref path"),
            ("INFO", "url target"),
            ("INFO", "url path"),
            ("INFO", "url path"),
        ),
    ),
]
_ENTRY_IDS = [
    "url-invalid",
    "ref-not-found",
    "missing",
    "unusable",
    "empty",
    "redirect-unusable",
    "filter-unusable",
    "link-unsafe",
    "git-page",
]


@pytest.mark.parametrize(("message", "facts", "shapes"), _ENTRIES, ids=_ENTRY_IDS)
def test_each_new_entry_says_what_the_plan_names(
    message: Message, facts: tuple[str, str, str, str], shapes: list[_Shape]
) -> None:
    code, condition, effect, actor = facts
    assert (message.code, message.condition) == (code, condition)
    assert (message.effect, message.actor) == (effect, actor)
    assert message.since == "0.25.0"
    assert MESSAGES[code] is message
    assert sorted((ln.level, ln.fields) for ln in message.lines) == shapes


def test_the_git_families_are_on_the_git_page_and_the_variant_on_targets() -> None:
    git = [GIT_URL_INVALID, GIT_REF_NOT_FOUND, GIT_MISSING, GIT_REPOSITORY_UNUSABLE]
    git += [GIT_REPOSITORY_EMPTY, GIT_FILTER_UNUSABLE, GIT_REDIRECT_UNUSABLE]
    git += [GIT_LINK_UNSAFE]
    assert {FAMILY_TOPICS[m.family] for m in git} == {"git"}
    assert FAMILY_TOPICS[TARGET_AMBIGUOUS_GIT_PAGE.family] == "targets"
    assert GIT_COMMAND.topic == "git"


@pytest.mark.parametrize(
    ("message", "line", "level", "names"),
    [
        (QUERY_NO_EFFECT, VERSION_IGNORED_LINE, "INFO", {"url"}),
        (URL_MOVED, URL_MOVED.lines[0], "INFO", {"url", "target"}),
        (
            URL_REFUSED,
            REDIRECT_REFUSED_WARNING_LINE,
            "WARNING",
            {"url", "target", "why", "outcome"},
        ),
        (URL_REFUSED, TOO_MANY_REDIRECTS_LINE, "ERROR", {"url", "number"}),
        (DOWNLOAD_TIMEOUT, GIT_TIMEOUT_LINE, "ERROR", {"command", "duration"}),
        (DOWNLOAD_FAILED, GIT_NETWORK_FAILED_LINE, "ERROR", {"command", "error"}),
        (PROJECT_NOT_FOUND, PROJECT_NOT_FOUND.lines[1], "ERROR", {"path", "folders"}),
        (PROJECT_NOT_FOUND, PROJECT_NOT_FOUND.lines[2], "ERROR", {"path", "folders"}),
        (NO_SBOM_TARGET, NO_SBOM_TARGET.lines[1], "ERROR", {"path", "folders"}),
        (NO_SBOM_TARGET, NO_SBOM_TARGET.lines[2], "ERROR", {"path", "folders"}),
    ],
    ids=[
        "version-ignored",
        "url-moved",
        "refused-warning",
        "too-many",
        "git-timeout",
        "network-failed",
        "project-whole",
        "project-folder",
        "target-whole",
        "target-folder",
    ],
)
def test_a_reused_entry_holds_the_git_line(
    message: Message, line: Line, level: str, names: set[str]
) -> None:
    assert line in message.lines
    assert (line.level, line.fields) == (level, frozenset(names))


def test_the_git_redirect_outcome_reads_in_the_refused_warning() -> None:
    values = {n: SAMPLES[n] for n in REDIRECT_REFUSED_WARNING_LINE.fields}
    values["outcome"] = GIT_REDIRECT_OUTCOME
    text = REDIRECT_REFUSED_WARNING_LINE.render(values)
    assert text.endswith("; the URL itself asked of git")
    line = f"WARNING: {GIT_PREFIX}{text} [url-unsafe]"
    assert trusted_message(line) is URL_REFUSED


# -- the printed lines after the frame ----------------------------------------

#: The messages a fetch says after ``Git source: ``.
_FRAMED = (
    GIT_REDIRECT_UNUSABLE,
    GIT_FILTER_UNUSABLE,
    GIT_LINK_UNSAFE,
    TARGET_AMBIGUOUS_GIT_PAGE,
    URL_MOVED,
    URL_REFUSED,
    QUERY_NO_EFFECT,
    CONFIG_UNSAFE,
)
_FRAMED_LINES = [
    pytest.param(m, ln, id=f"{m.code}-{i}")
    for m in _FRAMED
    for i, ln in enumerate(m.lines)
    if ln.level != "ERROR"
]


def _values(line: Line) -> dict[str, Any]:
    """A sample value of each field *line* names."""
    return {n: SAMPLES[n] for n in line.fields}


def _printed(line: Line) -> str:
    return line.render(_values(line))


@pytest.mark.parametrize(("message", "line"), _FRAMED_LINES)
def test_each_printed_git_line_is_trusted_after_the_frame(
    message: Message, line: Line
) -> None:
    printed = f"{line.level}: {GIT_PREFIX}{_printed(line)} [{message.code}]"
    assert trusted_message(printed) is message
    assert trusted_message(printed.replace(GIT_PREFIX, "", 1)) is message


@pytest.mark.parametrize(
    "message",
    [m for m in _FRAMED if m.family != "config-unsafe" and "url" in m.lines[0].fields],
    ids=lambda m: m.code,
)
def test_each_git_decision_names_its_url_first(message: Message) -> None:
    for line in message.lines:
        if line.level != "ERROR":
            assert line.template.startswith("URL=%(url)s: "), line.template


@pytest.mark.parametrize("message", [OVER_CAP, LFS_POINTER], ids=lambda m: m.code)
def test_a_line_of_another_family_is_not_trusted_after_the_frame(
    message: Message,
) -> None:
    line = message.lines[0]
    printed = _printed(line)
    assert trusted_message(f"{line.level}: {printed} [{message.code}]") is message
    framed = f"{line.level}: {GIT_PREFIX}{printed} [{message.code}]"
    assert trusted_message(framed) is None
    assert not GIT_FRAME.allows(message.code, line.level)
    with pytest.raises(InternalError):
        emit(
            _LOG,
            message,
            getattr(logging, line.level),
            line=line,
            frame=GIT_FRAME,
            **_values(line),
        )


_ERRORS = [
    (GIT_URL_INVALID, GIT_URL_INVALID.lines[0]),
    (GIT_URL_INVALID, GIT_URL_INVALID.lines[1]),
    (GIT_URL_INVALID, GIT_URL_INVALID.lines[2]),
    (GIT_REF_NOT_FOUND, GIT_REF_NOT_FOUND.lines[0]),
    (GIT_MISSING, GIT_MISSING.lines[0]),
    (GIT_REPOSITORY_UNUSABLE, GIT_REPOSITORY_UNUSABLE.lines[0]),
    (GIT_REPOSITORY_EMPTY, GIT_REPOSITORY_EMPTY.lines[0]),
]


@pytest.mark.parametrize(
    ("message", "line"),
    _ERRORS,
    ids=[f"{m.code}-{i}" for i, (m, _) in enumerate(_ERRORS)],
)
def test_an_error_line_never_carries_the_frame(message: Message, line: Line) -> None:
    printed = _printed(line)
    assert trusted_message(f"ERROR: {printed} [{message.code}]") is message
    assert trusted_message(f"ERROR: {GIT_PREFIX}{printed} [{message.code}]") is None
    assert not GIT_FRAME.allows(message.code, "ERROR")
    with pytest.raises(InternalError):
        emit(
            _LOG,
            message,
            logging.ERROR,
            line=line,
            frame=GIT_FRAME,
            **_values(line),
        )


def test_a_git_frame_before_the_wrong_text_is_not_trusted() -> None:
    printed = _printed(GIT_FILTER_UNUSABLE.lines[0])
    ok = f"INFO: {GIT_PREFIX}{printed} [git-filter-unusable]"
    assert trusted_message(ok) is GIT_FILTER_UNUSABLE
    for forged in (
        f"INFO: {GIT_PREFIX}{GIT_PREFIX}{printed} [git-filter-unusable]",
        f"INFO: {GIT_PREFIX.rstrip()}{printed} [git-filter-unusable]",
        f"WARNING: {GIT_PREFIX}{printed} [git-filter-unusable]",
        f"INFO: {GIT_PREFIX}{printed}; x [git-filter-unusable]",
        f"INFO: {GIT_PREFIX}{printed} [git-link-unsafe]",
    ):
        assert trusted_message(forged) is None, forged


# -- the closed ref_kind -------------------------------------------------------


def test_ref_kind_is_closed() -> None:
    assert set(REF_KINDS) == {"branch", "tag", "commit"}
    assert FIELDS["ref_kind"].pattern == "|".join(REF_KINDS)
    line = TARGET_AMBIGUOUS_GIT_PAGE.lines[1]
    values = {n: SAMPLES[n] for n in line.fields}
    for kind in REF_KINDS:
        assert f", {kind} v1.0" in line.render({**values, "ref_kind": kind})
    for unknown in ("head", "Tag", "", "tag\nx"):
        with pytest.raises(ValueError, match="ref_kind"):
            line.render({**values, "ref_kind": unknown})


# -- the words a retry reads in git's own text ---------------------------------

_SNIFFED = ("not found", "does not appear to be a git repository", "HTTP 400")


def test_no_git_error_template_holds_a_word_a_retry_reads() -> None:
    """``_not_a_repository`` and ``_checkout`` read ``str(exc)`` for these:
    a template holding one would turn every such failure into a retry."""
    lines = [ln for _, ln in _ERRORS]
    assert len(lines) == 7
    for line in lines:
        for word in _SNIFFED:
            assert word.lower() not in line.template.lower(), (word, line.template)


def test_the_unusable_line_is_not_the_network_line() -> None:
    values = {"command": "clone", "error": "fatal: repository gone"}
    text = GIT_FAILED_LINE.render(values)
    assert text == "git clone: fatal: repository gone; nothing fetched"
    assert text != GIT_NETWORK_FAILED_LINE.render(values)
    assert GIT_FAILED_LINE.template != GIT_NETWORK_FAILED_LINE.template
    assert GIT_FAILED_LINE in GIT_REPOSITORY_UNUSABLE.lines
    assert GIT_NETWORK_FAILED_LINE in DOWNLOAD_FAILED.lines


# -- a hostile value at the sink -------------------------------------------------


def _say(
    capsys: pytest.CaptureFixture[str],
    message: Message,
    line: Line | None = None,
    **values: Any,
) -> str:
    """What *message* prints at the level of *line* (its first line's), for
    *values*."""
    configure_logging()
    level = getattr(logging, (line or message.lines[0]).level)
    emit(_LOG, message, level, line=line, **values)
    return capsys.readouterr().err


_URL = "https://u:tok@h.example/r.git"


@pytest.mark.parametrize(
    ("message", "line", "values"),
    [
        (GIT_REDIRECT_UNUSABLE, None, {"url": _URL, "why": "HTTP 404"}),
        (GIT_URL_INVALID, GIT_URL_INVALID.lines[0], {"url": _URL}),
        (GIT_URL_INVALID, GIT_URL_INVALID.lines[1], {"url": _URL}),
        (GIT_URL_INVALID, GIT_URL_INVALID.lines[2], {"url": _URL}),
        (GIT_REPOSITORY_EMPTY, None, {"url": _URL}),
        (GIT_REF_NOT_FOUND, None, {"url": _URL, "ref": "v1"}),
        (GIT_LINK_UNSAFE, None, {"url": _URL, "number": 1}),
    ],
    ids=["redirect", "scheme", "port", "path", "empty", "ref", "link"],
)
def test_a_url_credential_is_masked_at_the_sink(
    capsys: pytest.CaptureFixture[str],
    message: Message,
    line: Line | None,
    values: dict[str, object],
) -> None:
    err = _say(capsys, message, line, **values)
    assert "tok" not in err and "https://***:***@h.example/r.git" in err
    assert len(err.splitlines()) == 1


def test_a_target_credential_is_masked_at_the_sink(
    capsys: pytest.CaptureFixture[str],
) -> None:
    line = TARGET_AMBIGUOUS_GIT_PAGE.lines[0]
    configure_logging()
    emit(
        _LOG,
        TARGET_AMBIGUOUS_GIT_PAGE,
        logging.INFO,
        line=line,
        frame=GIT_FRAME,
        url="https://h.example/g/p",
        target=_URL,
    )
    (err,) = capsys.readouterr().err.splitlines()
    assert "tok" not in err and "***:***@h.example" in err
    assert err.startswith(f"INFO: {GIT_PREFIX}URL=https://h.example/g/p: read as ")
    assert trusted_message(err) is TARGET_AMBIGUOUS_GIT_PAGE


def test_a_command_line_credential_is_masked_at_the_sink(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    line = f"git clone --depth 1 {_URL} -- dest"
    say_summary(_LOG, GIT_COMMAND, command_line=line)
    (err,) = capsys.readouterr().err.splitlines()
    assert "tok" not in err
    masked = "git clone --depth 1 https://***:***@h.example/r.git -- dest"
    assert err == f"INFO: {GIT_PREFIX}$ {masked}"
    assert trusted_message(err) is None  # a summary has no code


@pytest.mark.parametrize(
    "ref",
    [_TOKEN, f"v1 {_TOKEN}"],
    ids=["token", "token-after-text"],
)
def test_a_token_shaped_ref_is_masked_at_the_sink(
    capsys: pytest.CaptureFixture[str], ref: str
) -> None:
    err = _say(capsys, GIT_REF_NOT_FOUND, None, url="https://h.example/r", ref=ref)
    assert _TOKEN not in err and "ghp_***" in err
    assert len(err.splitlines()) == 1
    assert trusted_message(err.rstrip("\n")) is GIT_REF_NOT_FOUND


def test_a_ref_with_a_line_break_and_an_escape_is_one_escaped_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ref = "x\nERROR: forged [over-cap]\x1b[31m%0A"
    err = _say(capsys, GIT_REF_NOT_FOUND, None, url="https://h.example/r", ref=ref)
    (line,) = err.splitlines()
    assert "\x1b" not in err and "\\n" in line and "\\x1b" in line
    assert line.endswith(" [git-ref-not-found]")
    assert trusted_message(line) is GIT_REF_NOT_FOUND


def test_a_hostile_error_is_one_line_with_the_code_and_no_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Server ``remote:`` text: a CRLF, an escape, a fake code and a URL with
    a credential."""
    error = (
        "fatal: remote: see https://u:tok@h/r\r\nremote: \x1b[2Jgone [over-cap]"
        f"; token {_TOKEN}"
    )
    err = _say(capsys, GIT_REPOSITORY_UNUSABLE, None, command="clone", error=error)
    (line,) = err.splitlines()
    assert "tok@" not in line and _TOKEN not in line and "\x1b" not in line
    assert "\\r\\n" in line and line.endswith(
        "; nothing fetched [git-repository-unusable]"
    )
    assert trusted_message(line) is GIT_REPOSITORY_UNUSABLE
    assert line.count(" [git-repository-unusable]") == 1


def test_the_code_rides_on_the_record(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        emit(
            _LOG,
            GIT_FILTER_UNUSABLE,
            logging.INFO,
            frame=GIT_FRAME,
            url="https://h.example/r",
        )
    (record,) = caplog.records
    assert getattr(record, CODE_ATTR) == "git-filter-unusable"
    assert record.getMessage().startswith(f"{GIT_PREFIX}URL=https://h.example/r: ")
    assert "[" not in record.getMessage()
