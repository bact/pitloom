# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``test-all-os`` action reads the label from the API, failing open.

Runs the action's script with a fake ``gh`` on ``PATH``. POSIX only: the
script is bash and the fake ``gh`` is an executable shell script.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ACTION = (
    Path(__file__).resolve().parents[3]
    / ".github"
    / "actions"
    / "test-all-os"
    / "action.yml"
)
SKIP_REASON = "bash script with an executable fake gh"
NOT_POSIX = sys.platform == "win32" or shutil.which("bash") is None

pytestmark = [pytest.mark.platform, pytest.mark.skipif(NOT_POSIX, reason=SKIP_REASON)]


def _script() -> str:
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    script = action["runs"]["steps"][0]["run"]
    assert isinstance(script, str)
    return script


def _run(tmp_path: Path, event: str, gh_body: str) -> tuple[str, str]:
    """Run the script; return (the all-os output, stdout)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(f"#!/bin/sh\n{gh_body}\n", encoding="utf-8")
    gh.chmod(0o755)
    output = tmp_path / "out"
    output.write_bytes(b"")
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "EVENT_NAME": event,
        "PR_NUMBER": "7",
        "REPO": "owner/repo",
        "GITHUB_OUTPUT": str(output),
    }
    done = subprocess.run(
        ["bash", "-c", _script()],
        check=True,
        capture_output=True,
        env=env,
    )
    lines = output.read_bytes().decode("utf-8").splitlines()
    assert len(lines) == 1
    return lines[0], done.stdout.decode("utf-8")


@pytest.mark.parametrize(
    ("event", "gh_body", "expected"),
    [
        ("push", "exit 1", "all-os=true"),
        ("pull_request", "printf 'bug\\ntest-all-os\\n'", "all-os=true"),
        ("pull_request", "printf 'bug\\ndocumentation\\n'", "all-os=false"),
        ("pull_request", "printf 'test-all-os-later\\n'", "all-os=false"),
        ("pull_request", "true", "all-os=false"),
        ("pull_request", "echo '::error::gh said' >&2; exit 1", "all-os=true"),
    ],
    ids=["push", "label", "other-labels", "prefix-only", "no-labels", "api-error"],
)
def test_all_os_follows_the_current_labels(
    tmp_path: Path, event: str, gh_body: str, expected: str
) -> None:
    """The label read now decides; a non-PR event or an API error tests all."""
    out, _ = _run(tmp_path, event, gh_body)
    assert out == expected


def test_label_names_are_not_echoed(tmp_path: Path) -> None:
    """A label name could forge a workflow command: it never reaches stdout."""
    out, stdout = _run(tmp_path, "pull_request", "printf '::stop-commands::x\\n'")
    assert out == "all-os=false"
    assert "::" not in stdout
