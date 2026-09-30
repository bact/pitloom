# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI models inside a built wheel, on every wheel surface.

``loom wheel``, ``loom wheel --embed``, ``loom embed-wheel`` without
``--project-dir``, ``generate()`` on a ``.whl``, ``generate_wheel_sbom()`` and
``embed_wheel_sbom()`` without ``project_dir`` always find the wheel's AI
models; with ``scan-model-usage`` on they also record which ``.py`` members
reference them. A wheel has no config of its own, so the setting comes from
``--config``/``pitloom_config=`` and the per-run flag only.

See also: :mod:`tests.assemble.test_scan_model_usage` (project surfaces),
tests/extract/scanner/test_scanner_wheel.py (the producer).
"""

from __future__ import annotations

import dataclasses
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate, generate_wheel_sbom
from pitloom.core.config import PitloomConfig
from pitloom.embed import ConfigOverrides, embed_wheel_sbom
from pitloom.id_registry import IdRegistry
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.assemble.embed_surfaces_shared import run_cli
from tests.assemble.test_scan_model_usage import (
    _HINT_ONE,
    _MODEL,
    _SCENARIOS,
    _embedded,
    _flag,
    _graph,
    _hints,
    _usage,
)
from tests.warning_helpers import count_naming, logged_warnings

_MEMBERS = {
    f"demo/{_MODEL}": safetensors_bytes(),
    "demo/use.py": f'M = "{_MODEL}"\n'.encode(),
}
_Runner = Callable[..., str]  # (tmp, mp, usage, flag, ceiling=None) -> SBOM json


def _config(tmp: Path, usage: bool | None, extra: str = "") -> list[str]:
    """``--config`` argv for a config file with *usage* and *extra* lines."""
    if usage is None and not extra:
        return []
    body = "[tool.pitloom]\n" + extra
    if usage is not None:
        body += f"scan-model-usage = {str(usage).lower()}\n"
    path = tmp / "loom.toml"
    path.write_text(body, encoding="utf-8")
    return ["--config", str(path)]


def _ceiling_line(ceiling: int | None) -> str:
    return "" if ceiling is None else f"max-model-extract-bytes = {ceiling}\n"


def _pitloom_config(usage: bool | None, ceiling: int | None) -> PitloomConfig | None:
    if usage is None and ceiling is None:
        return None
    config = PitloomConfig(scan_model_usage=usage)
    if ceiling is not None:
        config = dataclasses.replace(config, max_model_extract_bytes=ceiling)
    return config


def _cli_wheel(
    tmp: Path,
    mp: pytest.MonkeyPatch,
    usage: bool | None,
    flag: bool | None,
    ceiling: int | None = None,
) -> str:
    out = tmp / "out.json"
    wheel = write_model_wheel(tmp / "dist", _MEMBERS)
    run_cli(
        [
            "wheel",
            str(wheel),
            "-o",
            str(out),
            "--offline",
            *_config(tmp, usage, _ceiling_line(ceiling)),
            *_flag(flag),
        ],
        mp,
    )
    return out.read_text(encoding="utf-8")


def _cli_wheel_embed(
    tmp: Path,
    mp: pytest.MonkeyPatch,
    usage: bool | None,
    flag: bool | None,
    ceiling: int | None = None,
) -> str:
    wheel = write_model_wheel(tmp / "dist", _MEMBERS)
    run_cli(
        [
            "wheel",
            str(wheel),
            "--embed",
            "--offline",
            *_config(tmp, usage, _ceiling_line(ceiling)),
            *_flag(flag),
        ],
        mp,
    )
    return _embedded(wheel)


def _cli_embed_wheel(
    tmp: Path,
    mp: pytest.MonkeyPatch,
    usage: bool | None,
    flag: bool | None,
    ceiling: int | None = None,
) -> str:
    wheel = write_model_wheel(tmp / "dist", _MEMBERS)
    run_cli(
        [
            "embed-wheel",
            str(wheel),
            "--offline",
            *_config(tmp, usage, _ceiling_line(ceiling)),
            *_flag(flag),
        ],
        mp,
    )
    return _embedded(wheel)


def _lib_generate(
    tmp: Path,
    _mp: pytest.MonkeyPatch,
    usage: bool | None,
    flag: bool | None,
    ceiling: int | None = None,
) -> str:
    wheel = write_model_wheel(tmp / "dist", _MEMBERS)
    return generate(
        wheel,
        offline=True,
        scan_model_usage=flag,
        pitloom_config=_pitloom_config(usage, ceiling),
    )


def _lib_wheel(
    tmp: Path,
    _mp: pytest.MonkeyPatch,
    usage: bool | None,
    flag: bool | None,
    ceiling: int | None = None,
) -> str:
    wheel = write_model_wheel(tmp / "dist", _MEMBERS)
    return generate_wheel_sbom(
        wheel,
        offline=True,
        scan_model_usage=flag,
        pitloom_config=_pitloom_config(usage, ceiling),
    )


def _lib_embed(
    tmp: Path,
    _mp: pytest.MonkeyPatch,
    usage: bool | None,
    flag: bool | None,
    ceiling: int | None = None,
) -> str:
    wheel = write_model_wheel(tmp / "dist", _MEMBERS)
    overrides = ConfigOverrides(offline=True, scan_model_usage=flag)
    embed_wheel_sbom(
        wheel, pitloom_config=_pitloom_config(usage, ceiling), overrides=overrides
    )
    return _embedded(wheel)


_SURFACES: dict[str, _Runner] = {
    "cli-wheel": _cli_wheel,
    "cli-wheel-embed": _cli_wheel_embed,
    "cli-embed-wheel-standalone": _cli_embed_wheel,
    "lib-generate": _lib_generate,
    "lib-generate_wheel_sbom": _lib_wheel,
    "lib-embed_wheel_sbom": _lib_embed,
}


@pytest.mark.parametrize("surface", _SURFACES)
def test_wheel_usage_pass_default_flag_config_and_cascade(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    monkeypatch.chdir(tmp_path)
    sboms: dict[str, str] = {}
    caplog.set_level(logging.INFO)
    for name, (usage, flag, edges) in _SCENARIOS.items():
        caplog.clear()
        sboms[name] = _SURFACES[surface](tmp_path / name, monkeypatch, usage, flag)
        packages = [e for e in _graph(sboms[name]) if e["type"] == "ai_AIPackage"]
        assert len(packages) == 1, name  # discovery never depends on the flag
        expected = [("demo/use.py", f"demo/{_MODEL}")] if edges else []
        assert _usage(sboms[name]) == expected, name
        unset = usage is None and flag is None
        assert _hints(caplog) == ([_HINT_ONE] if unset else []), name
        assert not [w for w in logged_warnings(caplog) if "has no effect" in w], name
    assert sboms["config"] != sboms["default"]  # not vacuous
    assert sboms["config"] == sboms["flag"]
    for quiet in ("config+no-flag", "flag-off", "config-false"):
        assert sboms[quiet] == sboms["default"], quiet


@pytest.mark.parametrize(
    ("flag", "hints"), [(None, 1), (False, 0), (True, 0)], ids=["unset", "no", "yes"]
)
def test_standalone_batch_hints_once_from_the_first_wheel_with_models(
    flag: bool | None,
    hints: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A model-less first wheel must not use up the hint."""
    caplog.set_level(logging.INFO)
    wheels = [
        write_model_wheel(tmp_path / "a", {}, name="plain"),
        write_model_wheel(tmp_path / "b", _MEMBERS, name="one"),
        write_model_wheel(tmp_path / "c", _MEMBERS, name="two"),
    ]
    run_cli(["embed-wheel", *map(str, wheels), "--offline", *_flag(flag)], monkeypatch)
    assert len(_hints(caplog)) == hints
    assert [bool(_usage(_embedded(w))) for w in wheels] == [
        False,
        flag is True,
        flag is True,
    ]


