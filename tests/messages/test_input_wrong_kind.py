# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An input of the wrong kind, or one the system will not let Pitloom look
at, on every surface: a directory named ``.whl`` or ``.tar.gz``, a file
given as a fragments directory, a path under a directory without search
permission (``file-unreadable`` for the input check: see
tests/messages/test_input_unreadable.py), a missing ID registry named as
given, and a malformed or padded Hugging Face URL (``hf-url-invalid``).

See also: tests/messages/test_input_not_found_surfaces.py (a missing
input), tests/core/test_given_file.py (an SBOM file on every surface).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import (
    _generators_git,
    generate,
    generate_git_sbom,
    generate_merged_sbom,
    generate_model_sbom,
    generate_wheel_sbom,
)
from pitloom.cli.commands import _remote
from pitloom.core.config_cascade import load_config_file
from pitloom.embed import embed_sbom_in_wheel, embed_wheel_sbom
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.remote import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout
from pitloom.extract.remote.git_url import is_hub_model_url
from pitloom.extract.wheel import read_wheel
from pitloom.id_registry import resolve_registry
from pitloom.logging_config import CODE_ATTR

pytestmark = pytest.mark.platform

_WHL = "d-1.0-py3-none-any.whl"
_NOT_FILE = f"wheel file not found: '{_WHL}' is not a file"


def _loom(argv: list[str], monkeypatch: pytest.MonkeyPatch, err: Any) -> list[str]:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 1
    return [ln for ln in err.readouterr().err.splitlines() if ln.startswith("ERROR:")]


@pytest.mark.parametrize(
    "command", ["wheel", "embed-wheel", "verify-wheel", "validate-wheel"]
)
def test_a_directory_named_whl_is_not_a_wheel_file_on_the_command_line(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / _WHL).mkdir()
    assert _loom([command, _WHL], monkeypatch, capsys) == [
        f"ERROR: loom {command}: {_NOT_FILE} [input-not-found]"
    ]


_LIBRARY: dict[str, Callable[[str], object]] = {
    "generate_wheel_sbom": generate_wheel_sbom,
    "embed_wheel_sbom": embed_wheel_sbom,
    "embed_sbom_in_wheel": lambda p: embed_sbom_in_wheel(p, "{}"),
    "read_wheel": read_wheel,
}


