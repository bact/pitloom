# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``--accept-url-credential`` and ``--allow-url-credentials`` flags,
and the :class:`~pitloom.core.credential_policy.CredentialPolicy` they give.

Added to the shared parent parser (every command built from it) and to
``merge``'s own parser, which is not built from it.

See also: :mod:`pitloom.core.credential_policy` (the fingerprint and the
policy) and :mod:`pitloom.cli.options_config` (where the policy joins the
other options).
"""

from __future__ import annotations

import argparse

from pitloom.core.credential_policy import CredentialPolicy, require_fingerprint

__all__ = [
    "ACCEPT_DEST",
    "ALLOW_DEST",
    "add_credential_arguments",
    "credential_policy_from_args",
    "fingerprint_argument",
]

#: The ``argparse`` dests of the two flags.
ACCEPT_DEST = "accept_url_credentials"
ALLOW_DEST = "allow_url_credentials"


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


def add_credential_arguments(parser: argparse.ArgumentParser) -> None:
    """Add ``--accept-url-credential FP`` (repeatable) and
    ``--allow-url-credentials`` to *parser*."""
    parser.add_argument(
        "--accept-url-credential",
        action="append",
        dest=ACCEPT_DEST,
        type=fingerprint_argument,
        default=None,
        metavar="FINGERPRINT",
        help=(
            "Let one URL field value that holds a credential into the SBOM, "
            "named by the fingerprint its ERROR: line prints (sha256: and 16 "
            "hex digits; a longer prefix of the value's SHA-256 is accepted "
            "too). Repeatable. Adds to [tool.pitloom] accept-url-credentials, "
            "never replaces it."
        ),
    )
    parser.add_argument(
        "--allow-url-credentials",
        action="store_true",
        dest=ALLOW_DEST,
        default=None,
        help=(
            "SECURITY: let every credential found in a URL field into the "
            "SBOM, each with a WARNING:. Prefer --accept-url-credential for "
            "the one value you mean. Command line and library only: "
            "deliberately has no [tool.pitloom] equivalent."
        ),
    )


def credential_policy_from_args(args: argparse.Namespace) -> CredentialPolicy | None:
    """The policy the two flags give, ``None`` when neither was given (the
    config's own then applies unchanged). A command without the flags gives
    ``None`` too."""
    accepted = getattr(args, ACCEPT_DEST, None)
    allow_all = getattr(args, ALLOW_DEST, None)
    if accepted is None and allow_all is None:
        return None
    return CredentialPolicy(
        accepted=frozenset(accepted or ()), allow_all=allow_all is True
    )
