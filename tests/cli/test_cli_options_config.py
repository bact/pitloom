# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.cli.options_config`, the one map from parsed
arguments to library parameters.

See also: :mod:`tests.cli.test_cli_option_reach` for every command's
options reaching the library end to end.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.options_config import (
    creation_flags_given,
    load_explicit_config,
    overrides_from_options,
    run_options,
)
from pitloom.cli.options_resolve import config_file_display
from pitloom.cli.parser import _build_parser
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.assemble.embed_surfaces_shared import demo_project
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.warning_helpers import count_naming, stderr_warnings


def _parse(*argv: str) -> argparse.Namespace:
    return _build_parser().parse_args(["wheel", "x.whl", *argv])


def test_omitted_flags_stay_none() -> None:
    """The CLI never resolves a cascade itself: an omitted flag reaches the
    library as ``None`` so the library's cascade decides."""
    options = run_options(_parse(), PitloomConfig())
    del options["creation_metadata"]
    assert set(options.values()) == {None}


@pytest.mark.parametrize(
    ("argv", "name", "expected"),
    [
        (["--no-pretty"], "pretty", False),
        (["--max-source-metadata-bytes", "0"], "max_source_metadata_bytes", 0),
        (["--no-update-id-registry"], "update_id_registry", False),
    ],
)
def test_false_and_zero_are_given_values(
    argv: list[str], name: str, expected: object
) -> None:
    """``False``/``0`` are explicit choices, not absences."""
    assert run_options(_parse(*argv), PitloomConfig())[name] == expected


def test_creation_metadata_resolves_against_the_config() -> None:
    options = run_options(_parse(), PitloomConfig(creation_comment="from-config"))
    assert options["creation_metadata"].creation_comment == "from-config"
    options = run_options(
        _parse("--creation-comment", "from-flag"),
        PitloomConfig(creation_comment="from-config"),
    )
    assert options["creation_metadata"].creation_comment == "from-flag"


@pytest.mark.parametrize(
    "argv",
    [
        ["--creator-name", "A"],
        ["--creation-tool", "t"],
        ["--no-creation-tool"],
        ["--creation-datetime", "2020-01-01T00:00:00Z"],
        ["--creation-comment", "c"],
    ],
)
def test_creation_flags_given(argv: list[str]) -> None:
    assert creation_flags_given(_parse(*argv))
    assert not creation_flags_given(_parse())


def test_overrides_carry_every_option_but_the_embed_api_arguments() -> None:
    """Every ConfigOverrides field but ``provenance`` (library-only, no
    flag) and ``build_options`` (settled separately) comes from a flag."""
    options = run_options(_parse(), PitloomConfig())
    overrides = overrides_from_options(options)
    fields = {f.name for f in dataclasses.fields(ConfigOverrides)}
    assert fields - {"provenance", "build_options"} <= set(options)
    assert overrides == ConfigOverrides()


def test_load_explicit_config(tmp_path: Path) -> None:
    assert load_explicit_config(_parse()) is None
    path = tmp_path / "team.toml"
    path.write_text("[tool.pitloom]\npretty = true\n", encoding="utf-8")
    config = load_explicit_config(_parse("--config", str(path)))
    assert config is not None
    assert config.pretty is True


def test_load_explicit_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_explicit_config(_parse("--config", str(tmp_path / "absent.toml")))


def test_relative_id_registry_is_made_absolute_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path typed on the command line means the file under the current
    directory on every command -- the library would otherwise resolve a
    relative one against the project directory on some of them."""
    monkeypatch.chdir(tmp_path)
    options = run_options(_parse("--id-registry", "ids.json"), PitloomConfig())
    assert options["id_registry"] == tmp_path / "ids.json"
    assert options["id_registry"].is_absolute()


def _loom(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def test_verbose_labels_values_from_a_config_by_its_file_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``-v`` names the ``--config`` file as the source of the values it
    set, whatever the file is called -- not "default" or pyproject.toml."""
    project = demo_project(tmp_path)
    config = tmp_path / "ci.toml"
    config.write_text(
        "[tool.pitloom]\npretty = true\n"
        'creation-comment = "from ci"\n'
        'creation-datetime = "2025-01-01T00:00:00Z"\n',
        encoding="utf-8",
    )
    argv = ["project", str(project), "--config", str(config), "-v", "--offline"]
    assert _loom([*argv, "-o", str(tmp_path / "o.json")], monkeypatch) == 0
    rows = {
        line.split(":")[0].strip(): line
        for line in capsys.readouterr().out.splitlines()
        if ":" in line
    }
    for key in ("pretty", "creation_comment", "creation_datetime"):
        assert rows[key].rstrip().endswith("[ci.toml]"), rows[key]


