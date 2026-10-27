# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A Git URL from end to end: a local GitLab-style server over smart HTTP
(``git http-backend``), then every surface that takes a URL -- the library,
``generate()`` and the ``loom`` program -- reads the project it holds and
writes one SBOM.

The server is on ``127.0.0.1``, so the tests opt out of the socket block.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate, generate_git_project_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.extract.remote import RemoteSourceError
from tests._git_http_server import backend_available, make_repo, serve_git
from tests._spdx3_validate import assert_spdx3_valid

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(not backend_available(), reason="needs git http-backend"),
]

_DEMO = '[project]\nname = "demo"\nversion = "1.0"\n'
_PRETTY = "[tool.pitloom]\npretty = true\n"
_WHEN = "2026-01-01T00:00:00Z"
_FIXED = CreationMetadata(creation_datetime=_WHEN)
_AT = ["--creation-datetime", _WHEN]
#: A setuptools project whose ``MANIFEST.in`` pattern matches nothing.
_MANIFEST_PROJECT = {
    "pyproject.toml": _DEMO + '[tool.setuptools]\npackages = ["demo"]\n',
    "demo/__init__.py": "",
    "MANIFEST.in": "include *.js\n",
}


def _packages(sbom: str) -> list[str]:
    graph = json.loads(sbom)["@graph"]
    return sorted(e["name"] for e in graph if e.get("type") == "software_Package")


@pytest.fixture(name="base")
def _base(tmp_path: Path) -> Iterator[str]:
    """A GitLab-style server holding ``g/p`` (a project at its root, a
    monorepo folder ``svc/a`` and a branch ``feat/x`` with a second project),
    ``g/mono`` (projects below a root with none) and ``g/hostile`` (a project
    that sets its own ``[tool.pitloom]``)."""
    root = tmp_path / "srv"
    make_repo(
        root,
        "g/p",
        {
            "main": {
                "pyproject.toml": _DEMO,
                "svc/a/pyproject.toml": '[project]\nname = "svc-a"\nversion = "2"\n',
            },
            "feat/x": {
                "pyproject.toml": '[project]\nname = "on-feat"\nversion = "3"\n'
            },
        },
    )
    make_repo(
        root,
        "g/mono",
        {
            "main": {
                "one/pyproject.toml": _DEMO,
                "two/setup.py": "from setuptools import setup\n",
            }
        },
    )
    make_repo(root, "g/hostile", {"main": {"pyproject.toml": _DEMO + _PRETTY}})
    make_repo(root, "g/manifest", {"main": _MANIFEST_PROJECT})
    with serve_git(root, gitlab_style=True) as base:
        yield base


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ("/g/p", ["demo"]),
        ("/g/p.git", ["demo"]),
        ("/g/p/", ["demo"]),
        ("/g/p/-/tree/main/svc/a", ["svc-a"]),
        ("/g/p/-/tree/feat/x", ["on-feat"]),
        ("/g/p/-/blob/main/svc/a/pyproject.toml", ["svc-a"]),
        ("/g/p/-/tree/main?ref_type=heads#readme", ["demo"]),
    ],
    ids=[
        "bare-redirected",
        "dot-git",
        "trailing-slash",
        "gitlab-folder",
        "gitlab-branch-with-slash",
        "gitlab-file-page",
        "query-and-fragment",
    ],
)
def test_the_library_reads_the_project_a_url_names(
    base: str, page: str, expected: list[str], tmp_path: Path
) -> None:
    """The SBOM describes the project the URL names, and is valid SPDX 3."""
    out = tmp_path / "out.spdx3.json"
    sbom = generate_git_project_sbom(base + page, output_path=out)
    assert expected[0] in _packages(sbom)
    assert out.read_text(encoding="utf-8") == sbom
    assert_spdx3_valid(out)


def test_generate_reads_a_url_as_a_git_project(base: str) -> None:
    """``generate()`` classifies the URL as a Git project."""
    assert "demo" in _packages(generate(base + "/g/p"))


def test_the_address_check_sees_each_redirect_target(base: str) -> None:
    """The caller's ``check_url`` gets the redirect target, as the URL that
    would be asked next, before the clone; refusing it stops the run."""
    seen: list[str] = []
    generate_git_project_sbom(base + "/g/p", check_url=seen.append)
    assert seen == [base + "/g/p.git"]

    def refuse(url: str) -> None:
        raise RemoteSourceError("test.refused", f"refused {url}")

    with pytest.raises(RemoteSourceError, match="refused") as excinfo:
        generate_git_project_sbom(base + "/g/p", check_url=refuse)
    assert excinfo.value.code == "test.refused"


def test_a_repository_cannot_set_its_own_pitloom_settings(base: str) -> None:
    """The hostile project asks for pretty output; it is not obeyed, but a
    config the caller passes is."""
    from pitloom.core.config import PitloomConfig  # pylint: disable=C0415

    assert "\n" not in generate_git_project_sbom(base + "/g/hostile").strip()
    pretty = generate_git_project_sbom(
        base + "/g/hostile", pitloom_config=PitloomConfig(pretty=True)
    )
    assert pretty.count("\n") > 10


@pytest.mark.parametrize(
    ("page", "code"),
    [
        ("/g/missing", "git.clone-failed"),
        ("/g/p/-/tree/nope/x", "git.ref-not-found"),
        ("/g/p/-/tree/main/no/such/folder", "git.path-not-found"),
    ],
)
def test_a_refused_url_has_a_code_and_a_warning(
    base: str, page: str, code: str
) -> None:
    """Missing repository, ref or folder: each its own code."""
    with pytest.raises(RemoteSourceError) as excinfo:
        generate_git_project_sbom(base + page)
    assert excinfo.value.code == code


