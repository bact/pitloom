# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The strict check of the catalogue at run time (:mod:`tests._strict_uncoded`):
a record or an ``ERROR:`` line said without a code needs a kind that
explains it, or the test's own ``uncoded_output`` marker; a stale allowance
fails.

See also: tests/messages/test_drift_records.py (coded records),
tests/messages/test_line_kind.py (reading a line back).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess  # nosec B404
import sys
import textwrap
import types
from pathlib import Path
from typing import Literal

import pytest

from pitloom import logging_config
from pitloom.logging_config import CODE_ATTR, KIND_ATTR, print_error
from pitloom.messages import LONGEST_LINE
from tests._loom_child import run_loom, uncoded_failures
from tests._message_drift import record_problem
from tests._strict_uncoded import (
    Finding,
    Verdict,
    call_ran,
    check,
    failures,
    in_scope,
    line_finding,
    note_call_report,
    rendered_line,
    strict_finding,
)

_REPO = Path(__file__).resolve().parents[2]
_SUMMARY_TEXT = "merge: merged 3 fragment(s)"


def _record(
    level: int,
    msg: str,
    *,
    code: str | None = None,
    kind: str | None = None,
    name: str = "pitloom.x",
) -> logging.LogRecord:
    record = logging.LogRecord(name, level, __file__, 1, msg, None, None)
    if code is not None:
        setattr(record, CODE_ATTR, code)
    if kind is not None:
        setattr(record, KIND_ATTR, kind)
    return record


@pytest.mark.parametrize(
    ("record", "fragment"),
    [
        (_record(logging.WARNING, "own words"), "no kind"),
        (_record(logging.WARNING, "own words", name="pitloom"), "no kind"),
        (_record(logging.INFO, "own words"), "no kind"),
        (_record(logging.DEBUG, "own words"), None),
        (_record(logging.WARNING, "own words", name="pitloomx"), None),
        (_record(logging.WARNING, "own words", name="pitloom.test_x"), None),
        (_record(logging.WARNING, "own words", name="other"), None),
        (_record(logging.INFO, _SUMMARY_TEXT, kind="summary"), None),
        (_record(logging.INFO, "own words", kind="summary"), "reads as 'uncoded'"),
        (_record(logging.INFO, "KEY=v", kind="detail"), None),
        (_record(logging.WARNING, "licenseid: its words", kind="relay"), None),
        (_record(logging.WARNING, "its words", kind="relay"), "reads as 'uncoded'"),
        (_record(logging.WARNING, "own words", kind="loud"), "kind 'loud'"),
        (
            _record(logging.WARNING, "x", code="lfs-pointer", kind="relay"),
            "code 'lfs-pointer' and kind",
        ),
        (
            _record(logging.WARNING, "x" * LONGEST_LINE, code="lfs-pointer"),
            "too long",
        ),
        (_record(logging.WARNING, "x" * LONGEST_LINE), "too long"),
    ],
    ids=[
        "uncoded",
        "root-logger",
        "info",
        "debug",
        "pitloomx",
        "test-logger",
        "third-party",
        "summary",
        "summary-text",
        "detail",
        "relay",
        "relay-unprefixed",
        "unknown-kind",
        "code-and-kind",
        "overlong-coded",
        "overlong",
    ],
)
def test_a_record_without_a_code_needs_its_kind(
    record: logging.LogRecord, fragment: str | None
) -> None:
    problem = record_problem(record)
    if fragment is None:
        assert problem is None
    else:
        assert problem is not None and fragment in problem


@pytest.mark.parametrize("kind", ["relay", "loud"])
def test_a_test_s_own_logger_is_never_checked(kind: str) -> None:
    """A ``pitloom.test_*`` logger is out of scope, the checks no marker may
    allow included (a code and a kind, an unknown kind)."""
    assert not in_scope("pitloom.test_x", logging.WARNING)
    record = _record(
        logging.WARNING, "x", code="lfs-pointer", kind=kind, name="pitloom.test_x"
    )
    assert strict_finding(record) is None


@pytest.mark.parametrize("when", ["setup", "teardown"])
def test_only_the_call_phase_is_noted(when: Literal["setup", "teardown"]) -> None:
    """A setup or teardown report never says the call ran: a test whose
    setup errored is not held to its allowances."""
    item = types.SimpleNamespace(stash=pytest.Stash())
    report = pytest.TestReport(
        nodeid="x",
        location=("x", 0, "x"),
        keywords={},
        outcome="passed",
        longrepr=None,
        when=when,
    )
    note_call_report(item, report)  # type: ignore[arg-type]
    assert not call_ran(item)  # type: ignore[arg-type]


def test_rendering_leaves_the_record_and_drops_the_traceback() -> None:
    """The line is the record's own, one line with no traceback, rendered
    from a copy: the record keeps its ``exc_info``."""
    record = _record(logging.WARNING, "own words")
    error = ValueError("boom")
    info = (ValueError, error, None)
    record.exc_info = info
    assert rendered_line(record) == "WARNING: own words"
    assert record.exc_info is info


