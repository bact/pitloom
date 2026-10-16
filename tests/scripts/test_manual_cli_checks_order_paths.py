# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The path-key side of the order matrix (``scripts/manual_cli_checks``):
the monorepo, subdirectory and spelling steps render as intended, the
spelling steps stay out of walks, a spelling check skips with a reason, and
the lookups the path-key invariants use (:func:`candidates`, :func:`held`).

See also: ``test_manual_cli_checks_order.py`` (the invariants themselves).
"""

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

NS = "https://example.org/t#"
SHA_A, SHA_B = "a" * 64, "b" * 64


def _lines(mcc: dict[str, ModuleType], profile: str, *ops: str) -> list[str]:
    gen = mcc["_order_gen"]
    seq = gen.plan("t", mcc["_order_fixtures"].PROFILES[profile], (), ops)
    return [line for step in seq.steps for line in step.lines]


@pytest.mark.parametrize(
    ("profile", "op", "expected"),
    [
        ("flat", "sdist", ["build_sdist 01 .", '"$SDIST" --id-registry']),
        ("monorepo", "project", ["project pkgs/demo --id-registry"]),
        (
            "monorepo",
            "embed",
            ["build 01 pkgs/demo", "embed-wheel", "--project-dir pkgs/demo"],
        ),
        ("monorepo", "gen-min", ["id generate pkgs/demo/pyproject.toml"]),
        ("monorepo", "sdist", ['"$SDIST" --id-registry', "--project-dir pkgs/demo"]),
        ("monorepo", "wheel", ['"$WHEEL" --id-registry', "--project-dir pkgs/demo"]),
        (
            "subdir",
            "train",
            ["in_dir scripts", "train.py", "../models/m.safetensors m ../data/t.txt"],
        ),
        ("subdir", "eval", ["in_dir scripts", "eval.py", "../models/m.safetensors"]),
        ("flat", "model-upper", ["model DEMO/TINY.safetensors"]),
        ("flat", "train-upper", ["in_dir . ", "DEMO/TINY.safetensors tiny"]),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_new_steps_render(
    mcc: dict[str, ModuleType], profile: str, op: str, expected: list[str]
) -> None:
    line = " ".join(_lines(mcc, profile, op))
    for part in expected:
        assert part in line


def test_add_nfd_names_the_module_in_nfd(mcc: dict[str, ModuleType]) -> None:
    ops = mcc["_order_ops"]
    (line,) = _lines(mcc, "flat", "add-nfd")
    assert ops.NFD_STEM in line
    assert ops.NFD_STEM != ops.NFD_STEM.encode().decode().replace("́", "")
    assert "́" in line and "é" not in line


def test_the_monorepo_runs_every_archive_step(mcc: dict[str, ModuleType]) -> None:
    """`sdist`, `wheel` and `embed` name the project directory, so each
    applies; a profile without one renders no `--project-dir`."""
    ops, fixtures = mcc["_order_ops"], mcc["_order_fixtures"]
    mono = fixtures.PROFILES["monorepo"]
    assert all(ops.applies(op, mono) for op in ("sdist", "wheel", "embed"))
    for op in ("sdist", "wheel"):
        assert "--project-dir" not in " ".join(_lines(mcc, "flat", op))


def test_spelling_steps_stay_out_of_walks_and_repeats(
    mcc: dict[str, ModuleType],
) -> None:
    gen, spelling = mcc["_order_gen"], mcc["_order_ops"].SPELLING
    for profile in gen.all_profiles():
        for seq in [*gen.walks(profile, 0, 16), *gen.repeats(profile)]:
            assert not spelling & set(seq.ops), (profile.name, seq.label)


@pytest.mark.parametrize(
    ("kind", "probe", "reason"),
    [("nfd", "keeps_nfd", "NFD"), ("upper", "folds_case", "case-sensitive")],
)
def test_a_spelling_check_skips_with_its_reason(
    mcc: dict[str, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    probe: str,
    reason: str,
) -> None:
    module = importlib.import_module("_checks_order_spelling")
    monkeypatch.setattr(module, probe, lambda _directory: False)
    harness = mcc["_harness"]
    ctx = harness.Context(work=tmp_path, network=False, verbose=False)
    profile = mcc["_order_fixtures"].PROFILES["flat"]
    with pytest.raises(harness.CheckSkipped, match=reason):
        # pylint: disable-next=protected-access
        module._spelling_check(ctx, profile, kind)


@pytest.mark.usefixtures("mcc")
def test_the_probes_answer_for_a_real_directory(tmp_path: Path) -> None:
    module = importlib.import_module("_checks_order_spelling")
    assert isinstance(module.keeps_nfd(tmp_path), bool)
    assert isinstance(module.folds_case(tmp_path), bool)
    assert not list(tmp_path.iterdir())  # each probe removes its file


def _elem(
    mcc: dict[str, ModuleType], type_name: str, name: str, sha: str | None
) -> Any:
    return mcc["_order_capture"].Element(
        mcc["_order_capture"].canonical(type_name, name), NS + "X-1", sha, name
    )


@pytest.mark.parametrize(
    ("profile", "surface", "elem", "disk", "expected"),
    [
        (
            "monorepo",
            "project",
            ("software_File", "demo/x.py"),
            ["pkgs/demo/demo/x.py"],
            ["pkgs/demo/demo/x.py", "demo/x.py"],
        ),
        (
            "monorepo",
            "embed",
            ("software_File", "demo/x.py"),
            [],
            ["pkgs/demo/demo/x.py", "demo/x.py"],
        ),
        (
            "monorepo",
            "wheel",
            ("software_File", "demo/x.py"),
            [],
            ["pkgs/demo/demo/x.py", "demo/x.py"],
        ),
        (
            "monorepo",
            "sdist",
            ("software_File", "demo-0.1/PKG-INFO"),
            [],
            ["pkgs/demo/PKG-INFO", "demo-0.1/PKG-INFO", "PKG-INFO"],
        ),
        (
            "flat",
            "sdist",
            ("software_File", "demo-0.1/demo/x.py"),
            ["demo/x.py"],
            ["demo-0.1/demo/x.py", "demo/x.py"],
        ),
        (
            "flat",
            "wheel",
            ("software_File", "demo/x.py"),
            ["demo/x.py"],
            ["demo/x.py"],
        ),
        (
            "src",
            "wheel",
            ("ai_AIPackage", "tiny"),
            [],
            [
                "src/sampleproject_hatchling/tiny.safetensors",
                "sampleproject_hatchling/tiny.safetensors",
            ],
        ),
        ("stems", "wheel", ("ai_AIPackage", "m"), [], []),
        ("stems", "train", ("ai_AIPackage", "m"), [], ["demo/a/m.safetensors"]),
        ("flat", "model", ("ai_AIPackage", "TINY"), [], ["demo/tiny.safetensors"]),
        (
            "subdir",
            "train",
            ("dataset_DatasetPackage", "../data/t.txt"),
            [],
            ["data/t.txt", "../data/t.txt"],
        ),
    ],
    ids=[
        "monorepo",
        "monorepo-embed",
        "monorepo-wheel",
        "monorepo-sdist-only",
        "sdist",
        "wheel",
        "src-model",
        "stems-ambiguous",
        "stems-loom",
        "upper-model-name",
        "subdir-dataset",
    ],
)
def test_candidates(
    mcc: dict[str, ModuleType],
    profile: str,
    surface: str,
    elem: tuple[str, str],
    disk: list[str],
    expected: list[str],
) -> None:
    paths = importlib.import_module("_order_paths")
    prof = mcc["_order_fixtures"].PROFILES[profile]
    got = paths.candidates(
        prof, surface, _elem(mcc, *elem, SHA_A), dict.fromkeys(disk, SHA_A)
    )
    assert [name for _, name in got] == expected


def test_held_is_gated_for_a_file_and_follows_a_layout_alias(
    mcc: dict[str, ModuleType],
) -> None:
    paths, cap = importlib.import_module("_order_paths"), mcc["_order_capture"]
    entry = cap.Entry
    reg = {
        ("software_File", "src/p/x.py"): entry(NS + "File-1", SHA_A),
        ("software_Package", "p"): entry(NS + "Package-1", None),
    }
    assert paths.held(reg, ("software_File", "src/p/x.py"), SHA_A)
    assert paths.held(reg, ("software_File", "src/p/x.py"), SHA_B) is None
    assert paths.held(reg, ("software_File", "p/x.py"), SHA_A)[0][1] == "src/p/x.py"
    assert paths.held(reg, ("software_File", "p/x.py"), SHA_B) is None
    assert paths.held(reg, ("software_File", "p/x.py"), None) is None
    assert paths.held(reg, ("software_Package", "p"), SHA_B)
