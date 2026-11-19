# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``--accept-url-credential`` and ``--refuse-url-credentials`` flags,
and the :class:`~pitloom.core.credential_policy.CredentialPolicy` they give.

Added to the shared parent parser (every command built from it) and to
``merge``'s own parser, which is not built from it.

See also: :mod:`pitloom.core.credential_policy` (the fingerprint and the
policy) and :mod:`pitloom.cli.options_config` (where the policy joins the
other options).
"""

from __future__ import annotations

import argparse
from typing import Final

from pitloom.core.credential_policy import CredentialPolicy, require_fingerprint

__all__ = [
    "ACCEPT_DEST",
    "REFUSE_DEST",
    "REFUSE_HELP_ID_GENERATE",
    "REFUSE_HELP_ID_IMPORT",
    "REFUSE_HELP_MERGE",
    "REFUSE_HELP_SBOM",
    "add_credential_arguments",
    "add_refuse_argument",
    "credential_policy_from_args",
    "fingerprint_argument",
]

#: The ``argparse`` dests of the two flags.
ACCEPT_DEST = "accept_url_credentials"
REFUSE_DEST = "refuse_url_credentials"


def fingerprint_argument(text: str) -> str:
    """``--accept-url-credential``'s type:
    :func:`~pitloom.core.credential_policy.require_fingerprint` as an
    ``argparse`` refusal. Not that function itself: for a ``ValueError``
    ``argparse`` quotes the value, which may be the credential pasted by
    mistake; this refusal does not."""
    try:
        return require_fingerprint(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


#: ``--refuse-url-credentials`` on a command that writes an SBOM and reads a
#: config (the parent parser's commands).
REFUSE_HELP_SBOM: Final = (
    "Refuse an SBOM whose URL field value holds a credential not "
    "accepted by --accept-url-credential: no SBOM is written (exit 1), "
    "and an ID registry file entry or key that holds one is refused too. "
    "The default writes it with a WARNING:. Same as [tool.pitloom] "
    'url-credentials = "refuse" where the command reads a config; '
    "recommended in CI."
)
#: The same on ``merge``, which reads no config.
REFUSE_HELP_MERGE: Final = (
    "Refuse the merged SBOM when a URL field value holds a credential "
    "not accepted by --accept-url-credential: no SBOM is written (exit 1). "
    "The default writes it with a WARNING:. merge reads no [tool.pitloom], "
    "so only this flag turns refusal on; recommended in CI."
)
#: The same on ``loom id generate``, which writes a registry, not an SBOM.
REFUSE_HELP_ID_GENERATE: Final = (
    "Refuse a key given with -e, or an entry of the registry file, that "
    "holds a credential (exit 1, the registry left as it was). The default "
    "stores it with a WARNING:. Without this flag the project's "
    '[tool.pitloom] url-credentials = "refuse" applies when --project-dir '
    "is given or no -o is."
)
#: The same on ``loom id import``.
REFUSE_HELP_ID_IMPORT: Final = (
    "Refuse an entry of the registry file that holds a credential (exit 1, "
    "the registry left as it was); an SBOM element whose key or id holds one "
    "is skipped either way. The default loads the file with a WARNING:. "
    "Without this flag the project's [tool.pitloom] url-credentials = "
    '"refuse" applies when --project-dir is given or no -o is.'
)

_ACCEPT_HELP: Final = (
    "Accept one URL field value that holds a credential, named by the "
    "fingerprint its WARNING: or ERROR: line prints (sha256: and 16 hex "
    "digits; a longer prefix of the value's SHA-256 is accepted too): with "
    "--refuse-url-credentials it no longer refuses the SBOM, and it is "
    "warned of more quietly. Repeatable."
)


def add_credential_arguments(
    parser: argparse.ArgumentParser, *, reads_config: bool = True
) -> None:
    """Add ``--accept-url-credential FP`` (repeatable) and
    ``--refuse-url-credentials`` to *parser*; *reads_config* is false for a
    command that reads no ``[tool.pitloom]`` (``merge``), whose help then
    names no setting."""
    parser.add_argument(
        "--accept-url-credential",
        action="append",
        dest=ACCEPT_DEST,
        type=fingerprint_argument,
        default=None,
        metavar="FINGERPRINT",
        help=_ACCEPT_HELP
        + (
            " Adds to [tool.pitloom] accept-url-credentials, never replaces it."
            if reads_config
            else ""
        ),
    )
    add_refuse_argument(parser, REFUSE_HELP_SBOM if reads_config else REFUSE_HELP_MERGE)


def add_refuse_argument(parser: argparse.ArgumentParser, help_text: str) -> None:
    """Add ``--refuse-url-credentials`` alone to *parser*, with the help
    *help_text* that says what the command refuses (``loom id`` takes this
    flag alone: it writes no SBOM, so accepts no fingerprint)."""
    parser.add_argument(
        "--refuse-url-credentials",
        action="store_true",
        dest=REFUSE_DEST,
        default=None,
        help=help_text,
    )


def credential_policy_from_args(args: argparse.Namespace) -> CredentialPolicy | None:
    """The policy the two flags give, ``None`` when neither was given (the
    config's own then applies unchanged). A command without the flags gives
    ``None`` too."""
    accepted = getattr(args, ACCEPT_DEST, None)
    refuse = getattr(args, REFUSE_DEST, None)
    if accepted is None and refuse is None:
        return None
    return CredentialPolicy(accepted=frozenset(accepted or ()), refuse=refuse is True)