def test_a_finding_names_the_logger_and_thread() -> None:
    """A record a thread of an earlier test logs is blamed on the test
    running: the finding says whose it is."""
    record = _record(logging.WARNING, "own words", name="pitloom.late")
    record.threadName = "leaked-reader"
    finding = strict_finding(record)
    assert finding is not None
    assert "'pitloom.late'" in finding.problem
    assert "'leaked-reader'" in finding.problem
    assert finding.line == "WARNING: own words"


@pytest.mark.parametrize(
    ("code", "kind", "name"),
    [("lfs-pointer", "relay", "pitloom.x"), (None, "loud", "other")],
    ids=["code-and-kind", "unknown-kind"],
)
def test_a_wrong_kind_is_never_allowed(code: str | None, kind: str, name: str) -> None:
    """Anywhere, at any level: a kind is Pitloom's own attribute."""
    record = _record(logging.DEBUG, "x", code=code, kind=kind, name=name)
    finding = strict_finding(record)
    assert finding is not None and not finding.allowable
    assert failures([finding], [".*"]) == [
        f"{finding.problem}: {finding.line!r}",
        "stale allowance, matches no line: '.*'",
    ]
    # A skipped test is not held to its allowances, but a finding no marker
    # may allow is still reported.
    assert failures([finding], [".*"], ran=False) == [
        f"{finding.problem}: {finding.line!r}"
    ]


def test_an_error_record_is_rendered_with_its_frame() -> None:
    """The line is the command line's own: an ``ERROR`` record takes the
    open frame, so a framed relay reads back as a relay."""
    record = _record(logging.ERROR, "fickling: its words", kind="relay")
    with logging_config.error_frame("loom generate: "):
        assert strict_finding(record) is None
        finding = strict_finding(_record(logging.ERROR, "own words"))
    assert finding is not None
    assert finding.line == "ERROR: loom generate: own words"


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("ERROR: own words", "uncoded"),
        ("ERROR: " + "x" * LONGEST_LINE, "overlong"),
        ("ERROR: loom generate: spdx3-validate: a finding", None),
        ("ERROR: Git LFS pointer (not a real line) [lfs-pointer]", "uncoded"),
        ("not tagged", None),
    ],
    ids=["uncoded", "overlong", "relay", "forged-code", "untagged"],
)
def test_an_error_line_is_read_back(line: str, kind: str | None) -> None:
    finding = line_finding(line)
    if kind is None:
        assert finding is None
    else:
        assert finding is not None and f"an {kind} stderr line" in finding.problem


@pytest.mark.parametrize(
    ("lines", "allowances", "verdict"),
    [
        (["a"], [], Verdict(("a",), ())),
        (["a", "b"], ["a|b"], Verdict((), ())),
        (["a", "b"], ["a"], Verdict(("b",), ())),
        ([], ["a"], Verdict((), ("a",))),
        (["a"], ["a", "z"], Verdict((), ("z",))),
        (["ERROR: own words"], ["^own"], Verdict(("ERROR: own words",), ("^own",))),
        ([], [], Verdict((), ())),
        (["a"], ["a", "."], Verdict((), ())),
    ],
    ids=[
        "none",
        "both",
        "one",
        "stale",
        "one-stale",
        "anchored",
        "empty",
        "two-patterns-one-line",
    ],
)
def test_check_matches_lines_to_allowances(
    lines: list[str], allowances: list[str], verdict: Verdict
) -> None:
    assert check(lines, allowances) == verdict


def test_check_refuses_a_bad_pattern() -> None:
    with pytest.raises(re.error, match="unterminated"):
        check(["a"], ["("])


def test_failures_say_each_unallowed_line_and_stale_pattern() -> None:
    found = [Finding("WARNING: a", "an uncoded record"), Finding("ERROR: b", "x")]
    assert failures(found, ["^WARNING: a$", "never"]) == [
        "x: 'ERROR: b'",
        "stale allowance, matches no line: 'never'",
    ]


def test_a_skipped_test_has_no_stale_allowance() -> None:
    found = [Finding("WARNING: a", "an uncoded record")]
    assert failures([], ["never"], ran=False) == []
    assert failures(found, ["never"], ran=False) == ["an uncoded record: 'WARNING: a'"]


