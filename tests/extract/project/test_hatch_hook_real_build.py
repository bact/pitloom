# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hatchling build hook through a real ``python -m hatchling build``
subprocess: what stderr and the wheel hold, not what ``initialize()`` returns.

See also: test_hatch_hook_hook_basic.py (the hook's methods called directly).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from importlib.metadata import entry_points
from pathlib import Path

import pytest

_PYPROJECT = """\
[build-system]
requires = ["hatchling>=1.29"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0"

[tool.hatch.build.targets.wheel]
packages = ["src/demo"]
{wheel}
[tool.hatch.build.hooks.pitloom]
{hook}
{tail}"""

_SRC = str(Path(__file__).resolve().parents[3] / "src")

# The entry point is how Hatchling finds the hook: a development install
# registers it; a bare source tree does not.
pytestmark = pytest.mark.skipif(
    not any(ep.name == "pitloom" for ep in entry_points(group="hatch")),
    reason="pitloom is not installed: Hatchling cannot find its hook",
)


def make_project(
    root: Path, *, wheel: str = "", hook: str = "", tail: str = ""
) -> Path:
    """A ``demo`` 1.0 project at *root*: *wheel* lines go in its wheel
    target's table, *hook* lines in the Pitloom hook's, *tail* is more TOML."""
    (root / "src" / "demo").mkdir(parents=True)
    (root / "src" / "demo" / "__init__.py").write_bytes(b"")
    text = _PYPROJECT.format(wheel=wheel, hook=hook, tail=tail)
    (root / "pyproject.toml").write_text(text, encoding="utf-8")
    return root


def run(
    command: list[str], project: Path, env: dict[str, str] | None = None
) -> tuple[int, list[str]]:
    """Run *command* in *project*: the exit code and the stderr lines (bytes
    decoded here, so a line ending is never rewritten)."""
    environ = {
        key: value
        for key, value in os.environ.items()
        if key != "SOURCE_DATE_EPOCH" and not key.startswith("HATCH_BUILD")
    }
    environ.update(env or {})
    # The child imports the tree under test, not an installed Pitloom (pytest's
    # own ``pythonpath`` setting does not reach it).
    environ["PYTHONPATH"] = os.pathsep.join(
        [_SRC, *([environ["PYTHONPATH"]] if environ.get("PYTHONPATH") else [])]
    )
    done = subprocess.run(
        command, cwd=project, env=environ, capture_output=True, check=False
    )
    return done.returncode, done.stderr.decode("utf-8").splitlines()


def build(
    project: Path, env: dict[str, str] | None = None
) -> tuple[int, list[str], list[Path]]:
    """``hatchling build -t wheel`` in *project*: exit code, stderr lines and
    the wheels in ``dist/``."""
    code, lines = run(
        [sys.executable, "-m", "hatchling", "build", "-t", "wheel"], project, env
    )
    return code, lines, sorted((project / "dist").glob("*.whl"))


def tagged(lines: list[str], tag: str) -> list[str]:
    return [line for line in lines if line.startswith(f"{tag}: ")]


def sbom_members(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        return sorted(n for n in zf.namelist() if "/sboms/" in n)


_SBOM = "demo-1.0.dist-info/sboms/demo-1.0.spdx3.json"


@pytest.mark.parametrize(
    ("kwargs", "env", "reason"),
    [
        ({"hook": "enabld = false"}, {}, "unknown key"),
        ({"tail": '[tool.pitloom]\npretty = "yes"'}, {}, "pretty"),
        (
            {"tail": '[tool.pitloom.creation]\ncreation-datetime = "garbage"'},
            {},
            "garbage",
        ),
        (
            {
                "tail": "[tool.pitloom.fragment]\n"
                'files = [{path = "no.json", required = true}]'
            },
            {},
            "no.json",
        ),
        ({"tail": '[tool.pitloom]\nid-registry = "missing.json"'}, {}, "missing.json"),
        ({}, {"SOURCE_DATE_EPOCH": "abc"}, "SOURCE_DATE_EPOCH='abc'"),
        (
            {"tail": '[tool.pitloom.creation]\ncreation-datetime = "2026-01-01"'},
            {"SOURCE_DATE_EPOCH": "abc"},
            "SOURCE_DATE_EPOCH='abc'",
        ),
        ({}, {"SOURCE_DATE_EPOCH": "99999999999999999"}, "out of range"),
    ],
    ids=[
        "unknown-key",
        "bad-value",
        "bad-datetime",
        "required-fragment",
        "registry",
        "epoch",
        "epoch-with-pinned-date",
        "epoch-out-of-range",
    ],
)
def test_a_failed_generation_is_one_error_line(
    tmp_path: Path, kwargs: dict[str, str], env: dict[str, str], reason: str
) -> None:
    code, lines, wheels = build(make_project(tmp_path, **kwargs), env)
    assert code != 0 and not wheels
    errors = tagged(lines, "ERROR")
    assert len(errors) == 1, lines
    assert errors[0].startswith("ERROR: SBOM generation failed: ")
    assert reason in errors[0]
    if "SOURCE_DATE_EPOCH" in env:
        assert not tagged(lines, "WARNING")


def test_hatchlings_own_hook_keys_are_accepted(tmp_path: Path) -> None:
    """``enable-by-default = false`` leaves the hook off until
    ``HATCH_BUILD_HOOK_ENABLE_PITLOOM`` turns it on; it is no unknown key."""
    project = make_project(
        tmp_path, hook="enable-by-default = false\nrequire-runtime-dependencies = false"
    )
    code, lines, wheels = build(project)
    assert code == 0 and not tagged(lines, "ERROR")
    assert sbom_members(wheels[0]) == []
    code, lines, wheels = build(project, {"HATCH_BUILD_HOOK_ENABLE_PITLOOM": "true"})
    assert code == 0 and not tagged(lines, "ERROR")
    assert sbom_members(wheels[0]) == [_SBOM]


def test_an_editable_build_is_skipped_with_one_info(tmp_path: Path) -> None:
    """An editable wheel holds a ``.pth`` file: no SBOM of files not in it.
    ``dev-mode-dirs`` makes that file, where Hatchling would otherwise need
    the ``editables`` package."""
    project = make_project(tmp_path, wheel='dev-mode-dirs = ["src"]')
    code, lines = run(
        [sys.executable, "-c", "import hatchling.build as b; b.build_editable('dist')"],
        project,
    )
    assert code == 0, lines
    assert len([line for line in tagged(lines, "INFO") if "editable" in line]) == 1
    assert sbom_members(next((project / "dist").glob("*.whl"))) == []


def test_an_sbom_files_entry_of_the_staged_name_is_an_error(tmp_path: Path) -> None:
    """Typically ``loom project``'s own ``<name>-<version>.spdx3.json``."""
    project = make_project(tmp_path, wheel='sbom-files = ["demo-1.0.spdx3.json"]')
    (project / "demo-1.0.spdx3.json").write_text("{}", encoding="utf-8")
    code, lines, wheels = build(project)
    assert code != 0 and not wheels
    errors = tagged(lines, "ERROR")
    assert len(errors) == 1
    assert "sbom-basename" in errors[0] and "demo-1.0.spdx3.json" in errors[0]


def test_another_sbom_basename_ships_both(tmp_path: Path) -> None:
    project = make_project(
        tmp_path,
        wheel='sbom-files = ["demo-1.0.spdx3.json"]',
        tail='[tool.pitloom]\nsbom-basename = "mine"',
    )
    (project / "demo-1.0.spdx3.json").write_text("{}", encoding="utf-8")
    code, lines, wheels = build(project)
    assert code == 0 and not tagged(lines, "ERROR"), lines
    assert sbom_members(wheels[0]) == [
        _SBOM,
        "demo-1.0.dist-info/sboms/mine.spdx3.json",
    ]


def _digest(wheel: Path) -> str:
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def test_epoch_makes_the_wheel_reproducible_and_the_clock_is_said(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    epoch = {"SOURCE_DATE_EPOCH": "1700000000"}
    _, lines, wheels = build(project, epoch)
    first = _digest(wheels[0])
    _, again, wheels = build(project, epoch)
    assert _digest(wheels[0]) == first
    assert not [line for line in lines + again if "clock" in line]

    code, lines, wheels = build(project)
    assert code == 0
    clock = [line for line in tagged(lines, "INFO") if "clock" in line]
    assert len(clock) == 1 and "SOURCE_DATE_EPOCH" in clock[0]
    assert "creation-datetime" in clock[0]


@pytest.mark.parametrize(
    ("key", "notes"),
    [
        ("update-id-registry = true", 1),
        ("describe-relationship = true", 1),
        ("update-id-registry = false", 0),
        ("describe-relationship = false", 0),
    ],
)
def test_a_true_key_the_hook_does_not_act_on_is_one_info(
    tmp_path: Path, key: str, notes: int
) -> None:
    project = make_project(tmp_path, tail=f"[tool.pitloom]\n{key}")
    code, lines, wheels = build(project)
    assert code == 0
    found = [line for line in tagged(lines, "INFO") if "has no effect" in line]
    assert len(found) == notes
    if notes:
        assert "--" + key.split(" ", maxsplit=1)[0] in found[0]
        assert found[0].startswith("INFO: Options: ")
    with zipfile.ZipFile(wheels[0]) as zf:
        graph = json.loads(zf.read(sbom_members(wheels[0])[0]))["@graph"]
    assert not [n for n in graph if n["type"] == "Relationship" and "description" in n]
