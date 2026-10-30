# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An input over a cap is said ``over-cap`` on every surface: a ``LICENSE``
over the licence-detection cap on the command line's stderr (read as bytes,
as a script reads it), on the library's log record, in the Hatchling build
hook and in a Git URL's run (its checkout named ``<checkout>``); an sdist's
configuration file over its cap as the command line's ``ERROR:`` and the
library's exception. The GitHub Action's annotation keeps the code too
(tests/scripts/action/test_generate_step.py).

See also: tests/messages/test_over_cap.py (the entry and its helper).
"""

from __future__ import annotations

import logging
import os
import subprocess  # nosec B404
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.extract._license_detect import LICENSE_FILE_MAX_BYTES
from pitloom.extract.project._sdist_scan import CONFIG_MEMBER_MAX_BYTES
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import OVER_CAP, code_of, over_cap_of, trusted_message
from tests._git_http_server import backend_available, make_repo, serve_git
from tests.assemble.conftest import _make_sdist
from tests.extract.conftest import make_hook, write_pyproject

_SRC = str(Path(__file__).resolve().parents[1] / "src")
_PYPROJECT = '[project]\nname = "demo"\nversion = "1.0"\n'
#: The end of the licence's warning, as printed.
_TAIL = "LICENSE: larger than the 262144-byte license-detection cap; skipped"


def _project(root: Path) -> Path:
    """A project whose ``LICENSE`` is one byte over the cap."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_bytes(_PYPROJECT.encode("utf-8"))
    (root / "LICENSE").write_bytes(b"x" * (LICENSE_FILE_MAX_BYTES + 1))
    return root


def _loom(args: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    """``loom`` in a child process; its output as bytes, not decoded."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [_SRC, env.get("PYTHONPATH")]))
    return subprocess.run(  # nosec B603
        [sys.executable, "-m", "pitloom", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
        timeout=300,
    )


def _said(stderr: bytes, needle: str) -> list[str]:
    """The stderr lines holding *needle*, a carriage return dropped."""
    lines = stderr.decode("utf-8").split("\n")
    return [line.removesuffix("\r") for line in lines if needle in line]


def _over_cap_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if over_cap_of(r) is not None]


def test_the_command_line_ends_the_warning_in_its_code(tmp_path: Path) -> None:
    project = _project(tmp_path / "demo")
    done = _loom(["project", str(project), "-o", str(tmp_path / "o.json")], tmp_path)
    assert done.returncode == 0, done.stderr
    (line,) = _said(done.stderr, "license-detection cap")
    assert line.startswith("WARNING: FILE=")
    assert line.endswith(f"{_TAIL} [over-cap]")
    assert trusted_message(line) is OVER_CAP


def test_the_library_puts_the_code_on_the_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path / "demo")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_project_sbom(project, output_path=tmp_path / "o.json", offline=True)
    (record,) = _over_cap_records(caplog)
    assert getattr(record, CODE_ATTR) == "over-cap"
    assert record.getMessage().endswith(_TAIL)


def test_the_build_hook_says_it_with_its_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path / "demo")
    write_pyproject(project)
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        hook.initialize("standard", build_data)
    hook.finalize("standard", build_data, "")
    (record,) = _over_cap_records(caplog)
    assert getattr(record, CODE_ATTR) == "over-cap"
    assert record.getMessage().endswith(_TAIL)


@pytest.fixture(name="served")
def _served(tmp_path: Path) -> Iterator[str]:
    """A Git URL of a repository holding the over-cap project."""
    if not backend_available():
        pytest.skip("needs git http-backend")
    files = {
        "pyproject.toml": _PYPROJECT,
        "LICENSE": "x" * (LICENSE_FILE_MAX_BYTES + 1),
    }
    make_repo(tmp_path / "srv", "g/demo", {"main": files})
    with serve_git(tmp_path / "srv") as base:
        yield f"{base}/g/demo.git"


@pytest.mark.loopback
def test_a_git_url_run_names_the_checkout_and_keeps_the_code(
    served: str, tmp_path: Path
) -> None:
    done = _loom(["project", served, "-o", str(tmp_path / "o.json")], tmp_path)
    assert done.returncode == 0, done.stderr
    (line,) = _said(done.stderr, "license-detection cap")
    assert line.startswith("WARNING: FILE=<checkout>")
    assert line.endswith(f"{_TAIL} [over-cap]")
    assert trusted_message(line) is OVER_CAP


def _oversized_sdist(tmp_path: Path) -> Path:
    tail = "#" + "x" * CONFIG_MEMBER_MAX_BYTES
    return _make_sdist(tmp_path, tail)


def test_the_command_line_ends_the_error_in_its_code(tmp_path: Path) -> None:
    sdist = _oversized_sdist(tmp_path)
    done = _loom(["generate", str(sdist), "-o", str(tmp_path / "o.json")], tmp_path)
    assert done.returncode == 1
    (line,) = _said(done.stderr, "config-member cap")
    assert line.startswith("ERROR: SBOM generation failed: config file ")
    assert line.endswith(
        ":pyproject.toml': larger than the 1048576-byte config-member cap; not read"
        " [over-cap]"
    )
    assert trusted_message(line) is OVER_CAP


def test_the_library_raises_it_with_its_code(tmp_path: Path) -> None:
    sdist = _oversized_sdist(tmp_path)
    with pytest.raises(ValueError, match="config-member cap; not read") as caught:
        generate_project_sbom(sdist, output_path=tmp_path / "o.json", offline=True)
    assert code_of(caught.value) == "over-cap"
