# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which URL credentials a run lets into its SBOM: the fingerprint of a
value, and the policy that accepts one.

An SBOM field whose value holds a credential is refused unless the run
accepts that exact value, by its fingerprint (``--accept-url-credential``,
``[tool.pitloom] accept-url-credentials``), or every value
(``--allow-url-credentials``, CLI and library only: a ``pyproject.toml``
setting set once for an example URL would later let a real token through
unseen). The fingerprint is the SHA-256 of the whole field value as it
stands in the output, so it is the same on every platform and never shows
the credential.

No leading underscore: imported from outside ``pitloom.core``. Imports
nothing from Pitloom but the internal error and the messages it raises
(:mod:`pitloom.messages.options`), so every layer can use it.

See also: :mod:`pitloom.core.config_cascade` (where the CLI's and the
config's policies are united) and :mod:`pitloom.cli._parser_credentials`
(the flags).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Final

from pitloom.core.internal_error import InternalError
from pitloom.messages import CodedValueError
from pitloom.messages.options import (
    FINGERPRINT_ARRAY_LINE,
    FINGERPRINT_ENTRY_LINE,
    FINGERPRINT_LINE,
    FINGERPRINT_SHAPE,
    OPTION_INVALID,
)

__all__ = [
    "ACCEPT_KEY",
    "ALLOW_KEY",
    "FINGERPRINT_RE",
    "FINGERPRINT_SHAPE",
    "CredentialPolicy",
    "fingerprint",
    "full_fingerprint",
    "read_accept_key",
    "require_fingerprint",
]

#: A fingerprint as printed (16 hex digits) or given (16 to 64), lowercase.
FINGERPRINT_RE: Final = re.compile(r"sha256:[0-9a-f]{16,64}")

#: The ``[tool.pitloom]`` key listing accepted fingerprints.
ACCEPT_KEY: Final = "accept-url-credentials"
#: The ``[tool.pitloom]`` spelling of ``--allow-url-credentials``: known, so
#: never an unknown-key warning, and never read (CLI and library only).
ALLOW_KEY: Final = "allow-url-credentials"

_PREFIX: Final = "sha256:"
#: Hex digits of a printed fingerprint.
_SHOWN_HEX: Final = 16
#: The ``pyproject.toml`` table that holds :data:`ACCEPT_KEY`, as a refusal
#: names it (``setup.cfg``'s is ``[tool:pitloom]``).
_TABLE: Final = "[tool.pitloom]"


def _digest(value: str) -> str:
    """The SHA-256 hex digest of *value* as UTF-8. A lone surrogate (JSON can
    carry one) is encoded as is (``surrogatepass``), so no value raises."""
    data = value.encode("utf-8", "surrogatepass")
    return hashlib.sha256(data).hexdigest()


def fingerprint(value: str) -> str:
    """The fingerprint an ``ERROR:`` line prints for *value*, the whole field
    value as it stands in the output: ``sha256:`` and the first 16 lowercase
    hex digits of its SHA-256."""
    return _PREFIX + _digest(value)[:_SHOWN_HEX]


def full_fingerprint(value: str) -> str:
    """As :func:`fingerprint`, with all 64 hex digits, for checking an
    accepted entry longer than the printed one."""
    return _PREFIX + _digest(value)


def require_fingerprint(
    text: str, *, entry: int | None = None, table: str = _TABLE
) -> str:
    """*text* if it is a fingerprint (:data:`FINGERPRINT_RE`, whole), else
    an ``option-invalid`` error. Uppercase hex is refused, not folded: one
    spelling per fingerprint. *entry* is its position in
    ``accept-url-credentials`` of the config table *table*, which the
    error then names.
    The error never quotes *text*, which may be the credential itself
    pasted by mistake.

    Raises:
        pitloom.messages.CodedValueError: ``option-invalid``: *text* is not
            ``sha256:`` and 16 to 64 lowercase hex digits.
    """
    if not isinstance(text, str) or FINGERPRINT_RE.fullmatch(text) is None:
        if entry is None:
            raise CodedValueError(OPTION_INVALID, line=FINGERPRINT_LINE)
        raise CodedValueError(
            OPTION_INVALID,
            line=FINGERPRINT_ENTRY_LINE,
            table=table,
            setting=ACCEPT_KEY,
            number=entry,
        )
    return text


@dataclass(frozen=True)
class CredentialPolicy:
    """Which credentials in URL fields a run accepts.

    Attributes:
        accepted: Fingerprints (:data:`FINGERPRINT_RE`), each a prefix of
            the full fingerprint of a value it accepts: the printed 16-digit
            one, or a longer one. Any iterable of strings is taken and kept
            as a ``frozenset``.
        allow_all: Accept every credential (``--allow-url-credentials``).
            Set by the CLI or a library caller only, never from
            ``[tool.pitloom]``. :meth:`accepts` does not read it: the caller
            tells the two apart, since each is reported differently.

    Raises:
        ValueError: an entry of *accepted* is not a fingerprint (a string
            given for the set is read as its characters, so it fails too).
    """

    accepted: frozenset[str] = frozenset()
    allow_all: bool = False

    def __post_init__(self) -> None:
        entries = frozenset(require_fingerprint(entry) for entry in self.accepted)
        object.__setattr__(self, "accepted", entries)
        object.__setattr__(self, "allow_all", self.allow_all is True)

    def accepts(self, digest: str) -> bool:
        """Whether an accepted entry is a prefix of (or equal to) *digest*,
        a fingerprint (:func:`fingerprint` or :func:`full_fingerprint`).

        Given the printed 16-digit one, an entry longer than 16 digits
        cannot be checked and does not accept it: pass the full one, or
        use :meth:`accepts_value`.

        Raises:
            pitloom.core.internal_error.InternalError: *digest* is not a
                fingerprint (a caller's bug, no user input gets here).
        """
        if not isinstance(digest, str) or FINGERPRINT_RE.fullmatch(digest) is None:
            raise InternalError(f"accepts() takes a fingerprint ({FINGERPRINT_SHAPE})")
        return any(digest.startswith(entry) for entry in self.accepted)

    def accepts_value(self, value: str) -> bool:
        """Whether an accepted entry is a prefix of the full fingerprint of
        *value*, the whole field value as it stands in the output."""
        return bool(self.accepted) and self.accepts(full_fingerprint(value))

    def union(self, other: CredentialPolicy) -> CredentialPolicy:
        """Both policies at once: every entry of either, and ``allow_all``
        if either allows all. Never narrows: a CLI flag adds to the
        config's list, it does not replace it."""
        return CredentialPolicy(
            accepted=self.accepted | other.accepted,
            allow_all=self.allow_all or other.allow_all,
        )


def read_accept_key(data: dict[str, Any], *, table: str = _TABLE) -> tuple[str, ...]:
    """``accept-url-credentials`` of the config table *data* (named *table*
    in an error: ``[tool.pitloom]``, or ``[tool:pitloom]`` whose value
    :mod:`pitloom.extract.project.setuptools_cfg` splits into a list): its
    fingerprints in sorted order, each once. Absent and an empty array are
    both ``()``: an empty list accepts nothing, as the default does.

    Raises:
        pitloom.messages.CodedValueError: ``option-invalid``: the value is
            not an array, or an entry is not a fingerprint (named by its
            position): never quoted, since it may be a pasted credential.
    """
    raw = data.get(ACCEPT_KEY)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise CodedValueError(
            OPTION_INVALID,
            line=FINGERPRINT_ARRAY_LINE,
            table=table,
            setting=ACCEPT_KEY,
        )
    found = {
        require_fingerprint(entry, entry=index, table=table)
        for index, entry in enumerate(raw)
    }
    return tuple(sorted(found))
