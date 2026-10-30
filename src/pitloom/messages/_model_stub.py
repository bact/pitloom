# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Why a model file is listed without its metadata (a format-only entry, a
"stub") or not listed as a model, and why its parameter count is missing or
replaced: ``library-missing``, ``reader-unsafe``, ``model-unreadable``,
``model-wrong-format``, ``parameter-count-invalid`` and
``hyperparameter-conflict``. An input over a cap is ``over-cap``; a Git LFS
pointer is ``lfs-pointer``.

See also: :mod:`pitloom.extract.scanner` (the one read rule every surface
applies), :mod:`pitloom.messages._model_limits` (the bound-check reasons) and
:mod:`pitloom.core.optional_libraries` (the libraries and their extras).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: What a model whose read stopped is, in the SBOM.
_STUB: Final = (
    "Listed the model by its file, format and hashes only (a format-only "
    "entry, named after its file), without its metadata"
)
#: The end of every advice an agent relays without acting on it.
_ASK: Final = "ask first, and with nobody to ask, report it only."

#: A model reader's library missing, in a scan or for a model file named on
#: its own: the model is a stub.
LIBRARY_MISSING_LINE: Final = Line(
    level="WARNING",
    template="FORMAT=%(format)s FILE=%(file)s: required library not installed; "
    "install %(requirement)s",
)
#: A library a step needs missing: the step does not run.
LIBRARY_MISSING_ERROR_LINE: Final = Line(
    level="ERROR",
    template="required library not installed: %(module)s; install %(requirement)s",
)
LIBRARY_MISSING: Final = Message(
    code="library-missing",
    condition="missing",
    lines=(LIBRARY_MISSING_LINE, LIBRARY_MISSING_ERROR_LINE),
    summary="A library Pitloom needs for a step is not installed: an optional "
    "extra for a model reader, the Hugging Face Hub, SPDX 3 validation, "
    "--allow-build or magika content types.",
    did="For a model file, listed the model by its file, format and hashes only "
    "(a format-only entry, named after its file), without its metadata. For "
    "any other step, did not run it: no SBOM of a Hugging Face model, no "
    "validation; --allow-build found the files without a build, as its Build: "
    "lines say. Installed nothing.",
    effect="thinner",
    actor="user",
    advice="Tell the user which models or which step went without the library "
    "and which extra installs it, as the line names it (pitloom[ai] installs "
    "every model reader and the Hugging Face Hub client). They install it where "
    "Pitloom runs (with uvx or pipx, in the --from or --spec requirement) and "
    "run again; a model reader then runs on each such file, so only for files "
    f"they trust. Do not install anything or run again for them; {_ASK}",
    subject_key="FILE",
)

#: The formats a wheel scan does not read: one line per scan.
READER_UNSAFE: Final = Message(
    code="reader-unsafe",
    condition="unsafe",
    lines=(
        Line(
            level="INFO",
            template="AI models in a wheel in these formats are listed without "
            "metadata, their reader not being run on a wheel's files: "
            "%(formats)s. Pass --trust-wheel-model for a wheel you trust.",
        ),
    ),
    summary="A wheel holds AI models in formats whose reader Pitloom does not "
    "run on a wheel's files (fastText, GGUF, HDF5, ONNX, PyTorch .pt and "
    ".pth): a hostile file could crash or hang it, or exhaust its memory.",
    did=f"{_STUB}, its reader not run. One line per scan names the formats "
    "met that no earlier line of the run named.",
    effect="thinner",
    actor="user",
    advice="Tell the user which formats in the wheel were not read, and why. If "
    "they trust the wheel, they pass --trust-wheel-model (trust_wheel_model="
    "True in the library; the trust-wheel-model input of the GitHub Action, "
    "with embed-wheel and an empty project-path) and generate again; no config "
    f"file can set it. Do not add the flag or generate again for them; {_ASK}",
)

#: A reader that failed on a file whose header is a model format's.
READ_FAILED_LINE: Final = Line(
    level="WARNING",
    template="FORMAT=%(format)s FILE=%(file)s: failed to extract metadata; %(error)s",
)
#: A bound check that found the file declares more than it can hold, or
#: could not run.
LIMIT_LINE: Final = Line(
    level="WARNING",
    template="FORMAT=%(format)s FILE=%(file)s: %(reason)s; metadata not read",
)
MODEL_UNREADABLE: Final = Message(
    code="model-unreadable",
    condition="unreadable",
    lines=(READ_FAILED_LINE, LIMIT_LINE),
    summary="A file whose header is a model format's could not be read: its "
    "reader failed (a truncated or corrupt file, a format version the reader "
    "does not know), or the file declares more than it can hold.",
    did=f"{_STUB}; the line says what failed.",
    effect="thinner",
    actor="user",
    advice="Tell the user the model is listed without its metadata, and what "
    "failed, as the line says. They check the file (a partial download or copy "
    "is the common cause: fetch or export it again), or update the reader's "
    "library or Pitloom for a newer format version, and generate again. Do not "
    f"change, replace or download the file for them; {_ASK}",
    subject_key="FILE",
)

