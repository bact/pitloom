# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Format-neutral AI model metadata dataclasses.

These classes are the format-neutral internal representation of AI model
metadata. They have no dependency on any SBOM library or model file format
library, making them easy to test and to consume from any serializer.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, TypedDict

from pitloom.core.canonical_json import canonical_json
from pitloom.core.dataset_metadata import DatasetReference
from pitloom.core.scalar_text import key_text, scalar_text, scalar_type, text_type

# Provenance of a name derived from the model's file name
FILE_NAME_STEM_PROVENANCE = "Source: Pitloom generator | Method: file_name_stem"


class AiModelFormat(str, Enum):
    """Supported AI model file formats.

    Attributes:
        extensions: File extensions (lowercase, with leading dot) that
            unambiguously identify this format and are used as the
            extension-fallback detection step.  Extensions shared across
            formats (e.g. ``.bin``) are omitted; those files are identified
            by magic bytes instead.
        magic: Fixed magic-byte prefix at byte offset 0, or ``None`` when
            the format has no fixed file-level signature or shares its
            signature with other formats (like ZIP-based formats).
    """

    # Declare instance attributes so static type checkers recognise them.
    extensions: tuple[str, ...]
    magic: bytes | None

    def __new__(
        cls,
        value: str,
        extensions: tuple[str, ...] = (),
        magic: bytes | None = None,
    ) -> AiModelFormat:
        obj = str.__new__(cls, value)
        obj._value_ = value  # pyrefly: ignore[missing-attribute]
        return obj  # pyrefly: ignore[bad-return]

    def __init__(
        self,
        # pylint: disable=unused-argument  # consumed by __new__
        value: str,
        extensions: tuple[str, ...] = (),
        magic: bytes | None = None,
    ) -> None:
        self.extensions = extensions
        self.magic = magic

    def __str__(self) -> str:
        return str(self.value)

    UNKNOWN = "unknown"
    CRFSUITE = ("crfsuite", (".crfsuite",), b"lCRF")
    FASTTEXT = ("fasttext", (".ftz",), b"\xba\x16\x4f\x2f")
    GGUF = ("gguf", (".gguf",), b"GGUF")
    HDF5 = ("hdf5", (".h5", ".hdf5"), b"\x89HDF\r\n\x1a\n")
    KERAS = ("keras", (".keras",))
    NUMPY = ("numpy", (".npy", ".npz"), b"\x93NUMPY")
    ONNX = ("onnx", (".onnx",))
    PYTORCH = ("pytorch", (".pt", ".pth"))
    PYTORCH_PT2 = ("pytorch_pt2", (".pt2",))
    SAFETENSORS = ("safetensors", (".safetensors",))


# Suffixes several formats share; a file with one is a model only when its
# header proves a format.
SHARED_MODEL_SUFFIXES: frozenset[str] = frozenset({".bin", ".model"})


def model_file_suffixes() -> frozenset[str]:
    """Every suffix a model file of a supported format can have."""
    return SHARED_MODEL_SUFFIXES | {
        ext for fmt in AiModelFormat for ext in fmt.extensions
    }


#: Most code points of the name shown for a model (:meth:`AiModelMetadata.
#: resolve_name`), which also seeds its ``spdxId``: a name read from a file
#: is untrusted and unbounded. A longer name is cut by :func:`cap_model_name`.
#: The bound applies before the display escape, so the name shown can be
#: longer: each escaped code point adds five characters.
MAX_MODEL_NAME_CHARS = 1024

#: What ends a name :func:`cap_model_name` cut, before its digest.
MODEL_NAME_CUT_MARK = "..."

#: Hex digits of the SHA-256 of the full name that end a cut name, after
#: ``~``: two long names sharing their first characters still differ.
MODEL_NAME_DIGEST_CHARS = 8

#: Appended to the ``name`` provenance of a cut name.
MODEL_NAME_CUT_NOTE = f" | Note: cut to {MAX_MODEL_NAME_CHARS} characters"


