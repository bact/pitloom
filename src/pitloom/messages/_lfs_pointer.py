# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``lfs-pointer`` family: a Git LFS pointer met instead of its content.

See also: :mod:`pitloom.core.lfs_pointer` (the summary warning),
:mod:`pitloom.extract.scanner` (a pointer that is not whole) and
:mod:`pitloom.assemble._model_generator` (a model file named on its own).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Message

_FAMILY: Final = "lfs-pointer"

#: Pointers left by a checkout made without Git LFS, or a model file named on
#: its own that is a whole pointer. The code equals the evidence reason
#: ``lfs-pointer`` (:data:`pitloom.core.evidence.REASON_CODES`).
LFS_POINTER: Final = Message(
    code=_FAMILY,
    family=_FAMILY,
    condition="lfs-pointer",
    levels=frozenset({"WARNING", "ERROR"}),
    subject="FILE: the first pointer in sorted order, or the model file named",
    summary="A file is a Git LFS pointer: the checkout holds the pointer "
    "text, not the content.",
    did="Recorded each pointer by the oid (content SHA-256) and size it "
    "states, without reading the content or listing an AI model; a model "
    "file named on its own is refused and nothing is written.",
    advice="Tell the user to run 'git lfs pull' in the checkout (for a Git "
    "URL, to clone it with Git LFS and run Pitloom on the directory), then "
    "to generate the SBOM again; do not pull or clone for them.",
    patterns=(
        "FILE=%s: Git LFS pointer, content not read%s; "
        "run 'git lfs pull' for the content",
        "FILE=%s: Git LFS pointer, content not read%s; "
        "clone with git lfs, then run on the directory",
        "%s: header is a Git LFS pointer, content not pulled "
        "(oid sha256:%s, size %s); run 'git lfs pull'",
    ),
)

#: Pointers a built artefact (a wheel, the build hook's wheel) holds as files.
LFS_POINTER_SHIPPED: Final = Message(
    code=f"{_FAMILY}.shipped",
    family=_FAMILY,
    condition="lfs-pointer",
    levels=frozenset({"WARNING"}),
    subject="FILE: the first pointer in sorted order",
    summary="A built artefact ships Git LFS pointer files instead of the "
    "content they stand for.",
    did="Recorded each pointer file with the hashes of the bytes it holds.",
    advice="Tell the user the artefact was built without the LFS content: "
    "to run 'git lfs pull' before building if the content belongs in it, "
    "and to rebuild; do not rebuild for them.",
    patterns=(
        "FILE=%s: Git LFS pointer shipped%s; the build did not pull LFS content",
    ),
)

#: A file that opens like a pointer but is not a whole, valid one.
LFS_POINTER_MALFORMED: Final = Message(
    code=f"{_FAMILY}.malformed",
    family=_FAMILY,
    condition="invalid",
    levels=frozenset({"WARNING", "ERROR"}),
    subject="FILE (after FORMAT= when the suffix names one), or the model file named",
    summary="A file opens with a Git LFS pointer line, but the rest is not a "
    "valid pointer (damaged, cut short or over 1 KiB).",
    did="Did not list the file as an AI model; a model file named on its own "
    "is refused and nothing is written.",
    advice="Tell the user the file is neither a model nor a valid pointer: "
    "to check it out again, or to replace it with the content.",
    patterns=(
        "%sFILE=%s: header is a Git LFS pointer; not listed as an AI model",
        "%s: header is a Git LFS pointer",
    ),
)

ENTRIES: Final = (LFS_POINTER, LFS_POINTER_SHIPPED, LFS_POINTER_MALFORMED)