@pytest.mark.parametrize("surface", sorted(_LIBRARY))
@pytest.mark.parametrize("given", ["missing", "directory"])
def test_the_library_raises_the_coded_error_for_a_wheel_that_is_no_file(
    surface: str, given: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    if given == "directory":
        (tmp_path / _WHL).mkdir()
    with pytest.raises(FileNotFoundError) as caught:
        _LIBRARY[surface](_WHL)
    assert str(caught.value) == (
        _NOT_FILE if given == "directory" else f"wheel file not found: '{_WHL}'"
    )
    assert getattr(caught.value, CODE_ATTR) == "input-not-found"


def test_a_directory_named_as_an_sdist_is_not_an_archive(tmp_path: Path) -> None:
    (tmp_path / "a-1.tar.gz").mkdir()
    with pytest.raises(FileNotFoundError, match=r" is not a file$") as caught:
        read_sdist(tmp_path / "a-1.tar.gz")
    assert getattr(caught.value, CODE_ATTR) == "input-not-found"


def test_a_file_given_as_the_fragments_directory_says_so_on_both_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("f.json").write_text("{}", encoding="utf-8")
    line = "fragments directory not found: 'f.json' is not a directory"
    assert _loom(["merge", "f.json"], monkeypatch, capsys) == [
        f"ERROR: loom merge: {line} [input-not-found]"
    ]
    with pytest.raises(FileNotFoundError) as caught:
        generate_merged_sbom("f.json")
    assert str(caught.value) == line
    assert getattr(caught.value, CODE_ATTR) == "input-not-found"


@pytest.mark.parametrize(
    ("argv", "line"),
    [
        (["--id-registry", "reg.json"], "'reg.json'"),
        (["--config", "c.toml"], "'sub/reg.json'"),
        (["--id-registry", "dir"], "'dir' is not a file"),
    ],
    ids=["flag", "config-key", "directory"],
)
@pytest.mark.parametrize("surface", ["project", "git"])
def test_a_missing_id_registry_is_named_as_given(
    surface: str,
    argv: list[str],
    line: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Never the absolute path it is read from: a flag as typed, a
    configuration key as written; a Git URL's checkout (stood in for by a
    local directory) changes neither."""
    monkeypatch.chdir(tmp_path)
    project = '[project]\nname = "p"\nversion = "1"\n'
    Path("pyproject.toml").write_text(project, encoding="utf-8")
    Path("c.toml").write_text(
        '[tool.pitloom]\nid-registry = "sub/reg.json"\n', encoding="utf-8"
    )
    Path("dir").mkdir()
    target, command = ".", "project"
    if surface == "git":
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        (checkout / "pyproject.toml").write_text(project, encoding="utf-8")

        @contextmanager
        def fetch(url: str, **_: object) -> Iterator[GitCheckout]:
            yield GitCheckout(str(checkout), url, None, "c", "", True)

        monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
        monkeypatch.setattr(_remote, "fetch_git_project", fetch)
        target, command = "https://gitlab.example.org/g/p", "generate"
        option: dict[str, Any] = (
            {"pitloom_config": load_config_file(Path(argv[1]))}
            if argv[0] == "--config"
            else {"id_registry": argv[1]}
        )
        with pytest.raises(FileNotFoundError) as caught:
            generate_git_sbom(target, output_path=Path("o.json"), **option)
        assert str(caught.value) == f"ID registry file not found: {line}"
    (cli,) = _loom([command, target, "-o", "o.json", *argv], monkeypatch, capsys)
    said = f"ID registry file not found: {line} [input-not-found]"
    assert cli == f"ERROR: loom {command}: {said}"
    assert str(tmp_path) not in cli


def test_the_library_names_a_relative_registry_as_given_where_it_looks(
    tmp_path: Path,
) -> None:
    """The wrong-kind probe looks where the path resolves, not under the
    current directory."""
    (tmp_path / "reg.json").mkdir()
    with pytest.raises(FileNotFoundError) as caught:
        resolve_registry("reg.json", None, tmp_path)
    assert str(caught.value) == "ID registry file not found: 'reg.json' is not a file"


@pytest.mark.parametrize(
    "url",
    [
        "https://huggingface.co/only-one-segment",
        "https://huggingface.co",
        "https://huggingface.co/",
        "HTTP://WWW.HF.CO/",
        "https://huggingface.co:8080/o/m",
        "https://u:SECRET@huggingface.co/o/m",
        " https://huggingface.co/owner\t",
    ],
    ids=["one-segment", "no-path", "root", "upper-case", "port", "userinfo", "pad"],
)
def test_a_malformed_hub_url_is_hf_url_invalid_on_every_surface(
    url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Not taken for a model file or a project path that is not found, nor
    sent by ``loom project`` to ``loom model``, which would refuse it."""
    monkeypatch.chdir(tmp_path)
    for argv in (["model", url], ["generate", url, "-o", "o.json"], ["project", url]):
        (cli,) = _loom(argv, monkeypatch, capsys)
        assert cli.endswith(
            ": not a valid Hugging Face URL or model ID [hf-url-invalid]"
        )
        assert "SECRET" not in cli
    with pytest.raises(ValueError) as caught:
        generate_model_sbom(url)
    assert getattr(caught.value, CODE_ATTR) == "hf-url-invalid"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("https://huggingface.co/o", True),
        ("https://huggingface.co/datasets/o/d", False),
        ("https://example.org/o/m", False),
        ("huggingface.co/o/m", False),
        ("https://[bad/x", False),
    ],
    ids=["model", "dataset", "other-host", "no-scheme", "bad-url"],
)
def test_is_hub_model_url(source: str, expected: bool) -> None:
    assert is_hub_model_url(source) is expected


_HUB = "https://huggingface.co/o/n"


@pytest.mark.parametrize(
    "pad", ["", "  ", "\t", "\n"], ids=["none", "space", "tab", "nl"]
)
def test_a_padded_hub_url_or_id_is_read_alike_on_every_surface(
    pad: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every route takes the model ``o/n`` (offline: refused only for the
    fetch it would make), and ``loom project`` names it a model; never
    ``hf-url-invalid``."""
    monkeypatch.chdir(tmp_path)
    for target in (f"{pad}{_HUB}{pad}", f"{pad}o/n{pad}"):
        for argv in (["model", target], ["generate", target, "-o", "o.json"]):
            (cli,) = _loom([*argv, "--offline"], monkeypatch, capsys)
            assert cli.endswith(" [offline-unusable]"), cli
            assert "https://huggingface.co/o/n" in cli
        for call in (generate_model_sbom, generate):
            with pytest.raises(RemoteSourceError) as caught:
                call(target, offline=True)
            assert getattr(caught.value, CODE_ATTR) == "offline-unusable"
    (cli,) = _loom(["project", f"{pad}{_HUB}{pad}"], monkeypatch, capsys)
    assert cli == (
        f"ERROR: loom project: URL={_HUB}: a Hugging Face model, not a project; "
        "use 'loom model' [target-wrong-format]"
    )
