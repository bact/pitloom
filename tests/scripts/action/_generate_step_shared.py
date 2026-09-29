# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared stub/fixture plumbing for the "Generate SBOM" step's tests
(``action.yml``'s ``generate`` step run under a stub ``loom``).

Split out of ``test_generate_step.py`` so
``test_generate_step_id_registry.py`` can share the exact same
``generate`` fixture and wheel-building helpers instead of a second,
independently-drifting copy.

See also: :mod:`tests.scripts.action.test_generate_step` (most of this
step's tests), :mod:`tests.scripts.action.test_generate_step_id_registry`
(the ``id-registry``/``update-id-registry`` input tests).
"""

from __future__ import annotations

import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest
import yaml

if TYPE_CHECKING:
    from tests.scripts.action.conftest import StubBin

# Stub env: LOOM_ARGS_FILE, LOOM_EXIT, LOOM_STDOUT, LOOM_STDERR (printf formats).
LOOM_STUB = """\
printf '%s\\0' "$@" > "${LOOM_ARGS_FILE}"
printf "${LOOM_STDOUT-PITLOOM_SBOM_OUTPUT_PATH=out/sbom.spdx3.json\\\\n}"
printf "${LOOM_STDERR-}" >&2
exit "${LOOM_EXIT:-0}"
"""


EMPTY_INPUTS = dict.fromkeys(
    "PL_EMBED_WHEEL PL_MODEL PL_OUTPUT PL_PRETTY PL_ENRICH "
    "PL_EXTRACT_FILE_HEADER PL_ID_REGISTRY PL_UPDATE_ID_REGISTRY "
    "PL_CONTENT_TYPE PL_CONTENT_TYPE_METHOD "
    "PL_MAX_SOURCE_METADATA_BYTES PL_CONFIG PL_OFFLINE PL_USE_LOCKFILE "
    "PL_ALLOW_BUILD PL_NO_BUILD_ISOLATION PL_BUILD_TIMEOUT".split(),
    "",
)

EMBED_STDOUT = "pitloom: embedded p-1.dist-info/sboms/p-1.spdx3.json into p-1.whl\\n"


class _Result(NamedTuple):
    returncode: int
    output: str  # the step's stdout and stderr, as the runner would log them
    sbom_path: str | None
    loom_args: list[str]


def _generate_script(action_yml: Path) -> str:
    steps = yaml.safe_load(action_yml.read_text(encoding="utf-8"))["runs"]["steps"]
    return str(next(step["run"] for step in steps if step.get("id") == "generate"))


def _make_wheel(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr("p-1.dist-info/sboms/p-1.spdx3.json", "{}")


@pytest.fixture(name="generate")
def generate_fixture(
    stub_bin: StubBin, tmp_path: Path, scripts_dir: Path
) -> Callable[..., _Result]:
    """Return ``generate(args, *, with_python, **env)``."""
    script = tmp_path / "generate.sh"
    script.write_text(_generate_script(scripts_dir.parent / "action.yml"), "utf-8")
    stub_bin.link("tee", "tr", "sed", "head", "basename", "mktemp", "rm")
    stub_bin.add("loom", LOOM_STUB)
    github_output = tmp_path / "github-output"
    args_file = tmp_path / "loom-args"
    workdir = tmp_path / "work"
    workdir.mkdir()
    stub_bin.cwd = workdir

    def run(args: str = "", *, with_python: bool = True, **env: str) -> _Result:
        if with_python:
            stub_bin.add("python", f'exec "{sys.executable}" "$@"\n')
        github_output.write_text("", encoding="utf-8")
        result = stub_bin.run(
            ["-eo", "pipefail", str(script)],
            GITHUB_ACTION_PATH=str(scripts_dir.parent),
            GITHUB_OUTPUT=str(github_output),
            LOOM_ARGS_FILE=str(args_file),
            PL_PROJECT_PATH=".",
            PL_ARGS=args,
            **{**EMPTY_INPUTS, **env},
        )
        written = github_output.read_text(encoding="utf-8").strip()
        sbom_path = written.removeprefix("sbom-path=") if written else None
        loom_args = (
            args_file.read_bytes().decode("utf-8").split("\0")[:-1]
            if args_file.exists()
            else []
        )
        return _Result(
            result.returncode, result.stdout + result.stderr, sbom_path, loom_args
        )

    return run
