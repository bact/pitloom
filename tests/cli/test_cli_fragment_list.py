# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI `fragment list` command.

See also: test_cli_fragment.py (`fragment validate` -- split out once
this file grew past the project's file-size soft limit).
"""

from __future__ import annotations

import errno
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble.spdx3.fragments import _missing_fragment_message
from pitloom.cli.commands.fragment import (
    _fragment_read_status,
    _report_fragment,
)
from pitloom.core.config import FragmentConfig

_MINIMAL_PROJECT = '[project]\nname = "smoke"\nversion = "0.1.0"\n'


def _write_pyproject(tmp_path: Path, fragment_toml: str) -> None:
    (tmp_path / "pyproject.toml").write_text(_MINIMAL_PROJECT + fragment_toml)


def test_fragment_list_no_fragments_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_pyproject(tmp_path, "")
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    assert __main__.main() == 0
    # Nothing on stdout: the hint is an INFO: line.
    assert capsys.readouterr() == ("", "INFO: fragment list: no fragments configured\n")


def test_fragment_list_plain_string_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A plain-string files entry (no role/sha256/etc.) shows ROLE=- and
    SHA256=- -- the "backward-compatible" shorthand form."""
    (tmp_path / "a.spdx3.json").write_text('{"@graph": [{"x": 1}]}')
    _write_pyproject(tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["a.spdx3.json"]\n')
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    out = capsys.readouterr().out
    assert (
        "PATH=a.spdx3.json ROLE=- REQUIRED=false EXISTS=true ELEMENTS=1 SHA256=-" in out
    )


def test_fragment_list_table_entry_sha256_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A full table entry with role and a correct sha256 shows ROLE=ai_model
    and SHA256=match."""
    content = '{"@graph": [{"x": 1}, {"y": 2}]}'
    (tmp_path / "model.spdx3.json").write_text(content)
    digest = hashlib.sha256(content.encode()).hexdigest()
    _write_pyproject(
        tmp_path,
        "\n[tool.pitloom.fragment]\nfiles = ["
        f'{{ path = "model.spdx3.json", role = "ai_model", sha256 = "{digest}" }}'
        "]\n",
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    out = capsys.readouterr().out
    assert "ROLE=ai_model" in out
    assert "SHA256=match" in out
    assert "ELEMENTS=2" in out


def test_fragment_list_sha256_mismatch_warns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / "model.spdx3.json").write_text('{"@graph": []}')
    _write_pyproject(
        tmp_path,
        '\n[tool.pitloom.fragment]\nfiles = [{ path = "model.spdx3.json", '
        'sha256 = "deadbeef" }]\n',
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    with caplog.at_level("WARNING", logger="pitloom.cli.commands.fragment"):
        result = __main__.main()
    assert result == 0
    assert any(
        "SHA-256 mismatch" in r.message and "deadbeef" in r.message
        for r in caplog.records
    )


def test_fragment_list_sha256_configured_but_file_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """sha256 configured but the file doesn't exist -> SHA256=unknown, the
    missing-file WARNING fires, not the mismatch one."""
    _write_pyproject(
        tmp_path,
        '\n[tool.pitloom.fragment]\nfiles = [{ path = "gone.spdx3.json", '
        'sha256 = "deadbeef" }]\n',
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    with caplog.at_level("WARNING"):
        result = __main__.main()
    assert result == 0
    out = capsys.readouterr().out
    assert "SHA256=unknown" in out
    assert "EXISTS=false" in out
    assert not any("mismatch" in r.message for r in caplog.records)
    assert any("not found" in r.message for r in caplog.records)


def test_fragment_list_required_missing_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    _write_pyproject(
        tmp_path,
        '\n[tool.pitloom.fragment]\nfiles = [{ path = "gone.spdx3.json", '
        "required = true }]\n",
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    expected_warning = _missing_fragment_message(
        tmp_path / "gone.spdx3.json", required=True
    )
    with caplog.at_level("WARNING"):
        result = __main__.main()
    assert result == 1
    out = capsys.readouterr().out
    assert "EXISTS=false" in out
    assert any(r.message == expected_warning for r in caplog.records)


def test_fragment_list_optional_missing_exits_0(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _write_pyproject(
        tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["gone.spdx3.json"]\n'
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    expected_warning = _missing_fragment_message(
        tmp_path / "gone.spdx3.json", required=False
    )
    with caplog.at_level("WARNING"):
        result = __main__.main()
    assert result == 0
    assert any(r.message == expected_warning for r in caplog.records)
    assert "merge will fail" not in expected_warning


def test_fragment_list_unparseable_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    frag_path = tmp_path / "broken.spdx3.json"
    frag_path.write_text("not valid json{{{")
    _write_pyproject(
        tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["broken.spdx3.json"]\n'
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    with caplog.at_level("WARNING"):
        result = __main__.main()
    assert result == 0
    assert "ELEMENTS=-" in capsys.readouterr().out
    assert any(
        r.message.startswith(f"Failed to read SBOM fragment {frag_path}: ")
        for r in caplog.records
    )


def test_fragment_list_unparseable_file_with_sha256_still_hashes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fragment with invalid JSON but a configured sha256 must still
    report SHA256=match/mismatch (the file's bytes are still readable and
    hashable), not SHA256=unknown -- SHA-256 verification is independent
    of JSON validity."""
    content = b"not valid json{{{"
    (tmp_path / "broken.spdx3.json").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    _write_pyproject(
        tmp_path,
        '\n[tool.pitloom.fragment]\nfiles = [{ path = "broken.spdx3.json", '
        f'sha256 = "{digest}" }}]\n',
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    out = capsys.readouterr().out
    assert "SHA256=match" in out
    assert "SHA256=unknown" not in out


def test_fragment_list_required_unparseable_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A required=True fragment that exists but fails to parse must also
    exit non-zero -- the same condition that makes a real merge raise
    FragmentMergeError, not just the missing-file case."""
    frag_path = tmp_path / "broken-required.spdx3.json"
    frag_path.write_text("not valid json{{{")
    _write_pyproject(
        tmp_path,
        '\n[tool.pitloom.fragment]\nfiles = [{ path = "broken-required.spdx3.json", '
        "required = true }]\n",
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 1
    assert "ELEMENTS=-" in capsys.readouterr().out


def test_fragment_list_required_invalid_spdx3_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A required=True fragment that's syntactically valid JSON but not a
    valid SPDX3 JSON-LD document must also exit non-zero -- matches
    merge_fragments() actually rejecting it via
    spdx3.JSONLDDeserializer(), not just a bare JSON-syntax check."""
    (tmp_path / "not-spdx3.spdx3.json").write_text('{"foo": "bar"}')
    _write_pyproject(
        tmp_path,
        '\n[tool.pitloom.fragment]\nfiles = [{ path = "not-spdx3.spdx3.json", '
        "required = true }]\n",
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 1
    assert "ELEMENTS=0" in capsys.readouterr().out


def test_report_fragment_stat_missing_errno_degrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A stat() race (the file is removed between being listed and being
    stat'd) must degrade to EXISTS=false, not crash the whole `fragment
    list` run -- covers _report_fragment's single up-front stat() call.
    Uses a real ENOENT errno, matching what an actual missing-file race
    produces (an errno-less OSError doesn't classify as "missing")."""
    frag = FragmentConfig(path="raced.spdx3.json")

    def _raise_os_error(self: Path) -> os.stat_result:
        raise FileNotFoundError(errno.ENOENT, "No such file or directory")

    monkeypatch.setattr(Path, "stat", _raise_os_error)
    result = _report_fragment(tmp_path, frag)
    assert result is False
    assert "EXISTS=false" in capsys.readouterr().out


def test_report_fragment_stat_permission_error_reports_exists_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A stat() failure that ISN'T a "missing path" errno (e.g. a
    permission error) must report EXISTS=true, not be misclassified as
    "not found" -- the file is present, just inaccessible; the read
    attempt below is what should explain why."""
    frag = FragmentConfig(path="denied.spdx3.json")

    def _raise_os_error(self: Path) -> os.stat_result:
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(Path, "stat", _raise_os_error)
    result = _report_fragment(tmp_path, frag)
    out = capsys.readouterr().out
    assert result is False
    assert "EXISTS=true" in out
    assert "MODIFIED=-" in out


def test_fragment_list_role_empty_string_distinct_from_unset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An explicitly-configured role = "" must print differently from a
    fragment with no role key at all -- both aren't the placeholder '-'."""
    _write_pyproject(
        tmp_path,
        "\n[tool.pitloom.fragment]\nfiles = ["
        '{ path = "a.spdx3.json", role = "" }, '
        '"b.spdx3.json",'
        "]\n",
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    __main__.main()
    lines = capsys.readouterr().out.splitlines()
    assert "PATH=a.spdx3.json ROLE= " in lines[0]
    assert "PATH=b.spdx3.json ROLE=-" in lines[1]


def test_fragment_read_status_os_error_on_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A fragment that exists but can't be read (e.g. a permission error
    hit after the is_file() check) is a distinct failure mode from a bad
    parse -- covers _fragment_read_status's read_bytes() except branch."""
    frag_path = tmp_path / "unreadable.spdx3.json"
    frag_path.write_text('{"@graph": []}')

    def _raise_os_error(self: Path) -> bytes:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_bytes", _raise_os_error)

    with caplog.at_level("WARNING"):
        raw, read_ok, elements = _fragment_read_status(frag_path, required=True)

    assert raw is None
    assert read_ok is False
    assert elements is None
    assert any(
        r.message.startswith(f"Failed to read SBOM fragment {frag_path}: ")
        for r in caplog.records
    )


def test_fragment_read_status_preserves_raw_bytes_on_json_parse_failure(
    tmp_path: Path,
) -> None:
    """A fragment that's fully readable but not valid JSON must still
    return its raw bytes -- SHA-256 verification is independent of JSON
    validity, matching _fragment_sha256_status's own documented contract."""
    frag_path = tmp_path / "broken.spdx3.json"
    content = b"not valid json{{{"
    frag_path.write_bytes(content)

    raw, read_ok, elements = _fragment_read_status(frag_path, required=False)

    assert raw == content
    assert read_ok is False
    assert elements is None


def test_fragment_read_status_tolerates_utf8_bom(tmp_path: Path) -> None:
    """A fragment with a leading UTF-8 BOM must parse successfully, matching
    the real merge path (json.load() on a binary handle, which auto-strips
    a BOM) -- json.loads(raw.decode("utf-8")) would instead raise
    "Unexpected UTF-8 BOM", a false-negative for a fragment a real build
    would merge fine."""
    frag_path = tmp_path / "bom.spdx3.json"
    frag_path.write_bytes(b"\xef\xbb\xbf" + b'{"@graph": []}')

    raw, read_ok, elements = _fragment_read_status(frag_path, required=False)

    assert raw is not None
    assert elements == 0
    assert read_ok is True


def test_fragment_read_status_non_list_graph_does_not_crash(tmp_path: Path) -> None:
    """A fragment whose '@graph' value is valid JSON but not a list (e.g.
    an int) must not crash with an uncaught TypeError from len() -- it's a
    malformed-but-parseable document, degrading like every other
    not-really-usable fragment shape, not aborting the whole command."""
    frag_path = tmp_path / "bad-graph.spdx3.json"
    frag_path.write_text('{"@graph": 5}')

    raw, _read_ok, elements = _fragment_read_status(frag_path, required=False)

    assert raw is not None
    assert elements is None


def test_fragment_list_valid_json_no_graph_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Valid JSON with no @graph key is a real 0-element count, not an
    unparseable-file case."""
    (tmp_path / "empty.spdx3.json").write_text('{"foo": "bar"}')
    _write_pyproject(
        tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["empty.spdx3.json"]\n'
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    assert "ELEMENTS=0" in capsys.readouterr().out


def test_fragment_list_project_dir_no_pyproject(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 1
    assert "ERROR: fragment list failed:" in capsys.readouterr().err


def test_fragment_list_two_fragments_both_reported(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One missing (non-required) and one with a good sha256 -- both
    problems are reported in the same run's output, loop doesn't
    short-circuit."""
    content = '{"@graph": [{"x": 1}]}'
    (tmp_path / "good.spdx3.json").write_text(content)
    digest = hashlib.sha256(content.encode()).hexdigest()
    _write_pyproject(
        tmp_path,
        "\n[tool.pitloom.fragment]\nfiles = [\n"
        '  "missing.spdx3.json",\n'
        f'  {{ path = "good.spdx3.json", sha256 = "{digest}" }},\n'
        "]\n",
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    out = capsys.readouterr().out
    assert "PATH=missing.spdx3.json" in out
    assert "EXISTS=false" in out
    assert "PATH=good.spdx3.json" in out
    assert "SHA256=match" in out


def test_fragment_list_modified_field_pinned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """MODIFIED reflects the fragment file's actual mtime, pinned via
    os.utime for a deterministic assertion."""
    frag_path = tmp_path / "a.spdx3.json"
    frag_path.write_text('{"@graph": []}')
    fixed_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    os.utime(frag_path, (fixed_ts, fixed_ts))
    _write_pyproject(tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["a.spdx3.json"]\n')
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    assert "MODIFIED=2026-01-01T12:00:00+00:00" in capsys.readouterr().out
