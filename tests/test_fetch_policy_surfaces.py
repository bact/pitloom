# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard: every surface that fetches (each CLI command, each library
call) hands its remote route the same
:class:`~pitloom.core.fetch_policy.RemoteFetchPolicy` for the same inputs,
the one :func:`~pitloom.core.config_cascade.resolve_fetch_policy` makes, for
a Git URL, a PyPI URL and a Hugging Face model alike. The hook fetches
nothing.

Each route is replaced by a spy that records the policy it is given and
stops the run.

See also: tests/core/test_fetch_policy.py (the resolver itself).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import (
    _generators_git,
    _generators_pypi,
    _model_generator,
    generate,
    generate_git_project_sbom,
    generate_git_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_pypi_sbom,
    generate_wheel_sbom,
)
from pitloom.cli.commands import _remote
from pitloom.core.config_cascade import load_config_file, resolve_fetch_policy
from pitloom.core.fetch_policy import RemoteFetchPolicy

_GIT = "https://example.invalid/g/p.git"
_PYPI = "https://pypi.org/project/demo/1.0/"
_HF = "acme/model"

#: Each route's spies: (module, the name the surfaces call).
_ROUTES = {
    "git": ((_generators_git, "fetch_git_project"), (_remote, "fetch_git_project")),
    "pypi": ((_generators_pypi, "fetch_pypi_file"),),
    "hf": ((_model_generator, "read_huggingface"),),
}

#: The library calls of each route.
_LIBRARY: dict[str, tuple[Callable[..., str], ...]] = {
    "git": (generate_git_sbom, generate_git_project_sbom, generate),
    "pypi": (generate_pypi_sbom, generate_project_sbom, generate_wheel_sbom, generate),
    "hf": (generate_model_sbom, generate),
}

#: The commands of each route.
_COMMANDS = {
    "git": ("project", "model", "generate"),
    "pypi": ("wheel", "project", "generate"),
    "hf": ("model", "generate"),
}

_TARGETS = {"git": _GIT, "pypi": _PYPI, "hf": _HF}

#: (--offline, --max-download-bytes, the config file's settings).
_CASES = {
    "defaults": (None, None, ""),
    "flag-offline": (True, None, ""),
    "config": (None, None, "offline = true\nmax-download-bytes = 1000\n"),
    "flags-beat-config": (False, 2000, "offline = true\nmax-download-bytes = 1000\n"),
}


class _Stop(Exception):
    """Raised by a spy: the route was reached."""


def _spy(monkeypatch: pytest.MonkeyPatch, route: str) -> list[RemoteFetchPolicy]:
    seen: list[RemoteFetchPolicy] = []

    def reached(*_args: Any, policy: RemoteFetchPolicy, **_kwargs: Any) -> Any:
        seen.append(policy)
        raise _Stop

    for module, name in _ROUTES[route]:
        monkeypatch.setattr(module, name, reached)
    return seen


def _config(tmp_path: Path, settings: str) -> Path | None:
    if not settings:
        return None
    path = tmp_path / "pitloom.toml"
    path.write_text(f"[tool.pitloom]\n{settings}", encoding="utf-8")
    return path


def _argv(command: str, route: str, case: str, tmp_path: Path) -> list[str]:
    offline, cap, settings = _CASES[case]
    argv = ["loom", command, _TARGETS[route], "-o", str(tmp_path / "o.json")]
    if offline is not None:
        argv.append("--offline" if offline else "--no-offline")
    if cap is not None:
        argv += ["--max-download-bytes", str(cap)]
    config = _config(tmp_path, settings)
    if config is not None:
        argv += ["--config", str(config)]
    return argv


def _expected(case: str, tmp_path: Path) -> RemoteFetchPolicy:
    offline, cap, settings = _CASES[case]
    config = _config(tmp_path, settings)
    return resolve_fetch_policy(
        None if config is None else load_config_file(config),
        offline=offline,
        max_download_bytes=cap,
    )


@pytest.mark.parametrize("case", _CASES)
@pytest.mark.parametrize("route", _ROUTES)
def test_every_surface_resolves_the_same_policy(
    route: str, case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    seen = _spy(monkeypatch, route)
    offline, cap, settings = _CASES[case]
    config_path = _config(tmp_path, settings)
    config = None if config_path is None else load_config_file(config_path)
    checked: list[str] = []
    check = checked.append
    for call in _LIBRARY[route]:
        with pytest.raises(_Stop):
            call(
                _TARGETS[route],
                offline=offline,
                max_download_bytes=cap,
                pitloom_config=config,
                check_url=check,
            )
    library = len(seen)
    for command in _COMMANDS[route]:
        monkeypatch.setattr(sys, "argv", _argv(command, route, case, tmp_path))
        assert __main__.main() == 1
    expected = _expected(case, tmp_path)
    assert len(seen) == len(_LIBRARY[route]) + len(_COMMANDS[route])
    # The library passes its check on; the command line has none.
    assert (
        seen[:library]
        == [RemoteFetchPolicy(expected.max_bytes, expected.offline, check)] * library
    )
    assert seen[library:] == [expected] * len(_COMMANDS[route])
    assert expected.offline is (case in ("flag-offline", "config"))