def cap_model_name(name: str) -> str:
    """*name* as is when it has at most :data:`MAX_MODEL_NAME_CHARS` code
    points, else its start, :data:`MODEL_NAME_CUT_MARK`, ``~`` and the first
    :data:`MODEL_NAME_DIGEST_CHARS` hex digits of the SHA-256 of the whole
    *name* in UTF-8: that many code points in all, and different for two
    names that differ anywhere. Every identity built from a model's name
    (its document, its ``spdxId``, the registry key, an enrichment's
    target) sees the same cut name. The display escape comes after, so
    the name shown can be longer than :data:`MAX_MODEL_NAME_CHARS`."""
    if len(name) <= MAX_MODEL_NAME_CHARS:
        return name
    digest = hashlib.sha256(name.encode("utf-8", "surrogatepass")).hexdigest()
    tail = f"{MODEL_NAME_CUT_MARK}~{digest[:MODEL_NAME_DIGEST_CHARS]}"
    return name[: MAX_MODEL_NAME_CHARS - len(tail)] + tail


# Nesting levels of a collection kept as JSON in raw_metadata; a deeper part
# becomes its JSON text, so a hostile nesting never exhausts the stack in
# this walk or in the canonical serialisation of the SBOM.
SOURCE_METADATA_MAX_DEPTH = 32

#: Most entries kept per list or map of one model (inputs, outputs,
#: hyperparameters, properties, raw metadata). A real model has tens to a
#: few hundreds; the first ones stay: in file order, or in key order for
#: Safetensors ``__metadata__``, which the library returns in no fixed order.
#: Applied by :func:`pitloom.extract.ai_model.limits.cap_entries`; here so
#: the annotation can name it without importing the readers.
MAX_MODEL_ENTRIES = 1000


def value_text(value: Any) -> str:
    """*value*, not ``None``, as text: a string or a scalar its
    :func:`~pitloom.core.scalar_text.scalar_text`, anything else
    ``str(value)``."""
    if isinstance(value, str) or scalar_type(value) is not None:
        return scalar_text(value)
    return str(value)


def source_element_text(value: Any) -> str:
    """A scalar inside a collection as text: ``None`` as ``null``; anything
    else its :func:`value_text` (``true``, ``1``, ``1e-7``, ``NaN``), as
    the collection's :func:`~pitloom.core.canonical_json.canonical_json`
    text spells it too."""
    return "null" if value is None else value_text(value)


def _collection_text(value: Any) -> str:
    """*value*, a collection nested too deeply to keep, as its JSON text."""
    try:
        return canonical_json(value)
    except (RecursionError, TypeError, ValueError):
        return f"<nested over {SOURCE_METADATA_MAX_DEPTH} levels>"


def _source_collection(value: Any, depth: int) -> Any:
    """A collection element of :func:`source_metadata_value`, *depth* levels
    inside the top-level collection."""
    if not isinstance(value, (Mapping, list, tuple)):
        return source_element_text(value)
    if depth >= SOURCE_METADATA_MAX_DEPTH:
        return _collection_text(value)
    if isinstance(value, Mapping):
        return {
            key_text(key): _source_collection(item, depth + 1)
            for key, item in value.items()
        }
    return [_source_collection(item, depth + 1) for item in value]


def source_metadata_value(value: Any) -> Any:
    """*value* as :attr:`AiModelMetadata.raw_metadata` holds it.

    *value* is not ``None`` (:func:`source_metadata` leaves such a key
    out). A mapping becomes a dict and a list or tuple a list; any other
    value becomes its :func:`value_text`, the text a reader puts in
    ``properties``. Inside a collection every
    scalar is text too (:func:`source_element_text`), and every key its
    :func:`~pitloom.core.scalar_text.key_text`. A collection over
    :data:`SOURCE_METADATA_MAX_DEPTH` levels down is its JSON text. A
    number or a boolean is never kept as one: it is never computed on, and
    a JSON number would widen a float32 or round an integer above 2**53.
    """
    if isinstance(value, (Mapping, list, tuple)):
        return _source_collection(value, 0)
    return value_text(value)


