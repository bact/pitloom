# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a run does with a URL credential in its SBOM: the fingerprint of a
value, and the policy that accepts one or refuses the SBOM.

A run has one of two modes (``[tool.pitloom] url-credentials``,
``--refuse-url-credentials``, :attr:`CredentialPolicy.refuse`). ``warn``,
the default, writes an SBOM field whose value holds a credential as it is,
with a loud ``WARNING:``: Pitloom runs in CI and build hooks and must not
fail them by default. ``refuse`` writes no SBOM unless the run accepts each
such value by its fingerprint (``--accept-url-credential``,
``[tool.pitloom] accept-url-credentials``); an accepted value is warned of
more quietly in either mode. The fingerprint is the SHA-256 of the whole
field value as it stands in the output, so it is the same on every
platform and never shows the credential.

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
from pitloom.messages.config import ConfigPlace, config_invalid
from pitloom.messages.options import (
    FINGERPRINT_LINE,
    FINGERPRINT_PATTERN,
    FINGERPRINT_SHAPE,
    OPTION_INVALID,
    REFUSE_ARGUMENT_LINE,
    URL_CREDENTIALS_MODE_ARGUMENT_LINE,
)

__all__ = [
    "ACCEPT_KEY",
    "FINGERPRINT_RE",
    "FINGERPRINT_SHAPE",
    "MODE_KEY",
    "MODE_REFUSE",
    "MODE_WARN",
    "CredentialPolicy",
    "fingerprint",
    "full_fingerprint",
    "read_accept_key",
    "read_mode_key",
    "require_fingerprint",
    "require_mode",
]

#: A fingerprint as printed (16 hex digits) or given (16 to 64), lowercase:
#: the pattern a message line's fingerprint field has, so the two never
#: disagree.
FINGERPRINT_RE: Final = re.compile(FINGERPRINT_PATTERN)

#: The ``[tool.pitloom]`` key listing accepted fingerprints.
ACCEPT_KEY: Final = "accept-url-credentials"
#: The ``[tool.pitloom]`` key naming the mode: :data:`MODE_WARN` (the
#: default) or :data:`MODE_REFUSE`.
MODE_KEY: Final = "url-credentials"
#: Write a credential found as it is, with a ``WARNING:``.
MODE_WARN: Final = "warn"
#: Write no SBOM while a credential found is not accepted.
MODE_REFUSE: Final = "refuse"
_MODES: Final = frozenset({MODE_WARN, MODE_REFUSE})

_PREFIX: Final = "sha256:"
#: Hex digits of a printed fingerprint.
_SHOWN_HEX: Final = 16
#: The ``pyproject.toml`` table that holds :data:`ACCEPT_KEY`, as a refusal
#: names it (``setup.cfg``'s is ``[tool:pitloom]``).
_TABLE: Final = "[tool.pitloom]"


