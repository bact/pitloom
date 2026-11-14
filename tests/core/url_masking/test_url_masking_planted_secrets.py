# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A property test of :func:`pitloom.core.url_masking.masked_given_path`: a
secret planted in a URL inside random text never shows, and masking the
masked text changes nothing.

See also: test_url_masking_given_path.py (the cases one by one) in this
folder.
"""

from __future__ import annotations

import random

import pytest

from pitloom.core.url_masking import masked_given_path

#: What the text around the URL is made of: separators, quotes, delimiters
#: and the starts of other URLs.
_NOISE = [*"a:/@?&=#;,\\ .%'\"\n\t", "https", "ftp", "s3", "://", ":/", ":\\", "\\'"]
#: What a password may hold besides the secret (no ``/`` or white space:
#: RFC 3986 percent-encodes both).
_PASSWORD = "a:@?%'\"=\\"
#: What a secret parameter value may hold besides the secret (no ``&``,
#: ``;``, ``#``: they end it; no white space: a line ends it there).
_VALUE = "a:@?%'\"=/."
_SCHEMES = ["https", "ftp", "s3", "hf", "git+ssh", "ldap", "rsync", "foo"]
_SEPARATORS = ["://", ":/", ":\\", ":\\\\"]
_NAMES = ["token", "access_token", "X-Amz-Signature", "password", "apiKey"]


def _planted(rng: random.Random, secret: str) -> str:
    """Random text holding one URL with *secret* in its password, its query
    or both, quoted or not."""

    def noise(size: int) -> str:
        return "".join(rng.choice(_NOISE) for _ in range(rng.randint(0, size)))

    def around(chars: str) -> str:
        return "".join(rng.choice(chars) for _ in range(2))

    scheme = rng.choice(_SCHEMES)
    separator = rng.choice(_SEPARATORS[::3] if scheme == "foo" else _SEPARATORS)
    kind = rng.choice(["userinfo", "query", "both"])
    userinfo = (
        f"u:{around(_PASSWORD)}{secret}{around(_PASSWORD)}@" if kind != "query" else ""
    )
    path = "\\h\\p" if "\\" in separator else "/h/p"
    value = f"{around(_VALUE)}{secret}{around(_VALUE)}"
    query = f"?a=1&{rng.choice(_NAMES)}={value}" if kind != "userinfo" else ""
    lead = rng.choice([" ", "\n", "(", "=", "'", '"'])
    close = lead if lead in "'\"" else rng.choice([" ", "\n", ",", ""])
    url = f"{scheme}{separator}{userinfo}h{path}{query}"
    return noise(12).replace("\n", " ") + lead + url + close + noise(12)


@pytest.mark.parametrize("seed", [7, 11, 2026])
def test_a_planted_secret_never_shows(seed: int) -> None:
    """300 random texts per seed, each masked as a path and as a line: the
    secret is gone, and masking again changes nothing."""
    rng = random.Random(seed)
    for index in range(300):
        secret = f"QZ{index:04d}K"
        text = _planted(rng, secret)
        for line in (False, True):
            masked = masked_given_path(text, line=line)
            assert secret not in masked, (text, line)
            assert masked_given_path(masked, line=line) == masked, (text, line)
