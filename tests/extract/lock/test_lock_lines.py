# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The lines the lock readers say, from the hostile side: a value read from
a lock is one escaped, cut line; a ``requirements.txt`` line is counted as
pip counts it; a credential is never printed; a lock is named by its file
name, never its directory.

See also: tests/messages/test_lock_entry.py (the entries and helpers).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract.lock.cascade import apply_locked_dependencies
from pitloom.extract.lock.common import resolve_pinned_dependencies
from pitloom.extract.lock.pipfile import extract_pipfile_lock_dependencies
from pitloom.extract.lock.requirements import extract_pinned_requirements_dependencies
from pitloom.extract.lock.uv import extract_uv_lock_dependencies
from pitloom.logging_config import EXCERPT_CHARS
from tests._code_records import coded, has_parts

pytestmark = pytest.mark.platform

_HOSTILE = ["\n", "\x1b[31m", "\ud800"]
_HOSTILE_IDS = ["newline", "escape", "lone-surrogate"]


def _write_pipfile(project: Path, default: dict[str, object]) -> None:
    """A ``Pipfile.lock`` (JSON, so it can hold a lone surrogate)."""
    text = json.dumps({"_meta": {"pipfile-spec": 6}, "default": default})
    (project / "Pipfile.lock").write_text(text, encoding="ascii")


def _only_line(caplog: pytest.LogCaptureFixture, *codes: str) -> str:
    """The one coded line, with one of *codes*, checked printable and
    encodable."""
    [(line_code, text)] = coded(caplog)
    assert line_code in codes
    assert text.isprintable()
    text.encode("utf-8")
    return text


@pytest.mark.parametrize("bad", _HOSTILE, ids=_HOSTILE_IDS)
def test_a_hostile_name_is_one_escaped_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, bad: str
) -> None:
    _write_pipfile(tmp_path, {f"pkg{bad}": {"version": "==1"}})
    with caplog.at_level(logging.WARNING):
        assert extract_pipfile_lock_dependencies(tmp_path) == []
    text = _only_line(caplog, "lock-entry-malformed")
    assert has_parts(text, "FILE=Pipfile.lock", "not a valid package name")


@pytest.mark.parametrize("bad", _HOSTILE, ids=_HOSTILE_IDS)
@pytest.mark.parametrize("field", ["specifier", "range"])
def test_a_hostile_version_is_one_escaped_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, bad: str, field: str
) -> None:
    version = f"=={bad}" if field == "specifier" else f">=1{bad}"
    _write_pipfile(tmp_path, {"pkg": {"version": version}})
    with caplog.at_level(logging.WARNING):
        assert extract_pipfile_lock_dependencies(tmp_path) == []
    # A version that is no specifier is malformed; a range is unusable.
    text = _only_line(caplog, "lock-entry-malformed", "lock-entry-unusable")
    assert has_parts(text, "FILE=Pipfile.lock", "PACKAGE=pkg")


@pytest.mark.parametrize("bad", _HOSTILE, ids=_HOSTILE_IDS)
def test_a_hostile_uv_lock_extra_is_one_escaped_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, bad: str
) -> None:
    """TOML cannot hold a lone surrogate: ``uv.lock`` gets the escape."""
    if bad == "\ud800":
        bad = "\u001b"
    extra = json.dumps(f"x{bad}")
    (tmp_path / "uv.lock").write_text(
        'version = 1\n[[package]]\nname = "app"\nversion = "1"\n'
        'source = {editable = "."}\n'
        f'dependencies = [{{name = "foo", extra = {extra}}}]\n'
        '[[package]]\nname = "foo"\nversion = "1"\n',
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "app") == ["foo==1"]
    text = _only_line(caplog, "lock-entry-malformed")
    assert has_parts(text, "FILE=uv.lock", "PACKAGE=foo", "optional-dependencies")


