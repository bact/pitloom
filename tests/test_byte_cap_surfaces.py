# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A bad byte cap (``max-source-metadata-bytes``, ``max-model-extract-bytes``)
is refused on every flag and library surface, even where the target cannot
use it, before any warning.

See also: :mod:`tests.test_config_key_surfaces` (the config-key surfaces and
the helpers shared here).
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pitloom.assemble import (
    generate,
    generate_env_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.cli.parser import _build_parser
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides, apply_overrides
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import embed_wheel_sbom
from pitloom.messages import MESSAGES, code_of
from tests.argument_errors import integer_refusal
from tests.assemble.conftest import _make_dummy_wheel
from tests.test_config_key_surfaces import (
    _HEAD,
    _OFFLINE,
    _PINNED,
    _cli,
    _loom,
    _project,
)
from tests.warning_helpers import logged_warnings


def _subcommands(flag: str = "--max-source-metadata-bytes") -> list[str]:
    """Every subcommand that offers *flag*."""
    # pylint: disable-next=protected-access
    actions = _build_parser()._actions
    # pylint: disable-next=protected-access
    (sub,) = [a for a in actions if isinstance(a, argparse._SubParsersAction)]
    return sorted(
        name for name, parser in sub.choices.items() if flag in parser.format_help()
    )


_SOURCE = "--max-source-metadata-bytes"
_MODEL = "--max-model-extract-bytes"


@pytest.mark.parametrize("command", _subcommands())
@pytest.mark.parametrize(
    ("flag", "value", "text"),
    [
        (_SOURCE, "-1", f"argument {_SOURCE}: must be 0 (no cap) or an integer"),
        (_SOURCE, "5", "of at least 8, got an integer 5"),
        (_SOURCE, "x", "must be an integer, got a string 'x'"),
        (_MODEL, "0", f"argument {_MODEL}: must be an integer of at least 1, got"),
        (_MODEL, "-1", "of at least 1, got an integer -1"),
        (_MODEL, "abc", "must be an integer, got a string 'abc'"),
    ],
    ids=["src-neg", "src-5", "src-x", "model-0", "model-neg", "model-abc"],
)
def test_flag_refuses_a_bad_value_on_every_subcommand(
    command: str,
    flag: str,
    value: str,
    text: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        _build_parser().parse_args([command, flag, value])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert text in err
    assert err.rstrip().endswith("[option-invalid]")  # the flag stage's code


def test_flag_is_offered_by_the_sbom_subcommands() -> None:
    """Not vacuous: the parametrisation above found the commands, and both
    caps are offered by the same ones."""
    assert {"project", "wheel", "embed-wheel"} <= set(_subcommands())
    assert _subcommands(_MODEL) == _subcommands()


def test_loom_flag_too_small_exits_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path, "p", _HEAD)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        _loom(
            ["project", str(project), "--max-source-metadata-bytes", "-1"], monkeypatch
        )
    assert exc.value.code == 2


def _library_calls(tmp_path: Path) -> dict[str, Callable[[int], Any]]:
    project = _project(tmp_path, "p", _HEAD)
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")
    sbom_wheel = _make_dummy_wheel(tmp_path / "x", "demo", "1.0.0")
    return {
        "project": lambda n: generate_project_sbom(
            project, creation_metadata=_PINNED, max_source_metadata_bytes=n
        ),
        "wheel": lambda n: generate_wheel_sbom(
            wheel, creation_metadata=_PINNED, max_source_metadata_bytes=n
        ),
        "env": lambda n: generate_env_sbom(
            creation_metadata=_PINNED, max_source_metadata_bytes=n
        ),
        "embed": lambda n: embed_wheel_sbom(
            wheel, overrides=ConfigOverrides(max_source_metadata_bytes=n)
        ),
        "embed-inert-sbom": lambda n: embed_wheel_sbom(
            sbom_wheel,
            sbom_path=_sbom_file(tmp_path),
            overrides=ConfigOverrides(max_source_metadata_bytes=n),
        ),
        "overrides": lambda n: apply_overrides(
            PitloomConfig(), ConfigOverrides(max_source_metadata_bytes=n)
        ),
        "provenance-config": lambda n: ProvenanceConfig(max_source_metadata_bytes=n),
        "pitloom-config": lambda n: (
            PitloomConfig(provenance_max_source_metadata_bytes=n).provenance
        ),
    }


def _sbom_file(tmp_path: Path) -> Path:
    """An SBOM for ``demo`` 1.0.0, to hand to ``embed_wheel_sbom(sbom_path=)``."""
    path = tmp_path / "s.json"
    path.write_text(
        generate_wheel_sbom(
            _make_dummy_wheel(tmp_path / "y", "demo", "1.0.0"),
            creation_metadata=_PINNED,
        ),
        encoding="utf-8",
    )
    return path


_CALLS = [
    "project",
    "wheel",
    "env",
    "embed",
    "embed-inert-sbom",
    "overrides",
    "provenance-config",
    "pitloom-config",
]


@pytest.mark.parametrize("value", [-1, 1, 7, 4096.0, True])
@pytest.mark.parametrize("call", _CALLS)
def test_library_refuses_an_invalid_budget(
    call: str, value: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An ``option-invalid`` error (a library parameter, not a file), with no
    warning ahead of it (not even the inert one)."""
    calls = _library_calls(tmp_path)
    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(
            integer_refusal(value), match="max_source_metadata_bytes: must be"
        ) as exc,
    ):
        calls[call](value)
    assert code_of(exc.value) == "option-invalid"
    assert not logged_warnings(caplog)


def test_a_library_config_names_itself_in_the_error() -> None:
    config = PitloomConfig(provenance_max_source_metadata_bytes=3)
    with pytest.raises(
        ValueError,
        match=r"^PitloomConfig\.provenance_max_source_metadata_bytes: must be",
    ) as exc:
        _ = config.provenance
    assert code_of(exc.value) == "option-invalid"


@pytest.mark.parametrize("call", ["overrides", "provenance-config", "pitloom-config"])
@pytest.mark.parametrize("value", [0, 8, 4096, np.int64(4096)])
def test_library_accepts_zero_and_a_real_budget(
    call: str, value: int, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The control: ``0`` (unlimited) and a usable budget stay valid, quietly."""
    with caplog.at_level(logging.WARNING):
        _library_calls(tmp_path)[call](value)
    assert not logged_warnings(caplog)


# --- max_model_extract_bytes: a library keyword and an override --------------


def _model_cap_calls(tmp_path: Path) -> dict[str, Callable[[Any], Any]]:
    """Every library surface of the model cap; the inert ones validate too."""
    project = _project(tmp_path, "p", _HEAD)
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")

    def embed(**kwargs: Any) -> Callable[[Any], Any]:
        return lambda n: embed_wheel_sbom(
            wheel, overrides=ConfigOverrides(max_model_extract_bytes=n), **kwargs
        )

    return {
        "generate-wheel": lambda n: generate(wheel, max_model_extract_bytes=n),
        "generate-project-inert": lambda n: generate(
            project, max_model_extract_bytes=n
        ),
        "wheel": lambda n: generate_wheel_sbom(wheel, max_model_extract_bytes=n),
        "embed": embed(),
        "embed-project-inert": embed(project_dir=project),
        "embed-sbom-inert": embed(sbom_path=_sbom_file(tmp_path)),
        "overrides": lambda n: apply_overrides(
            PitloomConfig(), ConfigOverrides(max_model_extract_bytes=n)
        ),
    }


_MODEL_CAP_CALLS = [
    "generate-wheel",
    "generate-project-inert",
    "wheel",
    "embed",
    "embed-project-inert",
    "embed-sbom-inert",
    "overrides",
]


@pytest.mark.parametrize("value", [0, -1, True, 4096.0, "4096"], ids=repr)
@pytest.mark.parametrize("call", _MODEL_CAP_CALLS)
def test_library_refuses_an_invalid_model_cap(
    call: str, value: object, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An error naming the keyword, with no warning ahead of it (not even
    the inert one)."""
    calls = _model_cap_calls(tmp_path)
    assert sorted(calls) == sorted(_MODEL_CAP_CALLS)
    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(
            integer_refusal(value), match="^max_model_extract_bytes: must be"
        ) as exc,
    ):
        calls[call](value)
    assert code_of(exc.value) == "option-invalid"
    assert not logged_warnings(caplog)


@pytest.mark.parametrize("value", [1, np.int64(4096)], ids=repr)
def test_library_accepts_a_numpy_model_cap(value: int) -> None:
    merged = apply_overrides(
        PitloomConfig(), ConfigOverrides(max_model_extract_bytes=value)
    )
    assert merged.max_model_extract_bytes == value
    assert isinstance(merged.max_model_extract_bytes, int)  # not numpy's


# --- one bad value, three stages, three codes --------------------------------

_STAGES: dict[str, tuple[list[str], str, dict[str, Any]]] = {
    "model": (
        ["--max-model-extract-bytes", "0"],
        "[tool.pitloom]\nmax-model-extract-bytes = 0\n",
        {"max_model_extract_bytes": 0},
    ),
    "source": (
        ["--max-source-metadata-bytes", "-1"],
        "[tool.pitloom.provenance]\nmax-source-metadata-bytes = -1\n",
        {"max_source_metadata_bytes": -1},
    ),
}


@pytest.mark.parametrize("cap", sorted(_STAGES))
def test_one_bad_cap_has_a_code_per_stage(
    cap: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The same bad value is ``option-invalid`` as a flag (argparse, exit 2)
    and as a library keyword, but ``config-invalid`` (exit 1) read from a
    file: the stage picks the code, not the text."""
    flag, file_tail, keyword = _STAGES[cap]
    project = _project(tmp_path, "flag", _HEAD)
    with pytest.raises(SystemExit) as flag_exit:
        _loom(["project", str(project), *flag, *_OFFLINE], monkeypatch)
    flag_err = capsys.readouterr().err
    assert flag_exit.value.code == 2
    assert flag_err.rstrip().endswith("[option-invalid]")
    assert f"argument {flag[0]}: must be" in flag_err

    file_project = _project(tmp_path, "file", _HEAD + file_tail)
    status, file_err = _cli(
        ["project", str(file_project), *_OFFLINE], monkeypatch, capsys
    )
    assert status == 1
    assert file_err.rstrip().endswith("[config-invalid]")
    assert "FILE=" in file_err
    assert "argument" not in file_err

    with pytest.raises(ValueError, match=": must be") as lib_exc:
        generate(project, creation_metadata=_PINNED, **keyword)
    assert code_of(lib_exc.value) == "option-invalid"
    assert "FILE=" not in str(lib_exc.value)
    assert [MESSAGES[c].actor for c in ("option-invalid", "config-invalid")] == [
        "caller",
        "user",
    ]
