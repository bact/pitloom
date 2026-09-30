# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Type definitions and data structures for Pitloom configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from pitloom.core.content_type_config import ContentTypeConfig, ContentTypeOverride
from pitloom.core.creation import CreationMetadata, Creator, Tool
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.provenance import ProvenanceConfig

_DEFAULT_PROVENANCE_SCHEMA = "pitloom/1"
VALID_CONTENT_TYPE_METHODS: frozenset[str] = frozenset({"auto", "magika", "extension"})

#: Every boolean ``[tool.pitloom]`` key, by sub-table (``""`` is
#: ``[tool.pitloom]`` itself), in both spellings. A ``setup.cfg`` value is a
#: string; these tell its reader which keys to coerce as TOML would type them.
BOOL_KEYS: dict[str, frozenset[str]] = {
    "": frozenset(
        {
            "describe-relationship",
            "describe_relationship",
            "enrich",
            "extract-file-header",
            "offline",
            "pretty",
            "update-id-registry",
            "use-lockfile",
        }
    ),
    "content-type": frozenset({"enabled"}),
    "creation": frozenset({"no-creation-tool", "no_creation_tool"}),
}
#: Every integer ``[tool.pitloom]`` key, as :data:`BOOL_KEYS`.
INT_KEYS: dict[str, frozenset[str]] = {
    "provenance": frozenset({"max-source-metadata-bytes", "max_source_metadata_bytes"}),
}


def _require_valid_content_type_method(value: str) -> None:
    """Raise ``ValueError`` unless *value* is a valid content-type method.

    The one spelling of this check for every caller that takes a method as
    a parameter rather than reading it from a ``[tool.pitloom]`` table;
    a table read reports the offending key's own path instead (see
    ``pitloom.core._config_read._require_choice``).
    """
    if value not in VALID_CONTENT_TYPE_METHODS:
        valid = ", ".join(sorted(VALID_CONTENT_TYPE_METHODS))
        raise ValueError(f"content_type_method must be one of {valid}, got {value!r}")


class AssembleOptions(TypedDict):
    """The config-resolved settings ``build()`` takes as keyword arguments.

    See :attr:`PitloomConfig.assemble_options`.
    """

    provenance: ProvenanceConfig
    offline: bool
    content_type_method: str


@dataclass
class FragmentConfig:
    """Configuration for a single SBOM fragment source, from one entry in
    ``[tool.pitloom.fragment] files``.

    Attributes:
        path: Path to the fragment file, relative to the project directory
            (or to *base_dir*).
        role: Optional, free-form label for what *part* this fragment's
            root element(s) play in a pipeline/system -- input for a
            *future* decision about which relationship type to emit
            between this fragment and the rest of the graph, when the
            merged elements' own types don't already make that obvious.
            Not validated against a fixed vocabulary (this list is
            examples, not a closed set) and not currently read by the
            merge itself -- purely descriptive until that later work
            lands. Recognised (but not enforced) values, grouped for
            clarity (both groups are the same axis -- "what part does
            this play" -- deliberately excluding a physical-format axis
            like "binary": an AI model file is usually also a binary
            artifact, so that would collide with ``"ai_model"``; and
            excluding provenance facts like "what environment built
            this", a different, still-deferred concern):

            Pipeline artifacts: ``"input_dataset"``, ``"output_dataset"``,
            ``"ai_model"`` (covers a training run's model output too --
            use ``description`` for that detail, no separate value
            needed), ``"software_package"``, ``"source"``.

            Pipeline processes: ``"training_script"``,
            ``"data_cleaning_script"``, ``"post_processing_script"``,
            ``"guardrail_safety_function"``.

            Distinct from the unrelated ``role`` concept in
            ``pitloom.core.provenance``/``core.dataset_metadata
            .DatasetReference.role`` (an SPDX-``RelationshipType``-mapped
            tag like ``"trainedOn"`` -- a different taxonomy; don't
            conflate the two). NOTE: ``DatasetReference.role`` is itself
            expected to be renamed in a future, separate change -- if
            that's landed by the time you're reading this, update this
            cross-reference to whatever it's renamed to.
        description: Human-readable description of what the fragment covers.
        required: If True, a missing or unreadable fragment raises
            ``FragmentMergeError`` instead of the default warn-and-skip.
            Defaults to False.
        sha256: Optional expected SHA-256 hex digest of the fragment file,
            checked for display only by ``pitloom fragment list`` -- NOT
            enforced during merge yet (see roadmap: "fragment sign +
            SHA-256 verification in merge").
        link_to_main: Reserved for a future SPDX relationship type between
            the fragment's root element and the project's main package.
            Stored but not yet acted on anywhere.
        base_dir: The directory a relative *path* resolves against: that
            of the ``--config`` file it came from. ``None`` (a project's
            own config) means the project directory. *path* itself is
            kept as written, since it is recorded in the SBOM.
    """

    path: str
    role: str | None = None
    description: str | None = None
    required: bool = False
    sha256: str | None = None
    link_to_main: str | None = None
    base_dir: str | None = None