def record_scalar_property(
    properties: dict[str, str], natives: dict[str, Any], key: str, value: Any
) -> None:
    """Record scalar *value* under *key*: its
    :func:`~pitloom.core.scalar_text.scalar_text` in *properties*, the value
    itself in *natives*, which a reader hands to :func:`source_metadata` so
    the key is typed."""
    properties[key] = scalar_text(value)
    natives[key] = value


class SourceMetadata(TypedDict):
    """What :func:`source_metadata` returns: the two
    :class:`AiModelMetadata` fields it sets, keyed by their names, so a
    reader passes them as ``AiModelMetadata(..., **source_metadata(...))``
    and never sets either by hand."""

    raw_metadata: dict[str, Any]
    raw_metadata_types: dict[str, str]


def source_metadata(
    items: Mapping[str, Any], natives: Mapping[str, Any] | None = None
) -> SourceMetadata:
    """A reader's :attr:`AiModelMetadata.raw_metadata` and
    :attr:`AiModelMetadata.raw_metadata_types`: *items* (usually its
    ``properties``) with each key of *natives* set to that native value (a
    list, a mapping, or a scalar the properties hold as text), every value
    through :func:`source_metadata_value`.

    A key of *natives* keeps its place in *items*; one not in *items*
    comes after them. A key whose value is ``None`` is left out: the file
    holds no value for it. The types map each key whose value is a
    non-string scalar to its :func:`~pitloom.core.scalar_text.text_type`,
    so a reader hands over the native value of every key it wants typed.
    """
    merged = dict(items)
    merged.update(natives or {})
    metadata: dict[str, Any] = {}
    value_types: dict[str, str] = {}
    for key, value in merged.items():
        if value is None:
            continue
        metadata[key] = source_metadata_value(value)
        kind = text_type(value)
        if kind is not None:
            value_types[key] = kind
    return SourceMetadata(raw_metadata=metadata, raw_metadata_types=value_types)


@dataclass
class AiModelFormatInfo:
    """Physical model file and format/framework metadata.

    Groups the file-level and toolchain fields that describe *how* the model
    is stored on disk, rather than what the model does.
    """

    # Physical model file name (basename only, no directory path)
    file_name: str | None = None

    # Canonical distribution path of the file inside the project
    file_path_relative: str | None = None

    # Project-root-relative filesystem path (e.g. "src/pkg/model.bin"), as
    # opposed to file_path_relative's wheel-distribution path. Set by
    # pitloom.extract.scanner.discover_ai_models from the producer's stable
    # path: project-relative, or file_path_relative when the file has no
    # project-relative path (--allow-build). Never a temporary path. The
    # assembler looks this exact string up in the id registry -- the same
    # string a pitloom.loom fragment's run.set_model(model_file_path, ...)
    # call would have registered it under -- letting the scan-discovered
    # AIPackage reuse that id instead of minting a new one.
    physical_path: str | None = None

    # Format enum value (e.g. AiModelFormat.GGUF)
    model_format: AiModelFormat = AiModelFormat.UNKNOWN

    # Version of the model file format (e.g. "v2" for Keras v2, "1.0" for NumPy 1.0)
    format_version: str | None = None

    # Framework that produced the model or is expected to consume it
    # (e.g. "keras", "pytorch", "llama.cpp")
    framework: str | None = None

    # Version of the framework/library used to produce the model
    # (e.g. "2.15.0" for Keras 2.15.0, "2.7.1" for PyTorch 2.7.1)
    framework_version: str | None = None


