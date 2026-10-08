# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A CRFsuite model on every surface: the same entry and the same warning.

``loom project``, ``loom wheel`` (without ``--trust-wheel-model``: CRFsuite
is not a gated format), ``loom model`` and the library API give one model
the same name, type and description; a truncated copy gives the same single
``WARNING:`` on each. Ids across ``loom id generate`` are in
tests/id_registry/test_registry_crfsuite_ids.py.

See also: :mod:`tests.assemble.test_model_outcome_parity` (every kind of
model file, in-process) and tests/extract/ai_model/test_crfsuite.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_model_sbom, generate_project_sbom
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import crfsuite
from pitloom.extract.ai_model.formats import Limits
from pitloom.extract.ai_model.formats.crfsuite import (
    read_crfsuite as read_crfsuite_header,
)
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from tests._wheel_models import write_model_wheel
from tests.id_registry.surfaces_base import demo_project
from tests.warning_helpers import file_values, logged_warnings

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "aimodels" / "crfsuite"
_COMPLETE = _FIXTURES / "complete.crfsuite"
_MINIMAL = _FIXTURES / "minimal.model"
_TRUNCATED = _COMPLETE.read_bytes()[:-5]  # declared size now past the file
_COMMON = ["--creation-datetime", "2026-01-01T00:00:00Z", "--offline"]
_SURFACES = ["project", "wheel", "model"]


def _ai_packages(sbom: str) -> list[dict[str, Any]]:
    graph = json.loads(sbom)["@graph"]
    return [e for e in graph if e["type"] == "ai_AIPackage"]


def _cli(
    surface: str, name: str, data: bytes, tmp_path: Path, mp: pytest.MonkeyPatch
) -> str:
    """The SBOM text ``loom <surface>`` writes for one model file."""
    out = tmp_path / "out.json"
    if surface == "project":
        root = demo_project(tmp_path)
        (root / "demo" / name).write_bytes(data)
        target = root
    elif surface == "wheel":
        target = write_model_wheel(tmp_path / "dist", {f"demo/{name}": data})
    else:
        target = tmp_path / name
        target.write_bytes(data)
    mp.setattr(sys, "argv", ["loom", surface, str(target), "-o", str(out), *_COMMON])
    assert __main__.main() == 0
    return out.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["complete.crfsuite", "m.model"])
def test_a_wheel_scan_reads_a_crfsuite_model_without_trust(
    name: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    data = (_COMPLETE if name.endswith(".crfsuite") else _MINIMAL).read_bytes()
    wheel = write_model_wheel(tmp_path, {f"demo/{name}": data})
    models = scan_wheel_for_ai_models(
        wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=10**7
    )
    assert [m.format_info.model_format for m in models] == [AiModelFormat.CRFSUITE]
    assert models[0].format_info.file_path_relative == f"demo/{name}"
    assert models[0].properties["num_labels"]  # read, not a format-only stub
    assert not logged_warnings(caplog)
    assert not [r for r in caplog.records if "trust-wheel-model" in r.getMessage()]


def test_every_surface_gives_a_model_the_same_name_type_and_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _COMPLETE.read_bytes()
    seen = {}
    for surface in _SURFACES:
        work = tmp_path / surface
        work.mkdir()
        (package,) = _ai_packages(
            _cli(surface, "complete.crfsuite", data, work, monkeypatch)
        )
        seen[surface] = (
            package["name"],
            package["ai_typeOfModel"],
            package["description"],
        )
    (package,) = _ai_packages(generate_model_sbom(_COMPLETE))
    seen["library"] = (
        package["name"],
        package["ai_typeOfModel"],
        package["description"],
    )
    root = demo_project(tmp_path / "lib")
    (root / "demo" / "complete.crfsuite").write_bytes(data)
    (package,) = _ai_packages(generate_project_sbom(root, offline=True))
    seen["library project"] = (
        package["name"],
        package["ai_typeOfModel"],
        package["description"],
    )
    assert len(set(map(str, seen.values()))) == 1, seen
    name, kinds, description = seen["project"]
    assert name == "complete"
    assert kinds == ["conditional random field"]
    assert description.startswith("CRFsuite model with 5 labels: ")


def test_a_truncated_model_gives_the_same_one_warning_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    seen = {}
    for surface in _SURFACES:
        caplog.clear()
        work = tmp_path / surface
        work.mkdir()
        sbom = _cli(surface, "cut.crfsuite", _TRUNCATED, work, monkeypatch)
        (package,) = _ai_packages(sbom)  # a stub entry, not a dropped one
        assert package["name"] == "cut"
        # ``loom model`` also says --offline is moot for a local file
        (message,) = [m for m in logged_warnings(caplog) if "FORMAT=" in m]
        (path,) = file_values([message])
        assert message.startswith("FORMAT=crfsuite FILE=")
        seen[surface] = message.replace(path, "<file>")
    assert len(set(seen.values())) == 1, seen
    assert "failed to extract metadata" in seen["model"]


def test_two_project_runs_over_both_fixtures_are_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = demo_project(tmp_path)
    (root / "demo" / "complete.crfsuite").write_bytes(_COMPLETE.read_bytes())
    (root / "demo" / "minimal.model").write_bytes(_MINIMAL.read_bytes())
    outputs = []
    for i in range(2):
        out = tmp_path / f"out{i}.json"
        monkeypatch.setattr(
            sys, "argv", ["loom", "project", str(root), "-o", str(out), *_COMMON]
        )
        assert __main__.main() == 0
        outputs.append(out.read_bytes())
    assert len(_ai_packages(outputs[0].decode("utf-8"))) == 2  # not vacuous
    assert outputs[0] == outputs[1]


def test_a_label_over_the_cap_gives_the_same_one_warning_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The reader's warning gets the scanner's ``FORMAT=``/``FILE=`` prefix;
    no label reaches the SBOM, the count does."""
    with _COMPLETE.open("rb") as handle:
        model = read_crfsuite_header(handle, Limits())
    over = model._replace(labels=(*model.labels[:-1], "x" * 4097))
    monkeypatch.setattr(
        crfsuite, "read_crfsuite_header", lambda *_args, **_kwargs: over
    )
    caplog.set_level(logging.WARNING)
    seen = {}
    for surface in _SURFACES:
        caplog.clear()
        work = tmp_path / surface
        work.mkdir()
        sbom = _cli(surface, "m.crfsuite", _COMPLETE.read_bytes(), work, monkeypatch)
        (package,) = _ai_packages(sbom)
        assert "description" not in package
        assert "x" * 4097 not in sbom
        (message,) = [m for m in logged_warnings(caplog) if "FORMAT=" in m]
        (path,) = file_values([message])
        seen[surface] = message.replace(path, "<file>")
    assert set(seen.values()) == {
        "FORMAT=crfsuite FILE=<file>: a label over 4096 bytes; no label recorded"
    }
