# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""`pitloom id generate --namespace` (D8), the project root a registry
stores (D9) and the model hash `id generate` records (D3), through the real
argument parser.

See also: test_cli_id.py (the rest of `pitloom id`), tests/core/
test_iri_namespace.py (the IRI rule), tests/id_registry/
test_registry_format.py (the registry-level checks).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom import __main__
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.id_registry import AI_PACKAGE_TYPE, IdRegistry
from tests._symlink import CAN_SYMLINK
from tests.id_registry.shared import _sha256, _write_sample_sbom

_NS = "https://example.org/ns/demo"
_GGUF = (AiModelFormat.GGUF.magic or b"") + b"\0" * 16


def _main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "src" / "demo" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (project / "models").mkdir()
    (project / "models" / "tiny.gguf").write_bytes(_GGUF)
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n\n'
        '[tool.hatch.build.targets.wheel]\npackages = ["src/demo"]\n',
        encoding="utf-8",
    )
    return project


def _generate(
    monkeypatch: pytest.MonkeyPatch,
    project: Path,
    registry: Path,
    *extra: str,
    paths: tuple[str, ...] = ("src", "models"),
    root: Path | None = None,
) -> int:
    """`id generate` of *paths* (below *project*), rooted at *root*."""
    return _main(
        monkeypatch,
        "id",
        "generate",
        *(str(project / path) for path in paths),
        "--project-dir",
        str(root or project),
        "-o",
        str(registry),
        *extra,
    )


def _errors(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [
        line
        for line in capsys.readouterr().err.splitlines()
        if line.startswith("ERROR:")
    ]


def _json(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_bytes())
    return loaded


@pytest.mark.parametrize(
    "value",
    ["relative", "demo", "https://example.org/ns#frag", ""],
    ids=["relative", "no-scheme", "fragment", "empty"],
)
def test_namespace_invalid_exits_2_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    project = _project(tmp_path)
    registry = tmp_path / "reg.json"

    with pytest.raises(SystemExit) as raised:
        _generate(monkeypatch, project, registry, "--namespace", value)

    assert raised.value.code == 2
    assert "argument --namespace:" in capsys.readouterr().err
    assert not registry.exists()


def test_namespace_is_the_registry_namespace_and_the_sbom_id_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two fresh registries with one namespace give byte-identical SBOMs;
    without it each mints its own UUID4 (the control)."""
    project = _project(tmp_path)

    def sbom(label: str, *extra: str) -> str:
        registry = tmp_path / f"{label}.json"
        assert _generate(monkeypatch, project, registry, *extra) == 0
        out = tmp_path / f"{label}-sbom.json"
        argv = ["project", str(project), "-o", str(out)]
        argv += ["--id-registry", str(registry), "--creation-datetime"]
        assert _main(monkeypatch, *argv, "2026-01-01T00:00:00Z") == 0
        return out.read_text(encoding="utf-8")

    first = sbom("a", "--namespace", _NS)
    second = sbom("b", "--namespace", _NS)

    assert _json(tmp_path / "a.json")["namespace"] == _NS
    assert f'"{_NS}#File-' in first
    assert first == second
    assert sbom("c") != sbom("d")


@pytest.mark.parametrize("namespace", [_NS, "urn:other"], ids=["same", "other"])
def test_namespace_on_an_existing_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    namespace: str,
) -> None:
    project = _project(tmp_path)
    registry = tmp_path / "reg.json"
    assert _generate(monkeypatch, project, registry, "--namespace", _NS) == 0
    before = registry.read_bytes()
    capsys.readouterr()

    code = _generate(monkeypatch, project, registry, "--namespace", namespace)

    if namespace == _NS:
        assert code == 0
        assert not _errors(capsys)
    else:
        assert code == 1
        (error,) = _errors(capsys)
        assert f"namespace {_NS} is not --namespace {namespace}; delete it" in error
    assert registry.read_bytes() == before  # unchanged either way


@pytest.mark.parametrize(
    ("registry_dir", "stored"),
    [("", "."), ("build", ".."), ("../out", "../proj")],
    ids=["beside", "in-build", "elsewhere"],
)
def test_generate_stores_the_project_dir_as_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry_dir: str, stored: str
) -> None:
    """Relative to the registry's directory, whatever the working directory."""
    project = _project(tmp_path)
    registry = (project / registry_dir / "reg.json").resolve()
    monkeypatch.chdir(tmp_path)

    assert _generate(monkeypatch, project, registry) == 0

    assert _json(registry)["project_root"] == stored
    assert IdRegistry.load(registry).project_root == project.resolve()


def test_import_stores_the_working_directory_as_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    sbom = tmp_path / "sbom.json"
    _write_sample_sbom(sbom)
    monkeypatch.chdir(project)

    registry = tmp_path / "build" / "reg.json"
    assert _main(monkeypatch, "id", "import", str(sbom), "-o", str(registry)) == 0

    assert _json(registry)["project_root"] == "../proj"


def test_an_existing_registry_keeps_its_root_on_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    registry = tmp_path / "reg.json"
    assert _generate(monkeypatch, project, registry) == 0
    sbom = tmp_path / "sbom.json"
    _write_sample_sbom(sbom)
    monkeypatch.chdir(tmp_path)  # not the project

    assert _main(monkeypatch, "id", "import", str(sbom), "-o", str(registry)) == 0

    assert _json(registry)["project_root"] == "proj"


def test_generate_into_a_registry_with_another_root_is_one_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path)
    registry = tmp_path / "reg.json"
    assert _generate(monkeypatch, project, registry) == 0
    before = registry.read_bytes()
    capsys.readouterr()

    assert _generate(monkeypatch, project, registry, root=project / "src") == 1

    (error,) = _errors(capsys)
    assert error.startswith("ERROR: ID registry file ")
    assert "project root " in error
    assert "delete it to change the project root" in error
    assert registry.read_bytes() == before