@pytest.mark.uncoded_output(r"^ERROR: own words$", r"^WARNING: said plain$")
def test_the_fixture_sees_print_error_and_a_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The autouse fixture wraps ``print_error``'s seam and
    ``Logger.handle``: each allowance matches a line, or the test fails
    stale."""
    # pylint: disable-next=protected-access
    assert logging_config._write_error_line.__name__ == "watching_lines"
    print_error("own words", frame="")
    logging.getLogger("pitloom.strict_probe").warning("said plain")
    assert capsys.readouterr().err.startswith("ERROR: own words\n")


@pytest.mark.uncoded_output(r"^INFO: told$")
def test_an_info_record_is_seen_once_enabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="pitloom"):
        logging.getLogger("pitloom.strict_probe").info("told")
        logging.getLogger("pitloom.strict_probe").debug("not checked")


def _fake_loom(root: Path, stderr: bytes) -> Path:
    """A ``pitloom`` package whose ``main`` writes the bytes *stderr*
    unchanged (text-mode stderr would turn each ``\\n`` into ``\\r\\n`` on
    Windows): put first on a child's import path, it stands in for the real
    one."""
    package = root / "pitloom"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"")
    (package / "__main__.py").write_bytes(
        "import sys\n"
        "def main():\n"
        f"    sys.stderr.buffer.write({stderr!r})\n"
        "    sys.stderr.buffer.flush()\n"
        "    return 0\n".encode()
    )
    return root


def test_run_loom_fails_on_an_uncoded_line(tmp_path: Path) -> None:
    path = [_fake_loom(tmp_path, b"INFO: KEY=v\nERROR: own words\nTraceback\n")]
    with pytest.raises(AssertionError, match="uncoded stderr line"):
        run_loom([], tmp_path, path=path)
    with pytest.raises(AssertionError, match="stale allowance"):
        run_loom([], tmp_path, path=path, allow=["own words", "never"])
    done = run_loom([], tmp_path, path=path, allow=["^ERROR: own words$"])
    assert done.returncode == 0


def test_uncoded_failures_reads_each_line() -> None:
    """A line ending in ``\\r\\n`` (a child's text-mode stderr on Windows)
    reads as the same line without its carriage return."""
    stderr = b"INFO: KEY=v\r\nERROR: \xff own\r\nWARNING: licenseid: x\n"
    assert uncoded_failures(stderr) == [
        "an uncoded stderr line (thread 'MainThread'): 'ERROR: \ufffd own'"
    ]
    assert not uncoded_failures(stderr, ["own"])


_CHILD_TESTS = """
import logging

import pytest

pytestmark = pytest.mark.uncoded_output("module wide")

_LOG = logging.getLogger("pitloom.smoke")


def test_module_marker_allows_nothing():
    _LOG.warning("module wide")


@pytest.mark.parametrize(
    "said",
    [pytest.param("allowed", marks=pytest.mark.uncoded_output("^WARNING: allowed$")),
     "unallowed"],
)
def test_param(said):
    _LOG.warning(said)


@pytest.mark.uncoded_output("never said")
def test_stale():
    pass


@pytest.mark.uncoded_output("never said")
def test_skipped_in_body():
    pytest.skip("not here")


@pytest.fixture
def skipping():
    pytest.skip("no setup")


@pytest.mark.uncoded_output("never said")
def test_skipped_in_setup(skipping):
    pass
"""


def test_markers_apply_per_test_only(tmp_path: Path) -> None:
    """In a child pytest with the repository's configuration and fixtures:
    a module-wide marker allows nothing, a marker on one parameter does not
    cover its sibling, and a stale allowance fails, unless the test was
    skipped in its body or its setup."""
    out = _run_child(tmp_path, _CHILD_TESTS)
    assert "4 passed, 2 skipped, 3 errors" in out, out
    assert "ERROR test_child.py::test_module_marker_allows_nothing" in out
    assert "ERROR test_child.py::test_param[unallowed]" in out
    assert "ERROR test_child.py::test_stale" in out


_CHILD_FIXTURES = """
import logging

import pytest

_LOG = logging.getLogger("pitloom.smoke")


@pytest.fixture(scope="module")
def noisy_setup():
    _LOG.warning("said in a module fixture's setup")


@pytest.fixture(scope="class")
def noisy_teardown():
    yield
    _LOG.warning("said in a class fixture's teardown")


@pytest.mark.uncoded_output("said in")
def test_setup(noisy_setup):
    pass


class TestTeardown:
    def test_teardown(self, noisy_teardown):
        pass
"""


def test_a_wider_fixture_is_held_to_the_check(tmp_path: Path) -> None:
    """An uncoded record in a module fixture's setup or a class fixture's
    teardown errors the test that ran it, naming the fixture; a test's
    marker does not allow it."""
    out = _run_child(tmp_path, _CHILD_FIXTURES)
    assert "1 passed, 2 errors" in out, out
    assert "the setup of fixture 'noisy_setup' (module" in out
    assert "the teardown of fixture 'noisy_teardown' (class" in out


def _run_child(tmp_path: Path, source: str) -> str:
    """Run *source* as a child pytest with the repository's configuration
    and fixtures; its stdout."""
    (tmp_path / "test_child.py").write_text(textwrap.dedent(source))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(_REPO / "src"), str(_REPO)])
    done = subprocess.run(  # nosec B603
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(_REPO / "pyproject.toml"),
            "--rootdir",
            str(tmp_path),
            "-p",
            "tests.conftest",
            "-p",
            "no:cacheprovider",
            "-n",
            "0",
            "-q",
            "-rE",
            str(tmp_path / "test_child.py"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        timeout=300,
    )
    return done.stdout.decode("utf-8", errors="replace")