def test_wheel_sbom_carries_no_scan_path_and_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    runs = [_lib_wheel(tmp_path / str(i), monkeypatch, True, None) for i in range(2)]
    assert runs[0] == runs[1]
    assert any(e["type"] == "ai_AIPackage" for e in _graph(runs[0]))
    assert f"Source: {_MODEL}" in runs[0]  # not the copy's own name
    for forbidden in (
        "pitloom-",
        tempfile.gettempdir(),
        os.path.realpath(tempfile.gettempdir()),
    ):
        assert forbidden not in runs[0], forbidden
    assert f"demo/{_MODEL}" in {e.get("name") for e in _graph(runs[0])}


def test_wheel_model_ids_are_stable_through_a_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    registry = tmp_path / "registry.json"
    IdRegistry.new("demo", path=registry).save()
    wheel = write_model_wheel(tmp_path / "dist", _MEMBERS)
    runs = []
    for i in range(3):
        out = tmp_path / f"out{i}.json"
        run_cli(
            [
                "wheel",
                str(wheel),
                "--offline",
                "-o",
                str(out),
                "--id-registry",
                str(registry),
            ],
            monkeypatch,
        )
        runs.append(out.read_text(encoding="utf-8"))
    assert runs[0] == runs[1] == runs[2]
    ids = [e["spdxId"] for e in _graph(runs[0]) if "spdxId" in e]
    assert len(ids) == len(set(ids))
    assert any(e["type"] == "ai_AIPackage" for e in _graph(runs[0]))