def test_embed_with_config_does_not_read_the_replaced_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--config`` replaces ``--project-dir``'s own config, as in the
    library: a fault in the replaced one cannot fail the embed."""
    project = demo_project(tmp_path, '\n[tool.pitloom]\nuse-lockfile = "bogus"\n')
    wheel = _make_dummy_wheel(tmp_path / "w", name="demo")
    config = tmp_path / "ci.toml"
    config.write_text("[tool.pitloom]\n", encoding="utf-8")
    argv = ["embed-wheel", str(wheel), "--project-dir", str(project)]
    assert _loom(argv, monkeypatch) == 1  # non-vacuous: the fault is real
    assert _loom([*argv, "--config", str(config)], monkeypatch) == 0


def test_verbose_labels_setup_cfg_values_by_its_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 1.0\n\n[options]\npackages = demo\n\n"
        "[tool:pitloom:creation]\ncomment = from setup cfg\n",
        encoding="utf-8",
    )
    argv = ["project", str(project), "-v", "--offline", "-o", str(tmp_path / "o.json")]
    assert _loom(argv, monkeypatch) == 0
    row = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("creation_comment")
    )
    assert row.rstrip().endswith("[setup.cfg]"), row


@pytest.mark.parametrize("command", ["project", "generate", "enrich"])
def test_use_lockfile_without_a_lock_file_target_warns_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """One ``Options:`` line, from the one layer that settles it -- not
    also from the lock-file resolver the CLI reads the project with."""
    if command == "enrich":
        target = str(SAFETENSORS_FIXTURE)
    else:
        target = str(_make_sdist(tmp_path))
    output = str(tmp_path / "o.json")
    argv = [command, target, "--use-lockfile", "-o", output]
    assert _loom(argv, monkeypatch) == 0
    warnings = stderr_warnings(capsys.readouterr().err)
    assert count_naming(warnings, "--use-lockfile") == 1, warnings


_FRAGMENT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "fragments"
    / "dataset-fragment.spdx3.json"
)


def test_config_fragment_path_resolves_beside_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every relative path in a ``--config`` file means the file beside it,
    as ``id-registry`` does, and no machine-specific directory leaks into
    the SBOM."""
    project = demo_project(tmp_path)
    config_dir = tmp_path / "ci"
    config_dir.mkdir()
    (config_dir / "frag.spdx3.json").write_bytes(_FRAGMENT.read_bytes())
    config = config_dir / "c.toml"
    config.write_text(
        '[tool.pitloom.fragment]\nfiles = [{ path = "frag.spdx3.json", '
        "required = true }]\n",
        encoding="utf-8",
    )
    output = tmp_path / "o.json"
    monkeypatch.chdir(tmp_path)
    argv = ["project", str(project), "--config", str(config), "--offline"]

    assert _loom([*argv, "-o", str(output)], monkeypatch) == 0

    sbom = output.read_text(encoding="utf-8")
    assert "DataCurator" in sbom  # merged (and required, so not skipped)
    assert str(config_dir) not in sbom


def test_verbose_on_sdist_names_its_own_config_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An sdist's own [tool.pitloom] applies, so ``-v`` names the archive
    member as the config file and labels a value taken from it."""
    sdist = _make_sdist(tmp_path, '[tool.pitloom]\ncreation-comment = "from-sdist"\n')
    argv = ["project", str(sdist), "-v", "-o", str(tmp_path / "o.json")]
    assert _loom(argv, monkeypatch) == 0
    out = capsys.readouterr().out.splitlines()
    config_row = next(line for line in out if line.strip().startswith("Config file"))
    assert f"{sdist}:pyproject.toml" in config_row
    comment_row = next(line for line in out if "from-sdist" in line)
    assert f"{sdist.name}:pyproject.toml" in comment_row


def test_config_file_row_without_a_config_says_none() -> None:
    assert config_file_display(None) == "(none)"
