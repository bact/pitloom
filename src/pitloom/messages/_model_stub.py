# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Why a model file is listed without its metadata (a format-only entry, a
"stub") or not listed as a model, and why its parameter count is missing or
replaced: ``library-missing``, ``library-unusable``, ``reader-unsafe`` (and
its Git URL variant), ``model-unreadable``, ``model-wrong-format``,
``parameter-count-invalid`` and ``hyperparameter-conflict``. An input over
a cap is ``over-cap``; a Git LFS pointer is ``lfs-pointer``.

See also: :mod:`pitloom.extract.scanner` (the one read rule every surface
applies), :mod:`pitloom.messages._model_limits` (the bound-check reasons) and
:mod:`pitloom.core.optional_libraries` (the libraries and their extras).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages._surface import Twins
from pitloom.messages._types import ASK_FIRST, Line, Message

#: The release of a library twin of a line that names a flag.
_TWIN_SINCE: Final = "0.25.0"
#: How each surface lifts the reader gate, after ``; ``.
_TRUST_CLI: Final = "pass --trust-model-files"
_TRUST_LIBRARY: Final = "set trust_model_files=True"

#: What a model whose read stopped is, in the SBOM.
_STUB: Final = (
    "Listed the model by its file, format and hashes only (a format-only "
    "entry, named after its file), without its metadata"
)

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
#: The same, said as a warning by a step that goes on without the library
#: (``--allow-build`` without PyPA build, after ``Build: ``).
LIBRARY_MISSING_WARNING_LINE: Final = Line(
    level="WARNING", template=LIBRARY_MISSING_ERROR_LINE.template, since="0.25.0"
)
LIBRARY_MISSING: Final = Message(
    code="library-missing",
    condition="missing",
    lines=(
        LIBRARY_MISSING_LINE,
        LIBRARY_MISSING_ERROR_LINE,
        LIBRARY_MISSING_WARNING_LINE,
    ),
    summary="A library Pitloom needs for a step is not installed: an optional "
    "extra for a model reader, the Hugging Face Hub, SPDX 3 validation, "
    "--allow-build or magika content types.",
    did="For a model file, listed the model by its file, format and hashes only "
    "(a format-only entry, named after its file), without its metadata. For "
    "any other step, did not run it: no SBOM of a Hugging Face model, no "
    "validation; --allow-build (its warning line, after Build: ) found the "
    "files without a build, as the file discovery line after it says. "
    "Installed nothing.",
    effect="thinner",
    actor="user",
    advice="Tell the user which models or which step went without the library "
    "and which extra installs it, as the line names it (pitloom[ai] installs "
    "every model reader and the Hugging Face Hub client). They install it where "
    "Pitloom runs (with uvx or pipx, in the --from or --spec requirement) and "
    "run again; a model reader then runs on each such file, so only for files "
    f"they trust. Do not install anything or run again for them; {ASK_FIRST}",
    subject_key="FILE",
)

