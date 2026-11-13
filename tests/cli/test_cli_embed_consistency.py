# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``wheel --embed`` and ``embed-wheel`` behave alike, and every option or
default either takes effect or says why not.

See also: :mod:`tests.cli.test_cli_wheel` (``wheel --embed`` output) and
:mod:`tests.cli.test_cli_option_reach` (every option reaches or warns).
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.core.build_options import EXTERNAL_SBOM_REASON
from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import demo_project
from tests.warning_helpers import count_naming, stderr_warnings


def _loom(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def _embedded(wheel: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(wheel) as archive:
        return {
            name.rsplit("/", 1)[1]: archive.read(name)
            for name in archive.namelist()
            if "/sboms/" in name
        }


def test_both_embed_commands_honour_the_config_sbom_basename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``--config`` ``sbom-basename`` names the embedded file on both
    commands, and the two embed the same bytes -- compact and without
    relationship text, whatever the config's ``pretty`` and
    ``describe-relationship`` say (documented as unused for an embed)."""
    config = tmp_path / "c.toml"
    config.write_text(
        '[tool.pitloom]\nsbom-basename = "custom"\npretty = true\n'
        "describe-relationship = true\n",
        encoding="utf-8",
    )
    common = ["--config", str(config), "--offline"]
    common += ["--creation-datetime", "2026-01-01T00:00:00Z"]
    one = _make_dummy_wheel(tmp_path / "one", "demo", "1.0.0")
    two = _make_dummy_wheel(tmp_path / "two", "demo", "1.0.0")

    assert _loom(["wheel", str(one), "--embed", *common], monkeypatch) == 0
    assert _loom(["embed-wheel", str(two), *common], monkeypatch) == 0

    assert list(_embedded(one)) == ["custom.spdx3.json"]
    assert _embedded(one) == _embedded(two)
    (embedded,) = _embedded(one).values()
    assert b"\n" not in embedded.rstrip(b"\n"), "not compact"
    # describe-relationship gives each Relationship a "description"
    graph = json.loads(embedded)["@graph"]
    relationships = [o for o in graph if o["type"] == "Relationship"]
    assert relationships and not any("description" in o for o in relationships)


@pytest.mark.parametrize("flag", ["--pretty", "--describe-relationship"])
def test_external_sbom_options_warn_with_the_external_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flag: str,
) -> None:
    """An ``--sbom`` file is embedded as is, so a formatting flag has no
    effect *because* nothing is regenerated -- not because the embed
    would reformat it."""
    project = demo_project(tmp_path)
    sbom = tmp_path / "given.spdx3.json"
    assert (
        _loom(["project", str(project), "-o", str(sbom), "--offline"], monkeypatch) == 0
    )
    capsys.readouterr()
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")
    argv = ["embed-wheel", str(wheel), "--sbom", str(sbom), "--allow-mismatch", flag]

    assert _loom(argv, monkeypatch) == 0

    named = [w for w in stderr_warnings(capsys.readouterr().err) if flag in w]
    assert len(named) == 1
    assert named[0].endswith(f"{EXTERNAL_SBOM_REASON} [option-no-effect]")


@pytest.mark.parametrize(
    "argv",
    [["generate", "{wheel}", "-o", "{out}"], ["embed-wheel", "{wheel}"]],
    ids=["generate-wheel", "embed-wheel"],
)
def test_verbose_without_verbose_output_warns_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")
    fields = {"wheel": str(wheel), "out": str(tmp_path / "o.json")}
    command = [part.format(**fields) for part in argv]

    assert _loom([*command, "--offline", "-v"], monkeypatch) == 0
    assert count_naming(stderr_warnings(capsys.readouterr().err), "-v") == 1
    # Non-vacuous: without -v, nothing warns about it.
    assert _loom([*command, "--offline"], monkeypatch) == 0
    assert count_naming(stderr_warnings(capsys.readouterr().err), "-v") == 0


@pytest.mark.parametrize("cwd_is_project", [True, False])
def test_embed_without_project_dir_says_the_cwd_project_is_not_used(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cwd_is_project: bool,
) -> None:
    """Run from inside a project without ``--project-dir``: one ``INFO:``
    says that project is not used, so nobody mistakes the standalone SBOM
    for a project rescan. Elsewhere, nothing to say."""
    cwd = demo_project(tmp_path) if cwd_is_project else tmp_path / "empty"
    cwd.mkdir(exist_ok=True)
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")
    monkeypatch.chdir(cwd)

    assert _loom(["embed-wheel", str(wheel), "--offline"], monkeypatch) == 0

    infos = [
        line
        for line in capsys.readouterr().err.splitlines()
        if line.startswith("INFO: ") and "--project-dir" in line
    ]
    assert len(infos) == int(cwd_is_project)


@pytest.mark.parametrize(
    ("flag", "missing"), [("--config", "missing.toml"), ("--project-dir", "nodir")]
)
def test_embed_external_sbom_does_not_read_config_or_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flag: str,
    missing: str,
) -> None:
    """``--sbom`` is embedded as is, so ``--config`` and ``--project-dir``
    have no effect: one warning each, and the path is not read -- a missing
    one fails nothing."""
    project = demo_project(tmp_path)
    sbom = tmp_path / "given.spdx3.json"
    assert (
        _loom(["project", str(project), "-o", str(sbom), "--offline"], monkeypatch) == 0
    )
    capsys.readouterr()
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")
    argv = ["embed-wheel", str(wheel), "--sbom", str(sbom), "--allow-mismatch"]

    assert _loom([*argv, flag, str(tmp_path / missing)], monkeypatch) == 0

    err = capsys.readouterr().err
    named = [w for w in stderr_warnings(err) if f" {flag} has no effect" in w]
    assert len(named) == 1 and named[0].endswith(
        f"{EXTERNAL_SBOM_REASON} [option-no-effect]"
    )
    assert "ERROR:" not in err
    # Non-vacuous: without --sbom the same missing path is an error.
    assert _loom(
        ["embed-wheel", str(wheel), flag, str(tmp_path / missing)], monkeypatch
    )
    assert "ERROR:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "flag", ["--enrich", "--extract-file-header", "--content-type", "--pretty"]
)
def test_both_embed_commands_give_the_same_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flag: str,
) -> None:
    """``wheel --embed`` and ``embed-wheel`` without a project embed the same
    SBOM, so an option neither can use warns once, for the same reason."""

    def reason(argv: list[str]) -> str:
        assert _loom([*argv, "--offline", flag], monkeypatch) == 0
        named = [w for w in stderr_warnings(capsys.readouterr().err) if flag in w]
        assert len(named) == 1
        return named[0].split(" has no effect ", 1)[1]

    one = _make_dummy_wheel(tmp_path / "one", "demo", "1.0.0")
    two = _make_dummy_wheel(tmp_path / "two", "demo", "1.0.0")
    assert reason(["wheel", str(one), "--embed"]) == reason(["embed-wheel", str(two)])
