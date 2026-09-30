# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the strict-mode hook in ``tests/_network.py``: with
``PITLOOM_REQUIRE_NETWORK`` set, a skipped ``network`` test fails.

See also: tests/test_network_helpers.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests._network import REQUIRE_NETWORK_ENV

_REPO = Path(__file__).resolve().parents[1]

_CONFTEST = (
    "from tests._network import (\n"
    "    pytest_configure, pytest_make_collect_report, pytest_runtest_makereport\n"
    ")\n"
)
_TESTS = """
import pytest

@pytest.mark.network
def test_net_skips():
    pytest.skip("no route")

@pytest.mark.network
def test_net_importorskip():
    pytest.importorskip("no_such_module_for_pitloom")

@pytest.mark.network
@pytest.mark.xfail(reason="known", strict=False)
def test_net_xfail():
    raise AssertionError

@pytest.mark.network
def test_net_passes():
    pass

def test_plain_skips():
    pytest.skip("plain")
"""


def _run(
    tmp_path: Path, env_value: str | None, *args: str, extra: str = ""
) -> tuple[int, str]:
    (tmp_path / "conftest.py").write_text(_CONFTEST, encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(_TESTS, encoding="utf-8")
    if extra:
        (tmp_path / "test_extra.py").write_text(extra, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n    network: real network\n", encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if k != REQUIRE_NETWORK_ENV}
    env["PYTHONPATH"] = os.pathsep.join([str(_REPO), str(_REPO / "src")])
    if env_value is not None:
        env[REQUIRE_NETWORK_ENV] = env_value
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rs", *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
    )
    return res.returncode, (res.stdout + res.stderr).decode("utf-8", "replace")


def test_lenient_run_skips_network_tests(tmp_path: Path) -> None:
    code, out = _run(tmp_path, None)
    assert code == 0, out
    assert "3 skipped" in out and "1 passed" in out


@pytest.mark.parametrize("value", ["1", "true"])
def test_strict_run_fails_every_skipped_network_test(
    tmp_path: Path, value: str
) -> None:
    code, out = _run(tmp_path, value)
    assert code == 1, out
    # skip and importorskip fail; xfail, pass and the unmarked skip do not
    assert "2 failed" in out and "1 passed" in out
    assert "1 skipped" in out and "1 xfailed" in out
    assert "no route" in out


def test_strict_run_unknown_value_is_a_usage_error(tmp_path: Path) -> None:
    code, out = _run(tmp_path, "maybe")
    assert code == 4, out
    assert REQUIRE_NETWORK_ENV in out


def test_select_nothing_exits_five(tmp_path: Path) -> None:
    """The gate's ``-m network`` run cannot pass with no network test."""
    code, out = _run(tmp_path, "1", "-m", "no_such_marker")
    assert code == 5, out


_MODULE_SKIP = "import pytest\npytest.importorskip('no_such_module_for_pitloom')\n"


def test_strict_module_level_skip_of_network_module_fails(tmp_path: Path) -> None:
    extra = _MODULE_SKIP + "\n@pytest.mark.network\ndef test_x():\n    pass\n"
    code, out = _run(tmp_path, "1", extra=extra)
    assert "network module skipped" in out, out
    assert code != 0, out


def test_strict_module_level_skip_of_plain_module_is_a_skip(tmp_path: Path) -> None:
    extra = _MODULE_SKIP + "\ndef test_x():\n    pass\n"
    _, out = _run(tmp_path, "1", extra=extra)
    assert "network module skipped" not in out, out
    assert "test_extra.py" in out and "skipped" in out


def test_lenient_module_level_skip_of_network_module_is_a_skip(tmp_path: Path) -> None:
    extra = _MODULE_SKIP + "\n@pytest.mark.network\ndef test_x():\n    pass\n"
    _, out = _run(tmp_path, None, extra=extra)
    assert "network module skipped" not in out, out


_ENV_DELETING = """
import pytest
from tests._network import REQUIRE_NETWORK_ENV

@pytest.mark.network
def test_deletes_env_then_skips(monkeypatch):
    monkeypatch.delenv(REQUIRE_NETWORK_ENV, raising=False)
    pytest.skip("env removed by the test")
"""


def test_strict_gate_holds_when_a_test_deletes_the_env_var(tmp_path: Path) -> None:
    """The gate reads the variable once at start-up, not at report time."""
    code, out = _run(tmp_path, "1", extra=_ENV_DELETING)
    assert code == 1, out
    assert "env removed by the test" in out
    assert "test_deletes_env_then_skips" in out
    assert "3 failed" in out, out


def _run_dir_skip(tmp_path: Path, env_value: str | None, body: str) -> str:
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "conftest.py").write_text(_MODULE_SKIP, encoding="utf-8")
    (sub / "test_inner.py").write_text(body, encoding="utf-8")
    _, out = _run(tmp_path, env_value)
    return out


_NET_BODY = "import pytest\n\n@pytest.mark.network\ndef test_x():\n    pass\n"


def test_strict_directory_level_skip_of_network_tests_fails(tmp_path: Path) -> None:
    out = _run_dir_skip(tmp_path, "1", _NET_BODY)
    assert "network module skipped" in out, out


def test_lenient_directory_level_skip_of_network_tests_is_a_skip(
    tmp_path: Path,
) -> None:
    out = _run_dir_skip(tmp_path, None, _NET_BODY)
    assert "network module skipped" not in out, out
    assert "sub" in out and "skipped" in out


def test_strict_directory_level_skip_of_plain_tests_is_a_skip(tmp_path: Path) -> None:
    out = _run_dir_skip(tmp_path, "1", "def test_x():\n    pass\n")
    assert "network module skipped" not in out, out
