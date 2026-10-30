# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Keeps the order-matrix checks (``O*`` in ``scripts/manual_cli_checks``)
honest: each invariant fires on a doctored step and stays quiet on the
clean one, G classifies convergence, and the allow-list names its item
only for its own case.

See also: ``tests/scripts/test_manual_cli_checks.py`` (the runner),
``test_manual_cli_checks_order_runs.py`` (the scripts and real runs).
"""

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

NS = "https://example.org/t#"
_POSIX_SH = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh scripts")
SHA_A = hashlib.sha256(b"a").hexdigest()


def _reg(
    entries: dict[tuple[str, str], tuple[str, str | None]], sep: str = ""
) -> bytes:
    elements: dict[str, dict[str, dict[str, str]]] = {}
    for (type_name, name), (spdx_id, sha) in entries.items():
        entry = {"spdxId": NS + spdx_id}
        if sha:
            entry["sha256"] = sha
        elements.setdefault(type_name, {})[name] = entry
    data = {
        "elements": elements,
        "namespace": NS[:-1],
        "project_root": ".",
        "version": 4,
    }
    return (json.dumps(data, sort_keys=True) + sep).encode()


_PKG = ("software_Package", "demo")
_FILE = ("software_File", "pkg/a.py")
_CLEAN: dict[tuple[str, str], tuple[str, str | None]] = {
    _PKG: ("Package-1", None),
    _FILE: ("File-1", SHA_A),
}


def _graph(package: str = "Package-1", extra: int = 0) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = [
        {"type": "software_Package", "name": "demo", "spdxId": NS + package},
        {
            "type": "software_File",
            "name": "pkg/a.py",
            "spdxId": NS + "File-1",
            "verifiedUsing": [{"algorithm": "sha256", "hashValue": SHA_A}],
        },
    ]
    return graph + [{"type": "Relationship", "spdxId": NS + "R-1"}] * extra


# pylint: disable-next=too-few-public-methods
class _Seq:
    """Four ``project`` steps (the first a setup) as captured, each a
    knob a test turns to doctor one fact."""

    def __init__(self, mods: dict[str, ModuleType], fixture: Path) -> None:
        self.mods = mods
        self.fixture = fixture
        self.regs = [_reg(_CLEAN)] * 4
        self.graphs = [_graph()] * 4
        self.surfaces = ["project"] * 4
        self.stderr = [""] * 4
        self.rcs = [0] * 4
        self.kinds = ["setup", "step", "step", "step"]
        self.ops = ["project"] * 4
        self.imported: list[str | None] = [None] * 4
        self.models: tuple[str, ...] = ()

    def check(self) -> set[str]:
        capture_mod, ops = self.mods["_order_capture"], self.mods["_order_ops"]
        captured = []
        for i in range(4):
            path = f"out/{i}.json"
            step = ops.Step(
                i + 1,
                self.ops[i],
                self.kinds[i],
                (),
                ((self.surfaces[i], path),),
                self.imported[i],
            )
            raw = json.dumps({"@graph": self.graphs[i]}).encode()
            captured.append(
                capture_mod.Captured(
                    step,
                    self.rcs[i],
                    "",
                    self.stderr[i],
                    self.regs[i],
                    {self.surfaces[i]: self.graphs[i]},
                    {self.surfaces[i]: raw},
                    {},
                )
            )
        profile = self.mods["_order_fixtures"].Profile(
            "t",
            None,
            None,
            "pkg/a.py",
            ("x", "y"),
            "pkg",
            wheel=False,
            models=self.models,
        )
        found, _ = self.mods["_order_invariants"].check_sequence(
            profile, self.fixture, captured
        )
        return {v.code for v in found}


def _churn(s: _Seq) -> None:
    s.regs[1:] = [_reg({**_CLEAN, _PKG: ("Package-2", None)})] * 3
    s.graphs[1:] = [_graph("Package-2")] * 3


def _vanished(s: _Seq) -> None:
    s.regs[1:] = [_reg({_FILE: _CLEAN[_FILE]})] * 3


def _erased(s: _Seq) -> None:
    s.regs[1:] = [_reg({**_CLEAN, _FILE: ("File-1", None)})] * 3


def _swap(s: _Seq) -> None:
    s.regs[1:] = [_reg({**_CLEAN, _FILE: ("File-1", "b" * 64)})] * 3


def _prefix(s: _Seq) -> None:
    s.regs = [_reg({**_CLEAN, _PKG: ("File-9", None)})] * 4
    s.graphs = [_graph("File-9")] * 4


def _cross_type(s: _Seq) -> None:
    s.regs = [_reg({**_CLEAN, _PKG: ("File-1", None)})] * 4
    s.graphs = [_graph("File-1")] * 4


def _multi_key(s: _Seq) -> None:
    s.regs = [_reg({**_CLEAN, ("software_Package", "other"): ("Package-1", None)})] * 4


def _reuse(s: _Seq) -> None:
    other = ("software_Package", "x")
    s.regs[1:] = [
        _reg({**_CLEAN, _PKG: ("Package-2", None), other: ("Package-1", None)})
    ] * 3


def _layout_demoted(s: _Seq) -> None:
    """The id moves from the src key to the shorter one (not a promotion)."""
    src = ("software_File", "src/pkg/a.py")
    s.regs[0] = _reg({**_CLEAN, src: ("File-1", SHA_A)} | {_FILE: ("File-2", SHA_A)})
    s.regs[1:] = [_reg(_CLEAN)] * 3


def _not_a_layout_alias(s: _Seq) -> None:
    """A longer path ending in the same name is no layout alias."""
    other = ("software_File", "other/pkg/a.py")
    s.regs = [_reg({**_CLEAN, other: ("File-1", SHA_A)})] * 4


def _stem_key(s: _Seq) -> None:
    s.models = ("pkg/m.bin",)
    s.regs = [_reg({**_CLEAN, ("ai_AIPackage", "m"): ("AIPackage-1", None)})] * 4


def _one_id_for_two_models(s: _Seq) -> None:
    s.models = ("pkg/a.bin", "pkg/b.bin")
    one = ("AIPackage-1", None)
    s.regs = [
        _reg(
            {
                **_CLEAN,
                ("ai_AIPackage", "pkg/a.bin"): one,
                ("ai_AIPackage", "pkg/b.bin"): one,
            }
        )
    ] * 4


def _nfd_key(s: _Seq) -> None:
    s.regs = [
        _reg({**_CLEAN, ("software_File", "pkg/cafe\u0301.py"): ("File-2", None)})
    ] * 4


def _wrong_case_key(s: _Seq) -> None:
    s.regs = [_reg({**_CLEAN, ("software_File", "pkg/A.py"): ("File-2", None)})] * 4


def _dotdot_key(s: _Seq) -> None:
    s.regs = [_reg({**_CLEAN, ("software_File", "../a.py"): ("File-2", None)})] * 4


def _dataset_unpinned(s: _Seq) -> None:
    """A loom step whose SBOM lacks the dataset `id generate` pinned."""
    pinned = ("dataset_DatasetPackage", "data/t.txt")
    s.regs = [_reg({**_CLEAN, pinned: ("DatasetPackage-1", None)})] * 4
    s.surfaces[1] = "train"


def _registry_bytes(s: _Seq) -> None:
    s.regs[2] = _reg(_CLEAN, sep="\n")


def _output_bytes(s: _Seq) -> None:
    s.graphs[3] = _graph(extra=1)


def _dup_id(s: _Seq) -> None:
    s.graphs[1] = _graph() + [_graph()[0]]


def _forbidden(s: _Seq) -> None:
    s.stderr[1] = "WARNING: Merge: x 'y' shares spdxId z with a w\n"


def _untagged(s: _Seq) -> None:
    s.stderr[1] = "oops\n"


def _exit(s: _Seq) -> None:
    s.rcs[1] = 1


def _pinned(s: _Seq) -> None:
    s.graphs[1] = _graph("Package-7")


def _disagree(s: _Seq) -> None:
    s.surfaces[2] = "wheel"
    s.graphs[2] = _graph("Package-7")


def _injected(s: _Seq) -> None:
    s.kinds[1] = "v2"
    s.graphs[1] = []


def _readonly(s: _Seq) -> None:
    s.kinds[1] = "readonly"
    s.regs[1] = _reg(_CLEAN, sep=" ")
    s.stderr[1] = "WARNING: ID registry: failed to save x: denied\n"


def _gen_erased(s: _Seq) -> None:
    """`id generate` drops a recorded sha256 (D12; BN)."""
    s.ops[1] = "gen"
    _erased(s)


_GATE = (
    "INFO: ID registry: content gate dropped for software_File 'pkg/a.py': "
    f"imported id {NS}File-7 replaces {NS}File-1\n"
)


def _imports_file_7(s: _Seq, info: bool = True) -> None:
    """Step 2 imports the setup's SBOM, which gave ``pkg/a.py`` the
    unhashed id File-7: the imported id wins and the sha256 goes, with the
    INFO when *info*."""
    unhashed = {"type": "software_File", "name": "pkg/a.py", "spdxId": NS + "File-7"}
    s.surfaces[0] = "model"  # not a harvester: its ids are only a source
    s.graphs[0] = [unhashed]
    s.ops[1], s.imported[1], s.graphs[1] = "import", "out/0.json", []
    s.regs[1:] = [_reg({**_CLEAN, _FILE: ("File-7", None)})] * 3
    s.graphs[2:] = [[_graph()[0], unhashed]] * 2
    s.stderr[1] = _GATE if info else ""


def _import_drop_silent(s: _Seq) -> None:
    _imports_file_7(s, info=False)


def _gate_info_off_import(s: _Seq) -> None:
    s.stderr[2] = _GATE


def _gate_info_twice(s: _Seq) -> None:
    _imports_file_7(s)
    s.stderr[1] = _GATE * 2


def _gen_readonly_old_text(s: _Seq) -> None:
    s.kinds[1], s.ops[1], s.rcs[1] = "readonly", "gen", 1
    s.stderr[1] = "ERROR: [Errno 13] Permission denied: 'reg.json'\n"


def _gen_readonly_unprefixed(s: _Seq) -> None:
    _gen_readonly_old_text(s)
    s.stderr[1] = "ERROR: failed to save reg.json: denied\n"


def _readonly_extra_error(s: _Seq) -> None:
    _readonly(s)
    s.stderr[1] += "ERROR: something else\n"


@pytest.mark.parametrize(
    ("doctor", "code"),
    [
        (_churn, "A/churn"),
        (_vanished, "A/vanished"),
        (_erased, "A/sha-erased"),
        (_swap, "A/sha-swap"),
        (_reuse, "A/reuse"),
        (_prefix, "B/prefix"),
        (_cross_type, "B/cross-type"),
        (_multi_key, "B/multi-key"),
        (_not_a_layout_alias, "B/multi-key"),
        (_layout_demoted, "A/reuse"),
        (_stem_key, "M/stem-key"),
        (_one_id_for_two_models, "M/distinct-ids"),
        (_nfd_key, "N/nfc"),
        (_wrong_case_key, "N/case"),
        (_dotdot_key, "S/dotdot"),
        (_dataset_unpinned, "S/dataset-pin"),
        (_registry_bytes, "C/registry"),
        (_output_bytes, "C/output"),
        (_exit, "D/exit"),
        (_untagged, "D/untagged"),
        (_forbidden, "D/warning"),
        (_dup_id, "D/dup-id"),
        (_disagree, "E/disagree"),
        (_pinned, "F/pinned"),
        (_injected, "H/overwritten"),
        (_readonly, "H/overwritten"),
        (_gen_erased, "A/sha-erased"),
        (_import_drop_silent, "A/sha-erased"),
        (_gate_info_off_import, "A/gate-info"),
        (_gate_info_twice, "A/gate-info"),
        (_gen_readonly_old_text, "H/message"),
        (_gen_readonly_unprefixed, "H/message"),
        (_readonly_extra_error, "H/message"),
    ],
    ids=lambda v: v if isinstance(v, str) else v.__name__,
)
def test_each_invariant_fires_on_its_doctored_step(
    mcc: dict[str, ModuleType],
    tmp_path: Path,
    doctor: Callable[[_Seq], None],
    code: str,
) -> None:
    (tmp_path / "proj" / "pkg").mkdir(parents=True)
    (tmp_path / "proj" / "pkg" / "a.py").write_bytes(b"a")
    clean = _Seq(mcc, tmp_path / "proj")
    assert clean.check() == set()  # the control: no false alarm
    doctored = _Seq(mcc, tmp_path / "proj")
    doctor(doctored)
    assert code in doctored.check()


def test_an_id_import_dropping_a_gate_with_its_info_is_clean(
    mcc: dict[str, ModuleType], tmp_path: Path
) -> None:
    """BN: the imported id wins over a gated entry and its
    sha256 goes, said once; a read-only step with the one failed-save
    line is clean too."""
    (tmp_path / "proj" / "pkg").mkdir(parents=True)
    (tmp_path / "proj" / "pkg" / "a.py").write_bytes(b"a")
    imported = _Seq(mcc, tmp_path / "proj")
    _imports_file_7(imported)
    readonly = _Seq(mcc, tmp_path / "proj")
    readonly.kinds[1], readonly.ops[1], readonly.rcs[1] = "readonly", "gen", 1
    readonly.stderr[1] = "ERROR: ID registry: failed to save reg.json: denied\n"
    assert (imported.check(), readonly.check()) == (set(), set())


def test_convergence_classes(mcc: dict[str, ModuleType]) -> None:
    classify = mcc["_checks_order"].classify
    entry = mcc["_order_capture"].Entry
    a = {_PKG: entry(NS + "Package-1", None), _FILE: entry(NS + "File-2", SHA_A)}
    renamed = {_PKG: entry(NS + "Package-3", None), _FILE: entry(NS + "File-4", SHA_A)}
    merged = {
        _PKG: entry(NS + "Package-1", None),
        _FILE: entry(NS + "Package-1", SHA_A),
    }
    other_sha = {**a, _FILE: entry(NS + "File-2", "c" * 64)}
    assert classify([a, dict(a)]) == ("order-independent", set())
    assert classify([a, renamed])[0].startswith("order-dependent (benign")
    assert classify([a, {_PKG: a[_PKG]}]) == ("VIOLATION (key sets differ)", {_FILE})
    assert classify([a, merged])[0].startswith("VIOLATION (ids not")
    assert classify([a, other_sha]) == ("VIOLATION (sha256 values differ)", {_FILE})
    gate = classify([a, other_sha], frozenset({_FILE}))
    assert gate == ("order-dependent (benign: id import dropped a content gate)", set())
    assert classify([a, other_sha], frozenset({_PKG}))[0].startswith("VIOLATION")
    assert classify([a, None])[0].startswith("VIOLATION")


def test_allow_list_names_its_item_only_for_its_case(
    mcc: dict[str, ModuleType],
) -> None:
    """Only a per-document entity's A/B finding is known: a src-layout file
    pair, once allow-listed, is a finding again."""
    violation = mcc["_order_invariants"].Violation
    known = mcc["_order_known"].known_item
    assert known(violation("A/churn", 2, "project", "Tool Pitloom", ""), "flat")
    for key in ("software_Package demo", "software_File pkg/x.py"):
        for code in ("A/churn", "F/pinned", "E/disagree", "G/key-sets-differ"):
            assert known(violation(code, 2, "wheel", key, ""), "src") is None


def test_a_promoted_layout_key_is_not_a_reuse(
    mcc: dict[str, ModuleType], tmp_path: Path
) -> None:
    """A/reuse allows only the shorter key becoming the src one."""
    (tmp_path / "proj" / "pkg").mkdir(parents=True)
    (tmp_path / "proj" / "pkg" / "a.py").write_bytes(b"a")
    promoted = _Seq(mcc, tmp_path / "proj")
    src = ("software_File", "src/pkg/a.py")
    promoted.regs[1:] = [_reg({_PKG: _CLEAN[_PKG], src: ("File-1", SHA_A)})] * 3
    assert "A/reuse" not in promoted.check()
