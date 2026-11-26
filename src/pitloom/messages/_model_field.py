# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model read whole but for some of its fields: a part the reader could
not read (``model-field-unreadable``), a key the file states twice
(``model-field-conflict``), a field SPDX 3.0.1 has no property for
(``field-not-recordable``), and a value its property cannot hold
(``model-field-invalid``).

A reader's line names no model: the scan puts
:data:`~pitloom.messages.RELAY_FRAME` (``FORMAT=<fmt> FILE=<path>: ``)
before it.

See also: :mod:`pitloom.messages._model_stub` (a model not read at all) and
:mod:`pitloom.extract.ai_model.unrecordable` (the elements SPDX 3.0.1 cannot
record).
"""

from __future__ import annotations

from typing import Final

from pitloom.logging_config import field_loss_suffix
from pitloom.messages._types import Line, Message

#: What a line ends in: the fields left unset.
_SKIPPED: Final = field_loss_suffix("skipped", "%(fields)s")
#: What a line ends in: the fields recorded weaker.
_DEGRADED: Final = field_loss_suffix("degraded", "%(fields)s")


#: The release that first prints the lines that began "Failed to" in lower
#: case, as every other line begins.
_LOWER_SINCE: Final = "0.25.0"


def _skipped(template: str, since: str | None = None) -> Line:
    """A ``WARNING`` line: *template*, then the fields left unset."""
    return Line(level="WARNING", template=template + _SKIPPED, since=since)


FASTTEXT_ARGS_LINE: Final = _skipped(
    "failed to read fastText model.f.getArgs(): %(error)s", _LOWER_SINCE
)
FASTTEXT_LABELS_LINE: Final = _skipped(
    "failed to read fastText model labels: %(error)s", _LOWER_SINCE
)
#: fickling refused the pickle (shared by the bound and the parse).
FICKLING_PARSE_LINE: Final = _skipped(
    "fickling failed to parse pickle bytes: %(error)s"
)
FICKLING_WALK_LINE: Final = _skipped(
    "fickling parsed pickle but AST walk failed: %(error)s"
)
#: A PyTorch archive's pickle member, *name* the provenance source.
PICKLE_MEMBER_LINE: Final = _skipped(
    "failed to inspect %(entry)s in %(name)s: %(error)s", _LOWER_SINCE
)
PT2_META_LINE: Final = _skipped(
    "failed to parse PT2 metadata entry %(entry)s: %(error)s", _LOWER_SINCE
)
PT2_EXTRA_LINE: Final = _skipped(
    "failed to read PT2 extra file %(entry)s: %(error)s", _LOWER_SINCE
)
PT2_TAGS_LINE: Final = Line(
    level="WARNING",
    template="failed to parse PT2 extra/tags as JSON: %(error)s" + _DEGRADED,
    since=_LOWER_SINCE,
)
PT2_GRAPH_LINE: Final = _skipped(
    "failed to parse PT2 model graph %(entry)s: %(error)s", _LOWER_SINCE
)
PT2_VERSION_LINE: Final = _skipped(
    "failed to read PT2 %(entry)s: %(error)s", _LOWER_SINCE
)
#: A Keras or HDF5 root attribute that h5py cannot read.
ATTRIBUTE_LINE: Final = _skipped("%(part)s attribute cannot be read; %(error)s")
#: A ``model_config`` part not as Keras writes it, the raw text kept.
CONFIG_RAW_LINE: Final = _skipped(
    "%(part)s %(error)s; kept as properties.model_config_raw"
)
#: As :data:`CONFIG_RAW_LINE`, the raw text cut to its cap.
CONFIG_RAW_CUT_LINE: Final = _skipped(
    "%(part)s %(error)s; kept as properties.model_config_raw, the first "
    "%(limit)s of %(number)s characters"
)
#: A ``model_config`` part not as Keras writes it, after some fields.
CONFIG_KEPT_LINE: Final = _skipped(
    "%(part)s %(error)s; the fields read before it are kept"
)
#: A ``training_config`` part not as Keras writes it.
TRAINING_CONFIG_LINE: Final = _skipped("%(part)s %(error)s; reading stopped there")
#: A JSON member of a ``.keras`` archive (``config.json``) that does not
#: parse, or whose top level is no object.
KERAS_MEMBER_LINE: Final = _skipped(
    "%(part)s %(error)s; the other archive members are read"
)

MODEL_FIELD_UNREADABLE: Final = Message(
    code="model-field-unreadable",
    condition="unreadable",
    lines=(
        FASTTEXT_ARGS_LINE,
        FASTTEXT_LABELS_LINE,
        FICKLING_PARSE_LINE,
        FICKLING_WALK_LINE,
        PICKLE_MEMBER_LINE,
        PT2_META_LINE,
        PT2_EXTRA_LINE,
        PT2_TAGS_LINE,
        PT2_GRAPH_LINE,
        PT2_VERSION_LINE,
        ATTRIBUTE_LINE,
        CONFIG_RAW_LINE,
        CONFIG_RAW_CUT_LINE,
        CONFIG_KEPT_LINE,
        TRAINING_CONFIG_LINE,
        KERAS_MEMBER_LINE,
    ),
    summary="A model reader read the file but not one of its parts (a fastText "
    "call, a PyTorch pickle, a PT2 archive member, a Keras or HDF5 attribute "
    "or config): the fields the line names are not recorded, or are recorded "
    "weaker.",
    did="Recorded the rest of the model; the line names the fields skipped "
    "(not recorded) or degraded (kept in a weaker form, such as raw text), and "
    "what the reader reported.",
    effect="thinner",
    actor="user",
    advice="Tell the user which model and which fields the SBOM lacks, and "
    "what the reader reported, as the line says: a damaged or unusual file, or "
    "a format version Pitloom does not read. The rest of the model is read. Do "
    "not edit or replace the file for them.",
    since="0.23.0",
)

GGUF_LENGTH_LINE: Final = Line(
    level="WARNING",
    template="GGUF key %(entry)s is in the file; the length of array %(name)s "
    "is not a property",
)
#: *name*: the first keys, each cut short, ``, ...`` after them when more.
ONNX_REPEATED_LINE: Final = Line(
    level="WARNING",
    template="ONNX metadata_props: %(number)s key(s) appear more than once; "
    "kept the last value of each: %(name)s",
)
MODEL_FIELD_CONFLICT: Final = Message(
    code="model-field-conflict",
    condition="conflict",
    lines=(GGUF_LENGTH_LINE, ONNX_REPEATED_LINE),
    summary="A model states one key twice: a GGUF file states the length of "
    "an array as a key of its own, or an ONNX file repeats a metadata_props "
    "key.",
    did="Recorded what the file's own reader sees: the GGUF key as the file "
    "states it, not the length Pitloom would derive; the last value of each "
    "repeated ONNX key, as protobuf keeps it.",
    effect="none",
    actor="none",
    advice="the SBOM states what the model's own reader sees; the other value "
    "is still in the model.",
    since="0.23.0",
)

FIELD_NOT_RECORDABLE: Final = Message(
    code="field-not-recordable",
    condition="not-recordable",
    lines=(
        Line(
            level="INFO",
            template="FORMAT=%(format)s FILE=%(file)s: no SPDX 3.0.1 property: "
            "%(elements)s",
        ),
    ),
    summary="A model holds a value for a G7 SBOM for AI element that SPDX "
    "3.0.1 has no property for (the model architecture).",
    did="Wrote the value in the broader property the line names "
    "(ai_typeOfModel, after the type), or did not record it; the SBOM is "
    "otherwise unchanged.",
    effect="weaker",
    actor="none",
    advice="SPDX 3.0.1 has no property for the element; the line says where its "
    "value is written, if anywhere.",
    subject_key="FILE",
    since="0.23.0",
)

#: A release time stated (a Hub revision's, or a library caller's
#: ``AiModelMetadata.release_time``) that is not an ISO 8601 time.
RELEASE_TIME_LINE: Final = Line(
    level="WARNING",
    template="FORMAT=%(format)s FILE=%(file)s: release time is not ISO 8601; left out",
)

MODEL_FIELD_INVALID: Final = Message(
    code="model-field-invalid",
    condition="invalid",
    lines=(RELEASE_TIME_LINE,),
    summary="A model states a value its SBOM property cannot hold: a release "
    "time (a Hugging Face revision's, or a library caller's "
    "AiModelMetadata.release_time) that is not an ISO 8601 time. The line "
    "does not print the value.",
    did="Left the property out (no releaseTime); the rest of the model is "
    "recorded. FORMAT=unknown names a library caller's model of no format.",
    effect="thinner",
    actor="user",
    advice="Tell the user which model's release time was left out. A library "
    "caller may pass an ISO 8601 time (2024-01-31T12:00:00Z) and generate "
    "again; a value read from a model or the Hub is the source's. Do not edit "
    "the source for them.",
    subject_key="FILE",
    since="0.25.0",
)

ENTRIES: Final = (
    MODEL_FIELD_UNREADABLE,
    MODEL_FIELD_CONFLICT,
    FIELD_NOT_RECORDABLE,
    MODEL_FIELD_INVALID,
)