#: A model reader's library installed but failing to import.
LIBRARY_UNUSABLE_LINE: Final = Line(
    level="WARNING",
    template="FORMAT=%(format)s FILE=%(file)s: required library failed to import: "
    "%(error)s; reinstall %(requirement)s",
)
#: A library a step needs installed but failing to import.
LIBRARY_UNUSABLE_ERROR_LINE: Final = Line(
    level="ERROR",
    template="required library failed to import: %(module)s: %(error)s; "
    "reinstall %(requirement)s",
)
#: magika failing to import under content-type method ``auto``: once per process.
LIBRARY_UNUSABLE_CONTENT_LINE: Final = Line(
    level="WARNING",
    template="required library failed to import: %(module)s: %(error)s; "
    "content types from file extensions; reinstall %(requirement)s",
)
#: poetry-core, a dependency of Pitloom, without the functions Pitloom calls.
LIBRARY_API_LINE: Final = Line(
    level="WARNING",
    template="required library API not found: poetry-core: %(error)s; Poetry "
    "dependency tables not read; reinstall Pitloom",
    since="0.25.0",
)
LIBRARY_UNUSABLE: Final = Message(
    code="library-unusable",
    condition="unusable",
    lines=(
        LIBRARY_UNUSABLE_LINE,
        LIBRARY_UNUSABLE_ERROR_LINE,
        LIBRARY_UNUSABLE_CONTENT_LINE,
        LIBRARY_API_LINE,
    ),
    summary="A library Pitloom needs for a step is installed but fails to "
    "import: a broken or partial install, a library it needs in turn missing, "
    "or a build for another Python or platform. The API line (since 0.25.0) "
    "is poetry-core, which Pitloom depends on, installed at a release that "
    "moved a function Pitloom calls.",
    did="For a model file, listed the model by its file, format and hashes only "
    "(a format-only entry, named after its file), without its metadata. For "
    "any other step, did not run it: no SBOM of a Hugging Face model, no "
    "validation, no SBOM with magika content types (method magika); with "
    "method auto, every file's content type from its extension, said once per "
    "process. Without poetry-core's API, read no [tool.poetry] dependency "
    "table, said once per process. Installed nothing.",
    effect="thinner",
    actor="user",
    advice="Tell the user which models or which step went without the library, "
    "what the import reported and which extra reinstalls it, as the line names "
    "it. They reinstall it where Pitloom runs (with uvx or pipx, in the --from "
    "or --spec requirement) and run again; a model reader then runs on each "
    "such file, so only for files they trust. Do not install anything or run "
    f"again for them; {ASK_FIRST}",
    subject_key="FILE",
    since="0.23.0",
)

_WHEEL_GATED: Final = (
    "AI models in a wheel in these formats are listed without metadata, their "
    "reader not being run on a wheel's files: %(formats)s; "
)
#: A wheel scan's line, as each surface lifts the gate.
READER_UNSAFE_LINES: Final = Twins.no_hook(
    cli=Line(
        level="INFO", template=f"{_WHEEL_GATED}{_TRUST_CLI} for a wheel you trust"
    ),
    library=Line(
        level="INFO",
        template=f"{_WHEEL_GATED}{_TRUST_LIBRARY} for a wheel you trust",
        since=_TWIN_SINCE,
    ),
)

#: The formats a wheel scan does not read: one line per scan.
READER_UNSAFE: Final = Message(
    code="reader-unsafe",
    condition="unsafe",
    lines=READER_UNSAFE_LINES.members,
    summary="A wheel holds AI models in formats whose reader Pitloom does not "
    "run on a wheel's files (fastText, GGUF, HDF5, ONNX, PyTorch .pt and "
    ".pth): a hostile file could crash or hang it, or exhaust its memory.",
    did=f"{_STUB}, its reader not run. One line per scan names the formats "
    "met that no earlier line of the run named.",
    effect="thinner",
    actor="user",
    advice="Tell the user which formats in the wheel were not read, and why. If "
    "they trust the wheel, they pass --trust-model-files (trust_model_files="
    "True in the library; the trust-model-files input of the GitHub Action, "
    "with embed-wheel and an empty project-path) and generate again; no config "
    f"file can set it. Do not add the flag or generate again for them; {ASK_FIRST}",
)

_GIT_GATED: Final = (
    "AI models from a Git URL in these formats are listed without metadata, "
    "their reader not being run on a downloaded file: %(formats)s; "
)
_PYPI_GATED: Final = (
    "FILE=%(file)s: AI models in these formats are listed without metadata, "
    "their reader not being run on a downloaded file: %(formats)s; "
)
#: The Git URL's line: a model file of its temporary clone, named on its own
#: or found in a project's build file list. One line per SBOM.
_READER_UNSAFE_REMOTE_LINE: Final = Line(
    level="INFO", template=f"{_GIT_GATED}{_TRUST_CLI} for a repository you trust"
)
#: The same for the models of a wheel downloaded from a PyPI URL, named by
#: its file (so a call naming no file says the Git URL's line).
_READER_UNSAFE_PYPI_LINE: Final = Line(
    level="INFO", template=f"{_PYPI_GATED}{_TRUST_CLI} for a release you trust"
)
#: The Git URL's line, as each surface lifts the gate.
READER_UNSAFE_REMOTE_LINES: Final = Twins.no_hook(
    cli=_READER_UNSAFE_REMOTE_LINE,
    library=Line(
        level="INFO",
        template=f"{_GIT_GATED}{_TRUST_LIBRARY} for a repository you trust",
        since=_TWIN_SINCE,
    ),
)
#: The PyPI URL's line, as each surface lifts the gate.
READER_UNSAFE_PYPI_LINES: Final = Twins.no_hook(
    cli=_READER_UNSAFE_PYPI_LINE,
    library=Line(
        level="INFO",
        template=f"{_PYPI_GATED}{_TRUST_LIBRARY} for a release you trust",
        since=_TWIN_SINCE,
    ),
)

