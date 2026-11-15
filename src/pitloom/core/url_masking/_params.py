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

#: A query or fragment parameter in free text, as ``(delimiter, name,
#: value)``; the value ends at white space. The name has no length bound: it
#: is a run of name characters after one delimiter, so a failed match
#: backtracks over that run only and matching stays linear.
PARAM_RE = re.compile(r"([?&;#])([\w.%-]+)=([^&;#\s]*)")
#: What ends a sentence or a quotation after a value in free text: not part
#: of the value (``?token=***: not a project``, ``'...?token=***'``).
_VALUE_TAIL = ":.,)]'\""
#: The same in a text that is one URL (:func:`sanitize_url`): the value runs
#: over a space, a line break or a quote (RFC 3986 allows ``'``), to the
#: next delimiter or the end.
WHOLE_PARAM_RE = re.compile(r"([?&;#])([\w.%-]+)=([^&;#]*)")
#: The ``delimiter name=`` that starts a parameter (of either pattern).
PARAM_HEAD = r"[?&;#](?P<name>[\w.%-]+)="

#: Words naming a secret: a parameter is named by one, or its last word is
#: one (``access_token``, ``db-password``, ``accessToken``,
#: ``X-Amz-Signature``).
_SECRET_WORDS = (
    *("token", "key", "secret", "password", "passwd", "signature", "sig"),
    *("jwt", "credential", "credentials", "auth", "hmac", "verifier"),
)
#: Names that hold a secret only sometimes (``code=utf8``, ``session=2024``):
#: masked in a message, never removed from an SBOM.
_WEAK_SECRET_NAMES = frozenset({"code", "session", "ticket", "sid", "otp"})
#: Lower-case names of a parameter that holds a secret, matched whole.
_SECRET_NAMES = frozenset(
    {*_SECRET_WORDS, "apikey", "pass", "pwd", "pw", "authorization"}
)
#: The endings of such a name: a separator and a word (``monkey`` and
#: ``author`` are not secrets).
_SECRET_ENDINGS = tuple(sep + word for word in _SECRET_WORDS for sep in "_-")
#: Where a camelCase name starts a word: ``accessToken`` is read as
#: ``access_token``.
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


#: Names (``_`` for ``-``) a secret key goes by: ``sort_key`` and
#: ``primary-key`` are not secrets, ``api_key`` is.
_SECRET_KEYS = tuple(
    f"{kind}_key" for kind in ("api", "access", "secret", "private", "signing", "auth")
) + ("session_key", "license_key", "encryption_key")
#: The words whose ending makes a name a secret to remove from an SBOM.
_STRIP_WORDS = tuple(w for w in _SECRET_WORDS if w not in {"key", "sig", "auth"})


def _strip_name(plain: str) -> bool:
    """Whether the lower-case *plain* name is removed from an SBOM."""
    plain = plain.replace("-", "_")
    if plain in _WEAK_SECRET_NAMES:
        return False
    if plain in _SECRET_NAMES or plain in _SECRET_KEYS:
        return True
    return plain.endswith(tuple(f"_{word}" for word in (*_STRIP_WORDS, *_SECRET_KEYS)))


def is_secret_name(name: str, *, weak: bool = True) -> bool:
    """Whether the parameter *name* names a secret (:data:`_SECRET_NAMES`,
    :data:`_SECRET_ENDINGS`), percent-decoded and camelCase read as words;
    with *weak* false (the removal from an SBOM), only a whole name or an
    ending that is a secret whatever the value (:func:`_strip_name`)."""
    plain = unquote(name) if "%" in name else name
    # ``token%3D=v`` is a parameter named ``token=``: a server may decode it.
    plain = plain.rstrip("=")
    if not plain.islower():
        plain = _CAMEL_BOUNDARY.sub("_", plain).lower()
    if weak:
        return (
            plain in _WEAK_SECRET_NAMES
            or plain in _SECRET_NAMES
            or plain.endswith(_SECRET_ENDINGS)
        )
    return _strip_name(plain)


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
