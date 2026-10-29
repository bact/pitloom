# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``lfs-pointer`` family (a Git LFS pointer met instead of its content)
and ``lfs-pointer-malformed`` (a file that only opens like one).

See also: :mod:`pitloom.core.lfs_pointer` (the summary warning),
:mod:`pitloom.extract.scanner` (a pointer that is not whole) and
:mod:`pitloom.assemble._model_generator` (a model file named on its own).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: The summary warning of a checkout's pointers.
LFS_PULL_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: Git LFS pointer, content not read%(count)s; "
    "run 'git lfs pull' for the content",
)
#: The summary warning of the pointers of a Git URL's temporary clone,
#: where there is nothing to pull into.
LFS_CLONE_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: Git LFS pointer, content not read%(count)s; "
    "clone with git lfs, then run on the directory",
)

#: Pointers left by a checkout made without Git LFS, or a model file named on
#: its own that is a whole pointer. The code equals the evidence reason
#: ``lfs-pointer`` (:data:`pitloom.core.evidence.REASON_CODES`).
LFS_POINTER: Final = Message(
    code="lfs-pointer",
    condition="lfs-pointer",
    lines=(
        LFS_PULL_LINE,
        LFS_CLONE_LINE,
        Line(
            level="ERROR",
            template="%(path)s: header is a Git LFS pointer, content not pulled "
            "(oid sha256:%(oid)s, size %(size)s); run 'git lfs pull'",
        ),
    ),
    summary="A file is a Git LFS pointer: the checkout holds the pointer "
    "text, not the content.",
    did="Recorded each pointer by the oid (content SHA-256) and size it "
    "states, without reading the content or listing an AI model; a model "
    "file named on its own is refused and nothing is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user to run 'git lfs pull' in the checkout (for a Git "
    "URL, to clone it with Git LFS and run Pitloom on the directory), then "
    "to generate the SBOM again. Do not pull or clone for them.",
    subject_key="FILE",
)

#: Pointers a built artefact (a wheel, the build hook's wheel) holds as files.
LFS_POINTER_SHIPPED: Final = Message(
    code="lfs-pointer/shipped",
    condition="lfs-pointer",
    lines=(
        Line(
            level="WARNING",
            template="FILE=%(file)s: Git LFS pointer shipped%(count)s; "
            "the build did not pull LFS content",
        ),
    ),
    summary="A built artefact ships Git LFS pointer files instead of the "
    "content they stand for.",
    did="Recorded each pointer file with the hashes of the bytes it holds.",
    effect="none",
    actor="user",
    advice="Tell the user the artefact was built without the LFS content: "
    "to run 'git lfs pull' before building if the content belongs in it, "
    "and to rebuild. Do not rebuild for them.",
    subject_key="FILE",
)

_LOOKS: Final = "header looks like a Git LFS pointer but is not a valid one"

#: A file that opens like a pointer but is not a whole, valid one: its own
#: family, since its condition is another.
LFS_POINTER_MALFORMED: Final = Message(
    code="lfs-pointer-malformed",
    condition="malformed",
    lines=(
        Line(
            level="WARNING",
            template=f"FORMAT=%(format)s FILE=%(file)s: {_LOOKS}; "
            "not listed as an AI model",
        ),
        Line(
            level="WARNING",
            template=f"FILE=%(file)s: {_LOOKS}; not listed as an AI model",
        ),
        Line(level="ERROR", template=f"%(path)s: {_LOOKS}"),
    ),
    summary="A file opens with a Git LFS pointer line, but the rest is not a "
    "valid pointer (damaged, cut short or over 1 KiB).",
    did="Did not list the file as an AI model; a model file named on its own "
    "is refused and nothing is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user the file is neither a model nor a valid pointer: "
    "to check it out again, or to replace it with the content. Do not change "
    "the file for them.",
    subject_key="FILE",
)

ENTRIES: Final = (LFS_POINTER, LFS_POINTER_SHIPPED, LFS_POINTER_MALFORMED)
