# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``%`` in ``setup.cfg`` is read as setuptools reads it: ``%%`` and a
defined ``%(key)s`` resolve, a bare ``%`` or an undefined reference fails
with one line naming the file, section, key and the ``%%`` escape.

See also: tests/extract/project/test_setuptools_merge.py (every unreadable
``setup.cfg`` is one error line) and
tests/extract/project/test_sdist_config.py (the sdist member).
"""

from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom
from pitloom.core.quote_source import quote_source
from pitloom.extract.project.setuptools_cfg import (
    read_setup_cfg,
    read_setup_cfg_options,
    setup_cfg_pitloom_config,
)

_BASE = "[metadata]\nname = demo\nversion = 1\n"

#: Ask setuptools' own reader (in a child: it warns on deprecations).
_SETUPTOOLS_READ = """
import json, sys, warnings
warnings.simplefilter("ignore")
from setuptools.config.setupcfg import read_configuration
try:
    meta = read_configuration(sys.argv[1])["metadata"]
except Exception as exc:
    print(json.dumps({"error": type(exc).__name__}))
else:
    print(json.dumps({k: meta.get(k) for k in ("description", "project_urls")}))
"""


def _setuptools_read(setup_cfg: Path) -> dict[str, object]:
    proc = subprocess.run(  # nosec B603
        [sys.executable, "-c", _SETUPTOOLS_READ, str(setup_cfg)],
        capture_output=True,
        check=True,
        timeout=120,
    )
    result: dict[str, object] = json.loads(proc.stdout)
    return result


def _write(tmp_path: Path, body: str) -> Path:
    setup_cfg = tmp_path / "setup.cfg"
    setup_cfg.write_bytes((_BASE + body + "\n").encode("utf-8"))
    return setup_cfg


@pytest.mark.parametrize(
    ("body", "where", "reason"),
    [
        ("description = 50% faster", "[metadata] description", "found: '% faster'"),
        ("author = R%D Team", "[metadata] author", "'%' must be followed"),
        (
            "project_urls =\n    Docs = https://x.org/a%20b",
            "[metadata] project_urls",
            "'%' must be followed",
        ),
        (
            "classifiers =\n    Programming Language :: Python\n    100% Pure",
            "[metadata] classifiers",
            "'%' must be followed",
        ),
        ("description = Schnell, 50% größer", "[metadata] description", "größer"),
        (
            "[DEFAULT]\nshared = %(missing)s",
            "[DEFAULT] shared",
            "%(missing)s names no key of [metadata] or [DEFAULT]",
        ),
        (
            "description = %(missing)s x",
            "[metadata] description",
            "%(missing)s names no key of [metadata] or [DEFAULT]",
        ),
        ("[DEFAULT]\nshared = 5% off", "[DEFAULT] shared", "'%' must be followed"),
        (
            "description = %(a)s\na = %(description)s",
            "[metadata] description",
            "nest deeper than 10 levels",
        ),
        ("[options]\npython_requires = >=3.10 %", "[options] python_requires", "'%'"),
        (
            "[options.extras_require]\nDev = x; python_version > '3' %",
            "[options.extras_require] Dev",
            "'%' must be followed",
        ),
        ("[tool:pitloom]\npretty = 100% x", "[tool:pitloom] pretty", "'%' must"),
    ],
    ids=[
        "description",
        "author",
        "urls-multiline",
        "classifiers-multiline",
        "non-ascii",
        "default-missing-reference",
        "missing-reference",
        "default-inherited",
        "recursive",
        "options",
        "extras-key-case",
        "tool-pitloom",
    ],
)
def test_a_bad_percent_fails_as_setuptools_does_naming_section_and_key(
    tmp_path: Path, body: str, where: str, reason: str
) -> None:
    setup_cfg = _write(tmp_path, body)
    with pytest.raises(ValueError) as caught:
        read_setup_cfg(tmp_path)
    message = str(caught.value)
    assert message.startswith(
        f"Could not parse setup.cfg: {quote_source(setup_cfg)} {where}: "
    )
    assert reason in message
    # '%%' mends a stray '%', not a missing key or a reference cycle
    stray = "names no key" not in reason and "nest deeper" not in reason
    assert message.endswith(
        "setuptools fails on it too"
        + ("; write a literal '%' as '%%'" if stray else "")
    )
    assert "\n" not in message
    assert "error" in _setuptools_read(setup_cfg)


@pytest.mark.parametrize(
    ("body", "description", "urls"),
    [
        ("description = 50%% faster", "50% faster", None),
        ("description = $HOME costs 5%%", "$HOME costs 5%", None),
        ("description = %(name)s tool", "demo tool", None),
        ("description = Schnell, 50%% größer", "Schnell, 50% größer", None),
        (
            "project_urls =\n    Docs = https://x.org/a%%20b",
            None,
            {"Docs": "https://x.org/a%20b"},
        ),
    ],
    ids=["escaped", "dollar", "defined-reference", "non-ascii", "urls-multiline"],
)
def test_a_value_setuptools_accepts_reads_the_same(
    tmp_path: Path, body: str, description: str | None, urls: dict[str, str] | None
) -> None:
    setup_cfg = _write(tmp_path, body)
    metadata = read_setup_cfg(tmp_path)[0]
    assert metadata.description == description
    assert _setuptools_read(setup_cfg) == {
        "description": description,
        "project_urls": urls,
    }
    if urls is not None:
        assert metadata.urls == urls


def test_a_duplicate_key_is_a_parse_error_not_a_percent_one(tmp_path: Path) -> None:
    """``configparser`` is strict, as for setuptools: the read fails before
    any value is interpolated, so the ``%%`` hint would mislead."""
    setup_cfg = _write(tmp_path, "description = a\ndescription = 50% b")
    with pytest.raises(ValueError, match="^Could not parse setup.cfg: ") as caught:
        read_setup_cfg(tmp_path)
    assert "'description'" in str(caught.value)
    assert "%%" not in str(caught.value)
    assert "error" in _setuptools_read(setup_cfg)


def test_a_key_with_a_display_control_is_escaped(tmp_path: Path) -> None:
    _write(tmp_path, "x\u202e = 5% off")
    with pytest.raises(ValueError) as caught:
        read_setup_cfg(tmp_path)
    assert "\u202e" not in str(caught.value)
    assert "x\\u202e" in str(caught.value)


def test_sdist_member_text_names_section_and_key() -> None:
    """The sdist route (``setup.cfg`` text) words it the same, unprefixed:
    the caller names the archive member."""
    text = _BASE + "[tool:pitloom]\npretty = 100% x\n"
    with pytest.raises(ValueError, match=r"^\[tool:pitloom\] pretty: '%' must "):
        setup_cfg_pitloom_config(text)


@pytest.mark.parametrize("command", ["project", "generate"])
def test_cli_prints_one_error_and_exits_1(
    tmp_path: Path,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "p"
    project.mkdir()
    _write(project, "description = 50% faster")
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["loom", command, str(project), "-o", str(out)])
    assert __main__.main() == 1
    errors = [x for x in capsys.readouterr().err.splitlines() if "ERROR" in x]
    assert len(errors) == 1
    assert errors[0].startswith("ERROR: ")
    assert "[metadata] description: " in errors[0]
    assert "'%%'" in errors[0]
    assert not out.exists()


def test_library_raises_the_same_error(tmp_path: Path) -> None:
    _write(tmp_path, "description = 50% faster")
    with pytest.raises(ValueError, match=r"\[metadata\] description: .*'%%'$"):
        generate_project_sbom(tmp_path, output_path=tmp_path / "out.json")


def test_an_extras_reference_finds_its_key_whatever_the_case(tmp_path: Path) -> None:
    """Extras keep the spelling they were written in (a marker is
    case-sensitive), but a ``%(key)s`` finds its key as it does for setuptools:
    case-insensitively, in the section or in ``[DEFAULT]``."""
    (tmp_path / "setup.cfg").write_bytes(
        b"[DEFAULT]\nBase = foo\n\n[metadata]\nname = demo\nversion = 1\n\n"
        b"[options.extras_require]\ndev = %(base)s\nX = bar\nY = %(x)s\n"
    )
    options, _ = read_setup_cfg_options(tmp_path)
    extras = options["extras_require"].value
    # setuptools gives the same values under lowercased keys (checked by hand
    # with setuptools.config.setupcfg.read_configuration on this file)
    assert extras == {"dev": ["foo"], "X": ["bar"], "Y": ["bar"], "Base": ["foo"]}
