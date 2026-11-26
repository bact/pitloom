# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests that :func:`pitloom.core.url_masking.masked_given_path` masks an
adversarial text, as a path and as a line, in time linear in its length.

See also: test_url_masking_given_path.py (what a given path or line shows)
in this folder.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pitloom.core.url_masking import masked_given_path
from tests._linear_time import RATIO_BOUND, linear_ratio, settled_ratio

#: Each adversarial text, of about *n* characters.
_ADVERSARIAL: dict[str, Callable[[int], str]] = {
    "long-query": lambda n: "https://" + "a" * n + "?" + "x=1&" * (n // 4),
    "long-camel-name": lambda n: "https://h/?" + "aB" * (n // 2) + "=1",
    "windows-ats": lambda n: "https:\\" + "@\\" * (n // 3),
    "long-name": lambda n: "https:/" + "?" + "a" * n,
    "many-urls": lambda n: "'ab:/=" * (n // 6),
    "scheme-run": lambda n: "a1" * (n // 2),
    "glued-urls": lambda n: "https://" * (n // 8),
    "windows-no-at": lambda n: "ab:\\a " * (n // 6),
    "windows-no-slash": lambda n: "ab:\\a" * (n // 5) + " @",
    "url-in-values": lambda n: "https://h/?token=ab:/" * (n // 20),
    "one-at-at-the-end": lambda n: "ab:/" * (n // 4) + "@",
    "escaped-quotes": lambda n: "'ab:/\\'" * (n // 7),
    "values-over-slashes": lambda n: "https:\\h" + "?token=a/b&c@d" * (n // 14),
    "secret-slash-chain": lambda n: "'https:/" + "#sig=/'@" * (n // 8),
    "secret-space-chain": lambda n: "'hx:/" + "&token= '@" * (n // 10),
    "skipped-stops": lambda n: "ab:/?a=?token=" * (n // 14) + "&/x@",
    "quote-tails": lambda n: "'ab:/" + "x'." * (n // 3),
    "escape-runs": lambda n: "\\t" * (n // 2),
    "escaped-near-tokens": lambda n: ("\\x1bglpat-" + "Ab1" * 6) * (n // 28),
    "scheme-separators": lambda n: "Bearer" + "\\t" * (n // 2) + "!",
    "scheme-short-runs": lambda n: "bearer abc\\t" * (n // 12),
    "scheme-long-run": lambda n: "Bearer " + "aB3" * (n // 3),
    "header-runs": lambda n: "Authorization: Bearer x " * (n // 24),
    "header-gaps": lambda n: "authorization" + " " * n + "x",
    "scheme-pct20-chain": lambda n: "Bearer%20x." * (n // 11),
    "basic-pct20-chain": lambda n: "Basic%20QQ==." * (n // 13),
    "header-pct20-chain": lambda n: "Authorization=x%20a." * (n // 20),
    "word-pct20-chain": lambda n: "a.Bearer%20" * (n // 11),
    "ansi-raw": lambda n: "\x1b[33m" * (n // 5),
    "ansi-escaped": lambda n: "\\x1b[33m" * (n // 8),
    "ansi-escaped-twice": lambda n: "\\\\x1b[33m" * (n // 9),
    "ansi-long-params": lambda n: ("\x1b[" + "1;" * 8 + "m") * (n // 19),
    "m-run": lambda n: "m" * n,
    "digit-m-run": lambda n: "1m" * (n // 2),
    "ansi-token-prefix": lambda n: ("\x1b[1mghp_" + "a" * 20) * (n // 30),
    "secret-header": lambda n: "X-Api-Key: " * (n // 11),
    "secret-header-no-space": lambda n: "X-Api-Key:" * (n // 10),
    "secret-header-scheme": lambda n: "X-Api-Key: Bearer " * (n // 18),
    "header-name-run": lambda n: "X-A-" * (n // 4) + ":",
    "dash-colon": lambda n: "a-b:" * (n // 4),
    "cookie-pairs-one": lambda n: "Cookie: " + "a=b; " * (n // 5),
    "cookie-headers": lambda n: "Cookie: a=b; " * (n // 13),
    "set-cookie-headers": lambda n: "Set-Cookie: a=b; Path=/; " * (n // 25),
    "cookie-quoted-pairs": lambda n: 'Cookie: "' + "a=b " * (n // 4),
    "json-cookie-keys": lambda n: '{"Cookie": "' * (n // 12),
    "header-lf": lambda n: "Authorization: Bearer\n" * (n // 22),
    "header-lf-run": lambda n: "Authorization: Bearer" + "\n" * n + "x:",
    "header-escaped-lf": lambda n: "Authorization: Bearer\\n" * (n // 23),
    "scheme-lf-letters": lambda n: "Bearer\n" + "a" * n,
    "bearer-quote": lambda n: "Bearer '" * (n // 8),
    "header-quote": lambda n: "Authorization: Bearer '" * (n // 23),
    "scp-ats": lambda n: "a:b" + "@b" * (n // 2),
    "scp-ats-repeat": lambda n: "a:b@" * (n // 4),
    "scp-ats-host": lambda n: "a:" + "b@" * (n // 2) + "h:",
    "scp-at-run": lambda n: "a:" + "@" * n + "h:",
    "scp-at-colons": lambda n: "a:@" * (n // 3),
    "header-word-breaks": lambda n: "Authorization: abc" + "\n " * (n // 2) + "x",
    "header-word-lf": lambda n: "Authorization: sk-live-x1\nmore " * (n // 30),
    "header-cr-runs": lambda n: "Authorization: Bearer\r" * (n // 22),
    "header-unicode-breaks": lambda n: "Authorization: Bearer" + "\u2028" * n,
    "header-indented-name": lambda n: "Authorization: Bearer\n" + " " * n + "X:",
    "header-indented-names": lambda n: "Authorization: x\n  X-A: " * (n // 24),
    "header-ansi": lambda n: "Authorization: Bearer " + "\x1b[1m" * (n // 4),
    "bearer-ansi-colon": lambda n: "Bearer \x1b[38:5:1m" * (n // 18),
    "triple-quotes": lambda n: '\\\\\\"X-Api-Key\\\\\\": ' * (n // 22),
    "header-pairs": lambda n: '("X-Api-Key", ' * (n // 14),
    "authorization-pairs": lambda n: '("Authorization", ' * (n // 18),
    "pair-gap": lambda n: '"X-Api-Key",' + " " * n + "x",
    "cookie-quoted-open": lambda n: "Cookie: " + 'a="b ' * (n // 5),
    "cookie-quote-run": lambda n: 'Cookie: a="' + "b " * (n // 2),
    "empty-values-lines": lambda n: "https://h/x" + "?token=\n" * (n // 8),
    "empty-value-spaces": lambda n: "https://h/x?token=" + " " * n + "x",
    "empty-value-spaces-lines": lambda n: "https://h/x" + "&token= \t\n" * (n // 10),
}


@pytest.mark.parametrize(
    ("ratios", "passes"),
    [
        ([16.0, 5.0], True),
        ([16.0, 17.0, 5.0], True),
        ([25.0, 24.0, 26.0], False),
        ([16.0, 17.0, 18.0, 5.0], False),
    ],
    ids=["noisy-once", "noisy-twice", "quadratic", "past-the-tries"],
)
def test_a_noisy_ratio_is_measured_again_but_a_quadratic_one_fails(
    ratios: list[float], passes: bool
) -> None:
    """One slow run on a shared runner (16 against a bound of 15) must not
    fail the linear-time test, and three tries over the bound still do."""
    queue = iter(ratios)
    assert (settled_ratio(lambda: next(queue)) < RATIO_BOUND) is passes


@pytest.mark.parametrize("line", [False, True], ids=["path", "line"])
@pytest.mark.parametrize("shape", sorted(_ADVERSARIAL))
def test_a_given_path_is_masked_in_linear_time(shape: str, line: bool) -> None:
    """Masking an adversarial text five times as long takes about five times
    as long (a quadratic masker: twenty-five). The ratio, not a wall-clock
    bound, so a slow or loaded runner, or coverage tracing, cancels out;
    each time is the best of three, a run under 5 ms counts as 5 ms, and a
    ratio over the bound is measured again (at most three tries)."""
    make = _ADVERSARIAL[shape]
    ratio = linear_ratio(lambda text: masked_given_path(text, line=line), make)
    assert ratio < RATIO_BOUND, f"ratio {ratio:.1f}"