def _place(table: str, key: str) -> ConfigPlace:
    """*key* of the config table *table* (``[tool.pitloom]``, or
    ``[tool:pitloom]`` from ``setup.cfg``) as a line names it."""
    return ConfigPlace("tool.pitloom", key, setup_cfg=table.startswith("[tool:"))


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
    an ``option-invalid`` error, or ``config-invalid`` given *entry*, its
    position in ``accept-url-credentials`` of the config table *table*,
    which the error then names. Uppercase hex is refused, not folded: one
    spelling per fingerprint.
    The error never quotes *text*, which may be the credential itself
    pasted by mistake.

    Raises:
        pitloom.messages.CodedValueError: ``option-invalid``
            (``config-invalid`` given *entry*): *text* is not ``sha256:``
            and 16 to 64 lowercase hex digits.
    """
    if not isinstance(text, str) or FINGERPRINT_RE.fullmatch(text) is None:
        if entry is None:
            raise CodedValueError(OPTION_INVALID, line=FINGERPRINT_LINE)
        place = _place(table, ACCEPT_KEY).entry_at(entry)
        raise config_invalid(place, "fingerprint", text, secret=True)
    return text


@dataclass(frozen=True)
class CredentialPolicy:
    """Which credentials in URL fields a run accepts.

    Attributes:
        accepted: Fingerprints (:data:`FINGERPRINT_RE`), each a prefix of
            the full fingerprint of a value it accepts: the printed 16-digit
            one, or a longer one. Any iterable of strings is taken and kept
            as a ``frozenset``.
        refuse: Refuse the SBOM while a credential found is not accepted
            (the ``refuse`` mode: ``--refuse-url-credentials``,
            ``url-credentials = "refuse"``); ``False``, the ``warn`` mode,
            writes it with a ``WARNING:`` per value.
        inherited: Fingerprints accepted as *accepted* are, from another
            target's settings (the project an enrichment fragment merges
            into): never reported as matching nothing, since they were
            not given for this SBOM. An entry in both counts as *accepted*'s.

    Raises:
        ValueError: an entry of *accepted* or *inherited* is not a
            fingerprint (a string given for the set is read as its
            characters, so it fails too), or *refuse* is not a ``bool``
            (``1`` or ``"refuse"`` is refused, never read as either mode).
    """

    accepted: frozenset[str] = frozenset()
    refuse: bool = False
    inherited: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        entries = frozenset(require_fingerprint(entry) for entry in self.accepted)
        object.__setattr__(self, "accepted", entries)
        if not isinstance(self.refuse, bool):
            raise CodedValueError(OPTION_INVALID, line=REFUSE_ARGUMENT_LINE)
        inherited = frozenset(require_fingerprint(entry) for entry in self.inherited)
        object.__setattr__(self, "inherited", inherited)

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
        entries = self.accepted | self.inherited
        return any(digest.startswith(entry) for entry in entries)

    def accepts_value(self, value: str) -> bool:
        """Whether an accepted (or inherited) entry is a prefix of the full
        fingerprint of *value*, the whole field value as it stands in the
        output."""
        if not (self.accepted or self.inherited):
            return False
        return self.accepts(full_fingerprint(value))

    def union(self, other: CredentialPolicy) -> CredentialPolicy:
        """Both policies at once: every entry of either, and ``refuse`` if
        either refuses. A CLI flag adds to the config's list, it does not
        replace it, and ``--refuse-url-credentials`` turns refusal on, never
        off."""
        return CredentialPolicy(
            accepted=self.accepted | other.accepted,
            refuse=self.refuse or other.refuse,
            inherited=self.inherited | other.inherited,
        )

    def inheriting(self, other: CredentialPolicy) -> CredentialPolicy:
        """This policy, also accepting every entry of *other* (another
        target's settings) as :attr:`inherited`, and refusing if *other*
        refuses: that target's own run would refuse the value anyway."""
        return CredentialPolicy(
            accepted=self.accepted,
            refuse=self.refuse or other.refuse,
            inherited=self.inherited | other.accepted | other.inherited,
        )


def read_accept_key(data: dict[str, Any], *, table: str = _TABLE) -> tuple[str, ...]:
    """``accept-url-credentials`` of the config table *data* (named *table*
    in an error: ``[tool.pitloom]``, or ``[tool:pitloom]`` whose value
    :mod:`pitloom.extract.project.setuptools_cfg` splits into a list): its
    fingerprints in sorted order, each once. Absent and an empty array are
    both ``()``: an empty list accepts nothing, as the default does.

    Raises:
        pitloom.messages.CodedValueError: ``config-invalid``: the value is
            not an array, or an entry is not a fingerprint (named by its
            position): never quoted, since it may be a pasted credential.
    """
    raw = data.get(ACCEPT_KEY)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise config_invalid(
            _place(table, ACCEPT_KEY), "fingerprints", raw, secret=True
        )
    found = {
        require_fingerprint(entry, entry=index, table=table)
        for index, entry in enumerate(raw)
    }
    return tuple(sorted(found))


def require_mode(value: object, *, table: str | None = _TABLE) -> str:
    """*value* if it is a mode (:data:`MODE_WARN`, :data:`MODE_REFUSE`),
    else a ``config-invalid`` error naming the setting of *table*, or
    ``option-invalid`` naming the library's ``url_credentials`` when
    *table* is ``None``. The value is never quoted.

    Raises:
        pitloom.messages.CodedValueError: ``config-invalid`` or
            ``option-invalid``.
    """
    if isinstance(value, str) and value in _MODES:
        return value
    if table is None:
        raise CodedValueError(OPTION_INVALID, line=URL_CREDENTIALS_MODE_ARGUMENT_LINE)
    raise config_invalid(
        _place(table, MODE_KEY), "url-credentials-mode", value, secret=True
    )


def read_mode_key(data: dict[str, Any], *, table: str = _TABLE) -> str:
    """``url-credentials`` of the config table *data* (named *table* in an
    error), :data:`MODE_WARN` when absent.

    Raises:
        pitloom.messages.CodedValueError: ``config-invalid``: the value is
            not ``"warn"`` or ``"refuse"``.
    """
    raw = data.get(MODE_KEY)
    return MODE_WARN if raw is None else require_mode(raw, table=table)
