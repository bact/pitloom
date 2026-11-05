# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model read without some of its fields says so with its code on every
surface: a project's and a wheel's scan and ``loom model`` on the command
line's stderr (read as bytes), the Hatchling build hook and the library's
log records. The scan's frame (``FORMAT=... FILE=...: ``) comes before a
reader's own line; the code stays.

See also: tests/messages/test_model_field.py (the entries and each site).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.logging_config import CODE_ATTR
from tests._loom_child import coded_lines, run_loom
from tests._wheel_models import write_model_wheel
from tests.extract.ai_model.zip_builders import dated_zip
from tests.extract.conftest import make_hook, staged_sbom

_PYPROJECT = (
    b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    b'[project]\nname = "demo"\nversion = "1.0"\n'
    b'[tool.hatch.build.targets.wheel]\npackages = ["demo"]\n'
)
#: A PT2 archive whose ``extra/tags`` is not JSON: read, the tags kept raw.
_PT2 = dated_zip({"mdl/version": b"2\n", "mdl/extra/tags": b"not json\n"})
_TAGS = (
    ": Failed to parse PT2 extra/tags as JSON: Expecting value: line 1 column 1 "
    "(char 0) | Field(s) affected (degraded): properties.tags (kept as raw string) "
    "[model-field-unreadable]"
)


def _project(root: Path) -> Path:
    (root / "demo").mkdir(parents=True)
    (root / "pyproject.toml").write_bytes(_PYPROJECT)
    (root / "demo" / "__init__.py").write_bytes(b"")
    (root / "demo" / "m.pt2").write_bytes(_PT2)
    return root


@pytest.mark.parametrize("command", ["project", "model", "wheel"])
def test_the_command_line_ends_the_readers_line_in_its_code(
    tmp_path: Path, command: str
) -> None:
    project = _project(tmp_path / "proj")
    target = {
        "project": project,
        "model": project / "demo" / "m.pt2",
        "wheel": write_model_wheel(tmp_path / "dist", {"demo/m.pt2": _PT2}),
    }[command]
    done = run_loom([command, str(target), "-o", str(tmp_path / "o.json")], tmp_path)
    assert done.returncode == 0, done.stderr
    (line,) = coded_lines(done.stderr)
    assert line.startswith("WARNING: FORMAT=pytorch_pt2 FILE=")
    assert line.endswith(f"m.pt2{_TAGS}")


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, CODE_ATTR) for r in caplog.records if hasattr(r, CODE_ATTR)]


def test_the_build_hook_says_it_with_its_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    hook = make_hook(str(_project(tmp_path / "proj")), {})
    build_data: dict[str, Any] = {}
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        hook.initialize("standard", build_data)
    hook.finalize("standard", build_data, "")
    assert staged_sbom(build_data) is not None
    assert _codes(caplog) == ["model-field-unreadable"]


def test_the_library_puts_the_code_on_its_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path / "proj")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_project_sbom(project, output_path=tmp_path / "o.json", offline=True)
    assert _codes(caplog) == ["model-field-unreadable"]


def test_a_raw_config_cut_is_the_models_over_cap(tmp_path: Path) -> None:
    """The HDF5 reader's own cap is said as the model's, naming its file."""
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "m.h5"
    config = '{"config": {}, "pad": "' + "x" * 600 + '"}'
    with h5py.File(path, "w") as hf:
        hf.attrs["model_config"] = config
    done = run_loom(["model", str(path), "-o", str(tmp_path / "o.json")], tmp_path)
    assert done.returncode == 0, done.stderr
    assert coded_lines(done.stderr) == {
        f"WARNING: FORMAT=hdf5 FILE={path}: larger than the 500-character "
        f"raw-model-config cap; the first 500 of {len(config)} characters kept in "
        "properties.model_config_raw [over-cap]": "over-cap"
    }
