# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A credential the run accepts is stated as written on every surface: by
the fingerprints a refusal printed (``--accept-url-credential``, the
library's ``PitloomConfig(accept_url_credentials=...)``, the hook's
``[tool.pitloom] accept-url-credentials``), or by
``--allow-url-credentials``; each accepted value is said, masked, and the
provenance statements stay JSON.

See also: tests/test_credential_surfaces.py (the same surfaces refusing).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from pitloom.core.credential_policy import fingerprint
from tests.test_credential_surfaces import (
    DEP,
    HOME,
    SURFACES,
    embedded,
    leaks,
    offered,
    refuse,
    run,
    wheel_of,
)

pytestmark = pytest.mark.platform

_ACCEPTED = "[credentials-unsafe/accepted]"


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_the_fingerprints_a_refusal_printed_accept_the_values(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The user's path: run, read the fingerprints, run again with them."""
    first, second = tmp_path / "refused", tmp_path / "accepted"
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(first)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        refuse(surface, first, monkeypatch, HOME)
    printed = offered(capsys.readouterr().err + caplog.text)
    assert printed
    caplog.clear()
    monkeypatch.chdir(second)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        sbom = SURFACES[surface](second, monkeypatch, HOME, printed)
    out, err = capsys.readouterr()
    sbom = sbom or out
    assert json.dumps(HOME) in sbom
    assert not leaks(err, caplog.text)
    assert "credentials-unsafe/accepted" in err + caplog.text + "".join(
        str(getattr(r, "pitloom_code", "")) for r in caplog.records
    )


@pytest.mark.parametrize(
    "surface", ["cli-generate", "cli-stdout", "embed-wheel", "merge"]
)
def test_one_fingerprint_short_of_the_set_still_refuses(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every value is accepted on its own: the fingerprint of another
    value of the same run accepts nothing more."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    refuse(surface, tmp_path / "a", monkeypatch, HOME)
    printed = offered(capsys.readouterr().err)
    with pytest.raises(Exception):  # noqa: B017 - the surface's own refusal
        SURFACES[surface](tmp_path / "b", monkeypatch, HOME, printed[1:])


def test_allow_url_credentials_accepts_every_value_on_the_command_line(
    tmp_path: Path,
) -> None:
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "pyproject.toml").write_text(
        "[project]\nname = 'p'\nversion = '1'\n"
        f"dependencies = ['{DEP}']\n[project.urls]\nHomepage = '{HOME}'\n",
        encoding="utf-8",
    )
    out = tmp_path / "o.json"
    done = run(
        tmp_path, "generate", str(proj), "-o", str(out), "--allow-url-credentials"
    )
    err = done.stderr.decode()
    assert done.returncode == 0, err
    assert err.count(_ACCEPTED) >= 2 and "--allow-url-credentials" in err
    assert not leaks(err) and json.dumps(HOME) in out.read_text(encoding="utf-8")


def test_allow_url_credentials_in_pyproject_is_ignored(
    tmp_path: Path,
) -> None:
    """A file setting set once for an example URL would let a real token in
    later: the hook and the command line read it from no file."""
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "pyproject.toml").write_text(
        "[project]\nname = 'p'\nversion = '1'\n"
        f"[project.urls]\nHomepage = '{HOME}'\n"
        "[tool.pitloom]\nallow-url-credentials = true\n",
        encoding="utf-8",
    )
    done = run(tmp_path, "generate", str(proj), "-o", str(tmp_path / "o.json"))
    err = done.stderr.decode()
    assert done.returncode == 1 and "[credentials-unsafe/refused]" in err
    assert "[config-unsafe/cli-only]" in err and not leaks(err)


@pytest.mark.parametrize("credentialed", [False, True], ids=["clean", "accepted"])
def test_every_provenance_statement_stays_json(
    credentialed: bool, tmp_path: Path
) -> None:
    """The strip once read ``"}}`` of a statement's JSON as part of a direct
    reference's URL and cut it: the check never rewrites a value."""
    dep = DEP if credentialed else "foo @ https://h.example/x.whl"
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "pyproject.toml").write_text(
        f"[project]\nname = 'p'\nversion = '1'\ndependencies = ['{dep}']\n",
        encoding="utf-8",
    )
    out = tmp_path / "o.json"
    flags = ["--accept-url-credential", fingerprint(DEP)] if credentialed else []
    done = run(tmp_path, "generate", str(proj), "-o", str(out), *flags)
    assert done.returncode == 0, done.stderr.decode()
    graph = json.loads(out.read_text(encoding="utf-8"))["@graph"]
    notes = [
        json.loads(e["statement"])
        for e in graph
        if e.get("contentType") == "application/json"
    ]
    assert any(dep in json.dumps(note) for note in notes)


def test_embed_wheel_sbom_embeds_an_accepted_file_unchanged(
    tmp_path: Path,
) -> None:
    """``embed-wheel --sbom`` checks the file it is given and embeds its
    bytes as they are: never rewritten."""
    given_dir = tmp_path / "given"
    given_dir.mkdir()
    sbom = tmp_path / "given.spdx3.json"
    done = run(
        tmp_path,
        "wheel",
        str(wheel_of(given_dir, HOME)),
        "-o",
        str(sbom),
        "--allow-url-credentials",
    )
    assert done.returncode == 0, done.stderr.decode()
    wheel = wheel_of(tmp_path, "https://e.example/h")
    refused = run(tmp_path, "embed-wheel", str(wheel), "--sbom", str(sbom))
    printed = offered(refused.stderr.decode())
    assert refused.returncode == 1 and printed and not embedded(wheel)
    flags = [arg for fp in printed for arg in ("--accept-url-credential", fp)]
    done = run(tmp_path, "embed-wheel", str(wheel), "--sbom", str(sbom), *flags)
    assert done.returncode == 0, done.stderr.decode()
    assert embedded(wheel) == sbom.read_text(encoding="utf-8")
