# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/action/url-credentials.sh``: the ``::add-mask::``
lines for the credential-shaped pieces of a URL in a secret-capable input,
and the ``url-credentials`` and ``accept-url-credentials`` inputs, alone
(builtins only: the ``PATH`` holds no program) and through the "Generate
SBOM" step.

See also: :mod:`tests.scripts.action.test_generate_step_inputs` (every
input reaches the step), :mod:`tests.scripts.action._generate_step_shared`
(the ``generate`` fixture).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core.credential_policy import FINGERPRINT_RE
from tests.scripts.action._generate_step_shared import _Result

# Imported so pytest discovers the shared "generate" fixture here.
# The alias keeps ruff from merging this re-export into the import above.
# pylint: disable-next=unused-import,useless-import-alias
from tests.scripts.action._generate_step_shared import (  # noqa: F401
    generate_fixture as generate_fixture,
)
from tests.scripts.action.conftest import StubBin

_SECRET = "S3CRETVALUE"
_FP = "sha256:" + "0123456789abcdef"


def _call(
    stub_bin: StubBin, scripts_dir: Path, call: str, *values: str
) -> tuple[int, list[str]]:
    """Run ``call "$@"`` with *values* after sourcing the script, under the
    step's ``set -euo pipefail``; its exit status and output lines."""
    script = scripts_dir / "action" / "url-credentials.sh"
    result = stub_bin.run(
        ["-c", f'set -euo pipefail; . "$0"; loom_args=(); {call}', str(script), *values]
    )
    return result.returncode, (result.stdout + result.stderr).splitlines()


def _masks(stub_bin: StubBin, scripts_dir: Path, *values: str) -> list[str]:
    status, lines = _call(stub_bin, scripts_dir, 'mask_url_secrets "$@"', *values)
    assert status == 0
    assert all(line.startswith("::add-mask::") for line in lines), lines
    return [line.removeprefix("::add-mask::") for line in lines]


@pytest.mark.parametrize(
    ("value", "masked"),
    [
        (f"https://alice:{_SECRET}@h/r", [f"alice:{_SECRET}", _SECRET]),
        ("https://ghp_abcdefgh@h/r", ["ghp_abcdefgh"]),
        (f"https://h/r.git?token={_SECRET}", [f"token={_SECRET}", _SECRET]),
        (
            f"https://h/r.git?access_token={_SECRET}#x",
            [f"access_token={_SECRET}", _SECRET],
        ),
        (f"https://h/r.git#token={_SECRET}", [f"token={_SECRET}", _SECRET]),
        (
            f'"https://h/r?token={_SECRET}"',
            [f"token={_SECRET}", _SECRET],
        ),
        (
            f"'https://h/r#access_token={_SECRET}';",
            [f"access_token={_SECRET}", _SECRET],
        ),
        (f"(https://u:{_SECRET}@h/r),", [f"u:{_SECRET}", _SECRET]),
        (
            f"<https://h/r?a=1&token={_SECRET}>",
            [f"a=1&token={_SECRET}", f"token={_SECRET}", _SECRET],
        ),
        (f"https:/alice:{_SECRET}@h/r", [f"alice:{_SECRET}", _SECRET]),
        (f'"https:/alice:{_SECRET}@h"', [f"alice:{_SECRET}", _SECRET]),
        ("C:/build.agent@corp/x", []),
        ("123:/build.agent@corp/x", []),
        (f"--model=https:/u:{_SECRET}@h/x", [f"u:{_SECRET}", _SECRET]),
        (f'--x="https:/u:{_SECRET}@h/x"', [f"u:{_SECRET}", _SECRET]),
        (f"-m=https:/u:{_SECRET}@h/x", [f"u:{_SECRET}", _SECRET]),
        (f"--model=https://u:{_SECRET}@h/x", [f"u:{_SECRET}", _SECRET]),
        (f"https://h/r?token='{_SECRET}'", [f"token='{_SECRET}", _SECRET]),
        ("https://u:p%40ssword@h/r", ["u:p%2540ssword", "p%2540ssword"]),
        ("https://u:pw@h/r", []),
        ("https://u:pass5@h/r", ["u:pass5"]),
        ("https://abcdef@h/r", ["abcdef"]),
        ("https://abcde@h/r", []),
        ("https://h/o/r", []),
        ("https://h/a@b/r", []),
        (".", []),
        ("m.safetensors", []),
        ("", []),
    ],
    ids=[
        "userinfo",
        "token-user",
        "query",
        "query-and-fragment",
        "fragment",
        "double-quoted",
        "single-quoted",
        "bracketed",
        "angle-pairs",
        "one-slash",
        "one-slash-quoted",
        "drive",
        "digits",
        "option-one-slash",
        "option-quoted",
        "short-option",
        "option-two-slashes",
        "quoted-value",
        "percent",
        "short",
        "short-password",
        "six",
        "five",
        "plain",
        "at-in-path",
        "dot",
        "file",
        "empty",
    ],
)
def test_the_credential_pieces_of_a_url_are_masked(
    stub_bin: StubBin, scripts_dir: Path, value: str, masked: list[str]
) -> None:
    """A piece under 6 characters is not masked (it would hide every such
    run of the log); ``%`` is written ``%25``, which the runner decodes. A
    quote, bracket, ``,`` or ``;`` around a URL in ``args`` is no part of a
    mask (it would not match the URL printed without it); a query value is
    masked alone as well; ``https:/`` with one slash is a URL."""
    assert _masks(stub_bin, scripts_dir, value) == masked


