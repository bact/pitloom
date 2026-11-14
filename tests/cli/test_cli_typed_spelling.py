# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A URL or path typed where a command reads a local path is named as typed
(a URL's ``//`` kept, its credentials masked) in the ``input-not-found``
and ``target-wrong-format`` lines of every command that takes one: the
argument keeps its spelling (:class:`pitloom.core.given_path.TypedPath`).

See also: tests/core/test_given_path.py, tests/messages/test_hub_target_refusal.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from tests.assemble.conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform

_WHL = "https://example.com/x-1-py3-none-any.whl"
_JSON = "https://example.com/x.json"
_W = "demo_pkg-1.0.0-py3-none-any.whl"
_PYPROJECT = b'[project]\nname = "p"\nversion = "1"\n'


def _gone(kind: str) -> str:
    """The line naming the missing ``gone//...`` input of *kind* as typed."""
    return f"{kind} not found: 'gone//"


def _error(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, err: pytest.CaptureFixture[str]
) -> str:
    """The one ``ERROR:`` line of ``loom <argv>``, which exits 1."""
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 1
    (line,) = [
        text for text in err.readouterr().err.splitlines() if text.startswith("ERROR")
    ]
    return line


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (["wheel", _WHL], f"wheel file not found: '{_WHL}' [input-not-found]"),
        (["verify-wheel", _WHL], f"wheel file not found: '{_WHL}' [input-not-found]"),
        (
            ["validate-wheel", _WHL],
            f"wheel file not found: '{_WHL}' [input-not-found]",
        ),
        (["embed-wheel", _WHL], f"wheel file not found: '{_WHL}' [input-not-found]"),
        (
            ["generate", _WHL, "-o", "o.json"],
            f"wheel file not found: '{_WHL}' [input-not-found]",
        ),
        (
            ["wheel", "https://huggingface.co/o/m"],
            "FILE=https://huggingface.co/o/m: not a .whl file [target-wrong-format]",
        ),
        (
            ["merge", "https://example.com/d"],
            "fragments directory not found: 'https://example.com/d' [input-not-found]",
        ),
        (
            ["fragment", "validate", _JSON],
            f"SBOM file not found: '{_JSON}' [input-not-found]",
        ),
        (["id", "import", _JSON], f"SBOM file not found: '{_JSON}' [input-not-found]"),
        (
            ["project", "gone//dir"],
            "project directory not found: 'gone//dir' [input-not-found]",
        ),
        (
            ["merge", "gone//dir"],
            "fragments directory not found: 'gone//dir' [input-not-found]",
        ),
        (["project", "p", "--id-registry", "gone//r.json"], _gone("ID registry file")),
        (["project", "p", "--config", "gone//c.toml"], _gone("config file")),
        (["wheel", _W, "--project-dir", "gone//d"], _gone("project directory")),
        (["id", "generate", "..//x", "-o", "r.json"], "PATH '..//x' is outside"),
        (
            ["id", "generate", "--project-dir", "p//", "..//x", "-o", "r.json"],
            "PATH '..//x' is outside --project-dir 'p//'",
        ),
        (["id", "generate", "--project-dir", "gone//d"], _gone("project directory")),
        (
            ["id", "import", "s.json", "--project-dir", "gone//d"],
            _gone("project directory"),
        ),
        (["enrich", "s.json", "--project-dir", "gone//d"], _gone("project path")),
        (["fragment", "list", "--project-dir", "gone//d"], _gone("project directory")),
        (["embed-wheel", _W, "--sbom", "gone//d"], _gone("SBOM file")),
        (["generate", "gone//d", "-o", "o.json"], _gone("project path")),
        (
            ["generate", "p.WHL//", "-o", "o.json"],
            "FILE=p.WHL//: not a .whl file [target-wrong-format]",
        ),
    ],
    ids=[
        "wheel",
        "verify-wheel",
        "validate-wheel",
        "embed-wheel",
        "generate",
        "wheel-hub",
        "merge",
        "fragment-validate",
        "id-import",
        "project-path",
        "merge-path",
        "id-registry",
        "config",
        "archive-project-dir",
        "id-generate-paths",
        "id-generate-outside-project-dir",
        "id-generate-project-dir",
        "id-import-project-dir",
        "enrich-project-dir",
        "fragment-list-project-dir",
        "embed-wheel-sbom",
        "generate-path",
        "generate-not-a-wheel",
    ],
)
def test_a_target_is_named_as_typed(
    argv: list[str],
    said: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    for project in ("p", "p.WHL"):  # a project named like a wheel is refused
        (tmp_path / project).mkdir()
        (tmp_path / project / "pyproject.toml").write_bytes(_PYPROJECT)
    (tmp_path / "s.json").write_bytes(b"{}")
    _make_dummy_wheel(tmp_path)
    assert f": {said}" in _error(argv, monkeypatch, capsys)


def test_the_library_names_a_project_path_as_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match=r"^project path not found: 'gone//d'$"):
        generate_project_sbom("gone//d", offline=True)


