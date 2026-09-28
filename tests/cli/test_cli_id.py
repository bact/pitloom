# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.cli.id import _load_or_create_registry, _run_id_command
from pitloom.cli.parser import _build_parser
from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME, IdRegistry

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def test_id_import_cli_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom id import` smoke test through main(): harvests ids from a real
    SBOM produced by `loom project`."""
    pyproject_content = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "importable-pkg"
version = "1.0.0"
"""
    (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    sbom_path = tmp_path / "importable-pkg-1.0.0.spdx3.json"
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(tmp_path)])
    assert __main__.main() == 0
    assert sbom_path.exists()

    monkeypatch.setattr(sys, "argv", ["loom", "id", "import", str(sbom_path)])
    assert __main__.main() == 0

    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    assert registry_path.exists()
    registry = IdRegistry.load(registry_path)
    assert registry.has_entity_named("importable-pkg")


def test_id_generate_registry_load_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # _load_or_create_registry returns None when it fails (e.g. invalid JSON)
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_text("invalid json")

    monkeypatch.setattr(
        sys, "argv", ["loom", "id", "generate", "--id-registry", str(registry_path)]
    )
    result = __main__.main()
    assert result == 1


def test_id_generate_no_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)

    # We provide no paths and the default path resolution fails
    monkeypatch.setattr(sys, "argv", ["loom", "id", "generate"])
    result = __main__.main()
    assert result == 1
    assert "ERROR: no source/data directories found" in capsys.readouterr().err


def test_id_import_sbom_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nonexistent = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(sys, "argv", ["loom", "id", "import", str(nonexistent)])
    result = __main__.main()
    assert result == 1
    assert "ERROR: SBOM file not found" in capsys.readouterr().err


def test_id_import_registry_load_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sbom_path = tmp_path / "valid.json"
    sbom_path.write_text("{}")

    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_text("invalid json")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "id", "import", str(sbom_path), "--id-registry", str(registry_path)],
    )
    result = __main__.main()
    assert result == 1


def test_id_import_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sbom_path = tmp_path / "valid.json"
    sbom_path.write_text("{}")

    # Force an exception during import_sbom

    def fake_import(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("Simulated failure")

    monkeypatch.setattr(IdRegistry, "import_sbom", fake_import)

    monkeypatch.setattr(sys, "argv", ["loom", "id", "import", str(sbom_path)])
    result = __main__.main()
    assert result == 1
    assert "ERROR: failed to import SBOM" in capsys.readouterr().err


def test_id_cli_invalid_command() -> None:
    # argparse will normally catch this, but if we bypass it
    # or test `_run_id_command` directly
    args = argparse.Namespace(id_command="invalid")
    result = _run_id_command(args)
    assert result == 1


def test_id_generate_cli_entity_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--entity NAME[:TYPE]` registers entities up front, before the model
    file exists, so loom.set_model() can already share the id."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "raw.txt").write_text("raw\n")
    monkeypatch.chdir(tmp_path)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "id",
            "generate",
            "data",
            "--entity",
            "sentimentdemo",
            "--entity",
            "other:dataset_DatasetPackage",
        ]
    )
    exit_code = _run_id_command(args)
    assert exit_code == 0

    registry = IdRegistry.load(tmp_path / DEFAULT_ID_REGISTRY_FILENAME)
    assert registry.entities[("ai_AIPackage", "sentimentdemo")].spdx_id.endswith(
        "#AIPackage-1"
    )
    assert ("dataset_DatasetPackage", "other") in registry.entities
    assert "data/raw.txt" in registry.files


def test_id_generate_entity_flag_hits_env_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--entity PyYAML:software_Package` registers the entity under its
    declared (mixed-case) name; a later ``generate_env_sbom()`` lookup,
    which only has pipdeptree's lowercased ``key`` to query with, must
    still hit it -- ``IdRegistry``'s own PEP 503 canonicalization
    (:func:`pitloom.id_registry._types._entity_key`) is what makes a raw ``--entity``
    registration and a real deployed-dependency lookup agree, not
    anything specific to harvest."""
    # pylint: disable=import-outside-toplevel
    import json
    import subprocess
    from unittest.mock import patch

    from pitloom.assemble import generate_env_sbom
    from pitloom.core.creation import CreationMetadata

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "raw.txt").write_text("raw\n")
    monkeypatch.chdir(tmp_path)
    parser = _build_parser()
    args = parser.parse_args(
        ["id", "generate", "data", "--entity", "PyYAML:software_Package"]
    )
    assert _run_id_command(args) == 0

    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    tree = [
        {
            "package": {
                "key": "pyyaml",
                "package_name": "PyYAML",
                "installed_version": "6.0",
            }
        }
    ]
    fake_result = subprocess.CompletedProcess(
        args=["pipdeptree", "--json-tree", "--all"],
        returncode=0,
        stdout=json.dumps(tree),
        stderr="",
    )
    registered_id = (
        IdRegistry.load(registry_path).entities[("software_Package", "pyyaml")].spdx_id
    )

    with patch("subprocess.run", return_value=fake_result):
        sbom = generate_env_sbom(
            id_registry=registry_path,
            creation_metadata=CreationMetadata(
                creation_datetime="2026-01-01T00:00:00+00:00"
            ),
        )

    graph = json.loads(sbom)["@graph"]
    pyyaml_pkg = next(
        e
        for e in graph
        if e.get("type") == "software_Package" and e.get("name") == "PyYAML"
    )
    assert pyyaml_pkg["spdxId"] == registered_id


def test_load_or_create_registry_fails(tmp_path: Path) -> None:

    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_text("invalid json")

    assert _load_or_create_registry(registry_path, "proj") is None


def test_main_returns_1_when_parsed_args_have_no_func(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive fallback: if a future parser change ever produced a
    Namespace with no ``func`` (the live parser's ``required=True``
    subparsers normally prevent this via SystemExit before main() is
    reached), main() returns 1 rather than crashing on the missing
    attribute."""

    class _FakeParser:
        def parse_args(self) -> argparse.Namespace:
            return argparse.Namespace()

    monkeypatch.setattr(__main__, "_build_parser", _FakeParser)
    assert __main__.main() == 1


def test_module_entrypoint_exits_with_main_return_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running ``python -m pitloom`` (the ``if __name__ == "__main__":``
    guard) calls ``sys.exit(main())``.

    Uses ``runpy.run_path`` (not ``run_module``): by the time this test
    runs, ``pitloom.__main__`` is already in ``sys.modules`` (imported
    above for ``__main__.main()``), and ``run_module`` documents +
    raises a ``RuntimeWarning`` for exactly that "already imported"
    case -- a real Python footgun, not a Pitloom bug, but one this test
    can simply avoid by executing the file directly instead.
    """
    import runpy

    monkeypatch.setattr(sys, "argv", ["pitloom", "id", "generate", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(__main__.__file__, run_name="__main__")
    assert exc_info.value.code == 0