def test_each_url_of_each_line_of_each_value_is_read(
    stub_bin: StubBin, scripts_dir: Path, tmp_path: Path
) -> None:
    """``args`` holds several words and lines; a ``*`` is never expanded
    against the working directory."""
    stub_bin.cwd = tmp_path
    (tmp_path / "file").write_text("", encoding="utf-8")
    args = f'--x "https://a:{_SECRET}1@h/*"\r\n\t--y https://b:{_SECRET}2@h/r'
    assert _masks(stub_bin, scripts_dir, ".", args) == [
        f"a:{_SECRET}1",
        f"{_SECRET}1",
        f"b:{_SECRET}2",
        f"{_SECRET}2",
    ]


@pytest.mark.parametrize(
    "text",
    [
        _FP,
        "sha256:" + "f" * 64,
        "sha256:" + "0" * 15,
        "sha256:" + "0" * 65,
        "sha256:" + "A" * 16,
        "sha256:",
        "sha1:" + "0" * 16,
        "0" * 16,
        f"sha256:{'0' * 8} {'0' * 8}",
        "sha256:" + "g" * 16,
    ],
    ids=["16", "64", "15", "65", "upper", "empty", "sha1", "bare", "space", "g"],
)
def test_the_fingerprint_shape_is_the_clis(
    stub_bin: StubBin, scripts_dir: Path, text: str
) -> None:
    """Drift guard: the script accepts exactly what ``loom`` accepts."""
    status, _ = _call(stub_bin, scripts_dir, '_is_fingerprint "$1"', text)
    assert (status == 0) == (FINGERPRINT_RE.fullmatch(text) is not None)


@pytest.mark.parametrize(
    ("mode", "accepted", "flags"),
    [
        ("", "", []),
        ("warn", "", []),
        ("refuse", "", ["--refuse-url-credentials"]),
        (
            "warn",
            f" {_FP} ,\n\nsha256:{'a' * 64}\r\n",
            ["--accept-url-credential", _FP]
            + ["--accept-url-credential", f"sha256:{'a' * 64}"],
        ),
    ],
    ids=["empty", "warn", "refuse", "list"],
)
def test_the_credential_inputs_become_their_flags(
    generate: Callable[..., _Result], mode: str, accepted: str, flags: list[str]
) -> None:
    result = generate(PL_URL_CREDENTIALS=mode, PL_ACCEPT_URL_CREDENTIALS=accepted)
    assert result.returncode == 0, result.output
    assert result.loom_args == ["project", ".", *flags]


@pytest.mark.parametrize(
    ("env", "error"),
    [
        (
            {"PL_ACCEPT_URL_CREDENTIALS": f"{_FP}\nhttps://u:{_SECRET}@h/r"},
            "::error::accept-url-credentials entry 2: not a fingerprint",
        ),
        ({"PL_URL_CREDENTIALS": "Refuse"}, "::error::url-credentials: must be"),
    ],
    ids=["pasted-url", "mode"],
)
def test_a_refused_input_fails_the_step_unprinted(
    generate: Callable[..., _Result], env: dict[str, str], error: str
) -> None:
    """The value is never echoed: a pasted entry may be the credential
    itself, so it is masked."""
    result = generate(**env)
    assert result.returncode == 1 and not result.loom_args
    assert error in result.output
    lines = result.output.splitlines()
    shown = [ln for ln in lines if not ln.startswith("::add-mask::")]
    assert not [ln for ln in shown if _SECRET in ln or "Refuse" in ln]
    masks = [ln.removeprefix("::add-mask::") for ln in lines if ln not in shown]
    pasted = [f"u:{_SECRET}", _SECRET, f"https://u:{_SECRET}@h/r"]
    assert masks == (pasted if _SECRET in str(env) else [])


def test_the_masks_come_before_any_other_output_of_the_step(
    generate: Callable[..., _Result],
) -> None:
    """A mask hides what is printed after it only."""
    result = generate(
        f"--creator-name x https://h/r?token={_SECRET}",
        PL_PROJECT_PATH=f"https://u:{_SECRET}@h/r",
        PL_MODEL=f"https://h/m#token={_SECRET}x",
        LOOM_STDERR=f"INFO: https://u:{_SECRET}@h/r\\n",
    )
    lines = result.output.splitlines()
    assert lines[:6] == [
        f"::add-mask::u:{_SECRET}",
        f"::add-mask::{_SECRET}",
        f"::add-mask::token={_SECRET}x",
        f"::add-mask::{_SECRET}x",
        f"::add-mask::token={_SECRET}",
        f"::add-mask::{_SECRET}",
    ]
    assert result.returncode == 0
