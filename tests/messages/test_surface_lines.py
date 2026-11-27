# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Each surface names what its user can change, end to end: the command
line (``main()``), the library and the Hatchling build hook, for an option
that has no effect, a build option without ``allow``, a setting the hook
never acts on and the usage hint; and the embed route, whose settings are
``ConfigOverrides`` fields.

See also: tests/messages/test_surface.py (the mechanism),
tests/messages/test_build_surfaces.py (the build lines on both surfaces) and
tests/messages/test_hub_target_refusal.py (``target-wrong-format``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.core.build_options import BuildOptions
from pitloom.core.config_cascade import ConfigOverrides
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.embed import embed_wheel_sbom
from pitloom.logging_config import configure_logging
from tests._wheel_fixtures import DIST_INFO, make_wheel, metadata
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.extract.ai_model.gguf_builders import gguf_file
from tests.extract.conftest import make_hook, write_pyproject_with_pitloom_config

# Projects on disk, paths in the lines and the real hook: every OS runs it.
pytestmark = pytest.mark.platform


@pytest.fixture(autouse=True)
def _pinned_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pinned time, so no ``datetime-unpinned`` line is said."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")


def _project(root: Path, table: str = "") -> Path:
    """A Hatchling project with one package, *table* added to its
    ``pyproject.toml``."""
    root.mkdir(exist_ok=True)
    write_pyproject_with_pitloom_config(root, table)
    package = root / "testpkg"
    package.mkdir(exist_ok=True)
    (package / "__init__.py").write_bytes(b"")
    return root


def _cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *argv: str,
) -> list[str]:
    """The stderr lines of ``loom *argv``, which must succeed."""
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 0
    return capsys.readouterr().err.splitlines()


def _library(
    capsys: pytest.CaptureFixture[str], project: Path, **kwargs: Any
) -> list[str]:
    """The stderr lines of ``generate_project_sbom(project, **kwargs)``."""
    configure_logging()
    generate_project_sbom(project, **kwargs)
    return capsys.readouterr().err.splitlines()


def _hook(capsys: pytest.CaptureFixture[str], project: Path) -> list[str]:
    """The stderr lines of the real Hatchling hook building *project*."""
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    hook.finalize("standard", build_data, "")
    return capsys.readouterr().err.splitlines()


def _coded(lines: list[str], code: str) -> list[str]:
    """The lines of *lines* that end in ``[code]``."""
    return [line for line in lines if line.endswith(f" [{code}]")]


def test_an_option_without_effect_is_named_as_each_surface_spells_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path / "p")
    reason = "has no effect for this target (it lifts the reader gate"
    cli = _cli(
        monkeypatch,
        capsys,
        "project",
        str(project),
        "--trust-model-files",
        "-o",
        str(tmp_path / "a.json"),
    )
    library = _library(capsys, project, trust_model_files=True)
    [said_cli] = _coded(cli, "option-no-effect")
    [said_library] = _coded(library, "option-no-effect")
    assert f"Options: {project}: --trust-model-files {reason}" in said_cli
    assert f"Options: {project}: trust_model_files {reason}" in said_library


def test_a_build_option_without_allow_names_each_surface_s_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path / "p")
    out = str(tmp_path / "a.json")
    cli = _cli(
        monkeypatch, capsys, "project", str(project), "--build-timeout", "5", "-o", out
    )
    cli += _cli(
        monkeypatch, capsys, "project", str(project), "--no-build-isolation", "-o", out
    )
    library = _library(
        capsys, project, build_options=BuildOptions(no_isolation=True, timeout=5)
    )
    assert [line.split(": ", 1)[1] for line in _coded(cli, "option-no-effect")] == [
        f"Build: {project}: --build-timeout has no effect without --allow-build "
        "[option-no-effect]",
        f"Build: {project}: --no-build-isolation has no effect without "
        "--allow-build [option-no-effect]",
    ]
    assert [line.split(": ", 1)[1] for line in _coded(library, "option-no-effect")] == [
        f"Build: {project}: BuildOptions.no_isolation has no effect without "
        "BuildOptions.allow [option-no-effect]",
        f"Build: {project}: BuildOptions.timeout has no effect without "
        "BuildOptions.allow [option-no-effect]",
    ]


def test_the_hook_names_a_setting_it_never_acts_on_by_its_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path / "p", "[tool.pitloom]\ndescribe-relationship = true\n")
    [said] = _coded(_hook(capsys, project), "option-no-effect")
    assert said == (
        f"INFO: Options: {project}: tool.pitloom.describe-relationship has no "
        "effect for the Hatchling build hook (relationship descriptions are not "
        "written) [option-no-effect]"
    )


