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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import pytest

from pitloom.assemble import (
    _classify_target,
    _generators_git,
    generate,
    generate_git_project_sbom,
    generate_git_sbom,
    target_is_git_url,
    target_resolves_to_project,
)
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.given_path import given_spelling
from pitloom.core.model_extract_limit import DEFAULT_MAX_DOWNLOAD_BYTES
from pitloom.extract.remote import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import CODE_ATTR
from pitloom.messages.targets import CONFIG_UNSAFE

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
        policy: RemoteFetchPolicy = RemoteFetchPolicy(),
        trust_model_files: bool = False,
    ) -> Iterator[GitCheckout]:
        seen.update(
            url=url,
            check_url=policy.check_url,
            offline=policy.offline,
            max_bytes=policy.max_bytes,
            trust_model_files=trust_model_files,
        )
        yield GitCheckout(
            str(folder), url, None, "c", "", True, trust_model_files=trust_model_files
        )

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
        ("https://huggingface.co/spaces/o/app", True, False),
        ("https://huggingface.co/datasets/o/data/tree/main", True, False),
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
    said = [r for r in caplog.records if getattr(r, CODE_ATTR, None) == "config-unsafe"]
    assert [r.getMessage() for r in said] == [CONFIG_UNSAFE.lines[0].template]
    caplog.clear()
    with caplog.at_level(logging.INFO):
        pretty = generate_git_project_sbom(
            _URL, pitloom_config=PitloomConfig(pretty=True)
        )
    assert pretty.count("\n") > 10 and "[tool.pitloom]" not in caplog.text
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


@pytest.mark.parametrize(
    ("given", "configured", "expected"),
    [
        (None, None, DEFAULT_MAX_DOWNLOAD_BYTES),
        (None, 1000, 1000),
        (2000, 1000, 2000),
        (2000, None, 2000),
    ],
    ids=["default", "config", "argument-beats-config", "argument"],
)
@pytest.mark.parametrize("call", [generate_git_project_sbom, generate])
def test_the_download_cap_cascades_to_the_fetch(
    seen: dict[str, object],
    call: Callable[..., str],
    given: int | None,
    configured: int | None,
    expected: int,
) -> None:
    """``max_download_bytes`` > the explicit config's > 512 MiB, never
    unlimited, on every library route to a Git URL."""
    config = (
        None if configured is None else PitloomConfig(max_download_bytes=configured)
    )
    call(_URL, max_download_bytes=given, pitloom_config=config)
    assert seen["max_bytes"] == expected


@pytest.mark.parametrize("bad", [0, -1, True, 1.5], ids=repr)
@pytest.mark.parametrize("call", [generate_git_project_sbom, generate])
def test_an_invalid_download_cap_is_refused_before_the_fetch(
    seen: dict[str, object], call: Callable[..., str], bad: object
) -> None:
    with pytest.raises(ValueError, match="max.download.bytes"):
        call(_URL, max_download_bytes=bad)
    with pytest.raises(ValueError, match="max.download.bytes"):
        call(_URL, pitloom_config=PitloomConfig(max_download_bytes=cast(int, bad)))
    assert "max_bytes" not in seen


def test_an_option_a_remote_repository_cannot_use_warns_once(
    seen: dict[str, object], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``max_model_extract_bytes`` and ``project_dir`` have no effect on a remote
    repository, and a build flag never runs its backend: each is one
    ``WARNING:``, never a silent drop."""
    with caplog.at_level(logging.WARNING):
        generate(
            _URL,
            max_model_extract_bytes=1024,
            project_dir=tmp_path,
            build_options=BuildOptions(allow=True),
        )
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert text.count("--max-model-extract-bytes has no effect for this target") == 1
    assert text.count("--project-dir has no effect for a remote repository") == 1
    assert text.count("--allow-build has no effect for a remote repository") == 1
    assert seen["url"] == _URL


@pytest.mark.parametrize("given", [True, False, None])
@pytest.mark.parametrize(
    "route", ["generate", "generate_git_sbom", "generate_git_project_sbom"]
)
def test_trust_model_files_reaches_the_fetch_on_every_route(
    seen: dict[str, object], route: str, given: bool | None
) -> None:
    """Only an explicit ``True`` vouches for the repository's model files."""
    routes: dict[str, Callable[..., str]] = {
        "generate": generate,
        "generate_git_sbom": generate_git_sbom,
        "generate_git_project_sbom": generate_git_project_sbom,
    }
    routes[route](_URL, trust_model_files=given)
    assert seen["trust_model_files"] is (given is True)


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
    # Read there, named as given.
    assert Path(given["id_registry"]) == tmp_path / "ids.json"
    assert given_spelling(given["id_registry"]) == "ids.json"
    assert seen["url"] == _URL
    registry = IdRegistry.__new__(IdRegistry)
    generate_git_project_sbom(_URL, id_registry=registry)  # an object is kept
    assert given["id_registry"] is registry


def test_a_refused_url_is_raised_with_its_code() -> None:
    """The library surface raises ``RemoteSourceError``; nothing is written."""
    with pytest.raises(RemoteSourceError) as excinfo:
        generate_git_project_sbom("ssh://git@host/o/r.git")
    assert excinfo.value.code == "git.url-invalid"


@pytest.mark.parametrize(
    ("target", "kind"),
    [
        ("env", "env"),
        ("pkg-1.0-py3-none-any.whl", "wheel"),
        ("https://huggingface.co/o/m", "hf"),
        ("https://hf.co/o/m/tree/main", "hf"),
        ("o/no-such-local-dir", "hf"),
        ("https://huggingface.co/spaces/o/app", "git"),
        ("https://hf.co/datasets/o/data", "git"),
        ("https://gitlab.com/g/p", "git"),
        ("ssh://git@host/o/r.git", "git"),
        (".", "project"),
    ],
)
def test_every_target_is_one_kind(target: str, kind: str) -> None:
    """The one classification behind ``generate()``: a Hugging Face Space or
    dataset is a Git repository, a Hugging Face model is a model."""
    assert _classify_target(target) == kind
