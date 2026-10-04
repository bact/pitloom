# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[tool.pitloom]`` reaches a CLI run only from the target or ``--config``.

A command whose target has no project of its own (``wheel``, ``env``,
``model``, ``enrich``, ``generate`` on one of those, ``embed-wheel``
without ``--project-dir``) reads no config and no ``loom-id-registry.json`` from
the current directory. Each no-implicit test runs the command from an
empty directory and from a project directory holding a decoy config and a
seeded registry (``SOURCE_DATE_EPOCH`` pinned): the outputs must be
byte-identical and the registry untouched. The same decoy named with
``--config`` must change the output, or the comparison proves nothing.

The rest pins ``--config`` itself: flag > ``--config`` > target config;
``--config`` replaces a project's own config; its relative ``id-registry``
resolves against its own directory; a bad ``--config`` is one ``ERROR:``
and exit 1 with nothing written; and a field-level byte cap from the flag
overrides the config's without resetting its other provenance settings.

See also: :mod:`tests.assemble.test_generator_no_implicit_config` for the
library counterpart, and :mod:`tests.cli.test_cli_option_reach` for which
options reach each command at all.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble.spdx3.deps import _finish_dependency_enrichment
from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME, FileEntry, IdRegistry
from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import DEPENDENCY, demo_project, demo_wheel
from tests.assemble.test_generator_no_implicit_config import _TARGET, _seed_registry
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.warning_helpers import error_lines

_EPOCH = "1767225600"
_DECOY_COMMENT = "comment-from-the-decoy"
_DECOY = f"""
[tool.pitloom]
pretty = true
describe-relationship = true
creation-comment = "{_DECOY_COMMENT}"
update-id-registry = true
offline = false

[[tool.pitloom.creator]]
name = "Decoy Creator"
type = "person"

[tool.pitloom.provenance]
format = "comment"
detail = "full"
"""

#: Surface -> argv after ``loom``; ``{name}`` fields are filled per run.
_NO_PROJECT: dict[str, tuple[str, ...]] = {
    "wheel": ("wheel", "{wheel}", "--offline"),
    "generate-wheel": ("generate", "{wheel}", "--offline"),
    "env": ("env", "--offline"),
    "generate-env": ("generate", "env", "--offline"),
    "model": ("model", "{model}"),
    "generate-model": ("generate", "{model}"),
    "enrich": ("enrich", "{model}"),
    "embed-wheel-standalone": ("embed-wheel", "{wheel}", "--offline"),
}


@pytest.fixture(name="env_tree")
def _env_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """read_environment() shells out to pipdeptree; pin its answer."""
    tree = [
        {"package": {"key": k, "package_name": k, "installed_version": "1.0"}}
        for k in (_TARGET, DEPENDENCY)
    ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["pipdeptree"], returncode=0, stdout=json.dumps(tree), stderr=""
        ),
    )


