# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""In the default ``warn`` mode, an SBOM whose URL values hold a credential
is written on every surface as it stands: exit 0, the Hatchling hook's
build goes on, one ``WARNING:`` per value naming how that surface turns the
``refuse`` mode on, no ``ERROR:``, and no secret on stderr or in a log
record (the SBOM itself states it, which the warning says).

See also: tests/test_credential_surfaces.py (the same surfaces in the
``refuse`` mode).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.export._spdx3_credentials import check_graph_credentials
from pitloom.logging_config import CODE_ATTR
from tests._author_routes import write_wheel
from tests.test_credential_surfaces import (
    HOME,
    SECRETS,
    SURFACES,
    _project,
    embedded,
    leaks,
    run,
)

pytestmark = pytest.mark.platform

WRITTEN = "credentials-unsafe/written"
_WHEN = "2026-01-01T00:00:00Z"
#: A fingerprint as a warning prints it.
_NAMED = re.compile(r", (sha256:[0-9a-f]{16})\); the SBOM states it")

#: How each surface's warning says to turn the refuse mode on.
_ADVICE = {
    "cli-generate": "refuse such values with --refuse-url-credentials",
    "cli-stdout": "refuse such values with --refuse-url-credentials",
    "embed-wheel": "refuse such values with --refuse-url-credentials",
    "embed-wheel-sbom": "refuse such values with --refuse-url-credentials",
    "merge": "refuse such values with --refuse-url-credentials",
    "hook": 'refuse such values with [tool.pitloom] url-credentials = "refuse"',
    "library": "refuse such values with credentials=CredentialPolicy(refuse=True)",
    "croissant": "refuse such values with credentials=CredentialPolicy(refuse=True)",
}


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_a_planted_secret_is_written_with_a_warning_on_every_surface(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        sbom = SURFACES[surface](tmp_path, monkeypatch, HOME, [], False)
    out, err = capsys.readouterr()
    written = sbom or out
    if surface.startswith("embed-wheel"):
        written = embedded(tmp_path / "demo-1.0-py3-none-any.whl")
    # The SBOM states the value as written: what the warning is about.
    assert leaks(written) and "@graph" in written
    assert not leaks(err, caplog.text)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert "ERROR: " not in err
    warned = [
        r.getMessage() for r in caplog.records if getattr(r, CODE_ATTR, "") == WRITTEN
    ]
    assert warned and all(_ADVICE[surface] in m for m in warned)
    assert all("; the SBOM states it as written; " in m for m in warned)


def test_the_hook_build_goes_on_in_the_warn_mode(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The hook fails no build unless the project set ``refuse``."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        sbom = SURFACES["hook"](tmp_path, pytest.MonkeyPatch(), HOME, [], False)
    assert any(s in sbom for s in SECRETS)
    codes = {getattr(r, CODE_ATTR, "") for r in caplog.records}
    assert WRITTEN in codes and "credentials-unsafe/refused" not in codes


@pytest.mark.parametrize("verbose", [False, True], ids=["default", "verbose"])
def test_a_project_with_planted_secrets_is_written_in_a_real_process(
    tmp_path: Path, verbose: bool
) -> None:
    """Exit 0; stdout and stderr (also under ``-v``) hold no secret; each
    value is named once, with its fingerprint; the SBOM is written."""
    proj = _project(tmp_path, HOME)
    args = ["generate", str(proj), "-o", str(tmp_path / "out.json")]
    done = run(tmp_path, *args, *(["-v"] if verbose else []))
    err = done.stderr.decode()
    assert done.returncode == 0, err
    assert not leaks(done.stdout.decode(), err)
    assert "ERROR: " not in err
    assert err.count(f"[{WRITTEN}]") == len(set(_NAMED.findall(err))) >= 2
    assert leaks((tmp_path / "out.json").read_text(encoding="utf-8"))


def _written(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage() for r in caplog.records if getattr(r, CODE_ATTR, "") == WRITTEN
    ]


def test_each_sbom_of_an_embed_batch_names_the_value_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two wheels in one process, one Homepage token: each SBOM's line is
    said, never folded into the first one's."""
    monkeypatch.chdir(tmp_path)
    wheels = []
    for version in ("1.0", "2.0"):
        metadata = (
            f"Metadata-Version: 2.4\nName: demo\nVersion: {version}\n"
            f"Project-URL: Homepage, {HOME}\n"
        )
        wheels.append(str(write_wheel(tmp_path, metadata, version)))
    argv = ["loom", "embed-wheel", *wheels, "--offline", "--creation-datetime", _WHEN]
    monkeypatch.setattr(sys, "argv", argv)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert main() == 0
    named = _written(caplog)
    assert len(named) == 2 and len(set(named)) == 2  # each names its own SBOM
    assert all("#Package-1 /software_downloadLocation, " in m for m in named)


def test_the_library_called_twice_warns_twice(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    proj = _project(tmp_path, HOME)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_project_sbom(proj, output_path=tmp_path / "a.json", offline=True)
        first = len(_written(caplog))
        generate_project_sbom(proj, output_path=tmp_path / "b.json", offline=True)
    assert first >= 2 and len(_written(caplog)) == 2 * first


def test_one_value_in_two_fields_of_one_sbom_is_one_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = [
        {"spdxId": "urn:a", "software_homePage": HOME},
        {"spdxId": "urn:b", "software_downloadLocation": HOME},
    ]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        check_graph_credentials(graph, CredentialPolicy())
    (line,) = _written(caplog)
    assert "(urn:a /software_homePage, " in line
