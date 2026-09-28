# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A target with no project of its own borrows no config from anywhere.

A wheel, an installed environment, a model file, an enrichment fragment and
a wheel embedded without a project directory have no ``[tool.pitloom]`` of
their own. A config lying in the current directory -- or beside the model
file -- may belong to an unrelated project, so none is read implicitly, and
no ``loom-ids.json`` is searched for. Settings come from arguments and from
a config the caller names explicitly (``pitloom_config=``, ``--config``).

Each test runs one surface twice with ``SOURCE_DATE_EPOCH`` pinned: once
from an empty directory and once from a directory holding a decoy config
and a seeded registry. The outputs must be byte-identical and the registry
untouched. A third run names the same decoy explicitly and must differ --
otherwise the decoy is inert and the first comparison proves nothing.

See also: :mod:`tests.cli.test_cli_no_implicit_config` for the CLI
counterpart, and :mod:`tests.core.test_config_cascade` for
``load_config_file`` itself.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import (
    embed_wheel_sbom,
    enrich_model,
    generate_env_sbom,
    generate_model_sbom,
    generate_wheel_sbom,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import load_config_file
from pitloom.ids import DEFAULT_REGISTRY_FILENAME, EntityEntry, FileEntry, IdRegistry

from ..cli.shared import SAFETENSORS_FIXTURE
from .conftest import _make_dummy_wheel

_TARGET = "targetpkg"
_IDS_NAMESPACE = "https://example.invalid/decoy-ids"
_DECOY = """
[project]
name = "unrelated-decoy-project"
version = "9.9.9"

[tool.pitloom]
pretty = true
describe-relationship = true
creation-comment = "comment-from-the-decoy"

[[tool.pitloom.creator]]
name = "Decoy Creator"
type = "person"
"""

# (surface, target) -> SBOM JSON. Each runs from the current directory.
_Surface = Callable[[Path, PitloomConfig | None], str]


def _seed_registry(path: Path, wheel: Path) -> None:
    """A registry holding ids the target *would* adopt: an entity (looked
    up by name) and a file entry (looked up by path and digest)."""
    registry = IdRegistry(namespace=_IDS_NAMESPACE, path=path)
    for name, kind in ((_TARGET, "software_Package"), ("model", "ai_AIPackage")):
        registry.entities[(kind, name)] = EntityEntry(
            spdx_id=f"{_IDS_NAMESPACE}#{kind}-seeded"
        )
    member = f"{_TARGET}/__init__.py"
    with zipfile.ZipFile(wheel) as archive:
        digest = hashlib.sha256(archive.read(member)).hexdigest()
    registry.files[member] = FileEntry(
        spdx_id=f"{_IDS_NAMESPACE}#File-seeded", sha256=digest
    )
    registry.save()


def _wheel(target: Path, config: PitloomConfig | None) -> str:
    return generate_wheel_sbom(target, offline=True, pitloom_config=config)


def _env(target: Path, config: PitloomConfig | None) -> str:
    del target
    return generate_env_sbom(offline=True, pitloom_config=config)


def _model(target: Path, config: PitloomConfig | None) -> str:
    return generate_model_sbom(target, pitloom_config=config)


def _enrich(target: Path, config: PitloomConfig | None) -> str:
    return enrich_model(target, pitloom_config=config)


def _embed(target: Path, config: PitloomConfig | None) -> str:
    return embed_wheel_sbom(target, pitloom_config=config)[2]


_SURFACES = {
    "wheel": (_wheel, "wheel"),
    "env": (_env, "wheel"),
    "model": (_model, "model"),
    "enrich": (_enrich, "model"),
    "embed-standalone": (_embed, "wheel"),
}


@pytest.fixture(name="stubbed_env")
def _stubbed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """read_environment() shells out to pipdeptree; pin its answer."""
    tree = [
        {
            "package": {
                "key": _TARGET,
                "package_name": _TARGET,
                "installed_version": "1.0.0",
            }
        }
    ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["pipdeptree"], returncode=0, stdout=json.dumps(tree), stderr=""
        ),
    )


@pytest.mark.usefixtures("stubbed_env")
@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_no_config_is_borrowed_from_the_current_directory(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, kind = _SURFACES[surface]
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    targets = tmp_path / "targets"
    targets.mkdir()
    wheel = _make_dummy_wheel(targets, _TARGET, "1.0.0")
    model = targets / "model.safetensors"
    shutil.copyfile(SAFETENSORS_FIXTURE, model)
    # A model card, so `enrich` has a result to attach a registry id to --
    # without one a wrongly adopted registry could not change the output.
    (targets / "README.md").write_text("---\nlicense: mit\n---\n", "utf-8")
    # The rewritten wheel is compared across runs, so each run embeds into
    # its own copy of the pristine wheel.
    pristine = wheel.read_bytes()

    def target() -> Path:
        if kind == "model":
            return model
        wheel.write_bytes(pristine)
        return wheel

    empty = tmp_path / "empty"
    empty.mkdir()
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "pyproject.toml").write_text(_DECOY, encoding="utf-8")
    _seed_registry(decoy / DEFAULT_REGISTRY_FILENAME, wheel)
    # Beside the model file too: that directory is not the model's project.
    shutil.copyfile(decoy / "pyproject.toml", targets / "pyproject.toml")
    registry_before = (decoy / DEFAULT_REGISTRY_FILENAME).read_bytes()

    monkeypatch.chdir(empty)
    from_empty = run(target(), None)
    monkeypatch.chdir(decoy)
    from_decoy = run(target(), None)
    monkeypatch.chdir(empty)
    named = run(target(), load_config_file(decoy / "pyproject.toml"))

    assert from_decoy == from_empty
    assert (decoy / DEFAULT_REGISTRY_FILENAME).read_bytes() == registry_before
    assert named != from_empty, "the decoy changes nothing even when named"
    assert "comment-from-the-decoy" in named