#: A file named as a model, on its own, whose header is another format's.
HEADER_IS_NOT_LINE: Final = Line(
    level="ERROR", template="%(path)s: header is not %(format)s"
)
#: An empty file named as a model, on its own.
EMPTY_LINE: Final = Line(level="ERROR", template="%(path)s: file is empty")
#: A file named on its own that is no model of any supported format.
NOT_A_MODEL_LINE: Final = Line(
    level="ERROR", template="%(path)s: not an AI model file of a supported format"
)
MODEL_WRONG_FORMAT: Final = Message(
    code="model-wrong-format",
    condition="wrong-format",
    lines=(
        Line(
            level="WARNING",
            template="FORMAT=%(format)s FILE=%(file)s: header is not "
            "%(format)s; not listed as an AI model",
        ),
        HEADER_IS_NOT_LINE,
        EMPTY_LINE,
        NOT_A_MODEL_LINE,
    ),
    summary="A file named as an AI model is not one: its header is not the "
    "format its suffix names, it is empty, or (a file named on its own) it is "
    "no model of a supported format.",
    did="In a scan, listed it as a file with its hashes, not as an AI model. "
    "loom model, loom enrich and loom generate refuse a file named on its own.",
    effect="thinner",
    actor="user",
    advice="Tell the user the file is not the model its name says: a wrong "
    "suffix, a placeholder or a damaged copy. If a model belongs there, they "
    "put the real file in its place and generate again; for loom model or loom "
    "enrich, they name the model file itself. Do not rename, replace or "
    f"download the file for them; {_ASK}",
    subject_key="FILE",
)

#: What a rejected parameter count leaves out, as each of its warnings ends.
PARAMETER_COUNT_SKIPPED: Final = "parameter count not recorded"
#: Why a tensor's dimension gives no count, ``%(value)s`` the dimension as
#: the file states it (:class:`pitloom.core.model_parameters.ParameterCountRejected`).
DIMENSION_REASON: Final = "tensor dimension %(value)s is not a non-negative integer"
#: Why a count a source states is none.
STATED_COUNT_REASON: Final = "stated parameter count is not a non-negative integer"
#: A reader's line, without the model's name: the scan names it, before the
#: line, when it says the line again.
DIMENSION_LINE: Final = Line(
    level="WARNING", template=f"{DIMENSION_REASON}; {PARAMETER_COUNT_SKIPPED}"
)
PARAMETER_COUNT_INVALID: Final = Message(
    code="parameter-count-invalid",
    condition="invalid",
    lines=(
        DIMENSION_LINE,
        Line(
            level="WARNING",
            template=f"FORMAT=%(format)s FILE=%(file)s: {STATED_COUNT_REASON}; "
            f"{PARAMETER_COUNT_SKIPPED}",
        ),
    ),
    summary="A model's parameter count cannot be had: a tensor dimension in the "
    "file, or the count its metadata or the Hugging Face Hub states, is not a "
    "non-negative integer.",
    did="Recorded no parameter count, never a partial one, and read the rest "
    "of the model.",
    effect="thinner",
    actor="user",
    advice="Tell the user the SBOM has no parameter count for the model, and "
    "why, as the line says: a malformed tensor shape, or a malformed count its "
    "metadata or the Hub states. The rest of the model is read. Do not edit "
    "the file or state a count for them.",
    subject_key="FILE",
)

#: A model's own ``parameters`` hyperparameter, where the SBOM holds the
#: count (:data:`pitloom.core.model_parameters.PARAMETER_COUNT_KEY`).
HYPERPARAMETER_CONFLICT: Final = Message(
    code="hyperparameter-conflict",
    condition="conflict",
    lines=(
        Line(
            level="WARNING",
            template="FORMAT=%(format)s FILE=%(file)s: hyperparameter parameters "
            "replaced by the parameter count",
        ),
    ),
    summary="A model states a hyperparameter named parameters, the key the SBOM "
    "holds its parameter count under.",
    did="Recorded the parameter count (summed from the model's tensors, or "
    "stated by the Hugging Face Hub) under the parameters key, in place of the "
    "model's own value.",
    effect="none",
    actor="none",
    advice="the parameters entry is the parameter count, as the package's "
    "comment says; the model's own value is still in the model.",
    subject_key="FILE",
)

ENTRIES: Final = (
    LIBRARY_MISSING,
    READER_UNSAFE,
    MODEL_UNREADABLE,
    MODEL_WRONG_FORMAT,
    PARAMETER_COUNT_INVALID,
    HYPERPARAMETER_CONFLICT,
)
