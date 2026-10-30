# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A file whose POSIX name is not UTF-8 (``b"\\xff.py"``, which Python reads
as ``"\\udcff.py"``) gives an SBOM on every surface that reads a project or a
dataset: the command line's ``project`` and ``generate``, the library on a
directory and on an sdist, the Hatchling build hook and a loom dataset. Its
name is written as text (``\\udcff``, six ASCII characters), with one
``WARNING:``, the SBOM validates and two runs write the same bytes.

See also: tests/assemble/test_lone_surrogates.py (a lone surrogate read from
a model's metadata), tests/core/test_untrusted_text.py (the escape).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io
import json
import logging
import os
import subprocess  # nosec B404
import sys
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata
from tests._spdx3_validate import assert_spdx3_valid
from tests.extract.conftest import make_hook, staged_sbom, write_pyproject
from tests.warning_helpers import logged_warnings

#: Windows names are UTF-16: no file name there reads as a lone surrogate.
_POSIX = sys.platform != "win32"
pytestmark = pytest.mark.skipif(not _POSIX, reason="non-UTF-8 POSIX file name")

_SRC = str(Path(__file__).resolve().parents[1] / "src")
_RAW = b"m-\xff.py"
_NAME = os.fsdecode(_RAW) if _POSIX else "m-\udcff.py"
#: The name as the SBOM holds it: the surrogate as six ASCII characters.
_SHOWN = "m-\\udcff.py"
_WHEN = "2026-01-01T00:00:00Z"
_WARNING = ": lone surrogates written as \\uXXXX"


def _demo(root: Path) -> Path:
    """A hatchling project ``testpkg`` whose package holds a non-UTF-8 name;
    skipped where the file system refuses one (APFS may)."""
    package = root / "testpkg"
    package.mkdir(parents=True)
    write_pyproject(root)
    (package / "__init__.py").write_bytes(b"")
    try:
        (package / _NAME).write_bytes(b"x = 1\n")
    except OSError:
        pytest.skip("the file system refuses a non-UTF-8 file name")
    return root


def _cli(root: Path, out: Path, subcommand: str) -> str:
    """``loom <subcommand>`` in a child process; its stderr, bytes decoded."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [_SRC, env.get("PYTHONPATH")]))
    args = [subcommand, str(root), "-o", str(out), "--creation-datetime", _WHEN]
    done = subprocess.run(  # nosec B603
        [sys.executable, "-m", "pitloom", *args],
        env=env,
        capture_output=True,
        check=False,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr
    return done.stderr.decode("utf-8")


def _cli_surface(subcommand: str) -> Callable[[Path, Path, Any], str]:
    def run(root: Path, out: Path, caplog: Any) -> str:
        del caplog
        return _cli(_demo(root), out, subcommand)

    return run


def _library(root: Path, out: Path, caplog: Any) -> str:
    del caplog
    generate_project_sbom(_demo(root), output_path=out, offline=True)
    return ""


def _sdist(root: Path, out: Path, caplog: Any) -> str:
    """The library on an sdist whose member name is not UTF-8."""
    del caplog
    root.mkdir()
    archive = root / "testpkg-0.1.0.tar.gz"
    members = {
        "PKG-INFO": b"Metadata-Version: 2.1\nName: testpkg\nVersion: 0.1.0\n",
        "pyproject.toml": b'[project]\nname = "testpkg"\nversion = "0.1.0"\n',
        "testpkg/__init__.py": b"",
        f"testpkg/{_NAME}": b"x = 1\n",
    }
    with tarfile.open(archive, "w:gz", errors="surrogateescape") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(f"testpkg-0.1.0/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    generate_project_sbom(archive, output_path=out, offline=True)
    return ""


def _hook(root: Path, out: Path, caplog: Any) -> str:
    del caplog
    build_data: dict[str, Any] = {}
    hook = make_hook(str(_demo(root)), {})
    hook.initialize("standard", build_data)
    staged = staged_sbom(build_data)
    assert staged is not None
    out.write_bytes(staged.read_bytes())
    hook.finalize("standard", build_data, "")
    return ""


_SURFACES: dict[str, Callable[[Path, Path, Any], str]] = {
    "cli-project": _cli_surface("project"),
    "cli-generate": _cli_surface("generate"),
    "library": _library,
    "library-sdist": _sdist,
    "hook": _hook,
}


def _names(sbom: Path) -> list[str]:
    graph = json.loads(sbom.read_bytes())["@graph"]
    return [e["name"] for e in graph if "name" in e and "udcff" in e["name"]]


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_a_non_utf8_file_name_is_written_as_text(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    monkeypatch.chdir(tmp_path)
    run = _SURFACES[surface]
    outs = [tmp_path / f"out{n}.spdx3.json" for n in (1, 2)]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        stderr = run(tmp_path / "one", outs[0], caplog)
    said = [line for line in stderr.splitlines() if _WARNING in line]
    said += [m for m in logged_warnings(caplog) if _WARNING in m]
    run(tmp_path / "two", outs[1], caplog)

    (name,) = _names(outs[0])
    assert name.endswith(f"/{_SHOWN}") and name.isascii()
    assert said == [f"{'WARNING: ' if stderr else ''}FILE='{name}'{_WARNING}"]
    assert_spdx3_valid(outs[0])
    assert outs[0].read_bytes() == outs[1].read_bytes()


def test_a_loom_dataset_named_so_is_written_as_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    try:
        Path(_NAME).write_bytes(b"a,b\n1,2\n")
    except OSError:
        pytest.skip("the file system refuses a non-UTF-8 file name")
    out = tmp_path / "fragment.spdx3.json"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(out, creation_metadata=CreationMetadata(creation_datetime=_WHEN)):
            loom.add_dataset(_NAME)

    said = [m for m in logged_warnings(caplog) if _WARNING in m]
    assert said == [f"FILE='{_SHOWN}'{_WARNING}"]
    assert set(_names(out)) == {_SHOWN}
    assert_spdx3_valid(out)
