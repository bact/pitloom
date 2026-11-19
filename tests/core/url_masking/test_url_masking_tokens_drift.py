# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""No token shape (:mod:`pitloom.core.url_masking._tokens`) is narrower
than the one before the gitleaks shapes (a8425fb5): a seeded sample of
token-like strings, each the earlier shapes match, is matched still.

See also: test_url_masking_tokens.py (the shapes, row by row) in this
folder.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable

from pitloom.core.url_masking._tokens import TOKEN_RE

_END = "(?![A-Za-z0-9])"


def _mixed(chars: str, length: int, *, digit: bool = True) -> str:
    ahead = f"[{chars}]{{0,{length - 1}}}"
    need = ("[0-9]", "[A-Z]", "[a-z]") if digit else ("[A-Z]", "[a-z]")
    return "".join(f"(?={ahead}{one})" for one in need) + f"[{chars}]{{{length}}}"


_GITLAB = _mixed("A-Za-z0-9_-", 20)
_HF = _mixed("A-Za-z", 34, digit=False) + _END
#: The shapes as a8425fb5 wrote them, but for AWS, whose key ids are read
#: as base32 now on purpose (``ASIAPACIFICREGION123`` is none).
_EARLIER: tuple[tuple[str, str], ...] = (
    *((f"gh{kind}_", f"[A-Za-z0-9]{{36}}{_END}") for kind in "porsu"),
    ("github_pat_", f"[A-Za-z0-9]{{22}}_[A-Za-z0-9]{{59}}{_END}"),
    *((p, _GITLAB) for p in ("glpat-", "gldt-", "glptt-", "glrt-", "gloas-", "glcbt-")),
    *((f"xox{kind}-", "[0-9]{1,15}-[0-9]{1,15}-[A-Za-z0-9]{8}") for kind in "abeprs"),
    ("xapp-", "[0-9]{1,3}-[A-Z0-9]{8,15}-[0-9]{1,15}-[A-Za-z0-9]{8}"),
    ("hf_", _HF),
    ("api_org_", _HF),
    ("pypi-", "AgE[A-Za-z0-9_-]{50}"),
    ("npm_", f"[A-Za-z0-9]{{36}}{_END}"),
)
_EARLIER_RE = re.compile(
    "|".join(f"{re.escape(prefix)}{body}" for prefix, body in _EARLIER)
)
_B62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _run(draw: random.Random, chars: str, low: int, high: int) -> str:
    return "".join(draw.choices(chars, k=draw.randint(low, high)))


def _number(draw: random.Random, high: int = 10**15 - 1) -> int:
    return draw.randint(0, high)


#: Each kind of piece of a token-like body.
_PARTS: tuple[Callable[[random.Random], str], ...] = (
    lambda d: _run(d, "0123456789", 1, 16),
    lambda d: "-",
    lambda d: _run(d, _B62[26:], 8, 15),
    lambda d: _run(d, _B62 + "_-", 1, 40),
    lambda d: "AgE" + _run(d, _B62 + "_-", 45, 60),
    lambda d: _run(d, _B62[:52], 30, 36),
    lambda d: "_",
    lambda d: _run(d, _B62, 8, 40),
    lambda d: f"{_number(d)}-{_number(d)}-",
    lambda d: f"{_number(d, 999)}-{_run(d, _B62[26:], 7, 16)}-{_number(d)}-",
    lambda d: _run(d, _B62, 21, 23) + "_" + _run(d, _B62, 58, 60),
)


def _part(draw: random.Random) -> str:
    """One piece of a token-like body."""
    return _PARTS[draw.randrange(len(_PARTS))](draw)


def test_every_string_the_earlier_shapes_matched_is_matched_still() -> None:
    """A seeded sample, and a fine-grained GitHub token followed by ``_``
    (once lost to a narrower end), which an earlier shape matched."""
    pat = "github_pat_" + "aB3" * 7 + "a_" + "aB3" * 19 + "aB_x"
    shortest_app = "xapp-1-A0T0KEN12-1-abcd1234"
    for text in (pat, shortest_app):
        assert _EARLIER_RE.match(text) and TOKEN_RE.match(text)
    draw = random.Random(489)
    prefixes = [prefix for prefix, _ in _EARLIER]
    matched = 0
    for _ in range(20_000):
        text = draw.choice(prefixes) + "".join(
            _part(draw) for _ in range(draw.randint(1, 6))
        )
        if _EARLIER_RE.match(text):
            matched += 1
            assert TOKEN_RE.match(text), text
    # Not vacuous: a good share of the sample is a token of an earlier shape.
    assert matched > 2_000, matched