@dataclass
# pylint: disable=too-many-instance-attributes
class PitloomConfig:
    """Settings from the ``[tool.pitloom]`` section of ``pyproject.toml``.

    All fields have safe defaults so that a project without a ``[tool.pitloom]``
    section works out of the box.  Adding new ``[tool.pitloom]`` options in
    future versions only requires adding a new field here with a default value.
    """

    fragments: list[FragmentConfig] = field(default_factory=list)
    pretty: bool = False
    describe_relationship: bool | None = None
    sbom_basename: str | None = None
    creators: list[Creator] = field(default_factory=list)
    tools: list[Tool] | None = None
    creation_datetime: str | None = None
    creation_comment: str | None = None
    id_registry: str | None = None
    update_id_registry: bool = True
    provenance_format: str = "both"
    provenance_schema: str = _DEFAULT_PROVENANCE_SCHEMA
    provenance_detail: str = "minimal"
    provenance_preserve_source_metadata: str = "auto"
    provenance_max_source_metadata_bytes: int = 0
    enrich_local: bool = False
    extract_file_header: bool = True
    content_type_enabled: bool = False
    content_type_method: str = "auto"
    content_type_overrides: tuple[ContentTypeOverride, ...] = ()
    offline: bool = False
    use_lockfile: bool = True

    @property
    def provenance(self) -> ProvenanceConfig:
        """Return ProvenanceConfig constructed from current config settings."""
        return ProvenanceConfig(
            format=self.provenance_format,
            schema=self.provenance_schema,
            detail=self.provenance_detail,
            preserve_source_metadata=self.provenance_preserve_source_metadata,
            max_source_metadata_bytes=self.provenance_max_source_metadata_bytes,
        )

    @property
    def content_type(self) -> ContentTypeConfig:
        """Return ContentTypeConfig constructed from current config settings."""
        return ContentTypeConfig(
            enabled=self.content_type_enabled,
            method=self.content_type_method,
            overrides=self.content_type_overrides,
        )

    @property
    def assemble_options(self) -> AssembleOptions:
        """Return the settings a build-stage caller hands to
        :func:`pitloom.assemble.spdx3.document.build` as ``**kwargs``.

        One place to add a setting ``build()`` starts consuming, so a
        surface that already has a resolved config (the Hatchling hook,
        ``embed-wheel --project-dir``) cannot forget it.
        """
        return AssembleOptions(
            provenance=self.provenance,
            offline=self.offline,
            content_type_method=self.content_type_method,
        )

    @property
    def enrich(self) -> EnrichConfig:
        """Return EnrichConfig constructed from current config settings."""
        return EnrichConfig(local=self.enrich_local)

    @property
    def creation_metadata(self) -> CreationMetadata:
        """Return CreationMetadata constructed from current config settings."""
        return CreationMetadata(
            creators=self.creators,
            tools=self.tools,
            creation_datetime=self.creation_datetime,
            creation_comment=self.creation_comment,
        )
