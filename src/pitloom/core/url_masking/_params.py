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
from collections.abc import Callable, Iterator
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
#: Each pattern as a secret's value runs: over ``;``, which Python's
#: ``parse_qsl`` (since 3.10) and the WHATWG URL parser read as part of a
#: value (``?token=S3C;RET``), to ``&``, ``#``, the end (in free text, white
#: space). A ``;`` still starts a parameter after any other value, and a
#: parameter it opens (a path parameter) ends at the next one.
_SECRET_RUN = {
    PARAM_RE: re.compile(rf"([?&;#])({_NAME})=([^&#\s]*)"),
    WHOLE_PARAM_RE: re.compile(rf"([?&;#])({_NAME})=([^&#]*)"),
}

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

#: The kinds of key that are secrets: ``api_key`` is, ``sort_key`` and
#: ``primary-key`` are not (a name ending in ``_key`` that none of these
#: starts is weak: masked in a message, kept in an SBOM).
_KEY_KINDS = (
    *("api", "access", "secret", "private", "signing", "auth", "ssh"),
    *("session", "license", "encryption", "subscription", "application"),
    *("app", "client", "master", "consumer", "deploy", "account", "shared"),
    *("service", "admin"),
)
#: Such a name whole (``api_key``).
_SECRET_KEYS = tuple(f"{kind}_key" for kind in _KEY_KINDS)
#: The words whose ending makes a name a secret to remove from an SBOM.
_STRIP_WORDS = tuple(w for w in _SECRET_WORDS if w not in {"key", "sig", "auth"})
#: Words a name may end in without a separator (``accesstoken``,
#: ``secretkey``, ``AccountKey``).
_JOINED_WORDS = (
    *("token", "secret", "password", "passwd", "signature", "passphrase"),
    *("sessionid", "privatekey"),
    *(f"{kind}key" for kind in _KEY_KINDS),
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
    (:data:`WEAK_SECRET_NAMES`, or a name ending in ``_key`` that is no
    kind of secret key: ``sort_key``): kept in an SBOM, masked in a
    message."""
    plain = plain_name(name)
    return plain in WEAK_SECRET_NAMES or (
        plain.endswith("_key") and not plain.endswith(_STRIP_ENDINGS)
    )


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


#: The most ``?`` a non-secret parameter's value may hold: a value with more
#: is read as a secret (the strip removes it, a message masks it), so a
#: crafted ``?q=1?q=1?...`` cannot nest the reading without limit.
MAX_QUERY_MARKS = 16


def is_secret_param(param: re.Match[str], *, weak: bool = True) -> bool:
    """Whether the parameter *param* (:data:`PARAM_RE` or
    :data:`WHOLE_PARAM_RE`) is a secret: :func:`is_secret_name` of its name
    (with *weak*), or a value with more than :data:`MAX_QUERY_MARKS` ``?``,
    which is read whole and not looked into."""
    return is_secret_name(param.group(2), weak=weak) or (
        param.group(3).count("?") > MAX_QUERY_MARKS
    )


def iter_params(
    pattern: re.Pattern[str],
    text: str,
    start: int,
    bound: int,
    *,
    weak: bool = True,
) -> Iterator[re.Match[str]]:
    """Each parameter of *text* from *start* to *bound* by *pattern*
    (:data:`PARAM_RE` or :data:`WHOLE_PARAM_RE`), in order, and the ones in
    the value of a parameter that is no secret after a second ``?``
    (``?q=1?token=T``: a ``?`` is a character of a query, but a server or a
    client reads a parameter after it), at most :data:`MAX_QUERY_MARKS`
    levels deep. A secret's value is read whole, a ``?`` in it included;
    with *weak* false (the strip, which keeps a weak name's value as
    written) a weak name's value is looked into too."""
    for param in _top_params(pattern, text, start, bound):
        yield param
        if "?" in param.group(3) and not is_secret_param(param, weak=weak):
            yield from iter_params(
                pattern, text, param.start(3), param.end(3), weak=weak
            )


def param_run(
    pattern: re.Pattern[str], text: str, start: int, bound: int
) -> re.Match[str] | None:
    """The parameter of *text* by *pattern* (:data:`PARAM_RE` or
    :data:`WHOLE_PARAM_RE`) at *start*, before *bound*: a secret's value
    (one an SBOM may not state) run over ``;`` (:data:`_SECRET_RUN`) when a
    ``?``, ``&`` or ``#`` opens it; a path parameter (``;jsessionid=``)
    ends at the next ``;`` as before."""
    param = pattern.match(text, start, bound)
    if (
        param is not None
        and param.group(1) != ";"
        and is_secret_param(param, weak=False)
    ):
        return _SECRET_RUN[pattern].match(text, start, bound) or param
    return param


def _top_params(
    pattern: re.Pattern[str], text: str, start: int, bound: int
) -> Iterator[re.Match[str]]:
    """Each parameter of *text* from *start* to *bound* by *pattern*, in
    order, a secret's value run over ``;`` (:func:`param_run`)."""
    pos = start
    while (found := pattern.search(text, pos, bound)) is not None:
        param = param_run(pattern, text, found.start(), bound) or found
        yield param
        pos = param.end()


def sub_params(
    pattern: re.Pattern[str],
    replace: Callable[[re.Match[str]], str],
    text: str,
) -> str:
    """*text* with each parameter by *pattern* written as *replace* writes
    it (:meth:`re.Pattern.sub`, a secret's value run over ``;``)."""
    parts: list[str] = []
    done = 0
    for param in _top_params(pattern, text, 0, len(text)):
        parts += (text[done : param.start()], replace(param))
        done = param.end()
    return "".join(parts) + text[done:]


def mask_param(match: re.Match[str]) -> str:
    delimiter, name, value = match.groups()
    if is_secret_param(match):
        value = "***"
    elif "?" in value:
        value = sub_params(WHOLE_PARAM_RE, mask_param, value)
    return f"{delimiter}{name}={value}"


def free_value_end(param: re.Match[str]) -> int:
    """Where the value of the free-text *param* (:data:`PARAM_RE`) ends:
    before the punctuation ending a sentence or a quotation."""
    return param.start(3) + len(param.group(3).rstrip(_VALUE_TAIL))


def mask_free_param(match: re.Match[str]) -> str:
    if not is_secret_param(match):
        value = match.group(3)
        if "?" not in value:
            return match.group(0)
        inner = sub_params(PARAM_RE, mask_free_param, value)
        return f"{match.group(1)}{match.group(2)}={inner}"
    tail = match.string[free_value_end(match) : match.end()]
    return f"{match.group(1)}{match.group(2)}=***{tail}"