@dataclass
class AiModelUsage:
    """Model design intent, use-case restrictions, and safety metadata.

    These fields describe how the model is intended (and not intended) to be
    used, and capture known risks and biases.  They map to the SPDX 3 AI
    profile fields ``ai_domain``, ``ai_limitation``, and
    ``ai_safetyRiskAssessment``.
    """

    # Domains in which the model can be used (e.g. "NLP", "computer vision")
    # Maps to SPDX 3: ai_domain (List[String])
    domains: list[str] = field(default_factory=list)

    # Intended use cases (e.g. "text summarisation", "sentiment analysis")
    # Maps to SPDX 3: ai_informationAboutApplication (part of JSON)
    intended_use: list[str] = field(default_factory=list)

    # Unintended / out-of-scope use cases
    # Maps to SPDX 3: ai_informationAboutApplication (part of JSON)
    unintended_use: list[str] = field(default_factory=list)

    # Known limitations of the model
    # Maps to SPDX 3: ai_limitation (String -- joined with "; " on export)
    limitations: list[str] = field(default_factory=list)

    # Known biases in the model
    # No dedicated SPDX 3 field; serialised into comment on export
    known_biases: list[str] = field(default_factory=list)

    # General safety risk assessment result
    # Maps to SPDX 3: ai_safetyRiskAssessment (enum: high | medium | low | serious)
    safety_risk_assessment: str | None = None


