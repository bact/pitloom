# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A base name that already ends in ``.spdx3.json`` names the file ``x.spdx3.json``,
not ``x.spdx3.json.spdx3.json``, on every surface that takes one, with one
``WARNING:``.

See also: :mod:`tests.core.test_file_names` (the helper itself).
"""

from __future__ import annotations

import logging
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.cli.options_resolve import _resolve_output_path
from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.embed import embed_wheel_sbom
from pitloom.logging_config import CODE_ATTR, configure_logging
from pitloom.messages import code_of, trusted_message
from pitloom.messages.options import SBOM_NAME_INVALID
from tests.assemble.conftest import _make_dummy_wheel
from tests.extract.conftest import make_hook
from tests.warning_helpers import logged_warnings, stderr_warnings

_PYPROJECT = (
    '[project]\nname = "demo"\nversion = "1.0.0"\n'
    '[tool.pitloom]\nsbom-basename = "{base}"\n'
)
_OFFLINE = ["--offline", "--creation-datetime", "2026-01-01T00:00:00Z"]


def _project(tmp_path: Path, base: str | None) -> Path:
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    text = (
        _PYPROJECT.format(base=base)
        if base
        else _PYPROJECT.split("[tool", maxsplit=1)[0]
    )
    (project / "pyproject.toml").write_text(text, encoding="utf-8")
    return project


def _config(tmp_path: Path, base: str) -> Path:
    config = tmp_path / "c.toml"
    config.write_text(f'[tool.pitloom]\nsbom-basename = "{base}"\n', encoding="utf-8")
    return config


def _embedded(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return [n.rsplit("/", 1)[1] for n in archive.namelist() if "/sboms/" in n]


def _run(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> list[str]:
    """The ``WARNING:`` lines of one ``loom`` run that must succeed."""
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 0
    return stderr_warnings(capsys.readouterr().err)


# Each surface: given (tmp_path, base, monkeypatch, capsys), returns the
# written file names and the warnings. ``base`` goes in via the config key
# or the flag, as the surface's name says.
_Surface = Callable[
    [Path, str, pytest.MonkeyPatch, pytest.CaptureFixture[str]],
    tuple[list[str], list[str]],
]


def _project_config(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    project = _project(tmp_path, base)
    monkeypatch.chdir(tmp_path)
    warnings = _run(["project", str(project), *_OFFLINE], monkeypatch, capsys)
    return sorted(p.name for p in tmp_path.glob("*.spdx3*")), warnings


def _project_setup_cfg(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "setup.cfg").write_text(
        f"[metadata]\nname = demo\nversion = 1.0\n"
        f"[tool:pitloom]\nsbom-basename = {base}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    warnings = _run(["project", str(project), *_OFFLINE], monkeypatch, capsys)
    return sorted(p.name for p in tmp_path.glob("*.spdx3*")), warnings


def _library_built_config(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,  # pylint: disable=unused-argument
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    """A ``PitloomConfig`` built in code is never parsed."""
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    embed_wheel_sbom(wheel, pitloom_config=PitloomConfig(sbom_basename=base))
    return _embedded(wheel), stderr_warnings(capsys.readouterr().err)


def _output_path_built_config(
    tmp_path: Path,  # pylint: disable=unused-argument
    base: str,
    monkeypatch: pytest.MonkeyPatch,  # pylint: disable=unused-argument
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    """``loom project``'s output name for a config built in code."""
    configure_logging()
    path = _resolve_output_path(
        None, ProjectMetadata(name="demo"), PitloomConfig(sbom_basename=base)
    )
    return [str(path)], stderr_warnings(capsys.readouterr().err)


