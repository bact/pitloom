# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The dataset lines every route shares (the CLI, the build hook, the
library and the loom SDK): a dataset value that is not of its field's shape
(``dataset-field-invalid``), a Croissant document with no name
(``dataset-name-missing``), and two references to one dataset that differ
(``dataset-conflict``) or spell its name two ways
(``dataset-conflict/spelling``).

See also: :mod:`pitloom.messages._datasets_say` (the helpers that say
them), :mod:`pitloom.extract.dataset.values` (the value checks),
:mod:`pitloom.extract.dataset.croissant`, :mod:`pitloom.core.dataset_merge`
and :mod:`pitloom.core.dataset_names` (where they are said).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

_SINCE: Final = "0.25.0"

#: What every ``dataset-field-invalid`` line starts with.
DATASET_METADATA_PREFIX: Final = "dataset metadata: "
_WHERE: Final = (
    f"{DATASET_METADATA_PREFIX}SOURCE=%(dataset_source)s FIELD=%(dataset_field)s: "
)

#: A value of a type that holds no text (a number, a mapping, several
#: items).
NOT_TEXT_LINE: Final = Line(
    level="WARNING",
    template=f"{_WHERE}a value of type %(dataset_value_type)s, not text; skipped",
)
#: A card ``version`` YAML read as a number, a Boolean, a date or nothing
#: (``1.10`` reads as ``1.1``): written unquoted.
UNQUOTED_VERSION_LINE: Final = Line(
    level="WARNING",
    template=f"{_WHERE}a value of type %(dataset_value_type)s, not text; quote it "
    "to keep it as written; skipped",
)
#: Text in a URL field that is not a URL.
NOT_A_URL_LINE: Final = Line(level="WARNING", template=f"{_WHERE}not a URL; skipped")
#: A size or count that is not a whole number of zero or more.
NOT_A_COUNT_LINE: Final = Line(
    level="WARNING",
    template=f"{_WHERE}not a whole number of zero or more; skipped",
)

DATASET_FIELD_INVALID: Final = Message(
    code="dataset-field-invalid",
    condition="invalid",
    lines=(NOT_TEXT_LINE, UNQUOTED_VERSION_LINE, NOT_A_URL_LINE, NOT_A_COUNT_LINE),
    summary="A dataset source (a dataset card, a Croissant document, a GGUF "
    "file's dataset keys, a Hugging Face model card's datasets) or a library "
    "caller's DatasetMetadata states a value its field cannot hold: a value "
    "that is not text, text in a URL field that is not a URL, or a size that "
    "is not a whole number of zero or more. A card version YAML read as a "
    "number, a Boolean or a date was written unquoted (1.10 reads as 1.1).",
    did="Left that value out of the dataset (for a list, that item); the "
    "dataset and its other fields are recorded.",
    effect="thinner",
    actor="user",
    advice="Tell the user which source and field the SBOM lacks, as the line "
    "names them. They may correct the value in the source (quote a card "
    "version, give a URL with its scheme and host, a size in whole bytes) "
    "and generate again. Do not edit the source for them.",
    subject_key="SOURCE",
    since=_SINCE,
)

#: A Croissant name that holds no text.
NAME_NOT_TEXT_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: no dataset name: the Croissant name is a value of "
    "type %(dataset_value_type)s, not text; not read",
)
#: A Croissant document with no name, or a blank one.
NAME_ABSENT_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: Croissant document has no name; not read"
)

DATASET_NAME_MISSING: Final = Message(
    code="dataset-name-missing",
    condition="missing",
    lines=(NAME_NOT_TEXT_LINE, NAME_ABSENT_LINE),
    summary="A Croissant document (read for a loom dataset's croissant=, or "
    "by the library's read_croissant) states no name for its dataset, or "
    "one that is not text.",
    did="Read nothing from the document: read_croissant and a loom "
    "declaration with croissant= raise ValueError carrying the code; the "
    "dataset is not declared, so a run the exception leaves writes nothing.",
    effect="not-written",
    actor="user",
    advice="Tell the user which document has no usable name. They give the "
    "document a name (schema.org name, as text) or name another document, "
    "and run again. Do not edit the document for them.",
    subject_key="FILE",
    since=_SINCE,
)

#: Two references to one dataset that state different values of a field.
CONFLICT_LINE: Final = Line(
    level="WARNING",
    template="DATASET=%(dataset)s FIELD=%(dataset_field)s: references differ; "
    "kept the first",
)

DATASET_CONFLICT: Final = Message(
    code="dataset-conflict",
    condition="conflict",
    lines=(CONFLICT_LINE,),
    summary="Two references to one dataset (a model's card and its file, "
    "or a model listing it twice) state different values of one field. Said "
    "once per dataset and field.",
    did="Recorded the first reference's value; the other is left out. The "
    "dataset is recorded once, with the roles of every reference.",
    effect="weaker",
    actor="user",
    advice="Tell the user which dataset and field the references disagree "
    "on; the SBOM states the first value read. They may correct the source "
    "that is wrong and generate again. Do not edit a source for them.",
    subject_key="DATASET",
    since=_SINCE,
)

#: Two spellings of one dataset's name, read as one dataset.
SPELLING_LINE: Final = Line(
    level="INFO",
    template="DATASET=%(dataset)s: %(dataset_spelling)s names it too; kept the "
    "first spelling",
)

DATASET_CONFLICT_SPELLING: Final = Message(
    code="dataset-conflict/spelling",
    condition="conflict",
    lines=(SPELLING_LINE,),
    summary="Two references name one dataset in different spellings (a Hub "
    "id in other case, or other spacing), which name one dataset.",
    did="Recorded one dataset, named by the first spelling read.",
    effect="none",
    actor="none",
    advice="Nothing to do: the spellings name one dataset, recorded once "
    "under the first.",
    subject_key="DATASET",
    since=_SINCE,
)

ENTRIES: Final = (
    DATASET_FIELD_INVALID,
    DATASET_NAME_MISSING,
    DATASET_CONFLICT,
    DATASET_CONFLICT_SPELLING,
)
