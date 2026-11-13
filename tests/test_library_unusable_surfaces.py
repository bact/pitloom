# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A library that is installed but fails to import is said with
``[library-unusable]`` on every surface: a project's scan (a
model reader's library), ``loom model`` naming a Hugging Face model,
``loom fragment validate`` and ``--content-type-method magika`` on the
command line's stderr, the Hatchling build hook and the library. The broken
library is a package, on the child's import path, whose import raises.

See also: tests/messages/test_library_unusable.py (the rule and each
import).
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.logging_config import CODE_ATTR
from tests._loom_child import coded_lines, run_loom
from tests._wheel_models import safetensors_bytes
from tests.extract.conftest import make_hook, staged_sbom

_CODE = "library-unusable"
_PYPROJECT = (
    b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    b'[project]\nname = "demo"\nversion = "1.0"\n'
    b'[tool.hatch.build.targets.wheel]\npackages = ["demo"]\n'
)
_RAISED = "libfake.so: cannot open shared object file"


def _broken(root: Path, *modules: str) -> Path:
    """A directory holding a package per module whose import raises."""
    for module in modules:
        (root / module).mkdir(parents=True)
        (root / module / "__init__.py").write_bytes(
            f"raise OSError({_RAISED!r})\n".encode()
        )
    return root


def _project(root: Path) -> Path:
    (root / "demo").mkdir(parents=True)
    (root / "pyproject.toml").write_bytes(_PYPROJECT)
    (root / "demo" / "__init__.py").write_bytes(b"")
    (root / "demo" / "m.safetensors").write_bytes(safetensors_bytes())
    return root


def test_a_project_scan_says_the_reader_library_is_broken(tmp_path: Path) -> None:
    project = _project(tmp_path / "proj")
    site = _broken(tmp_path / "site", "safetensors")
    args = ["project", str(project), "-o", str(tmp_path / "o.json")]
    done = run_loom(args, tmp_path, path=[site])
    assert done.returncode == 0, done.stderr
    (line,) = [ln for ln, code in coded_lines(done.stderr).items() if code == _CODE]
    assert line.startswith("WARNING: FORMAT=safetensors FILE=")
    assert line.endswith(
        f"m.safetensors: required library failed to import: {_RAISED}; reinstall "
        f"pitloom[safetensors] [{_CODE}]"
    )


@pytest.mark.parametrize(
    ("args", "module", "frame", "extra"),
    [
        (
            ["model", "google-bert/bert-base-uncased", "-o", "h.json"],
            "huggingface_hub",
            "loom model: ",
            "huggingface_hub",
        ),
        (
            ["fragment", "validate", "f.json"],
            "spdx3_validate",
            "loom fragment validate: ",
            "validate",
        ),
        (
            [
                "project",
                "proj",
                "--content-type",
                "--content-type-method",
                "magika",
                "-o",
                "o.json",
            ],
            "magika",
            "loom project: ",
            "content-type",
        ),
    ],
    ids=["hub", "validate", "magika"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_a_step_whose_library_is_broken_stops_with_its_code(
    tmp_path: Path, args: list[str], module: str, frame: str, extra: str
) -> None:
    """Before anything is fetched or read: no network."""
    _project(tmp_path / "proj")
    site = _broken(tmp_path / "site", module)
    done = run_loom(args, tmp_path, path=[site])
    assert done.returncode == 1, done.stderr
    assert coded_lines(done.stderr) == {
        f"ERROR: {frame}required library failed to import: {module}: {_RAISED}; "
        f"reinstall pitloom[{extra}] [{_CODE}]": _CODE
    }


def test_auto_content_types_keep_the_files_and_warn_once(tmp_path: Path) -> None:
    """A broken magika under ``--content-type`` (method ``auto``): every
    file keeps its extension's type, with one warning for the run."""
    project = _project(tmp_path / "proj")
    (project / "demo" / "b.py").write_bytes(b"x = 1\n")
    site = _broken(tmp_path / "site", "magika")
    args = ["project", "proj", "--content-type", "-o", "o.json"]
    done = run_loom(args, tmp_path, path=[site])
    assert done.returncode == 0, done.stderr
    assert list(coded_lines(done.stderr).values()) == [_CODE]
    sbom = (tmp_path / "o.json").read_text(encoding="utf-8")
    assert '"text/x-python"' in sbom


@pytest.fixture(name="broken_safetensors")
def fixture_broken_safetensors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``safetensors`` broken in this process (its real modules hidden)."""
    monkeypatch.syspath_prepend(str(_broken(tmp_path / "site", "safetensors")))
    for name in [n for n in sys.modules if n.partition(".")[0] == "safetensors"]:
        monkeypatch.delitem(sys.modules, name)
    importlib.invalidate_caches()


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, CODE_ATTR) for r in caplog.records if hasattr(r, CODE_ATTR)]


@pytest.mark.usefixtures("broken_safetensors")
def test_the_build_hook_says_it_with_its_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    hook = make_hook(str(_project(tmp_path / "proj")), {})
    build_data: dict[str, Any] = {}
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        hook.initialize("standard", build_data)
    hook.finalize("standard", build_data, "")
    assert staged_sbom(build_data) is not None
    assert _codes(caplog) == [_CODE]


@pytest.mark.usefixtures("broken_safetensors")
def test_the_library_puts_the_code_on_its_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path / "proj")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_project_sbom(project, output_path=tmp_path / "o.json", offline=True)
    assert _codes(caplog) == [_CODE]
