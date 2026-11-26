# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A credential URL behind a leading character that may not start a URL
(``!https://u:p@h``), in a project URL or a dependency's direct reference
alone, is warned of in the ``warn`` mode and refused in the ``refuse``
mode on ``loom generate``, the library and the Hatchling hook, with no
secret in stderr or a log record.

See also: tests/test_credential_surfaces.py (the surfaces, every value
holding a secret at once), tests/test_credential_surfaces_warn.py (the
``warn`` mode) and tests/core/url_masking/test_url_masking_detect.py (the
detector's first-word reading).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.core.config import PitloomConfig
from pitloom.logging_config import CODE_ATTR
from tests._author_routes import hook_sbom

pytestmark = pytest.mark.platform

_CLEAN_DEP = "foo @ https://h.example/x.whl"
_CLEAN_HOME = "https://e.example/h"
#: Each value alone holding the secret: (Homepage, dependency).
_VALUES = {
    "homepage": ("!https://u:S3CRET@e.example/h", _CLEAN_DEP),
    "dependency": (_CLEAN_HOME, "foo @ !https://a:S3CRET@h.example/x.whl"),
}
_WHEN = "2026-01-01T00:00:00Z"


def _project(tmp: Path, value: str, refusing: bool) -> Path:
    home, dep = _VALUES[value]
    proj = tmp / "proj"
    (proj / "testpkg").mkdir(parents=True)
    (proj / "testpkg" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        "[project]\nname = 'testpkg'\nversion = '0.1.0'\n"
        f"dependencies = ['{dep}']\n[project.urls]\nHomepage = '{home}'\n"
        "[tool.hatch.metadata]\nallow-direct-references = true\n"
        + ('[tool.pitloom]\nurl-credentials = "refuse"\n' if refusing else ""),
        encoding="utf-8",
    )
    return proj


def _cli(tmp: Path, mp: pytest.MonkeyPatch, value: str, refusing: bool) -> None:
    out = tmp / "o.json"
    argv = ["loom", "generate", str(_project(tmp, value, False)), "-o", str(out)]
    argv += ["--offline", "--creation-datetime", _WHEN]
    mp.setattr(sys, "argv", argv + (["--refuse-url-credentials"] if refusing else []))
    if main() != 0:
        raise ValueError("refused")


def _library(tmp: Path, _mp: pytest.MonkeyPatch, value: str, refusing: bool) -> None:
    config = PitloomConfig(url_credentials="refuse" if refusing else "warn")
    generate_project_sbom(
        _project(tmp, value, False),
        output_path=tmp / "o.json",
        offline=True,
        pitloom_config=config,
    )


def _hook(tmp: Path, _mp: pytest.MonkeyPatch, value: str, refusing: bool) -> None:
    (tmp / "o.json").write_text(
        hook_sbom(_project(tmp, value, refusing)), encoding="utf-8"
    )


_SURFACES = {"cli-generate": _cli, "library": _library, "hook": _hook}


#: Each (value holding the secret, whether in the ``refuse`` mode).
_CASES = [(value, refusing) for value in sorted(_VALUES) for refusing in (False, True)]


@pytest.mark.parametrize(
    "case", _CASES, ids=[f"{v}-{'refuse' if r else 'warn'}" for v, r in _CASES]
)
@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_a_credential_behind_a_leading_character_is_warned_or_refused(
    surface: str,
    case: tuple[str, bool],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    value, refusing = case
    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        if refusing:
            with pytest.raises(ValueError):
                _SURFACES[surface](tmp_path, monkeypatch, value, True)
        else:
            _SURFACES[surface](tmp_path, monkeypatch, value, False)
    _, err = capsys.readouterr()
    assert "S3CRET" not in err + caplog.text
    codes = [getattr(r, CODE_ATTR, "") for r in caplog.records]
    if refusing:
        assert "credentials-unsafe/refused" in codes
        assert not (tmp_path / "o.json").exists()
    else:
        assert "credentials-unsafe/written" in codes
        assert "S3CRET" in (tmp_path / "o.json").read_text(encoding="utf-8")
