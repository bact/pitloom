# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hugging Face Hub's own conditions: a model read without a revision
(``hub-revision-unpinned``) or at the default branch though its URL names
another (``hub-revision-unpinned/url``), and an answer of the Hub API
(``model_info()``, ``dataset_info()``) that could not be read
(``hub-response-invalid``). A failed, timed-out or offline Hub API request
is said by the families every remote route shares.

See also: :mod:`pitloom.messages._remote_fetch` (``download-network-failed``,
``download-timeout``, ``offline-unusable``) and
:mod:`pitloom.extract.remote._hub_api` (which says each failure).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"

#: A model whose files are read without a revision the Hub stated.
HUB_UNPINNED_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: the Hub stated no revision; files are read at the "
    "default branch as it is now",
)

#: A model read at no stated revision.
HUB_REVISION_UNPINNED: Final = Message(
    code="hub-revision-unpinned",
    condition="unpinned",
    lines=(HUB_UNPINNED_LINE,),
    summary="model_info() stated no revision (commit hash) of a Hugging "
    "Face model: the request failed, or the Hub (a mirror, a private Hub) "
    "sent none. Its files (config.json, the model card, a licence file) "
    "are read at the default branch as it is at the time of the run, which "
    "can change between runs.",
    did="Read the model's files at the default branch (said once per read "
    "of a model, however many files); the SBOM records no version of the "
    "model.",
    effect="weaker",
    actor="user",
    advice="Tell the user the files were read without a revision, so a "
    "later run can read other files. Nothing they pass to Pitloom pins it; "
    "for a repeatable result they download the repository at a commit and "
    f"run Pitloom on the local copy. Do not download it for them; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

#: A model URL that names a revision the files are not read at.
HUB_URL_REVISION_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: the URL names the revision %(ref)s; files are read "
    "at the default branch",
)

#: A model URL whose revision is not read.
HUB_REVISION_UNPINNED_URL: Final = Message(
    code="hub-revision-unpinned/url",
    condition="unpinned",
    lines=(HUB_URL_REVISION_LINE,),
    summary="The Hugging Face model URL given names a revision after a page "
    "kind (/tree/<rev>, /blob/<rev>/<file>, /commit/<sha>) other than main. "
    "Pitloom reads a model's files at its default branch only, so they can "
    "differ from that revision's.",
    did="Read the model's files at the default branch, said before anything "
    "is fetched; the SBOM records the revision the Hub states for that "
    "branch.",
    effect="weaker",
    actor="user",
    advice="Tell the user the SBOM describes the default branch, not the "
    "revision their URL names. For that revision they download the "
    "repository at it and run Pitloom on the local copy. Do not download it "
    f"for them; {ASK_FIRST}",
    subject_key="URL",
    since="0.25.1",
)

#: An answer of the Hub API that could not be read.
HUB_RESPONSE_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: the Hub's answer could not be read (%(failure)s); "
    "%(outcome)s",
)

#: An answer of the Hub API Pitloom could not read.
HUB_RESPONSE_INVALID: Final = Message(
    code="hub-response-invalid",
    condition="invalid",
    lines=(HUB_RESPONSE_LINE,),
    summary="The Hugging Face Hub answered model_info() or dataset_info() "
    "with something huggingface_hub or Pitloom could not read: not JSON, "
    "or JSON without the shape the API gives.",
    did="Recorded none of what the request states, as the line's outcome "
    "names, and read the rest.",
    effect="thinner",
    actor="user",
    advice="Tell the user the Hub's answer was not usable, as the line says. "
    "They may run again later; with HF_ENDPOINT set, the Hub it names may "
    f"not speak the Hugging Face API. Do not change HF_ENDPOINT for them; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (
    HUB_REVISION_UNPINNED,
    HUB_REVISION_UNPINNED_URL,
    HUB_RESPONSE_INVALID,
)