@pytest.mark.skipif(not CAN_SYMLINK, reason="cannot create a symlink here")
def test_generate_accepts_the_root_spelled_through_a_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    registry = tmp_path / "reg.json"
    assert _generate(monkeypatch, project, registry) == 0
    (tmp_path / "link").symlink_to(project, target_is_directory=True)

    assert _generate(monkeypatch, project, registry, root=tmp_path / "link") == 0


def test_generate_reports_a_root_that_cannot_be_stored_as_one_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``os.path.relpath`` raises across Windows drives."""
    project = _project(tmp_path)
    registry = tmp_path / "reg.json"

    with patch("pitloom.id_registry._format.relpath", autospec=True) as fake:
        fake.side_effect = ValueError("path is on mount 'C:', start on mount 'D:'")
        assert _generate(monkeypatch, project, registry) == 1

    (error,) = _errors(capsys)
    assert error.startswith(f"ERROR: ID registry: failed to save '{registry}': ")
    assert "no path relative" in error
    assert not registry.exists()


def test_generate_records_the_model_hash_and_a_rerun_is_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    registry = tmp_path / "reg.json"
    assert _generate(monkeypatch, project, registry) == 0
    first = registry.read_bytes()

    entry = _json(registry)["elements"][AI_PACKAGE_TYPE]["models/tiny.gguf"]
    assert entry["sha256"] == _sha256(_GGUF)
    assert _generate(monkeypatch, project, registry) == 0
    assert registry.read_bytes() == first


def test_entity_pin_then_generate_mints_one_new_model_id_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`-e KEY` of a model file not there yet pins a hash-less entry under
    its key; the first `generate` that hashes the file replaces it (D12),
    and the next one leaves it be."""
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")
    project = _project(tmp_path)
    registry = tmp_path / "reg.json"
    key = "models/tiny.gguf"
    (project / key).unlink()
    assert _generate(monkeypatch, project, registry, "-e", key, paths=("src",)) == 0
    pinned = _json(registry)["elements"][AI_PACKAGE_TYPE][key]
    assert "sha256" not in pinned  # name only: non-vacuous
    (project / key).write_bytes(_GGUF)

    caplog.clear()
    assert _generate(monkeypatch, project, registry) == 0
    changed = [m for m in caplog.messages if f"content changed for {key};" in m]
    assert len(changed) == 1
    hashed = _json(registry)["elements"][AI_PACKAGE_TYPE][key]
    assert hashed["sha256"] == _sha256(_GGUF)
    assert hashed["spdxId"] != pinned["spdxId"]

    caplog.clear()
    assert _generate(monkeypatch, project, registry) == 0
    assert not [m for m in caplog.messages if "content changed" in m]
