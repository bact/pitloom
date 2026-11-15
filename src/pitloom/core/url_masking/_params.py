# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The query and fragment parameters of a URL that hold a secret: which
names do, and the masking of their values.

See also: :mod:`pitloom.core.url_masking` (the public functions) and
:mod:`pitloom.core.url_masking._scan` (the scanner of a path or a line).
Standard library only.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

#: The characters of a parameter name: word characters, ``.``, ``%``, ``-``
#: and the brackets of an array or a map (``token[]``, ``secret[key]``).
_NAME = r"[\w.%\[\]-]+"
#: A query or fragment parameter in free text, as ``(delimiter, name,
#: value)``; the value ends at white space. The name has no length bound: it
#: is a run of name characters after one delimiter, so a failed match
#: backtracks over that run only and matching stays linear.
PARAM_RE = re.compile(rf"([?&;#])({_NAME})=([^&;#\s]*)")
#: What ends a sentence or a quotation after a value in free text: not part
#: of the value (``?token=***: not a project``, ``'...?token=***'``).
_VALUE_TAIL = ":.,)]'\""
#: The same in a text that is one URL (:func:`sanitize_url`): the value runs
#: over a space, a line break or a quote (RFC 3986 allows ``'``), to the
#: next delimiter or the end.
WHOLE_PARAM_RE = re.compile(rf"([?&;#])({_NAME})=([^&;#]*)")
#: The ``delimiter name=`` that starts a parameter (of either pattern).
PARAM_HEAD = rf"[?&;#](?P<name>{_NAME})="

#: Words naming a secret: a parameter is named by one, or its last word is
#: one (``access_token``, ``db-password``, ``accessToken``,
#: ``X-Amz-Signature``).
_SECRET_WORDS = (
    *("token", "key", "secret", "password", "passwd", "signature", "sig"),
    *("jwt", "credential", "credentials", "auth", "hmac", "verifier"),
    *("passphrase", "passcode", "bearer", "creds"),
)
#: Names that hold a secret only sometimes (``code=utf8``, ``session=2024``):
#: masked in a message, never removed from an SBOM. ``session_id`` and its
#: spellings are no weak name: they are secrets (:data:`_SECRET_NAMES`).
WEAK_SECRET_NAMES = frozenset({"code", "session", "ticket", "sid", "otp"})
#: Names of a parameter that hold a secret, matched whole (as
#: :func:`plain_name` writes them).
_SECRET_NAMES = frozenset(
    {*_SECRET_WORDS, "apikey", "pass", "pwd", "pw", "authorization"}
    | {"session_id", "sessionid", "jsessionid", "phpsessid", "privatekey"}
    | {"userpwd", "tokens"}
)
#: The endings of such a name: ``_`` and a word (``monkey`` and ``author``
#: are not secrets).
_SECRET_ENDINGS = tuple(f"_{word}" for word in _SECRET_WORDS)
#: Where a camelCase name starts a word: ``accessToken`` is read as
#: ``access_token``.
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
#: The index of an array (``token[]``, ``token[0]``) or the key of a map
#: (``user[password]``), read as a last word.
_BRACKET = re.compile(r"\[([^\[\]]*)\]")
#: Last words that only number or describe a name's value (``token_v2``,
#: ``token.value``): a name is read without them.
_NOISE_ENDINGS = ("_v", "_value", "_val")
#: What a name is read without at its end (``token1``, ``token_``).
_NOISE_TAIL = "_0123456789"
#: How many times a name is percent-decoded at most (``t%256Fken``).
_DECODE_ROUNDS = 3

#: Names a secret key goes by: ``sort_key`` and ``primary-key`` are not
#: secrets, ``api_key`` is.
_SECRET_KEYS = tuple(
    f"{kind}_key"
    for kind in ("api", "access", "secret", "private", "signing", "auth", "ssh")
) + ("session_key", "license_key", "encryption_key")
#: The words whose ending makes a name a secret to remove from an SBOM.
_STRIP_WORDS = tuple(w for w in _SECRET_WORDS if w not in {"key", "sig", "auth"})
#: Words a name may end in without a separator (``accesstoken``).
_JOINED_WORDS = (
    *("token", "secret", "password", "passwd", "signature", "passphrase"),
    *("sessionid", "privatekey"),
)
#: The endings that make a name removed from an SBOM.
_STRIP_ENDINGS = (
    *(f"_{word}" for word in (*_STRIP_WORDS, *_SECRET_KEYS)),
    *_JOINED_WORDS,
)
#: The endings that make a name masked in a message.
_MASK_ENDINGS = (*_SECRET_ENDINGS, *_JOINED_WORDS)


def _bracket_word(match: re.Match[str]) -> str:
    inner = match.group(1)
    return "" if not inner or inner.isdigit() else f"_{inner}"


def plain_name(name: str) -> str:
    """The parameter *name* as the secret names are written: percent-decoded
    (at most :data:`_DECODE_ROUNDS` times), without a trailing ``=``
    (``token%3D=v`` is a parameter named ``token=``: a server may decode
    it), a bracket's key read as a last word and an index dropped
    (``token[0]``), camelCase read as words, lower case, ``-`` and ``.``
    read as ``_``, and without trailing digits, ``_`` or a word that numbers
    or describes the value (``token1``, ``token_``, ``token-v2``,
    ``token.value``)."""
    plain = name
    for _ in range(_DECODE_ROUNDS):
        if "%" not in plain:
            break
        plain = unquote(plain)
    plain = _BRACKET.sub(_bracket_word, plain.rstrip("="))
    if not plain.islower():
        plain = _CAMEL_BOUNDARY.sub("_", plain).lower()
    plain = plain.replace("-", "_").replace(".", "_").rstrip(_NOISE_TAIL)
    for ending in _NOISE_ENDINGS:
        if plain.endswith(ending):
            return plain[: -len(ending)].rstrip(_NOISE_TAIL)
    return plain


def is_weak_name(name: str) -> bool:
    """Whether the parameter *name* holds a secret only sometimes
    (:data:`WEAK_SECRET_NAMES`): kept in an SBOM, masked in a message."""
    return plain_name(name) in WEAK_SECRET_NAMES


def is_secret_name(name: str, *, weak: bool = True) -> bool:
    """Whether the parameter *name* names a secret (:data:`_SECRET_NAMES`,
    :data:`_SECRET_ENDINGS`), read as :func:`plain_name`; with *weak* false
    (the removal from an SBOM), only a whole name or an ending that is a
    secret whatever the value: ``sort_key`` and the weak names
    (:data:`WEAK_SECRET_NAMES`) are kept."""
    plain = plain_name(name)
    if plain in _SECRET_NAMES or plain in _SECRET_KEYS:
        return True
    if weak:
        return plain in WEAK_SECRET_NAMES or plain.endswith(_MASK_ENDINGS)
    return plain.endswith(_STRIP_ENDINGS)


def mask_param(match: re.Match[str]) -> str:
    delimiter, name, value = match.groups()
    if is_secret_name(name):
        value = "***"
    return f"{delimiter}{name}={value}"


def free_value_end(param: re.Match[str]) -> int:
    """Where the value of the free-text *param* (:data:`PARAM_RE`) ends:
    before the punctuation ending a sentence or a quotation."""
    return param.start(3) + len(param.group(3).rstrip(_VALUE_TAIL))


def mask_free_param(match: re.Match[str]) -> str:
    if not is_secret_name(match.group(2)):
        return match.group(0)
    tail = match.string[free_value_end(match) : match.end()]
    return f"{match.group(1)}{match.group(2)}=***{tail}"