@pytest.mark.parametrize("surface", _SURFACES)
def test_ceiling_comes_from_the_config(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``max-model-extract-bytes`` reaches the scan on every wheel surface,
    and a model over it stays listed, without its metadata."""
    caplog.set_level(logging.WARNING)
    sbom = _SURFACES[surface](tmp_path, monkeypatch, None, None, 64)
    (package,) = [e for e in _graph(sbom) if e["type"] == "ai_AIPackage"]
    assert f"demo/{_MODEL}" in sbom
    assert f"Source: {_MODEL}" not in sbom  # nothing was read from the model
    assert package.get("ai_typeOfModel") is None
    (message,) = [m for m in logged_warnings(caplog) if "scan ceiling" in m]
    assert f"demo/{_MODEL}" in message
    assert "64-byte" in message


@pytest.mark.parametrize("surface", _SURFACES)
@pytest.mark.parametrize("bad", [0, -1, True, "5"], ids=repr)
def test_library_ceiling_is_validated_before_scanning(
    surface: str, bad: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``PitloomConfig`` is never parsed, so a bad ceiling reaches the scan
    as is and is refused with the config reader's one-line error."""
    if surface.startswith("cli-"):
        pytest.skip("the config reader rejects it: test_config")
    with pytest.raises(ValueError, match="'max-model-extract-bytes' must be"):
        _SURFACES[surface](tmp_path, monkeypatch, None, None, bad)


def _run(
    kind: str,
    tmp: Path,
    mp: pytest.MonkeyPatch,
    *argv: str,
    members: dict[str, bytes] = _MEMBERS,
) -> str:
    """One ``wheel`` or standalone ``embed-wheel`` run over the model wheel."""
    wheel = write_model_wheel(tmp / "dist", members)
    out = tmp / "out.json"
    head = ["wheel", str(wheel), "-o", str(out)] if kind == "wheel" else ["embed-wheel"]
    run_cli([*head, *([str(wheel)] if kind != "wheel" else []), "--offline", *argv], mp)
    return out.read_text(encoding="utf-8") if kind == "wheel" else _embedded(wheel)


@pytest.mark.parametrize("kind", ["wheel", "embed-wheel"])
@pytest.mark.parametrize(
    "flag", ["--enrich", "--extract-file-header", "--content-type"]
)
def test_inert_flags_still_warn_once_and_change_nothing_on_a_model_wheel(
    kind: str,
    flag: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    plain = _run(kind, tmp_path / "a", monkeypatch)
    caplog.clear()
    given = _run(kind, tmp_path / "b", monkeypatch, flag)
    assert count_naming(logged_warnings(caplog), flag) == 1
    assert given == plain
    assert any(e["type"] == "ai_AIPackage" for e in _graph(given))


@pytest.mark.parametrize("kind", ["wheel", "embed-wheel"])
@pytest.mark.parametrize(("preserve", "changes"), [("auto", False), ("always", True)])
def test_source_metadata_cap_acts_on_a_wheel_model_only_when_always_preserved(
    kind: str,
    preserve: str,
    changes: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shipped model's metadata is preserved only under ``always``, so only
    then has ``--max-source-metadata-bytes`` anything to cap."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    config = _config(
        tmp_path,
        None,
        f'\n[tool.pitloom.provenance]\npreserve-source-metadata = "{preserve}"\n',
    )
    members = {
        f"demo/{_MODEL}": safetensors_bytes(
            metadata={f"k{i}": "v" * 40 for i in range(9)}
        )
    }
    cap = ["--max-source-metadata-bytes", "64"]
    uncapped = _run(kind, tmp_path / "a", monkeypatch, *config, members=members)
    capped = _run(kind, tmp_path / "b", monkeypatch, *config, *cap, members=members)
    assert (capped != uncapped) is changes
