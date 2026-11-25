# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Merged SBOM generator: a directory of SPDX 3 fragments into one document.

See also:
- :mod:`pitloom.assemble.spdx3._fragments_envelope` for the merged
  document's envelope.
- :mod:`pitloom.assemble.spdx3.fragments` for the merge itself, shared with
  a project build's configured fragments.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble.spdx3._fragments_envelope import (
    finish_merge_document,
    new_merge_document,
)
from pitloom.assemble.spdx3.fragments import (
    FragmentMergeError,
    fragment_files,
    merge_fragments,
)
from pitloom.core.config import FragmentConfig
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.core.given_path import TypedPath
from pitloom.logging_config import configure_logging
from pitloom.messages import CodedValueError
from pitloom.messages.fragments import FRAGMENT_MISSING, NONE_MERGED_LINE
from pitloom.messages.targets import (
    INPUT_NOT_FOUND,
    NO_FRAGMENT_FILE_LINE,
    input_not_found,
    is_input_dir,
)


def generate_merged_sbom(
    fragments_dir: Path | str,
    *,
    output_path: Path | str | None = None,
    pretty: bool = True,
    credentials: CredentialPolicy | None = None,
    on_merged: Callable[[int], None] | None = None,
) -> str:
    """Merge every ``*.json`` SPDX 3 fragment in *fragments_dir* into one
    SBOM, as ``loom merge`` does, and return it as JSON-LD.

    The output is one ``SpdxDocument`` rooted at what the fragments' own
    envelopes rooted; equal elements unify as in a project build with
    fragments. The same fragments give the same bytes, whatever the
    directory or the order the files were written in.

    A fragment field holding a credential that *credentials*
    (:class:`~pitloom.core.credential_policy.CredentialPolicy`) does not
    accept is warned of, or, in its ``refuse`` mode, refused; fragments
    have no ``[tool.pitloom]`` to add to it.

    A fragment that cannot be merged is left out with one ``WARNING:``
    naming it by *fragments_dir* as given joined with its file name; when
    none can be, nothing is written. *on_merged*, when given, is called with
    the number of fragments merged, once the SBOM is written (``loom
    merge`` says it).

    Raises:
        FileNotFoundError: *fragments_dir* does not exist, is given as
            empty, or is not a directory (``input-not-found``, carrying the
            code).
        ValueError: it has no ``*.json`` file (``input-not-found``).
        pitloom.assemble.FragmentMergeError: no fragment of it could be
            merged (``fragment-missing``; each one's ``WARNING:`` says why).
        pitloom.assemble.FragmentMergeError: the merge left a dangling
            reference, a root included, or a licence relationship end of the
            wrong type (a ``pitloom.assemble.spdx3.fragments.
            FragmentLicenseRangeError``, code ``license-relationship-invalid``).
        pitloom.messages.CodedOSError: The system refused a write
            (``file-unwritable``): the ``-o`` copy at *output_path* (as
            given).
    """
    configure_logging()
    # A Path as given (a TypedPath keeps the user's spelling for the lines).
    # A str too: an empty one names nothing (the input probe), not ".".
    fragments_dir = (
        fragments_dir if isinstance(fragments_dir, Path) else TypedPath(fragments_dir)
    )
    if not is_input_dir(fragments_dir):
        raise input_not_found("fragments directory", fragments_dir)
    files = fragment_files(fragments_dir)
    if not files:
        raise CodedValueError(
            INPUT_NOT_FOUND, line=NO_FRAGMENT_FILE_LINE, path=fragments_dir
        )
    exporter = new_merge_document(fragments_dir, files)
    merged = merge_fragments(
        fragments_dir,
        [FragmentConfig(path=f) for f in files],
        exporter,
        adopt_fragment_roots=True,
    )
    if not merged:
        raise FragmentMergeError(
            FRAGMENT_MISSING, line=NONE_MERGED_LINE, path=fragments_dir
        )
    finish_merge_document(exporter)
    sbom_json = exporter.to_json(
        pretty=pretty, credentials=credentials or CredentialPolicy()
    )
    write_sbom_output(sbom_json, output_path)
    if on_merged is not None:
        on_merged(merged)
    return sbom_json
