# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``--scan-model-usage`` on every surface that can act on it.

A project directory (CLI ``project``, ``embed-wheel --project-dir``,
``generate_project_sbom()``, ``generate()``, ``embed_wheel_sbom()``, the
Hatchling hook) always finds its AI models; only with the flag or config key
on does it also record which ``.py`` files reference them (``hasDataFile``).
Off, one ``INFO:`` line from the shared scanner says so -- only when the
setting was never given (an explicit ``false`` on any surface is silent), and
once per ``embed-wheel`` batch. Every other target warns once that the flag
has no effect.

See also: :mod:`tests.assemble.embed_surfaces_shared` (the demo project
these runners are modelled on), ``tests/extract/test_scanner.py`` (the gate
itself).
"""

from __future__ import annotations

import json
import logging
import struct
import subprocess
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __file__ as pitloom_file
from pitloom.assemble import generate, generate_project_sbom
from pitloom.embed import ConfigOverrides, embed_wheel_sbom
from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import run_cli
from tests.extract.conftest import make_hook

_MODEL = "tiny.safetensors"
_HINT = "(or set scan-model-usage = true) to also record which Python files"
_HINT_ONE = (
    "Found 1 AI model file(s); pass --scan-model-usage "
    "(or set scan-model-usage = true) to also record which Python files "
    "reference them."
)
_PYPROJECT = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    '[project]\nname = "demo"\nversion = "1.0.0"\nrequires-python = ">=3.10"\n'
)
_Runner = Callable[[Path, pytest.MonkeyPatch, "bool | None", "bool | None"], str]


def _project(tmp: Path, usage: bool | None = None, *, model: bool = True) -> Path:
    """A flat-layout project: ``demo/tiny.safetensors`` and ``demo/use.py``;
    *usage* writes ``scan-model-usage`` into its own config (``None``: absent)."""
    root = tmp / "proj"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    if model:
        header = json.dumps(
            {"t": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}
        ).encode()
        (root / "demo" / _MODEL).write_bytes(
            struct.pack("<Q", len(header)) + header + b"\0" * 4
        )
        (root / "demo" / "use.py").write_text(f'M = "{_MODEL}"\n', encoding="utf-8")
    config = "\n[tool.pitloom]\noffline = true\n"
    if usage is not None:
        config += f"scan-model-usage = {str(usage).lower()}\n"
    (root / "pyproject.toml").write_text(_PYPROJECT + config, encoding="utf-8")
    return root


def _wheel(tmp: Path, project: Path) -> Path:
    """A wheel of *project*'s model and script (so usage edges have targets)."""
    members = {
        f"demo/{name}": (project / "demo" / name).read_bytes()
        for name in (_MODEL, "use.py")
    }
    return _make_dummy_wheel(tmp / "dist", "demo", "1.0.0", extra_members=members)


def _flag(value: bool | None) -> list[str]:
    return (
        []
        if value is None
        else ["--scan-model-usage" if value else "--no-scan-model-usage"]
    )


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as zf:
        (name,) = (n for n in zf.namelist() if ".dist-info/sboms/" in n)
        return zf.read(name).decode("utf-8")


def _cli_project(
    tmp: Path, mp: pytest.MonkeyPatch, usage: bool | None, flag: bool | None
) -> str:
    out = tmp / "out.json"
    run_cli(
        [
            "project",
            str(_project(tmp, usage)),
            "-o",
            str(out),
            "--offline",
            *_flag(flag),
        ],
        mp,
    )
    return out.read_text(encoding="utf-8")


def _cli_generate(
    tmp: Path, mp: pytest.MonkeyPatch, usage: bool | None, flag: bool | None
) -> str:
    out = tmp / "out.json"
    argv = ["generate", str(_project(tmp, usage)), "-o", str(out), "--offline"]
    run_cli([*argv, *_flag(flag)], mp)
    return out.read_text(encoding="utf-8")


def _cli_embed(
    tmp: Path, mp: pytest.MonkeyPatch, usage: bool | None, flag: bool | None
) -> str:
    project = _project(tmp, usage)
    wheel = _wheel(tmp, project)
    run_cli(
        ["embed-wheel", str(wheel), "--project-dir", str(project), "--offline"]
        + _flag(flag),
        mp,
    )
    return _embedded(wheel)


def _lib_project(
    tmp: Path, _mp: pytest.MonkeyPatch, usage: bool | None, flag: bool | None
) -> str:
    return generate_project_sbom(
        _project(tmp, usage), offline=True, scan_model_usage=flag
    )


