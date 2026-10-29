# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``lfs-pointer`` family (a Git LFS pointer met instead of its content)
and ``lfs-pointer-malformed`` (a file that only opens like one).

See also: :mod:`pitloom.core.lfs_pointer` (the summary warning, and the
refusal of a model file named on its own) and :mod:`pitloom.extract.scanner`
(a pointer that is not whole).
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
    summary="A file is a Git LFS pointer: a small text file standing in for "
    "content the checkout does not have (made or cloned without Git LFS).",
    did="Listed each pointer file by the SHA-256 the pointer states for its "
    "content, with the stated size in the hash comment (no SHA-512, no "
    "content type); did not read the content or list it as an AI model. One "
    "warning names the first file in sorted order and, for more than one, "
    "how many.",
    effect="thinner",
    actor="user",
    advice="Tell the user the SBOM still identifies each file by its "
    "content's SHA-256 but lacks what reading it gives (AI model details, "
    "SHA-512). If they want them, they run 'git lfs pull' in the checkout "
    "(for a Git URL: clone it with Git LFS and run Pitloom on that "
    "directory) and generate again. Do not pull, clone or regenerate for "
    "them; ask first, and with nobody to ask, report it only.",
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
    summary="A built wheel or sdist holds Git LFS pointer files where the "
    "content belongs: it was built from a checkout without the LFS content.",
    did="Listed each file as the artefact holds it, with the hashes of the "
    "pointer text.",
    effect="none",
    actor="user",
    advice="Tell the user the artefact is probably broken: whoever installs "
    "it gets pointer text, not the files. If the content belongs in it, they "
    "run 'git lfs pull' before building and build again, before publishing. "
    "Do not rebuild for them.",
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
    summary="A file starts with the Git LFS pointer line but is not a valid "
    "pointer: damaged, cut short, or 1 KiB or larger.",
    did="Listed it as an ordinary file, hashed as it is, not as an AI model.",
    effect="thinner",
    actor="user",
    advice="Tell the user the file is neither its content nor a valid "
    "pointer: they check it out again or replace it with the real content, "
    "then generate again. Do not change the file for them.",
    subject_key="FILE",
)

ENTRIES: Final = (LFS_POINTER, LFS_POINTER_SHIPPED, LFS_POINTER_MALFORMED)