def _loom(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


# pylint: disable-next=too-few-public-methods
class _Files:
    """One run's targets under *tmp*, each run getting a pristine wheel."""

    def __init__(self, tmp: Path) -> None:
        targets = tmp / "targets"
        self.wheel = _make_dummy_wheel(targets, _TARGET, "1.0.0")
        self.pristine = self.wheel.read_bytes()
        self.model = targets / "model.safetensors"
        shutil.copyfile(SAFETENSORS_FIXTURE, self.model)
        # A model card, so `enrich` has a result to attach a registry id to.
        (targets / "README.md").write_text("---\nlicense: mit\n---\n", "utf-8")
        self.out = tmp / "out"
        self.out.mkdir()
        self.runs = 0
        self.fields = {
            "wheel": str(self.wheel),
            "model": str(self.model),
            "project": str(demo_project(tmp)),
        }

    def run(self, argv: tuple[str, ...], mp: pytest.MonkeyPatch, *extra: str) -> bytes:
        """Run *argv* (plus *extra*) on a pristine wheel; return the SBOM."""
        self.wheel.write_bytes(self.pristine)
        self.runs += 1
        out = self.out / f"run{self.runs}.json"
        filled = [a.format(**self.fields) for a in argv]
        assert _loom([*filled, *extra, "-o", str(out)], mp) == 0
        return out.read_bytes()


@pytest.mark.usefixtures("env_tree")
@pytest.mark.parametrize("surface", sorted(_NO_PROJECT))
def test_no_config_or_registry_is_read_from_the_current_directory(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", _EPOCH)
    files = _Files(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    # A real project directory, as when embed-wheel runs from a project's
    # root without --project-dir: still not the wheel's project.
    decoy = demo_project(tmp_path / "decoy", _DECOY)
    registry = decoy / DEFAULT_ID_REGISTRY_FILENAME
    _seed_registry(registry, files.wheel)
    shutil.copyfile(decoy / "pyproject.toml", files.model.parent / "pyproject.toml")
    registry_before = registry.read_bytes()
    argv = _NO_PROJECT[surface]

    monkeypatch.chdir(empty)
    from_empty = files.run(argv, monkeypatch)
    monkeypatch.chdir(decoy)
    from_decoy = files.run(argv, monkeypatch)
    monkeypatch.chdir(empty)
    named = files.run(argv, monkeypatch, "--config", str(decoy / "pyproject.toml"))

    assert from_decoy == from_empty
    assert registry.read_bytes() == registry_before
    assert not (empty / DEFAULT_ID_REGISTRY_FILENAME).exists()
    assert named != from_empty, "the decoy changes nothing even when named"
    assert _DECOY_COMMENT.encode() in named


#: Surface -> argv; each honours --creation-comment and --pretty unless
#: listed in _NO_PRETTY.
_PRECEDENCE: dict[str, tuple[str, ...]] = {
    **_NO_PROJECT,
    "project": ("project", "{project}", "--offline"),
    "generate-project": ("generate", "{project}", "--offline"),
    "embed-wheel-project": (
        "embed-wheel",
        "{wheel}",
        "--project-dir",
        "{project}",
        "--offline",
    ),
}
#: A wheel-embedded SBOM is always canonical JSON.
_NO_PRETTY = {"embed-wheel-standalone", "embed-wheel-project"}
_KNOBS = {
    # knob -> (config line, flag argv, opposite flag argv)
    "comment": (
        'creation-comment = "knob"',
        ("--creation-comment", "knob"),
        ("--creation-comment", "other"),
    ),
    "pretty": ("pretty = true", ("--pretty",), ("--no-pretty",)),
}


@pytest.mark.usefixtures("env_tree")
@pytest.mark.parametrize(
    ("surface", "knob"),
    [
        (surface, knob)
        for surface in sorted(_PRECEDENCE)
        for knob in sorted(_KNOBS)
        if not (knob == "pretty" and surface in _NO_PRETTY)
    ],
)
def test_flag_beats_config_beats_default(
    surface: str, knob: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", _EPOCH)
    monkeypatch.chdir(tmp_path)
    files = _Files(tmp_path)
    line, flag, opposite = _KNOBS[knob]
    config = _write(tmp_path / "explicit.toml", f"[tool.pitloom]\n{line}\n")
    argv = _PRECEDENCE[surface]

    plain = files.run(argv, monkeypatch)
    by_flag = files.run(argv, monkeypatch, *flag)
    by_config = files.run(argv, monkeypatch, "--config", str(config))
    by_opposite = files.run(argv, monkeypatch, "--config", str(config), *opposite)
    by_opposite_flag = files.run(argv, monkeypatch, *opposite)

    assert by_flag != plain, "the knob changes nothing on this surface"
    assert by_config == by_flag
    assert by_opposite == by_opposite_flag


@pytest.mark.parametrize("command", ["project", "generate"])
def test_config_replaces_the_projects_own(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A key set only in the project's config is gone under --config."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", _EPOCH)
    monkeypatch.chdir(tmp_path)
    files = _Files(tmp_path)
    project = demo_project(
        tmp_path / "own", '\n[tool.pitloom]\ncreation-comment = "from-project"\n'
    )
    config = _write(tmp_path / "explicit.toml", "[tool.pitloom]\npretty = true\n")
    argv = (command, str(project), "--offline")

    own = files.run(argv, monkeypatch)
    replaced = files.run(argv, monkeypatch, "--config", str(config))

    assert b"from-project" in own
    assert b"from-project" not in replaced
    # pretty: indented (the line ending is the platform's, CRLF on Windows)
    assert b'\n  "@context"' in replaced, "the explicit config did not apply"
    assert b'\n  "@context"' not in own


@pytest.mark.parametrize("command", ["wheel", "project"])
def test_relative_id_registry_resolves_against_the_config(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", _EPOCH)
    files = _Files(tmp_path)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    registry = cfg_dir / "ids.json"
    _seed_registry(registry, files.wheel)
    # The demo project's file too, so either target adopts a seeded id.
    seeded = IdRegistry.load(registry)
    source = Path(files.fields["project"], "demo", "__init__.py").read_bytes()
    seeded.files["demo/__init__.py"] = FileEntry(
        spdx_id=f"{seeded.namespace}#File-demo-seeded",
        sha256=hashlib.sha256(source).hexdigest(),
    )
    seeded.save()
    config = _write(
        cfg_dir / "explicit.toml", '[tool.pitloom]\nid-registry = "ids.json"\n'
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    # Where a cwd-relative resolution would look: not a registry at all.
    _write(elsewhere / "ids.json", "not json")
    monkeypatch.chdir(elsewhere)
    target = "{wheel}" if command == "wheel" else "{project}"
    argv = (command, target, "--offline", "--no-update-id-registry")

    plain = files.run(argv, monkeypatch)
    named = files.run(argv, monkeypatch, "--config", str(config))

    assert b"decoy-ids" not in plain
    assert b"decoy-ids" in named, "the config's id-registry was not used"


_BAD_CONFIGS: dict[str, Callable[[Path], Path]] = {
    "missing": lambda d: d / "absent.toml",
    "invalid-toml": lambda d: _write(d / "bad.toml", "[tool.pitloom\npretty = "),
    "directory": lambda d: d,
}


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.usefixtures("env_tree")
@pytest.mark.parametrize("bad", sorted(_BAD_CONFIGS))
@pytest.mark.parametrize("surface", sorted(_PRECEDENCE))
def test_bad_config_is_one_error_and_writes_nothing(
    surface: str,
    bad: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _Files(tmp_path)
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    config = _BAD_CONFIGS[bad](bad_dir)
    out = tmp_path / "must-not-exist.json"
    argv = [a.format(**files.fields) for a in _PRECEDENCE[surface]]
    capsys.readouterr()

    code = _loom([*argv, "--config", str(config), "-o", str(out)], monkeypatch)

    assert code == 1
    assert len(error_lines(capsys.readouterr().err)) == 1
    assert not out.exists()
    assert files.wheel.read_bytes() == files.pristine, "the wheel was rewritten"


# Both call sites hold their own reference to the leaf.
_LEAF = (
    "pitloom.assemble.spdx3.deps._finish_dependency_enrichment",
    "pitloom.assemble.spdx3._document_deployed._finish_dependency_enrichment",
)
_CAP_SURFACES: dict[str, tuple[str, ...]] = {
    "wheel": ("wheel", "{wheel}"),
    "generate-wheel": ("generate", "{wheel}", "-o", "{out}"),
    "env": ("env",),
    "project": ("project", "{project}"),
    "embed-wheel-project": ("embed-wheel", "{wheel}", "--project-dir", "{project}"),
}


def _cap_argv(surface: str, tmp: Path) -> list[str]:
    fields = {
        "wheel": str(demo_wheel(tmp)),
        "project": str(demo_project(tmp)),
        "out": str(tmp / "out.json"),
    }
    return [a.format(**fields) for a in _CAP_SURFACES[surface]]


@pytest.mark.usefixtures("env_tree")
@pytest.mark.parametrize("surface", sorted(_CAP_SURFACES))
def test_byte_cap_flag_overrides_one_field_of_the_config(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def _spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return _finish_dependency_enrichment(*args, **kwargs)

    for leaf in _LEAF:
        monkeypatch.setattr(leaf, _spy)
    monkeypatch.chdir(tmp_path)
    config = _write(
        tmp_path / "explicit.toml",
        '[tool.pitloom.provenance]\ndetail = "full"\n'
        "max-source-metadata-bytes = 7000\n",
    )
    argv = _cap_argv(surface, tmp_path)
    extra = ["--offline", "--config", str(config)]

    assert (
        _loom([*argv, *extra, "--max-source-metadata-bytes", "5000"], monkeypatch) == 0
    )

    assert calls, "the run never reached the assembler"
    configs = {
        (
            c["provenance_config"].max_source_metadata_bytes,
            c["provenance_config"].detail,
        )
        for c in calls
    }
    assert configs == {(5000, "full")}


@pytest.mark.usefixtures("env_tree")
@pytest.mark.parametrize("surface", sorted(_CAP_SURFACES))
def test_too_small_byte_cap_is_refused(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    argv = [*_cap_argv(surface, tmp_path), "--offline"]
    with pytest.raises(SystemExit) as exc:
        _loom([*argv, "--max-source-metadata-bytes", "5"], monkeypatch)
    assert exc.value.code == 2
    assert "at least 8 bytes, got 5" in capsys.readouterr().err
