# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A relative path with the current directory gone: the one coded
``file-unreadable`` ``DIR=.`` line
(:func:`pitloom.core.current_dir.absolute_path`, and the input probe for a
relative path not there), never a bare ``FileNotFoundError``; an absolute
path still never reads the current directory.

See also: tests/core/test_current_dir.py (the current directory gone with
the default target or absolute paths).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble import generate_git_sbom, generate_project_sbom
from pitloom.core import current_dir
from pitloom.embed import embed_sbom_in_wheel, embed_wheel_sbom
from pitloom.id_registry import IdRegistry, registry_copy, resolve_registry
from pitloom.messages import code_of
from pitloom.messages.targets import is_input_file
from tests._loom_child import coded_lines, run_loom
from tests._wheel_fixtures import make_wheel

#: Windows cannot remove a process's current directory.
_CANNOT_REMOVE_CWD = sys.platform == "win32"

pytestmark = [
    pytest.mark.platform,
    pytest.mark.skipif(_CANNOT_REMOVE_CWD, reason="Windows cannot remove the cwd"),
]

_SAID = "DIR=.: could not read for resolving relative paths; "
_WHEEL = "{abs}/demo-1.0-py3-none-any.whl"
#: Run first in the child: its current directory is removed before ``loom``
#: builds its parser.
_REMOVE_CWD = "import os\nos.rmdir(os.getcwd())\n"


def _no_fetch(url: str) -> None:
    raise AssertionError(f"fetched {url}")


@pytest.fixture(name="gone_cwd")
def _gone_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An absolute directory that exists, the current directory removed."""
    kept = tmp_path / "abs"
    kept.mkdir()
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    return kept


_ABS_OUT = ["-o", "{abs}/out.json"]
_NPY = str(
    Path(__file__).parent / "fixtures" / "aimodels" / "numpy" / "example-model-v1.npy"
)


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(
            ["id", "generate", "--project-dir", "proj", "-o", "{abs}/r.json"],
            id="id-gen-dir",
        ),
        pytest.param(
            ["id", "generate", "--project-dir", "{abs}", "-o", "r.json"],
            id="id-gen-registry",
        ),
        pytest.param(
            ["id", "generate", "--project-dir", "{abs}", "-o", "{abs}/r.json", "x"],
            id="id-gen-path",
        ),
        pytest.param(
            ["id", "import", "s.json", "-o", "{abs}/r.json"], id="id-imp-sbom"
        ),
        pytest.param(
            ["id", "import", "{abs}/s.json", "--project-dir", "proj", "-o", "r.json"],
            id="id-imp-dir",
        ),
        pytest.param(
            ["embed-wheel", _WHEEL, "--project-dir", "proj", "-o", "{abs}/o.whl"],
            id="embed-dir",
        ),
        pytest.param(
            ["embed-wheel", _WHEEL, "--id-registry", "r.json", "-o", "{abs}/o.whl"],
            id="embed-registry",
        ),
        pytest.param(["embed-wheel", "x.whl", "-o", "{abs}/o.whl"], id="embed-wheel"),
        pytest.param(["verify-wheel", "x.whl"], id="verify-wheel"),
        pytest.param(["validate-wheel", "x.whl"], id="validate-wheel"),
        pytest.param(["wheel", "x.whl", *_ABS_OUT], id="wheel"),
        pytest.param(["project", "proj", *_ABS_OUT], id="project"),
        pytest.param(["project", ".", *_ABS_OUT], id="project-dot"),
        pytest.param(["generate", "proj", *_ABS_OUT], id="generate"),
        pytest.param(["merge", "frags", *_ABS_OUT], id="merge"),
        pytest.param(["enrich", "m.npy", *_ABS_OUT], id="enrich"),
        pytest.param(["fragment", "list", "--project-dir", "proj"], id="fragment"),
        pytest.param(["env", "--id-registry", "r.json", *_ABS_OUT], id="env-registry"),
        # the work is done, then the write: the cause, not a failed write
        pytest.param(["model", _NPY, "-o", "o.json"], id="model-output"),
    ],
)
def test_cli_relative_path_with_cwd_gone(argv: list[str], tmp_path: Path) -> None:
    """One coded line, no traceback, exit 1."""
    make_wheel(tmp_path / "abs")
    (tmp_path / "abs" / "s.json").write_bytes(b"{}")
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(_REMOVE_CWD, encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    args = [a.replace("{abs}", str(tmp_path / "abs")) for a in argv]
    done = run_loom(args, cwd, path=[shim])
    assert not cwd.exists()  # the shim ran
    assert b"Traceback" not in done.stderr
    assert done.returncode == 1
    lines = coded_lines(done.stderr)
    assert list(lines.values()) == ["file-unreadable"]
    assert _SAID in next(iter(lines))


@pytest.mark.parametrize(
    "call",
    [
        lambda kept: embed_wheel_sbom(
            make_wheel(kept), project_dir="proj", output_path=kept / "o.whl"
        ),
        lambda _kept: resolve_registry("reg.json", None, Path("proj")),
        lambda kept: registry_copy(
            IdRegistry(
                "https://spdx.org/spdxdocs/test-1",
                path=Path("reg.json"),
                project_root=kept,
            )
        ),
        lambda _kept: generate_project_sbom("proj"),
        lambda _kept: generate_project_sbom("."),
        lambda kept: embed_wheel_sbom("x.whl", output_path=kept / "o.whl"),
        lambda _kept: embed_sbom_in_wheel("x.whl", "{}"),
        lambda _kept: generate_git_sbom(
            "https://127.0.0.1:9/o/r.git", id_registry="r.json", check_url=_no_fetch
        ),
        lambda _kept: IdRegistry("https://spdx.org/spdxdocs/test-1").save(
            Path("r.json")
        ),
        lambda _kept: write_sbom_output("{}", "o.json"),
        # Looked up when called: one name, not an import of the module.
        lambda _kept: current_dir.absolute_path("x"),
    ],
    ids=[
        "embed-project-dir",
        "registry-base-dir",
        "registry-copy",
        "project-path",
        "project-dot",
        "embed-wheel",
        "embed-sbom",
        "git-registry",
        "registry-save",
        "sbom-write",
        "absolute-path",
    ],
)
def test_library_relative_path_with_cwd_gone(
    call: Callable[[Path], object], gone_cwd: Path
) -> None:
    """The coded error, not the bare one: a relative project path says the
    current directory is gone, not that the project is not found."""
    with pytest.raises(ValueError, match="^" + _SAID) as caught:
        call(gone_cwd)
    assert code_of(caught.value) == "file-unreadable"


def test_absolute_path_reads_no_cwd(gone_cwd: Path) -> None:
    """An absolute path, there or not, never reads the current directory."""
    assert current_dir.absolute_path(gone_cwd) == gone_cwd
    assert not is_input_file(gone_cwd / "missing.json")