@dataclass
# pylint: disable=too-many-instance-attributes
class AiModelMetadata:
    """Metadata extracted from an AI model file.

    Fields align with the SPDX 3.0 AI profile where applicable.
    See: https://spdx.github.io/spdx-spec/v3.0/model/AI/Classes/AIPackage/

    Attributes that naturally form a group are collected into sub-dataclasses
    to keep the attribute count manageable:

    - :class:`AiModelFormatInfo` -- physical file, format, and framework fields.
    - :class:`AiModelUsage` -- use-case, limitation, bias, and safety fields.
    """

    # Physical file, format, and framework metadata
    format_info: AiModelFormatInfo = field(default_factory=AiModelFormatInfo)

    # Core identification (maps to SPDX Core: name, description)
    name: str | None = None
    description: str | None = None
    version: str | None = None
    license: str | None = None  # licence as read: SPDX expression, name or URL

    # External identifiers and references (DOI, arXiv, repository / model-card URL)
    # Maps to SPDX 3: externalIdentifier / externalRef
    doi: str | None = None
    arxiv_ids: list[str] = field(default_factory=list)
    url: str | None = None

    # Base model lineage (parent model ID and relation type e.g. "finetune",
    # "quantized")
    # Maps to SPDX 3: Relationship (descendantOf)
    base_model: str | None = None
    base_model_relation: str | None = None

    # General model metadata
    domain: list[str] = field(default_factory=list)

    # Technical model metadata
    # SPDX AI profile: typeOfModel (e.g. "neural network", "transformer")
    type_of_model: str | None = None
    # Specific model architecture (e.g. "llama", "bert", "stable-diffusion-xl")
    # Maps to SPDX 3: ai_typeOfModel (together with type_of_model)
    architecture: str | None = None
    # Quantization level (e.g. "Q4_K_M", "int8", "fp16")
    # Maps to SPDX 3: ai_hyperparameter as key="quantization"
    quantization: str | None = None

    # SPDX AI profile: hyperparameter -- model configuration values
    hyperparameters: dict[str, Any] = field(default_factory=dict)

    # Format-specific key/value metadata (e.g. GGUF general.*, ONNX metadata_props)
    properties: dict[str, str] = field(default_factory=dict)

    # The model file's own metadata in its own key vocabulary (e.g. the
    # full GGUF kv-store or safetensors ``__metadata__``), for preservation
    # (P1) when the model is not shipped with the distribution and cannot be
    # re-extracted later. Every reader sets it, with raw_metadata_types,
    # by splatting :func:`source_metadata` into the constructor:
    # a collection is a list (or a dict for a mapping), a scalar is its
    # scalar_text, the same text as in ``properties`` (inside a collection
    # too; ``None`` there is ``null``), a key without a value absent. A GGUF
    # array is recorded as ``{"length": "N", "type": "<element type>"}``
    # (no ``type`` for an element code the format does not define), its
    # elements never recorded.
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    # The type of each raw_metadata key whose value was a non-string scalar
    # in the file ("boolean", "integer" or "float"), from the native value
    # the reader handed to source_metadata; the annotation's valueTypes.
    raw_metadata_types: dict[str, str] = field(default_factory=dict)

    # How many of the file's metadata keys the MAX_MODEL_ENTRIES cap left
    # out of raw_metadata; the annotation's truncatedKeyCount. 0: none.
    raw_metadata_dropped: int = 0

    # Input and output tensor specifications
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)

    # Use-case, limitation, bias, and safety metadata
    usage: AiModelUsage = field(default_factory=AiModelUsage)

    # Datasets associated with this model (training, evaluation, fine-tuning, etc.)
    # Maps to SPDX 3 via dataset_DatasetPackage + trainedOn/testedOn relationships.
    datasets: list[DatasetReference] = field(default_factory=list)

    # Provenance tracking: field name -> source description
    provenance: dict[str, str] = field(default_factory=dict)

    # Distribution paths of Python scripts that use/load this model, sorted
    # and deduplicated by the scanner
    usage_files: list[str] = field(default_factory=list)

    # -- User-defined extension slots ------------------------------------------
    # Use these for metadata that does not map to any standard field above.
    # Keys should be namespaced with a source prefix separated by a dot so
    # consumers can identify the origin:
    #   "hf.library_name", "hf.license_name", "onnx.producer_version", ...
    # The exporter decides how (or whether) to include these in the SBOM.

    # Key -> any scalar or structured value (str, int, float, bool, dict).
    # For single-valued metadata that is richer than a plain string.
    # Examples: "hf.model_index" -> {...eval results...}, "hf.sha" -> "abc123"
    extra_data: dict[str, Any] = field(default_factory=dict)

    # Key -> list of values (str, int, dict, ...) for multi-valued properties.
    # Examples:
    #   "hf.language"  -> ["en", "th"]
    #   "hf.tags"      -> ["pretrained", "reasoning"]
    extra_lists: dict[str, list[Any]] = field(default_factory=dict)

    @property
    def own_name(self) -> str:
        """:attr:`name` stripped and capped (:func:`cap_model_name`), or
        ``""`` when it is absent or blank."""
        return cap_model_name((self.name or "").strip())

    @property
    def file_name_stem(self) -> str:
        """The stem of ``format_info.file_name`` capped
        (:func:`cap_model_name`), or ``""`` without one.

        ``file_name`` is a base name (every reader sets it from the file's
        or archive member's last component), so POSIX parsing is exact.
        """
        return cap_model_name(PurePosixPath(self.format_info.file_name or "").stem)

    def name_cut_length(self) -> int | None:
        """The length, in code points, of the name :meth:`resolve_name`
        shows before :func:`cap_model_name` cut it, or ``None`` when it was
        not cut."""
        name = (self.name or "").strip()
        if not name:
            name = PurePosixPath(self.format_info.file_name or "").stem
        return len(name) if len(name) > MAX_MODEL_NAME_CHARS else None

    def resolve_name(self) -> tuple[str, dict[str, str]]:
        """The name to show for this model, and the provenance to go with it.

        The model's own :attr:`name` stripped (a blank one is no name),
        else its file name stem, else its format; the first two capped by
        :func:`cap_model_name`. :attr:`name` itself stays as read from the
        file (``None`` when the file names no model). The provenance is
        always a new dict, a copy of :attr:`provenance`, with a ``name``
        entry set for a stem fallback and dropped for the format fallback
        (a reader's entry for a blank name cites nothing shown); a cut name
        adds :data:`MODEL_NAME_CUT_NOTE` to its entry.
        """
        provenance = dict(self.provenance)
        name = self.own_name or self.file_name_stem
        if not name:
            provenance.pop("name", None)
            return str(self.format_info.model_format), provenance
        if not self.own_name:
            provenance["name"] = FILE_NAME_STEM_PROVENANCE
        if self.name_cut_length() is not None and "name" in provenance:
            provenance["name"] += MODEL_NAME_CUT_NOTE
        return name, provenance