#: The formats whose reader is not run on a downloaded model file: of a Git
#: URL's temporary clone, or of a wheel downloaded from a PyPI URL.
READER_UNSAFE_REMOTE: Final = Message(
    code="reader-unsafe/remote",
    condition="unsafe",
    lines=(*READER_UNSAFE_REMOTE_LINES.members, *READER_UNSAFE_PYPI_LINES.members),
    summary="A model file or a project's model files read from a Git URL, or "
    "the models of a wheel downloaded from a PyPI URL, are in a format whose "
    "reader Pitloom does not run on a downloaded file (fastText, GGUF, HDF5, "
    "ONNX, PyTorch .pt and .pth): a hostile file could crash or hang it, or "
    "exhaust its memory.",
    did=f"{_STUB}, its reader not run.",
    effect="thinner",
    actor="user",
    advice="Tell the user which models from the Git URL or the PyPI URL were "
    "not read, and why. If they trust the repository's or the release's model "
    "files, they pass --trust-model-files (trust_model_files=True in the "
    "library; for a Git URL, the trust-model-files input of the GitHub "
    "Action) and generate again; no config file can set it. For a Git URL, "
    "running Pitloom on a local clone reads them in full too, but also "
    "honours the repository's own configuration and build file list. Do not "
    f"add the flag or generate again for them; {ASK_FIRST}",
    since="0.23.4",
)

#: The ``reader-unsafe`` line of a gate: its entry's code, and whether the
#: line names the downloaded file (a PyPI URL's wheel).
READER_UNSAFE_TWINS: Final[Mapping[tuple[str, bool], Twins[Line]]] = MappingProxyType(
    {
        (READER_UNSAFE.code, False): READER_UNSAFE_LINES,
        (READER_UNSAFE_REMOTE.code, False): READER_UNSAFE_REMOTE_LINES,
        (READER_UNSAFE_REMOTE.code, True): READER_UNSAFE_PYPI_LINES,
    }
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
    f"change, replace or download the file for them; {ASK_FIRST}",
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
    f"download the file for them; {ASK_FIRST}",
    subject_key="FILE",
)

#: What a rejected parameter count leaves out, as each of its warnings ends.
PARAMETER_COUNT_SKIPPED: Final = "parameter count not recorded"
#: What a GGUF header read in part leaves out, as its ``over-cap`` warning
#: ends: the walk stopped in the pair ``%(key)s`` (an array: its length is
#: the declared one), in the pair ``%(pair)d`` counted from 1 (its key
#: unread or empty; an array of an empty key: its length as declared), or in
#: the tensor infos.
GGUF_ARRAY_CUT: Final = (
    "%(key)s length as declared; later fields and the tensor shapes not read"
)
GGUF_FIELDS_NOT_READ: Final = "fields from %(key)s on and the tensor shapes not read"
GGUF_PAIR_NOT_READ: Final = (
    "fields from pair %(pair)d on and the tensor shapes not read"
)
GGUF_PAIR_ARRAY_CUT: Final = (
    "pair %(pair)d length as declared; later fields and the tensor shapes not read"
)
GGUF_TENSORS_NOT_READ: Final = f"tensor shapes not read; {PARAMETER_COUNT_SKIPPED}"
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
    LIBRARY_UNUSABLE,
    READER_UNSAFE,
    READER_UNSAFE_REMOTE,
    MODEL_UNREADABLE,
    MODEL_WRONG_FORMAT,
    PARAMETER_COUNT_INVALID,
    HYPERPARAMETER_CONFLICT,
)
