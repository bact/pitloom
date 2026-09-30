# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``setup.cfg``'s boolean and integer ``[tool:pitloom]`` keys reach the
config on every surface that reads a target's own config: the library and
``loom project``, for a project directory and for its sdist.

See also: :mod:`tests.extract.project.test_setup_cfg_values` for each key.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom
from pitloom.core import _config_parse
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from tests.assemble.conftest import _make_sdist
from tests.warning_helpers import error_lines

_PINNED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_TYPED = (
    "[tool:pitloom]\n"
    "extract-file-header = false\nuse-lockfile = no\nupdate-id-registry = 0\n"
    "offline = yes\ndescribe-relationship = false\nenrich = false\n"
    "no-creation-tool = true\n"
    "[tool:pitloom:provenance]\nmax-source-metadata-bytes = {bytes}\n"
    "[tool:pitloom:content-type]\nenabled = false\n"
)
_EXPECTED = {
    "extract_file_header": False,
    "use_lockfile": False,
    "update_id_registry": False,
    "offline": True,
    "describe_relationship": False,
    "tools": [],
    "provenance_max_source_metadata_bytes": 4096,
}
_SURFACES = ["library", "cli"]
_KINDS = ["directory", "tar", "zip"]


def _target(tmp_path: Path, kind: str, max_bytes: str) -> Path:
    cfg = (
        "[metadata]\nname = demo\nversion = 1.0.0\n" + _TYPED.format(bytes=max_bytes)
    ).encode("utf-8")
    if kind != "directory":
        members: dict[str, bytes | None] = {"pyproject.toml": None, "setup.cfg": cfg}
        return _make_sdist(tmp_path, members=members, fmt=kind)
    project = tmp_path / "demo-1.0.0"  # setup.cfg, no pyproject.toml
    project.mkdir()
    (project / "setup.cfg").write_bytes(cfg)
    return project


def _run(surface: str, target: Path, out: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    if surface == "library":
        sbom = generate_project_sbom(target, creation_metadata=_PINNED)
        out.write_text(sbom, encoding="utf-8")
        return 0
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(target), "-o", str(out)])
    return __main__.main()


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("surface", _SURFACES)
def test_typed_setup_cfg_keys_reach_the_config(
    tmp_path: Path, surface: str, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed: list[PitloomConfig] = []

    def spy(*args: Any, **kwargs: Any) -> PitloomConfig:
        config = _config_parse.parse_pitloom_config(*args, **kwargs)
        parsed.append(config)
        return config

    target = _target(tmp_path, kind, "4096")
    out = tmp_path / "out.spdx3.json"
    site = "pitloom.extract.project.setuptools_cfg.parse_pitloom_config"
    with patch(site, side_effect=spy):
        assert _run(surface, target, out, monkeypatch) == 0
    assert out.stat().st_size > 0
    assert parsed, "setup.cfg's [tool:pitloom] was not read"
    for field, value in _EXPECTED.items():
        assert getattr(parsed[-1], field) == value, field
        assert getattr(PitloomConfig(), field) != value, field  # not a default


@pytest.mark.parametrize("kind", _KINDS)
def test_invalid_typed_setup_cfg_key_fails_every_surface(
    tmp_path: Path,
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = _target(tmp_path, kind, "12x")
    out = tmp_path / "out.spdx3.json"
    with pytest.raises(ValueError, match="must be an integer"):
        _run("library", target, out, monkeypatch)
    capsys.readouterr()
    assert _run("cli", target, out, monkeypatch) != 0
    errors = error_lines(capsys.readouterr().err)
    assert len(errors) == 1 and "max-source-metadata-bytes" in errors[0], errors
    assert not out.exists()
