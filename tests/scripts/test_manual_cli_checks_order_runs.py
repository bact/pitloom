# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Order-matrix checks that run generated scripts: a retrain step writes
new model bytes, the scripts parse, walks replay, and a deliberately
broken registry lookup in a real run is caught.

See also: ``test_manual_cli_checks_order.py`` (the invariants); the ``mcc``
fixture is in ``conftest.py``.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

from tests.build_and_read_shared import pitloom_subprocess_env

_POSIX_SH = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh scripts")


def test_retrain_script_writes_model_bytes(
    mcc: dict[str, ModuleType], tmp_path: Path
) -> None:
    fx = mcc["_order_fixtures"]
    target = tmp_path / "m.safetensors"
    subprocess.run([sys.executable, "-c", fx.RETRAIN_PY, str(target), "7"], check=True)
    assert target.read_bytes() == fx.model_bytes(7)
    assert fx.model_bytes(7) != fx.model_bytes(0)


@_POSIX_SH
def test_scripts_parse_and_walks_replay(
    mcc: dict[str, ModuleType], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gen = mcc["_order_gen"]
    profile = mcc["_order_fixtures"].PROFILES["flat"]
    every_op = tuple(op for op in mcc["_order_ops"].OPS if op != "import0")
    seqs = [
        gen.plan("all", profile, ("gen",), every_op + ("v2:project", "readonly:train")),
        *gen.walks(profile, 0, 2),
    ]
    for i, seq in enumerate(seqs):
        script = tmp_path / f"s{i}.sh"
        script.write_text(gen.render(seq, "O-test", sys.executable), encoding="utf-8")
        subprocess.run(["sh", "-n", str(script)], check=True)
        if shutil.which("shellcheck"):
            subprocess.run(["shellcheck", "-x", str(script)], check=True)
    assert [s.ops for s in gen.walks(profile, 0, 3)] == [s.ops for s in seqs[1:]] + [
        gen.walks(profile, 2, 1)[0].ops
    ]
    monkeypatch.setenv("PITLOOM_ORDER_SEED", "1")
    assert [s.ops for s in gen.walks(profile, 0, 2)] != [s.ops for s in seqs[1:]]


_BROKEN_LOOKUP = """\
from pitloom.id_registry import _registry
_registry.IdRegistry.lookup = lambda self, type_name, names, *, sha256=None: None
"""


@_POSIX_SH
@pytest.mark.parametrize("broken", [False, True], ids=["clean", "lookup-misses"])
def test_a_real_run_catches_a_broken_lookup(
    mcc: dict[str, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    broken: bool,
) -> None:
    """Every registry lookup missing (a shim the scripts' interpreter loads
    first) must break A and F; the same run without it breaks nothing."""
    env = pitloom_subprocess_env()
    if broken:
        shim = tmp_path / "shim"
        shim.mkdir()
        (shim / "sitecustomize.py").write_text(_BROKEN_LOOKUP, encoding="utf-8")
        env["PYTHONPATH"] = os.pathsep.join([str(shim), env["PYTHONPATH"]])
    for name in ("PYTHONPATH", "PITLOOM_DEBUG"):
        monkeypatch.delenv(name, raising=False)
        if name in env:
            monkeypatch.setenv(name, env[name])
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    profile = mcc["_order_fixtures"].PROFILES["flat"]
    seq = mcc["_order_gen"].plan("t", profile, ("gen",), ("project", "project"))
    ctx = mcc["_harness"].Context(work=tmp_path / "work", network=False, verbose=False)
    ctx.work.mkdir()
    # pylint: disable-next=protected-access
    outcome = mcc["_checks_order"]._execute(ctx, "O-test", seq, 0)
    codes = {v.code for v in outcome.violations}
    if broken:
        assert {"A/churn", "F/pinned"} <= codes
        assert outcome.repro is not None
        assert (outcome.repro / "seq.sh").is_file()
        assert (outcome.repro / "fixture" / "pyproject.toml").is_file()
    else:
        assert not codes, outcome.violations
        assert outcome.stats["F"] > 0  # the clean run did compare ids
