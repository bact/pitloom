# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The strict check of the catalogue at run time (:mod:`tests._strict_uncoded`)
in a child pytest with the repository's configuration and fixtures: which
markers apply to which test, and fixtures wider than a test.

See also: tests/messages/test_drift_strict.py (the check in process).
"""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
import textwrap
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


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


_CHILD_LAZY = """
import logging

import pytest

from pitloom.logging_config import print_error

_LOG = logging.getLogger("pitloom.smoke")


@pytest.fixture(scope="module")
def quiet():
    return 1


@pytest.fixture(scope="module")
def noisy():
    _LOG.warning("said in a module fixture's setup")


@pytest.fixture(scope="module")
def lazy_noisy():
    _LOG.warning("said in a lazy fixture's setup")


@pytest.fixture(scope="module")
def lazy_printing():
    print_error("printed in a lazy fixture's setup", frame="")


def test_a_lazy(request):
    request.getfixturevalue("quiet")


def test_b_noisy(noisy):
    pass


def test_c_lazy_noisy(request):
    request.getfixturevalue("lazy_noisy")


def test_d_lazy_printing(request):
    request.getfixturevalue("lazy_printing")
"""


def test_a_lazy_fixture_keeps_the_watch(tmp_path: Path) -> None:
    """A wider fixture a test body sets up first (``getfixturevalue``) does
    not lose the watch for a later fixture; an uncoded record or ``ERROR:``
    line in a lazy fixture's setup fails that test once, not again at its
    teardown."""
    out = _run_child(tmp_path, _CHILD_LAZY)
    assert "2 failed, 1 passed, 1 error" in out, out
    assert "ERROR test_child.py::test_b_noisy" in out
    assert "the setup of fixture 'lazy_noisy' (module" in out
    assert "the setup of fixture 'lazy_printing' (module" in out


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
