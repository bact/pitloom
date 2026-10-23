# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The library entry points for a Git URL: ``generate()`` classifies it,
``generate_git_project_sbom()`` fetches and reads it.

The fetch is stood in for by a prepared directory; see
``tests/extract/remote/test_git_http_e2e.py`` for a real (local) server.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import (
    _generators_git,
    generate,
    generate_git_project_sbom,
    target_is_git_url,
    target_resolves_to_project,
)
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.extract.remote import RemoteSourceError
from pitloom.extract.remote.git import CONFIG_IGNORED_INFO, GitCheckout
from pitloom.id_registry import IdRegistry

_URL = "https://gitlab.example.org/g/p"


@pytest.fixture(name="seen")
def _seen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Stand in for the fetch with a project directory; records the call."""
    folder = tmp_path / "checkout"
    folder.mkdir()
    (folder / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n[tool.pitloom]\npretty = true\n',
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    @contextmanager
    def fetch(
        url: str,
        *,
        check_url: object = None,
        offline: bool | None = None,
        max_bytes: int | None = None,
    ) -> Iterator[GitCheckout]:
        seen.update(url=url, check_url=check_url, offline=offline, max_bytes=max_bytes)
        yield GitCheckout(str(folder), url, None, "c", "", True)

    monkeypatch.setattr(_generators_git, "fetch_git_project", fetch)
    return seen


@pytest.mark.parametrize(
    ("target", "is_git", "is_project"),
    [
        (_URL, True, False),
        ("http://127.0.0.1:3000/o/r", True, False),
        ("ssh://git@host/o/r.git", True, False),
        ("git@host:o/r.git", True, False),
        ("https://huggingface.co/o/m", False, False),
        (".", False, True),
    ],
)
def test_a_url_is_classified_as_a_git_project(
    target: str, is_git: bool, is_project: bool
) -> None:
    """An http(s) URL, and an address that is remote but not fetched (so it
    is refused, not mistaken for a missing directory), are Git targets."""
    assert target_is_git_url(target) is is_git
    assert target_resolves_to_project(target) is is_project


@pytest.mark.skipif(
    sys.platform == "win32", reason="a colon is not valid in a Windows file name"
)
def test_an_existing_path_is_never_a_git_target(tmp_path: Path) -> None:
    """A directory that looks like ``user@host:path`` is a path."""
    path = tmp_path / "a@b:c"
    path.mkdir()
    assert not target_is_git_url(str(path))


def test_the_repositorys_own_settings_are_ignored_unless_the_caller_gives_some(
    seen: dict[str, object], caplog: pytest.LogCaptureFixture
) -> None:
    """The repository asks for pretty output: not obeyed, said once in an
    ``INFO:``; a ``pitloom_config`` is the caller's and is."""
    with caplog.at_level(logging.INFO):
        compact = generate_git_project_sbom(_URL)
    assert "\n" not in compact.strip()
    assert [r.getMessage() for r in caplog.records].count(CONFIG_IGNORED_INFO) == 1
    caplog.clear()
    with caplog.at_level(logging.INFO):
        pretty = generate_git_project_sbom(
            _URL, pitloom_config=PitloomConfig(pretty=True)
        )
    assert pretty.count("\n") > 10 and CONFIG_IGNORED_INFO not in caplog.text
    assert seen["url"] == _URL


def test_generate_passes_the_address_check_and_offline_to_the_fetch(
    seen: dict[str, object],
) -> None:
    """``check_url`` and ``offline`` reach the fetch; the output goes to the
    file and is returned."""

    def check(_url: str) -> None:
        """A caller's address check."""

    generate(_URL, check_url=check, offline=False)
    assert seen["check_url"] is check and seen["offline"] is False


@pytest.mark.parametrize("given", [1234, None])
def test_the_clone_size_cap_reaches_the_fetch(
    seen: dict[str, object], given: int | None
) -> None:
    generate_git_project_sbom(_URL, max_clone_bytes=given)
    assert seen["max_bytes"] == given


def test_an_option_a_remote_repository_cannot_use_warns_once(
    seen: dict[str, object], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``trust_wheel_model`` and ``project_dir`` have no effect on a remote
    repository, and a build flag never runs its backend: each is one
    ``WARNING:``, never a silent drop."""
    with caplog.at_level(logging.WARNING):
        generate(
            _URL,
            trust_wheel_model=True,
            project_dir=tmp_path,
            build_options=BuildOptions(allow=True),
        )
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert text.count("--trust-wheel-model has no effect for this target") == 1
    assert text.count("--project-dir has no effect for a remote repository") == 1
    assert text.count("--allow-build has no effect for a remote repository") == 1
    assert seen["url"] == _URL


def test_a_relative_id_registry_means_the_callers_directory(
    seen: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The checkout is a temporary directory: a relative registry path is made
    absolute against the caller's, so the registry is not looked for (or
    created) inside the checkout."""
    monkeypatch.chdir(tmp_path)
    given: dict[str, Any] = {}

    def fake(_folder: str, **kwargs: object) -> str:
        given.update(kwargs)
        return "{}"

    monkeypatch.setattr(_generators_git, "generate_project_sbom", fake)
    generate_git_project_sbom(_URL, id_registry="ids.json")
    assert given["id_registry"] == tmp_path / "ids.json"
    assert seen["url"] == _URL
    registry = IdRegistry.__new__(IdRegistry)
    generate_git_project_sbom(_URL, id_registry=registry)  # an object is kept
    assert given["id_registry"] is registry


def test_a_refused_url_is_raised_with_its_code() -> None:
    """The library surface raises ``RemoteSourceError``; nothing is written."""
    with pytest.raises(RemoteSourceError) as excinfo:
        generate_git_project_sbom("ssh://git@host/o/r.git")
    assert excinfo.value.code == "git.url-invalid"
