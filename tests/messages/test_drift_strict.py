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
from pathlib import Path

import pytest

from pitloom import logging_config
from pitloom.logging_config import CODE_ATTR, KIND_ATTR, print_error
from pitloom.messages import LONGEST_LINE
from tests._loom_child import run_loom, uncoded_failures
from tests._message_drift import record_problem
from tests._strict_uncoded import (
    Finding,
    Verdict,
    check,
    failures,
    line_finding,
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
        (_record(logging.WARNING, "own words", kind="loud"), "unknown kind"),
        (
            _record(logging.WARNING, "x", code="lfs-pointer", kind="relay"),
            "both code",
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


def test_a_record_with_code_and_kind_is_never_allowed() -> None:
    record = _record(logging.WARNING, "x", code="lfs-pointer", kind="relay")
    finding = strict_finding(record)
    assert finding is not None and not finding.allowable
    assert failures([finding], [".*"]) == [
        f"{finding.problem}: {finding.line!r}",
        "stale allowance, matches no line: '.*'",
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
    ],
    ids=["none", "both", "one", "stale", "one-stale", "anchored", "empty"],
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


@pytest.mark.uncoded_output(r"^ERROR: own words$", r"^WARNING: said plain$")
def test_the_fixture_sees_print_error_and_a_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The autouse fixture wraps ``print_error``'s seam and
    ``Logger.handle``: each allowance matches a line, or the test fails
    stale."""
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


def _fake_loom(root: Path, stderr: str) -> Path:
    """A ``pitloom`` package whose ``main`` writes *stderr*: put first on a
    child's import path, it stands in for the real one."""
    package = root / "pitloom"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"")
    (package / "__main__.py").write_bytes(
        "import sys\n"
        "def main():\n"
        f"    sys.stderr.write({stderr!r})\n"
        "    return 0\n".encode()
    )
    return root


def test_run_loom_fails_on_an_uncoded_line(tmp_path: Path) -> None:
    path = [_fake_loom(tmp_path, "INFO: KEY=v\nERROR: own words\r\nTraceback\n")]
    with pytest.raises(AssertionError, match="uncoded stderr line"):
        run_loom([], tmp_path, path=path)
    with pytest.raises(AssertionError, match="stale allowance"):
        run_loom([], tmp_path, path=path, allow=["own words", "never"])
    done = run_loom([], tmp_path, path=path, allow=["^ERROR: own words$"])
    assert done.returncode == 0


def test_uncoded_failures_reads_each_line() -> None:
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
"""


def test_markers_apply_per_test_only(tmp_path: Path) -> None:
    """In a child pytest with the repository's configuration and fixtures:
    a module-wide marker allows nothing, a marker on one parameter does not
    cover its sibling, and a stale allowance fails."""
    (tmp_path / "test_child.py").write_text(textwrap.dedent(_CHILD_TESTS))
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
    out = done.stdout.decode("utf-8", errors="replace")
    assert "4 passed, 3 errors" in out, out
    assert "ERROR test_child.py::test_module_marker_allows_nothing" in out
    assert "ERROR test_child.py::test_param[unallowed]" in out
    assert "ERROR test_child.py::test_stale" in out