@pytest.mark.parametrize(
    ("surface", "how"),
    [
        ("cli", "pass --scan-model-usage (or set scan-model-usage = true)"),
        ("library", "set scan_model_usage=True (or set scan-model-usage = true)"),
        ("hook", "set scan-model-usage = true in [tool.pitloom]"),
    ],
    ids=["cli", "library", "hook"],
)
def test_the_usage_hint_names_each_surface_s_way_to_scan(
    surface: str,
    how: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path / "p")
    (project / "testpkg" / "m.safetensors").write_bytes(safetensors_bytes())
    if surface == "cli":
        out = str(tmp_path / "a.json")
        lines = _cli(monkeypatch, capsys, "project", str(project), "-o", out)
    elif surface == "library":
        lines = _library(capsys, project)
    else:
        lines = _hook(capsys, project)
    hints = [line for line in lines if "AI model file(s); " in line]
    assert hints == [
        f"INFO: Found 1 AI model file(s); {how} to also record which Python "
        "files reference them."
    ]


@pytest.mark.parametrize(
    ("route", "trust", "scan"),
    [
        ("cli-embed", "pass --trust-model-files", "pass --scan-model-usage"),
        ("library", "set trust_model_files=True", "set scan_model_usage=True"),
        (
            "library-embed",
            "set ConfigOverrides.trust_model_files=True",
            "set ConfigOverrides.scan_model_usage=True",
        ),
    ],
    ids=["cli-embed", "library", "library-embed"],
)
def test_a_wheel_scan_names_the_routes_way_to_set_each_setting(
    route: str,
    trust: str,
    scan: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``embed_wheel_sbom()`` takes no ``trust_model_files=`` or
    ``scan_model_usage=`` keyword: its lines name the ``ConfigOverrides``
    fields; ``generate_wheel_sbom()`` names its keywords, ``loom
    embed-wheel`` its flags."""
    wheel = write_model_wheel(tmp_path / "dist", {"demo/m.gguf": gguf_file(0, 0)})
    monkeypatch.chdir(tmp_path)
    if route == "cli-embed":
        lines = _cli(monkeypatch, capsys, "embed-wheel", str(wheel))
    else:
        configure_logging()
        if route == "library":
            generate_wheel_sbom(wheel)
        else:
            embed_wheel_sbom(wheel)
        lines = capsys.readouterr().err.splitlines()
    [gated] = _coded(lines, "reader-unsafe")
    assert gated.endswith(f": gguf; {trust} for a wheel you trust [reader-unsafe]")
    hints = [line for line in lines if "AI model file(s); " in line]
    assert len(hints) == 1 and f"; {scan} (or set " in hints[0]


def test_a_project_backed_embed_names_the_overrides_field(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path / "p")
    (project / "testpkg" / "m.safetensors").write_bytes(safetensors_bytes())
    wheel = write_model_wheel(tmp_path / "dist", {"testpkg/__init__.py": b""})
    configure_logging()
    embed_wheel_sbom(wheel, project_dir=project)
    hints = [ln for ln in capsys.readouterr().err.splitlines() if "file(s); " in ln]
    assert hints == [
        "INFO: Found 1 AI model file(s); set ConfigOverrides.scan_model_usage=True "
        "(or set scan-model-usage = true) to also record which Python files "
        "reference them."
    ]


@pytest.mark.parametrize(
    ("refuse", "code", "how"),
    [
        (False, "credentials-unsafe/written", "CredentialPolicy(refuse=True)"),
        (True, "credentials-unsafe/refused", "CredentialPolicy(accepted=["),
    ],
    ids=["written", "refused"],
)
def test_an_embed_names_the_credentials_field(
    refuse: bool,
    code: str,
    how: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A credential in a URL of the wheel's metadata: ``embed_wheel_sbom()``
    takes the policy as ``ConfigOverrides.credentials``, not a keyword."""
    home = b"Home-page: https://alice:pw@example.com/x\n"
    wheel = make_wheel(
        tmp_path, extra={f"{DIST_INFO}/METADATA": metadata("demo", "1.0") + home}
    )
    overrides = ConfigOverrides(credentials=CredentialPolicy(refuse=refuse))
    configure_logging()
    if refuse:
        with pytest.raises(ValueError):
            embed_wheel_sbom(wheel, overrides=overrides)
    else:
        embed_wheel_sbom(wheel, overrides=overrides)
    [said] = _coded(capsys.readouterr().err.splitlines(), code)
    assert f"with ConfigOverrides.credentials={how}" in said
