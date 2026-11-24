# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The lines of a ``loom.run()`` (the loom SDK) that are its own: the
caller of a loom call that could not be found on the stack
(``caller-info-unreadable``), a model ``path=`` that is no file when the
run ends with no ID registry loaded (``model-file-missing``), and an
output dataset naming an input this run never declared
(``reference-not-found/dataset``). Each starts with
:data:`LOOM_SDK_PREFIX`, a literal, not a frame.

See also: :mod:`pitloom._loom_caller`, :mod:`pitloom._loom_model` and
:mod:`pitloom._loom_active_run` (where they are said),
:mod:`pitloom.messages.datasets` and :mod:`pitloom.messages.fragments`
(the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.logging_config import field_loss_suffix
from pitloom.messages._types import Line, Message

_SINCE: Final = "0.25.0"

#: What every line of the loom SDK starts with.
LOOM_SDK_PREFIX: Final = "loom SDK: "

#: ``inspect.stack()`` failed while naming a loom call's caller.
CALLER_INFO_LINE: Final = Line(
    level="WARNING",
    template=f"{LOOM_SDK_PREFIX}caller info not determined: %(failure)s"
    + field_loss_suffix(
        "degraded",
        "provenance Source (falls back to 'unknown'; Method: inspect_caller "
        "is still recorded)",
    ),
)
#: ``inspect.stack()`` failed while naming the script that opened the run.
CALLER_SCRIPT_LINE: Final = Line(
    level="WARNING",
    template=f"{LOOM_SDK_PREFIX}caller script path not determined: %(failure)s"
    + field_loss_suffix("skipped", "caller_script_path"),
)

CALLER_INFO_UNREADABLE: Final = Message(
    code="caller-info-unreadable",
    condition="unreadable",
    lines=(CALLER_INFO_LINE, CALLER_SCRIPT_LINE),
    summary="The loom SDK could not inspect the call stack (inspect.stack "
    "raised: a sandboxed or frozen interpreter) to name the script and "
    "function that made a loom call, or the script that opened the run. "
    "Said once per process.",
    did="Recorded the provenance with Source 'unknown' (Method: "
    "inspect_caller still recorded), or the fragment without the calling "
    "script's file and its relationships to the model and output datasets; "
    "the fragment is written.",
    effect="thinner",
    actor="none",
    advice="Nothing to do: the interpreter does not let a program inspect "
    "its own call stack. Run the script under a standard CPython to have "
    "the caller recorded.",
    since=_SINCE,
)

#: A model ``path=`` that is no regular file at run exit, no ID registry
#: loaded (with one, ``registry-hash-missing`` says it).
MODEL_FILE_LINE: Final = Line(
    level="WARNING",
    template=f"{LOOM_SDK_PREFIX}model %(entity)s: path= %(path)s is not a file "
    "at exit; not hashed",
)

MODEL_FILE_MISSING: Final = Message(
    code="model-file-missing",
    condition="missing",
    lines=(MODEL_FILE_LINE,),
    summary="A model declared with loom.set_model or loom.use_model names a "
    "path= that is no regular file when the run ends: it is gone, a "
    "directory, or a name holding a NUL. No ID registry is loaded (with one, "
    "registry-hash-missing says the lookup is ungated).",
    did="Recorded the model without a hash (no verifiedUsing); the fragment "
    "is written.",
    effect="thinner",
    actor="caller",
    advice="The caller may give path= the model file the run writes, and "
    "keep it in place until the run ends, so the model is hashed.",
    since=_SINCE,
)

#: ``add_output_dataset(input_datasets=[...])`` naming an input this run did
#: not declare.
DATASET_REFERENCE_LINE: Final = Line(
    level="WARNING",
    template=f"{LOOM_SDK_PREFIX}add_output_dataset(%(dataset)s) names "
    "input_datasets=%(dataset_input)s, which no add_input_dataset of this run "
    "declared; not linked",
)

REFERENCE_NOT_FOUND_DATASET: Final = Message(
    code="reference-not-found/dataset",
    condition="not-found",
    lines=(DATASET_REFERENCE_LINE,),
    summary="A loom run's add_output_dataset names, in input_datasets, a "
    "dataset no add_input_dataset of the same run declared (a typo, or an "
    "input declared in another run).",
    did="Linked the output dataset to the inputs it names that were declared, "
    "not to this one; the fragment is written.",
    effect="thinner",
    actor="caller",
    advice="The caller may declare the input with add_input_dataset in the "
    "same run, or correct the name in input_datasets, and run again.",
    since=_SINCE,
)

ENTRIES: Final = (
    CALLER_INFO_UNREADABLE,
    MODEL_FILE_MISSING,
    REFERENCE_NOT_FOUND_DATASET,
)