def test_a_10_kb_version_is_cut_to_the_excerpt_length(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    long = "9" * 10_000
    _write_pipfile(tmp_path, {"pkg": {"version": f">={long}"}})
    with caplog.at_level(logging.WARNING):
        assert extract_pipfile_lock_dependencies(tmp_path) == []
    # An overlong number is no specifier (see parse_specifier_set).
    text = _only_line(caplog, "lock-entry-malformed", "lock-entry-unusable")
    assert has_parts(text, "PACKAGE=pkg", "...")
    assert len(text) < 2 * EXCERPT_CHARS + 100


def test_a_conflict_lists_each_version_cut(caplog: pytest.LogCaptureFixture) -> None:
    pins = [("pkg", "1" * 10_000), ("pkg", "2")]
    with caplog.at_level(logging.WARNING):
        assert resolve_pinned_dependencies(pins, "pylock.toml") == []
    text = _only_line(caplog, "lock-entry-conflict")
    assert has_parts(text, "FILE=pylock.toml", "PACKAGE=pkg", "'2'")
    assert len(text) < 2 * EXCERPT_CHARS + 100


def test_a_toml_error_names_the_parsers_line_not_a_line_number_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``tomllib`` counts ``\\n``, so a CRLF file reports the same line."""
    (tmp_path / "uv.lock").write_bytes(b"version = 1\r\nb = 2\r\nc = = 3\r\n")
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "app") is None
    text = _only_line(caplog, "lock-file-malformed")
    assert has_parts(text, "FILE=uv.lock", "does not parse", "line 3")
    assert "LINE=" not in text


@pytest.mark.parametrize(
    ("raw", "line"),
    [
        (b"idna==3.7\r\nurllib3==2.0\r\nrequests>=2\r\n", 3),
        (b"idna==3.7\n# note\x0crequests>=2\n", 3),
        (b"idna==3.7\rurllib3==2.0\rrequests>=2\r", 3),
    ],
    ids=["crlf", "form-feed", "lone-cr"],
)
def test_a_requirements_line_is_counted_as_pip_counts_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, raw: bytes, line: int
) -> None:
    """``str.splitlines()``: CRLF and a lone CR count once, a form feed
    starts a line (an editor may disagree)."""
    (tmp_path / "requirements.txt").write_bytes(raw)
    with caplog.at_level(logging.WARNING):
        assert extract_pinned_requirements_dependencies(tmp_path) is None
    text = _only_line(caplog, "lock-entry-unusable")
    assert has_parts(text, f"FILE=requirements.txt LINE={line}", "requests")


def test_a_credential_is_in_neither_the_text_nor_the_record_args(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "requirements.txt").write_text(
        "idna==3.7\nhttps://user:secret_pass@example.com/pkg-1.0.whl\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        assert extract_pinned_requirements_dependencies(tmp_path) is None
    text = _only_line(caplog, "lock-entry-malformed")
    assert has_parts(text, "FILE=requirements.txt LINE=2")
    assert "secret_pass" not in text
    assert "secret_pass" not in repr([r.args for r in caplog.records])


def test_a_direct_reference_prints_its_name_never_its_url(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "requirements.txt").write_text(
        "pkg @ https://user:secret_pass@example.com/pkg-1.0.whl\n", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        assert extract_pinned_requirements_dependencies(tmp_path) is None
    text = _only_line(caplog, "lock-entry-unusable")
    assert has_parts(text, "LINE=1", "pkg is a direct reference")
    assert "example.com" not in text
    assert "example.com" not in repr([r.args for r in caplog.records])


@pytest.mark.parametrize(
    ("previous", "lock", "said"),
    [
        (None, True, False),
        ("poetry.lock", False, False),
        ("poetry.lock", True, True),
    ],
    ids=["no-previous-result", "no-higher-lock", "previous-and-higher-lock"],
)
def test_a_lock_conflict_needs_a_previous_result_and_a_higher_lock(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    previous: str | None,
    lock: bool,
    said: bool,
) -> None:
    """``A and B``: one leg each (a previous result; a lock above it that
    wins)."""
    if lock:
        (tmp_path / "pylock.toml").write_text(
            'lock-version = "1.0"\ncreated-by = "t"\n'
            '[[packages]]\nname = "a"\nversion = "1"\n',
            encoding="utf-8",
        )
    metadata = ProjectMetadata(
        name="pkg",
        locked_dependencies=["b==1"],
        provenance=(
            {}
            if previous is None
            else {"locked_dependencies": f"Source: {previous} | Method: x"}
        ),
    )
    with caplog.at_level(logging.WARNING):
        apply_locked_dependencies(metadata, tmp_path)
    assert [code for code, _text in coded(caplog)] == (
        ["lock-file-conflict"] if said else []
    )
    assert metadata.locked_dependencies == (["a==1"] if lock else ["b==1"])
