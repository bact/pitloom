# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An sdist's own ``[tool.pitloom]`` shapes its SBOM as the unpacked
directory's does, and ``--config``/``pitloom_config=`` replaces it without
parsing it.

What an sdist cannot use is documented, not warned: its ``id-registry`` names a
file inside the archive, and fragments merge only into a directory's SBOM.

See also:
- :mod:`tests.extract.project.test_sdist_config` for the config read itself.
- :mod:`tests.assemble.test_explicit_config_edges` for an sdist's flags.
"""

from __future__ import annotations

import json
import logging
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom
from pitloom.core import _config_parse
from pitloom.core.config import FragmentConfig, PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import IdRegistry
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.warning_helpers import error_lines, logged_warnings

_PINNED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_CONFIG = (
    "[tool.pitloom]\npretty = true\n"
    "[tool.pitloom.creation]\ncreation-comment = 'from-own-config'\n"
    "creation-datetime = '2026-01-01T00:00:00Z'\n"
    "[[tool.pitloom.creator]]\nname = 'Own Creator'\n"
)
_INVALID = "[tool.pitloom]\npretty = 'yes'\n"
#: Every module that parses a target's own config (spied: none may run).
_PARSE_SITES = (
    "core._config_parse",
    "extract.project.pyproject",
    "extract.project.sdist",
    "extract.project.setuptools_cfg",
)


def _directory(tmp_path: Path, tail: str) -> Path:
    project = tmp_path / "demo-1.0.0"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n' + tail, encoding="utf-8"
    )
    return project


def _config_view(sbom: str) -> tuple[bool, list[str], list[str]]:
    """The parts of an SBOM that the config above decides."""
    graph = json.loads(sbom)["@graph"]
    comments = sorted(
        o["comment"] for o in graph if o["type"] == "CreationInfo" and "comment" in o
    )
    names = sorted(o["name"] for o in graph if o["type"] == "Person")
    return sbom.startswith("{\n  "), comments, names


@pytest.mark.parametrize("fmt", ["tar", "zip"])
def test_sdist_and_its_directory_apply_the_same_config(
    tmp_path: Path, fmt: str
) -> None:
    directory = _directory(tmp_path, _CONFIG)
    sdist = _make_sdist(tmp_path, _CONFIG, fmt=fmt)
    # no creation_metadata=: an argument would replace the config's identity
    view = _config_view(generate_project_sbom(sdist))
    assert view == (True, ["from-own-config"], ["Own Creator"])
    assert view == _config_view(generate_project_sbom(directory))
    # not vacuous: without the config the same parts differ
    (tmp_path / "bare").mkdir()
    bare = _make_sdist(tmp_path / "bare", fmt=fmt)
    assert _config_view(generate_project_sbom(bare, creation_metadata=_PINNED)) != view


@pytest.mark.parametrize("fmt", ["tar", "zip"])
def test_invalid_own_config_fails_the_run(tmp_path: Path, fmt: str) -> None:
    sdist = _make_sdist(tmp_path, _INVALID, fmt=fmt)
    with pytest.raises(ValueError, match=f"{sdist.name}:pyproject.toml"):
        generate_project_sbom(sdist, creation_metadata=_PINNED)


_INVALID_CFG = (
    "[metadata]\nname = demo\nversion = 1.0.0\n[tool:pitloom]\npretty = maybe\n"
)


def _target(tmp_path: Path, kind: str, tail: str) -> Path:
    if kind == "sdist":
        return _make_sdist(tmp_path, tail)
    if kind == "directory":
        return _directory(tmp_path, tail)
    project = tmp_path / "cfg-only"  # setup.cfg, no pyproject.toml
    project.mkdir()
    (project / "setup.cfg").write_text(_INVALID_CFG, encoding="utf-8")
    return project


@pytest.mark.parametrize("kind", ["sdist", "directory", "setup.cfg directory"])
def test_explicit_config_rescues_an_invalid_target_config(
    tmp_path: Path, kind: str
) -> None:
    """The replaced config is never parsed, so its fault cannot fail the
    run (a directory and an sdist alike)."""
    target = _target(tmp_path, kind, _INVALID)
    with pytest.raises(ValueError):
        generate_project_sbom(target, creation_metadata=_PINNED)
    parse = _config_parse.parse_pitloom_config
    with ExitStack() as stack:
        spies = [
            stack.enter_context(
                patch(f"pitloom.{module}.parse_pitloom_config", wraps=parse)
            )
            for module in _PARSE_SITES
        ]
        sbom = generate_project_sbom(
            target,
            creation_metadata=_PINNED,
            pitloom_config=PitloomConfig(pretty=True),
        )
    assert sbom.startswith("{\n  ")
    assert not any(spy.called for spy in spies)


def test_own_id_registry_is_not_searched_or_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An sdist's ``id-registry`` can only name a file inside the archive: no
    registry is loaded (not even one sitting beside the archive under that
    name), and nothing is warned -- it is documented."""
    (tmp_path / "ids.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    sdist = _make_sdist(tmp_path, "[tool.pitloom]\nid-registry = 'ids.json'\n")
    with (
        patch.object(IdRegistry, "load", autospec=True) as load,
        patch.object(IdRegistry, "find", autospec=True) as find,
        caplog.at_level(logging.WARNING),
    ):
        generate_project_sbom(sdist, creation_metadata=_PINNED)
    assert not load.called and not find.called
    assert not logged_warnings(caplog)


def test_own_fragments_are_not_merged_nor_warned(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Fragments merge only into a directory's SBOM; a ``required`` one
    missing from an sdist does not fail it."""
    tail = (
        "[tool.pitloom.fragment]\n"
        "files = [{ path = 'missing.spdx3.json', required = true }]\n"
    )
    sdist = _make_sdist(tmp_path, tail)
    with caplog.at_level(logging.WARNING):
        generate_project_sbom(sdist, creation_metadata=_PINNED)
    assert not logged_warnings(caplog)
    # the directory with the same config does try, and fails: not vacuous
    with pytest.raises(Exception, match="missing.spdx3.json"):
        generate_project_sbom(_directory(tmp_path, tail), creation_metadata=_PINNED)


def test_own_fragments_are_not_merged_by_embed_wheel(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``embed-wheel --project-dir <sdist>`` gets the same config: the
    required fragment neither fails the embed nor is mentioned."""
    tail = (
        "[tool.pitloom.fragment]\n"
        "files = [{ path = 'missing.spdx3.json', required = true }]\n"
    )
    sdist = _make_sdist(tmp_path, tail)
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    with caplog.at_level(logging.WARNING):
        embed_wheel_sbom(wheel, project_dir=sdist, creation_metadata=_PINNED)
    assert not [w for w in logged_warnings(caplog) if "missing.spdx3.json" in w]


def _loom(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def test_cli_invalid_sdist_config_errors_then_config_rescues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sdist = _make_sdist(tmp_path, _INVALID)
    out = tmp_path / "o.json"
    assert _loom(["project", str(sdist), "-o", str(out)], monkeypatch) != 0
    errors = error_lines(capsys.readouterr().err)
    assert len(errors) == 1 and f"{sdist.name}:pyproject.toml" in errors[0]
    assert not out.exists()

    good = tmp_path / "good.toml"
    good.write_text("[tool.pitloom]\npretty = true\n", encoding="utf-8")
    argv = ["project", str(sdist), "--config", str(good), "-o", str(out)]
    assert _loom(argv, monkeypatch) == 0
    assert out.read_text(encoding="utf-8").startswith("{\n  ")


def test_cli_sdist_sbom_basename_cannot_escape_the_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no ``-o``, the file name comes from the archive's own config:
    a path there is an ``ERROR:``, and nothing is written outside."""
    work = tmp_path / "work"
    work.mkdir()
    sdist = _make_sdist(tmp_path, "[tool.pitloom]\nsbom-basename = '../escaped'\n")
    monkeypatch.chdir(work)
    assert _loom(["project", str(sdist)], monkeypatch) != 0
    errors = error_lines(capsys.readouterr().err)
    assert len(errors) == 1 and "sbom-basename" in errors[0], errors
    assert not list(tmp_path.glob("escaped*")) and not list(work.iterdir())


def test_sdist_sbom_does_not_depend_on_the_archive_location(tmp_path: Path) -> None:
    """Errors name the archive by path; the SBOM must not."""
    (tmp_path / "a").mkdir()
    first = _make_sdist(tmp_path / "a")
    second = tmp_path / "b" / "deeper" / first.name
    second.parent.mkdir(parents=True)
    second.write_bytes(first.read_bytes())
    sboms = [
        generate_project_sbom(p, creation_metadata=_PINNED) for p in (first, second)
    ]
    assert str(first.parent) != str(second.parent)  # the input really moved
    assert sboms[0] == sboms[1]


@pytest.mark.parametrize("surface", ["project", "embed-wheel"])
def test_explicit_config_fragments_skip_an_sdist_on_every_surface(
    tmp_path: Path, surface: str
) -> None:
    """Fragments merge only into a project directory's SBOM -- also those
    of an explicit config: ``project`` and ``embed-wheel --project-dir``
    agree for an sdist."""
    sdist = _make_sdist(tmp_path)
    config = PitloomConfig(
        fragments=[FragmentConfig(path=str(tmp_path / "missing.json"), required=True)]
    )
    if surface == "project":
        generate_project_sbom(sdist, pitloom_config=config, creation_metadata=_PINNED)
    else:
        wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
        embed_wheel_sbom(
            wheel, project_dir=sdist, pitloom_config=config, creation_metadata=_PINNED
        )