def _lib_generate(
    tmp: Path, _mp: pytest.MonkeyPatch, usage: bool | None, flag: bool | None
) -> str:
    return generate(_project(tmp, usage), offline=True, scan_model_usage=flag)


def _lib_embed(
    tmp: Path, _mp: pytest.MonkeyPatch, usage: bool | None, flag: bool | None
) -> str:
    project = _project(tmp, usage)
    wheel = _wheel(tmp, project)
    overrides = ConfigOverrides(offline=True, scan_model_usage=flag)
    return embed_wheel_sbom(wheel, project_dir=project, overrides=overrides)[2]


def _hook(
    tmp: Path, _mp: pytest.MonkeyPatch, usage: bool | None, flag: bool | None
) -> str:
    del flag  # the hook has no per-run override; the caller skips those runs
    hook = make_hook(str(_project(tmp, usage)), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    (staged,) = build_data["sbom_files"]
    try:
        return Path(staged).read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")


_LIVE: dict[str, _Runner] = {
    "cli-project": _cli_project,
    "cli-generate": _cli_generate,
    "cli-embed-wheel-project-dir": _cli_embed,
    "lib-generate_project_sbom": _lib_project,
    "lib-generate": _lib_generate,
    "lib-embed_wheel_sbom": _lib_embed,
    "hatch-hook": _hook,
}
# scenario -> (config key, flag, whether usage edges are expected); the hint
# is expected exactly when the setting was never given and no edges result.
_SCENARIOS: dict[str, tuple[bool | None, bool | None, bool]] = {
    "default": (None, None, False),
    "flag": (None, True, True),
    "flag-off": (None, False, False),
    "config": (True, None, True),
    "config-false": (False, None, False),
    "config+no-flag": (True, False, False),
}


def _graph(sbom: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _usage(sbom: str) -> list[tuple[str, str]]:
    """(script, model file) name pairs of every ``hasDataFile``."""
    graph = _graph(sbom)
    names = {e["spdxId"]: e["name"] for e in graph if e["type"] == "software_File"}
    return [
        (names[r["from"]], names[t])
        for r in graph
        if r["type"].endswith("Relationship") and r["relationshipType"] == "hasDataFile"
        for t in r["to"]
    ]


def _hints(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if _HINT in r.getMessage()]


@pytest.mark.parametrize("surface", _LIVE)
def test_usage_pass_default_flag_config_and_cascade(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    sboms: dict[str, str] = {}
    caplog.set_level(logging.INFO)
    for name, (usage, flag, edges) in _SCENARIOS.items():
        if flag is not None and surface == "hatch-hook":
            continue
        caplog.clear()
        sboms[name] = _LIVE[surface](tmp_path / name, monkeypatch, usage, flag)
        packages = [e for e in _graph(sboms[name]) if e["type"] == "ai_AIPackage"]
        assert len(packages) == 1, name  # discovery never depends on the flag
        expected = [("demo/use.py", f"demo/{_MODEL}")] if edges else []
        assert _usage(sboms[name]) == expected, name
        unset = usage is None and flag is None
        assert _hints(caplog) == ([_HINT_ONE] if unset else []), name
    assert sboms["config"] != sboms["default"]  # not vacuous
    if surface != "hatch-hook":
        assert sboms["config"] == sboms["flag"]
        for quiet in ("config+no-flag", "flag-off", "config-false"):
            assert sboms[quiet] == sboms["default"], quiet


@pytest.mark.parametrize("via_cli", [False, True], ids=["library", "cli"])
def test_no_hint_when_no_model_was_found(
    via_cli: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    project = _project(tmp_path, model=False)
    if via_cli:
        out = tmp_path / "out.json"
        run_cli(["project", str(project), "-o", str(out)], monkeypatch)
        sbom = out.read_text(encoding="utf-8")
    else:
        sbom = generate_project_sbom(project)
    assert "demo" in sbom  # a real SBOM, without any AI model
    assert not [e for e in _graph(sbom) if e["type"] == "ai_AIPackage"]
    assert not _hints(caplog)


def _setup_cfg_project(tmp: Path, value: str) -> Path:
    root = _project(tmp)
    (root / "pyproject.toml").unlink()
    (root / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 1.0.0\n\n[options]\npackages = demo\n"
        "[options.package_data]\ndemo = *.safetensors\n\n"
        f"[tool:pitloom]\noffline = true\nscan-model-usage = {value}\n",
        encoding="utf-8",
    )
    return root


@pytest.mark.parametrize("form", ["pyproject", "setup.cfg", "--config"])
@pytest.mark.parametrize("value", [False, True])
def test_config_forms_of_the_setting_settle_the_hint(
    form: str,
    value: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An explicit ``false`` is silent in every config form; ``true`` scans."""
    caplog.set_level(logging.INFO)
    lower = str(value).lower()
    if form == "setup.cfg":
        sbom = generate_project_sbom(_setup_cfg_project(tmp_path, lower))
    elif form == "pyproject":
        sbom = generate_project_sbom(_project(tmp_path, value))
    else:
        cfg = tmp_path / "loom.toml"
        cfg.write_text(f"[tool.pitloom]\nscan-model-usage = {lower}\n", "utf-8")
        out = tmp_path / "out.json"
        project = _project(tmp_path)
        run_cli(
            [
                "project",
                str(project),
                "-o",
                str(out),
                "--offline",
                "--config",
                str(cfg),
            ],
            monkeypatch,
        )
        sbom = out.read_text(encoding="utf-8")
    assert bool(_usage(sbom)) is value
    assert not _hints(caplog)


@pytest.mark.parametrize(
    ("flag", "hints", "edges"),
    [(None, 1, False), (False, 0, False), (True, 0, True)],
    ids=["unset", "no-flag", "flag"],
)
def test_multi_wheel_embed_hints_at_most_once_per_run(
    flag: bool | None,
    hints: int,
    edges: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    project = _project(tmp_path)
    wheels = [_wheel(tmp_path / name, project) for name in ("a", "b", "c")]
    run_cli(
        ["embed-wheel", *map(str, wheels), "--project-dir", str(project), "--offline"]
        + _flag(flag),
        monkeypatch,
    )
    assert len(_hints(caplog)) == hints
    for wheel in wheels:  # the usage pass still follows the setting per wheel
        assert bool(_usage(_embedded(wheel))) is edges


def test_hint_text_has_one_source() -> None:
    root = Path(pitloom_file).parent
    hits = [
        p
        for p in root.rglob("*.py")
        if "AI model file(s); pass --scan-model-usage" in p.read_text(encoding="utf-8")
    ]
    assert [p.name for p in hits] == ["scanner.py"]


def _sdist(tmp: Path, project: Path) -> Path:
    sdist = tmp / "demo-1.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as tf:
        tf.add(project, arcname="demo-1.0.0")
    return sdist


def _stub_env(mp: pytest.MonkeyPatch) -> None:
    mp.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["pipdeptree"], returncode=0, stdout="[]", stderr=""
        ),
    )


def _inert_argv(kind: str, tmp: Path, mp: pytest.MonkeyPatch) -> tuple[list[str], Path]:
    """The argv for *kind* and where its SBOM ends up (a file or a wheel)."""
    out = tmp / "out.json"
    project = _project(tmp)
    if kind == "wheel":
        return ["wheel", str(_wheel(tmp, project)), "-o", str(out)], out
    if kind in ("wheel-embed", "embed-wheel-standalone"):
        wheel = _wheel(tmp, project)
        head = (
            ["wheel", str(wheel), "--embed"]
            if kind == "wheel-embed"
            else [
                "embed-wheel",
                str(wheel),
            ]
        )
        return head, wheel
    if kind == "env":
        _stub_env(mp)
        return ["env", "-o", str(out)], out
    if kind == "model":
        model = project / "demo" / _MODEL
        return ["model", str(model), "-o", str(out)], out
    return ["project", str(_sdist(tmp, project)), "-o", str(out)], out


@pytest.mark.parametrize(
    "kind",
    ["wheel", "wheel-embed", "embed-wheel-standalone", "env", "model", "sdist"],
)
def test_inert_surfaces_warn_once_and_change_nothing(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    results: dict[bool, str] = {}
    for given in (False, True):
        caplog.clear()
        argv, artefact = _inert_argv(kind, tmp_path / str(given), monkeypatch)
        run_cli([*argv, "--offline", *(_flag(True) if given else [])], monkeypatch)
        warned = [
            r.getMessage()
            for r in caplog.records
            if r.levelno == logging.WARNING
            and r.getMessage().startswith("Options:")
            and "--scan-model-usage" in r.getMessage()
        ]
        assert len(warned) == int(given)
        assert not _hints(caplog)
        results[given] = (
            _embedded(artefact)
            if artefact.suffix == ".whl"
            else artefact.read_text(encoding="utf-8")
        )
    assert results[True] == results[False]
