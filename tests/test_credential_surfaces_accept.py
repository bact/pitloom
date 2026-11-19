# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A credential the run accepts is stated as written on every surface, in
either mode, by the fingerprints a refusal printed
(``--accept-url-credential``, the library's
``PitloomConfig(accept_url_credentials=...)``, the hook's
``[tool.pitloom] accept-url-credentials``); each accepted value is said,
masked, by the ``accepted`` line alone (no ``written`` line in the ``warn``
mode), and the provenance statements stay JSON.

See also: tests/test_credential_surfaces.py (the same surfaces refusing)
and tests/test_credential_surfaces_warn.py (the ``warn`` mode).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from pitloom.core.credential_policy import fingerprint
from pitloom.logging_config import CODE_ATTR
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


@pytest.mark.parametrize("refusing", [False, True], ids=["warn", "refuse"])
@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_the_fingerprints_a_refusal_printed_accept_the_values(
    surface: str,
    refusing: bool,
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
        sbom = SURFACES[surface](second, monkeypatch, HOME, printed, refusing)
    out, err = capsys.readouterr()
    sbom = sbom or out
    assert json.dumps(HOME) in sbom
    assert not leaks(err, caplog.text)
    codes = [getattr(r, CODE_ATTR, "") for r in caplog.records]
    assert "credentials-unsafe/accepted" in codes
    # Accepted is quieter than written: no value of the run is warned of so.
    assert "credentials-unsafe/written" not in codes
    assert "credentials-unsafe/refused" not in codes


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
        SURFACES[surface](tmp_path / "b", monkeypatch, HOME, printed[1:], True)


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
    done = run(tmp_path, "wheel", str(wheel_of(given_dir, HOME)), "-o", str(sbom))
    assert done.returncode == 0, done.stderr.decode()
    wheel = wheel_of(tmp_path, "https://e.example/h")
    embed = ["embed-wheel", str(wheel), "--sbom", str(sbom), "--refuse-url-credentials"]
    refused = run(tmp_path, *embed)
    printed = offered(refused.stderr.decode())
    assert refused.returncode == 1 and printed and not embedded(wheel)
    flags = [arg for fp in printed for arg in ("--accept-url-credential", fp)]
    done = run(tmp_path, *embed, *flags)
    assert done.returncode == 0, done.stderr.decode()
    assert embedded(wheel) == sbom.read_text(encoding="utf-8")