def test_a_monorepo_root_names_the_projects_below_it(base: str) -> None:
    """``git.no-project`` lists the folders to give a URL for."""
    with pytest.raises(RemoteSourceError) as excinfo:
        generate_git_project_sbom(base + "/g/mono")
    assert excinfo.value.code == "git.no-project"
    assert "one" in str(excinfo.value) and "two" in str(excinfo.value)
    assert "Give the URL of one of them" in str(excinfo.value)


def _loom(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pitloom", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def test_the_loom_program_reads_a_url(base: str, tmp_path: Path) -> None:
    """``loom project <url>`` and ``loom generate <url> -o``: exit 0, the SBOM
    written, the output path on stdout alone, and an ``INFO:`` for the
    redirect and one for the folder on stderr."""
    out = tmp_path / "sbom.json"
    done = _loom(
        "project", base + "/g/p/-/tree/main/svc/a", "-o", str(out), *_AT, cwd=tmp_path
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"PITLOOM_SBOM_OUTPUT_PATH={out}"
    assert "svc-a" in _packages(out.read_text(encoding="utf-8"))
    assert f"INFO: Git source: {base}/g/p redirected to {base}/g/p.git" in done.stderr
    assert "folder svc/a" in done.stderr
    assert_spdx3_valid(out)
    again = tmp_path / "again.json"
    done = _loom(
        "generate",
        base + "/g/p/-/tree/main/svc/a",
        "-o",
        str(again),
        *_AT,
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    assert again.read_text(encoding="utf-8") == out.read_text(encoding="utf-8")


def test_setuptools_manifest_lines_from_a_url_are_tagged(
    base: str, tmp_path: Path
) -> None:
    """``loom --debug project <url>`` on a setuptools project whose
    ``MANIFEST.in`` matches nothing: setuptools' bare ``warning:`` line
    arrives as one ``DEBUG:`` line; every stderr line carries a level."""
    done = subprocess.run(  # nosec B603
        [sys.executable, "-m", "pitloom", "--debug", "project", base + "/g/manifest"]
        + ["-o", str(tmp_path / "sbom.json")],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=300,
    )
    lines = done.stderr.decode("utf-8").splitlines()
    assert done.returncode == 0, lines
    tags = ("ERROR: ", "WARNING: ", "INFO: ", "DEBUG: ")
    assert [line for line in lines if not line.startswith(tags)] == []
    assert [
        line.startswith("DEBUG: ")
        for line in lines
        if line.endswith("setuptools stderr: warning: no files found matching '*.js'")
    ] == [True]


def test_every_surface_writes_the_same_sbom(base: str, tmp_path: Path) -> None:
    """The library, ``generate()``, ``loom project`` and ``loom generate``
    give the same bytes for one URL (surface parity and determinism)."""
    url = base + "/g/p/-/tree/feat/x"
    via_library = generate_git_project_sbom(url, creation_metadata=_FIXED)
    via_generate = generate(url, creation_metadata=_FIXED)
    out_a, out_b = tmp_path / "a.json", tmp_path / "b.json"
    assert _loom("project", url, "-o", str(out_a), *_AT, cwd=tmp_path).returncode == 0
    assert _loom("generate", url, "-o", str(out_b), *_AT, cwd=tmp_path).returncode == 0
    texts: list[Any] = [
        json.loads(via_library),
        json.loads(via_generate),
        json.loads(out_a.read_text(encoding="utf-8")),
        json.loads(out_b.read_text(encoding="utf-8")),
    ]
    for text in texts:  # the CLI says it made the document; the library does not
        for element in text["@graph"]:
            if element.get("type") == "CreationInfo":
                element.pop("comment", None)
    assert all(t == texts[0] for t in texts)


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (["--offline"], "network access is forbidden"),
        ([], "only http and https URLs are fetched"),
    ],
    ids=["offline", "ssh-url"],
)
def test_the_loom_program_refuses_what_it_does_not_fetch(
    base: str, tmp_path: Path, args: list[str], needle: str
) -> None:
    """A refusal is a non-zero exit, an ``ERROR:`` line saying why and a
    ``WARNING:`` too; nothing is written."""
    target = "ssh://git@host/o/r.git" if not args else base + "/g/p"
    done = _loom("project", target, "-o", str(tmp_path / "x.json"), *args, cwd=tmp_path)
    assert done.returncode == 1
    assert "ERROR: SBOM generation failed: " in done.stderr and needle in done.stderr
    assert "WARNING: Git source:" in done.stderr  # logged as well as shown
    assert not (tmp_path / "x.json").exists()


def test_a_build_flag_has_no_effect_on_a_remote_repository(
    base: str, tmp_path: Path
) -> None:
    """The build backend of a downloaded repository is never run: the flag is
    said to have no effect, once."""
    done = _loom(
        "project",
        base + "/g/p",
        "--allow-build",
        "-o",
        str(tmp_path / "o.json"),
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    assert done.stderr.count("--allow-build has no effect for a remote repository") == 1


def test_an_option_a_remote_repository_cannot_use_is_said_as_the_library_says_it(
    base: str, tmp_path: Path
) -> None:
    """The CLI names the URL, not the temporary checkout, as the library does."""
    done = _loom(
        "project",
        base + "/g/p",
        "--trust-wheel-model",
        "--project-dir",
        str(tmp_path),
        "-o",
        str(tmp_path / "o.json"),
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    warnings = [ln for ln in done.stderr.splitlines() if ln.startswith("WARNING:")]
    assert warnings and not any("pitloom-git-" in ln for ln in warnings)
    assert f"Options: {base}/g/p: --trust-wheel-model has no effect" in done.stderr
    assert "--project-dir has no effect for a remote repository" in done.stderr
