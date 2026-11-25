# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A URL with a thousand ``?`` in its query, planted in a project URL, is
written with one ``WARNING:`` by default (exit 0) and, with
``--refuse-url-credentials``, refused (exit 1, one ``ERROR:`` with its
fingerprint, no SBOM; never a ``RecursionError``) on every command that reads
a project, with no secret on stdout or stderr; accepted by that fingerprint,
the SBOM states it as written.

See also: tests/test_credential_surfaces.py (the planted-secret routes),
tests/test_credential_surfaces_accept.py (the override on each surface) and
tests/core/url_masking/test_url_masking_modes.py (the reading itself).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.core.credential_policy import fingerprint

pytestmark = pytest.mark.platform

_DEEP = "ftp://u:S3CRET@h.invalid/x?" + "q=1?" * 1000 + "token=T0KEN"
_SECRETS = ("S3CRET", "T0KEN")
_FINGERPRINT_RE = re.compile(r"--accept-url-credential (sha256:[0-9a-f]{16})\b")


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "pkg").mkdir(parents=True)
    (proj / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        "[project]\nname = 'pkg'\nversion = '0.1.0'\n"
        f"[project.urls]\nHomepage = '{_DEEP}'\n",
        encoding="utf-8",
    )
    return proj


def _run(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    code = main()
    seen = capsys.readouterr()
    return code, seen.out, seen.err


@pytest.mark.parametrize("command", ["generate", "project"])
def test_a_deeply_nested_query_is_written_with_a_warning_by_default(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "o.json"
    argv = [command, str(_project(tmp_path)), "-o", str(out), "--offline"]
    code, stdout, stderr = _run(argv, monkeypatch, capsys)
    assert code == 0 and "ERROR: " not in stderr and "Traceback" not in stderr
    warned = [
        line
        for line in stderr.splitlines()
        if line.startswith("WARNING: ")
        and line.endswith("[credentials-unsafe/written]")
    ]
    assert len(warned) == 1 and f", {fingerprint(_DEEP)}); " in warned[0]
    assert not any(secret in stdout + stderr for secret in _SECRETS)
    assert _DEEP in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("command", ["generate", "project"])
def test_a_deeply_nested_query_is_refused_then_accepted_by_fingerprint(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "o.json"
    argv = [command, str(_project(tmp_path)), "-o", str(out), "--offline"]
    argv.append("--refuse-url-credentials")

    code, stdout, stderr = _run(argv, monkeypatch, capsys)
    assert code == 1
    assert not out.exists()
    assert "Traceback" not in stderr
    assert not any(secret in stdout + stderr for secret in _SECRETS)
    refused = [
        line
        for line in stderr.splitlines()
        if line.startswith("ERROR: ") and line.endswith("[credentials-unsafe/refused]")
    ]
    assert len(refused) == 2  # the value's line, then the closing count
    offered = _FINGERPRINT_RE.findall(stderr)
    assert offered == [fingerprint(_DEEP)]

    code, stdout, stderr = _run(
        [*argv, "--accept-url-credential", offered[0]], monkeypatch, capsys
    )
    assert code == 0
    assert "ERROR: " not in stderr
    assert "[credentials-unsafe/accepted]" in stderr
    assert not any(secret in stdout + stderr for secret in _SECRETS)
    assert _DEEP in out.read_text(encoding="utf-8")


# The unshown-message line stays uncoded (sweep B ruling R5).
@pytest.mark.uncoded_output(
    r"^ERROR: loom enrich: \(a log message that could not be shown\)$"
)
def test_a_url_that_cannot_be_masked_never_prints_raw(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An error whose text the masker fails on is a fixed text, never the
    exception's own (the traceback the default hook prints holds it)."""

    def fail(*_args: object, **_kwargs: object) -> str:
        raise RecursionError

    monkeypatch.setattr("pitloom.log_masking.masked_given_path", fail)
    monkeypatch.setattr(sys, "argv", ["loom", "enrich", _DEEP, "-o", "x.json"])
    main()
    seen = capsys.readouterr()
    assert "S3CRET" not in seen.err + seen.out