def _wheel_embed_config(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    argv = ["wheel", str(wheel), "--embed", "--config", str(_config(tmp_path, base))]
    warnings = _run([*argv, *_OFFLINE], monkeypatch, capsys)
    return _embedded(wheel), warnings


def _embed_wheel_config(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    argv = ["embed-wheel", str(wheel), "--config", str(_config(tmp_path, base))]
    warnings = _run([*argv, *_OFFLINE], monkeypatch, capsys)
    return _embedded(wheel), warnings


def _embed_wheel_project_dir(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    project = _project(tmp_path, base)
    argv = ["embed-wheel", str(wheel), "--project-dir", str(project)]
    warnings = _run([*argv, *_OFFLINE], monkeypatch, capsys)
    return _embedded(wheel), warnings


def _embed_wheel_flag(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    argv = ["embed-wheel", str(wheel), "--sbom-basename", base]
    warnings = _run([*argv, *_OFFLINE], monkeypatch, capsys)
    return _embedded(wheel), warnings


def _embed_wheel_flag_project_dir(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    project = _project(tmp_path, None)
    argv = ["embed-wheel", str(wheel), "--project-dir", str(project)]
    warnings = _run([*argv, "--sbom-basename", base, *_OFFLINE], monkeypatch, capsys)
    return _embedded(wheel), warnings


def _embed_wheel_flag_sbom(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    wheel = _make_dummy_wheel(tmp_path / "a", "demo", "1.0.0")
    made = _make_dummy_wheel(tmp_path / "b", "demo", "1.0.0")
    _run(
        ["embed-wheel", str(made), "-o", str(tmp_path / "s.json"), *_OFFLINE],
        monkeypatch,
        capsys,
    )
    argv = ["embed-wheel", str(wheel), "--sbom", str(tmp_path / "s.json")]
    warnings = _run([*argv, "--sbom-basename", base], monkeypatch, capsys)
    return _embedded(wheel), warnings


def _library_kwarg(
    tmp_path: Path,
    base: str,
    monkeypatch: pytest.MonkeyPatch,  # pylint: disable=unused-argument
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], list[str]]:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    embed_wheel_sbom(wheel, sbom_basename=base)
    return _embedded(wheel), stderr_warnings(capsys.readouterr().err)


_SURFACES: dict[str, _Surface] = {
    "project-config": _project_config,
    "project-setup-cfg": _project_setup_cfg,
    "library-built-config": _library_built_config,
    "output-path-built-config": _output_path_built_config,
    "wheel-embed-config": _wheel_embed_config,
    "embed-wheel-config": _embed_wheel_config,
    "embed-wheel-project-dir-config": _embed_wheel_project_dir,
    "embed-wheel-flag": _embed_wheel_flag,
    "embed-wheel-flag-project-dir": _embed_wheel_flag_project_dir,
    "embed-wheel-flag-sbom": _embed_wheel_flag_sbom,
    "library-kwarg": _library_kwarg,
}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
@pytest.mark.parametrize("base", ["x.spdx3.json", "x.SPDX3.Json"])
def test_base_name_with_the_extension_is_not_doubled(
    surface: str,
    base: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One ``x.spdx3.json`` and one coded ``WARNING:`` naming the stripped
    value (``sbom-name-invalid``), whatever the surface."""
    names, warnings = _SURFACES[surface](tmp_path, base, monkeypatch, capsys)
    assert names == ["x.spdx3.json"]
    assert len(warnings) == 1
    assert repr(base) in warnings[0]
    assert warnings[0].endswith("; using x [sbom-name-invalid]")
    assert trusted_message(warnings[0]) is SBOM_NAME_INVALID


@pytest.mark.parametrize(
    ("surface", "label"),
    [
        ("library-kwarg", "sbom_basename"),
        ("library-built-config", "PitloomConfig.sbom_basename"),
        ("output-path-built-config", "PitloomConfig.sbom_basename"),
        ("embed-wheel-flag", "--sbom-basename"),
        ("embed-wheel-flag-project-dir", "--sbom-basename"),
    ],
)
def test_the_line_names_the_parameter_as_the_surface_spells_it(
    surface: str,
    label: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A library caller's ``sbom_basename``, the command line's
    ``--sbom-basename``: once, not again by the library the command calls."""
    _, warnings = _SURFACES[surface](tmp_path, " x ", monkeypatch, capsys)
    assert len(warnings) == 1
    assert warnings[0].startswith(f"WARNING: {label}: a string ' x ' ")


@pytest.mark.parametrize("base", ["a/b", "..", 5])
def test_a_built_config_refuses_a_base_name_that_is_no_file_name(base: Any) -> None:
    """At construction, named as the field, before anything is generated."""
    with pytest.raises(ValueError) as raised:
        PitloomConfig(sbom_basename=base)
    assert code_of(raised.value) == "option-invalid"
    assert str(raised.value).startswith("PitloomConfig.sbom_basename: must be ")


def test_a_built_config_takes_an_empty_base_name_as_no_name() -> None:
    """``""`` is the default, as no name is, not a file name refused."""
    assert PitloomConfig(sbom_basename="").sbom_basename == ""


def test_a_built_config_keeps_the_callers_logger() -> None:
    """A dataclass is no entry point: a base name it does not warn of
    leaves a library caller's ``pitloom`` logger as the caller set it."""
    logger = logging.getLogger("pitloom")
    mine = logging.NullHandler()
    logger.handlers = [mine]
    logger.setLevel(logging.ERROR)
    assert PitloomConfig(sbom_basename="x").sbom_basename == "x"
    assert logger.handlers == [mine]
    assert logger.level == logging.ERROR


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_base_name_without_the_extension_is_untouched_and_quiet(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The control: a plain base name still gets the extension, no warning."""
    names, warnings = _SURFACES[surface](tmp_path, "x", monkeypatch, capsys)
    assert names == ["x.spdx3.json"]
    assert not warnings


def test_hatchling_hook_strips_the_extension(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The build hook reads the config key as the CLI does."""
    with tempfile.TemporaryDirectory() as tmp:
        pyproject = _PYPROJECT.format(base="x.spdx3.json")
        (Path(tmp) / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        (Path(tmp) / "demo").mkdir()
        (Path(tmp) / "demo" / "__init__.py").write_text("", encoding="utf-8")
        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)
        assert [Path(p).name for p in build_data["sbom_files"]] == ["x.spdx3.json"]
        hook.finalize("standard", build_data, "")
    assert len(logged_warnings(caplog)) == 1
    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert getattr(record, CODE_ATTR) == SBOM_NAME_INVALID.code
    assert record.getMessage().startswith("[tool.pitloom] sbom-basename: ")


@pytest.mark.parametrize("flag", ["config", "flag"])
def test_base_name_of_only_the_extension_is_an_error(
    flag: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``.spdx3.json`` leaves no name: one ``ERROR:`` line, exit 1."""
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    argv = ["embed-wheel", str(wheel), *_OFFLINE]
    if flag == "config":
        argv += ["--config", str(_config(tmp_path, ".spdx3.json"))]
    else:
        argv += ["--sbom-basename", ".spdx3.json"]
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 1
    errors = [x for x in capsys.readouterr().err.splitlines() if "ERROR:" in x]
    assert len(errors) == 1
    assert "sbom-basename" in errors[0]