def test_embed_wheel_names_a_project_dir_as_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _make_dummy_wheel(tmp_path)
    line = _error(
        ["embed-wheel", str(wheel), "--project-dir", "https://example.com/p"],
        monkeypatch,
        capsys,
    )
    assert line.endswith(
        ": project directory not found: 'https://example.com/p' [input-not-found]"
    )


@pytest.mark.parametrize(
    ("typed", "said"),
    [
        (
            "ftp://user:SECRET@h/x-1-py3-none-any.whl",
            "wheel file not found: 'ftp://***:***@h/x-1-py3-none-any.whl' "
            "[input-not-found]",
        ),
        (
            "https://h/x-1-py3-none-any.whl?token=SECRET",
            "FILE=https://h/x-1-py3-none-any.whl?token=***: not a .whl file "
            "[target-wrong-format]",
        ),
        (
            "https://user:SECRET@h/x",
            "FILE=https://***:***@h/x: not a .whl file [target-wrong-format]",
        ),
        (
            "C:\\dir\\x-1-py3-none-any.whl",
            "wheel file not found: 'C:\\dir\\x-1-py3-none-any.whl' [input-not-found]",
        ),
    ],
    ids=["userinfo", "query-token", "userinfo-not-wheel", "windows-path"],
)
def test_a_wheel_url_is_masked_and_a_windows_path_kept(
    typed: str,
    said: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    line = _error(["wheel", typed], monkeypatch, capsys)
    assert line == f"ERROR: loom wheel: {said}"
    assert "SECRET" not in line


@pytest.mark.parametrize(
    "typed",
    ["{w}/", "./{w}", "d//{w}"],
    ids=["trailing-slash", "dot-slash", "double-slash"],
)
def test_a_wheel_spelling_reads_alike_from_the_cli_and_the_library(
    typed: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom wheel`` and ``generate_wheel_sbom`` both read the wheel for a
    spelling :class:`pathlib.Path` normalises, each writing the SBOM it
    writes for the plain spelling."""
    wheel = _make_dummy_wheel(tmp_path / "d")
    monkeypatch.chdir(tmp_path if typed.startswith("d") else tmp_path / "d")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    plain = str(Path(typed.format(w=wheel.name)))
    for spelling, out in ((typed.format(w=wheel.name), "typed"), (plain, "plain")):
        monkeypatch.setattr(sys, "argv", ["loom", "wheel", spelling, "-o", out])
        assert __main__.main() == 0, capsys.readouterr().err
    assert Path("typed").read_bytes() == Path("plain").read_bytes()
    assert generate_wheel_sbom(typed.format(w=wheel.name)) == generate_wheel_sbom(plain)


def test_generate_refuses_a_non_wheel_name_before_settling_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``x.WHL`` is refused at once: no option is settled for a target that
    is never read, so the one line is all ``stderr`` says."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["loom", "generate", "d//x.WHL", "-o", "o", "--allow-build"]
    )
    assert __main__.main() == 1
    assert capsys.readouterr().err.splitlines() == [
        "ERROR: loom generate: FILE=d//x.WHL: not a .whl file [target-wrong-format]"
    ]


@pytest.mark.skipif(
    sys.platform == "win32", reason="a colon in a path component is not a name"
)
def test_id_generate_names_a_missing_path_as_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The warning for a PATH that is not there names it as typed, a URL in
    it without its credentials, not the absolute path it was read as."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "p").mkdir()
    typed = "p/https://u:SECRET@h/x.txt"
    argv = ["id", "generate", "--project-dir", "p", "--id-registry", "r.json"]
    monkeypatch.setattr(sys, "argv", ["loom", *argv, typed])
    assert __main__.main() == 0
    err = capsys.readouterr().err
    assert (
        "WARNING: ID registry: path not found, skipping: 'p/https://***:***@h/x.txt'\n"
    ) in err
    assert "SECRET" not in err
