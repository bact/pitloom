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
from pitloom.core.credential_policy import (
    MODE_REFUSE,
    MODE_WARN,
    CredentialPolicy,
    require_mode,
)
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.file_names import (
    bare_sbom_base,
    is_plain_file_name,
    sbom_base_name,
)
from pitloom.core.model_extract_limit import DEFAULT_MAX_DOWNLOAD_BYTES
from pitloom.core.provenance import (
    DEFAULT_PROVENANCE_SCHEMA,
    ProvenanceConfig,
    require_max_source_metadata_bytes,
    require_provenance_choices,
)
from pitloom.logging_config import configure_logging
from pitloom.messages.config import Parameter, invalid_value

_DEFAULT_PROVENANCE_SCHEMA = DEFAULT_PROVENANCE_SCHEMA
VALID_CONTENT_TYPE_METHODS: frozenset[str] = frozenset({"auto", "magika", "extension"})
#: Default ``max-model-extract-bytes``: 512 MiB.
DEFAULT_MAX_MODEL_EXTRACT_BYTES = 512 * 1024 * 1024
#: Default ``max-dataset-hash-bytes``: 4 GiB.
DEFAULT_MAX_DATASET_HASH_BYTES = 4 * 1024 * 1024 * 1024

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
            "scan-model-usage",
            "update-id-registry",
            "use-lockfile",
        }
    ),
    "content-type": frozenset({"enabled"}),
    "creation": frozenset({"no-creation-tool", "no_creation_tool"}),
}
#: Every integer ``[tool.pitloom]`` key, as :data:`BOOL_KEYS`.
INT_KEYS: dict[str, frozenset[str]] = {
    "": frozenset(
        {"max-dataset-hash-bytes", "max-download-bytes", "max-model-extract-bytes"}
    ),
    "provenance": frozenset({"max-source-metadata-bytes", "max_source_metadata_bytes"}),
}


def _require_valid_content_type_method(value: str) -> None:
    """Refuse *value* unless it is a valid content-type method.

    The one spelling of this check for every caller that takes a method as
    a parameter rather than reading it from a ``[tool.pitloom]`` table;
    a table read reports the offending key's own path instead (see
    ``pitloom.core._config_read._require_choice``). Only a library caller
    reaches it: the TOML reader and the CLI's ``choices=`` refuse first.

    Raises:
        pitloom.messages.CodedValueError: ``option-invalid``, a
            ``ValueError``.
    """
    if value not in VALID_CONTENT_TYPE_METHODS:
        raise invalid_value(
            Parameter("content_type_method"), "one-of-method", got=value
        )


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

            Not the ``role`` of ``core.dataset_metadata.DatasetReference``,
            an SPDX ``RelationshipType`` tag such as ``"trainedOn"``: a
            different taxonomy. Both names are provisional and are revised
            with the provenance taxonomy (roadmap: "Provenance and
            enrichment vocabulary").
        description: Human-readable description of what the fragment covers.
        required: If True, a missing or unreadable fragment raises
            ``FragmentMergeError`` instead of the default warn-and-skip.
            Defaults to False.
        sha256: Optional expected SHA-256 hex digest of the fragment file,
            checked only by ``loom fragment list``, for display; not
            enforced during merge (roadmap: ``loom fragment sign``).
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
    #: The keys the ``[tool.pitloom]`` table itself holds, as written, and
    #: not part of a config's equality: what tells a choice from a default
    #: (``update_id_registry`` is ``True`` either way), for a surface that
    #: ignores a key (:func:`pitloom.core.inert_options.configured_options`).
    table_keys: frozenset[str] = field(default=frozenset(), compare=False, repr=False)
    provenance_format: str = "both"
    provenance_schema: str = _DEFAULT_PROVENANCE_SCHEMA
    provenance_detail: str = "minimal"
    provenance_preserve_source_metadata: str = "auto"
    provenance_max_source_metadata_bytes: int = 0
    enrich_local: bool = False
    extract_file_header: bool = True
    #: ``None`` = never given (treated as off, but the scan hints at the flag).
    scan_model_usage: bool | None = None
    #: Ceiling on one AI model file copied out of a wheel to be read.
    max_model_extract_bytes: int = DEFAULT_MAX_MODEL_EXTRACT_BYTES
    #: Ceiling on the bytes one loom dataset hash reads (``loom.Run`` only).
    max_dataset_hash_bytes: int = DEFAULT_MAX_DATASET_HASH_BYTES
    #: Ceiling on a release file downloaded from PyPI (a PyPI URL target).
    max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES
    content_type_enabled: bool = False
    content_type_method: str = "auto"
    content_type_overrides: tuple[ContentTypeOverride, ...] = ()
    offline: bool = False
    use_lockfile: bool = True
    #: ``accept-url-credentials``: fingerprints of URL field values let into
    #: the SBOM with their credential (:mod:`pitloom.core.credential_policy`).
    accept_url_credentials: tuple[str, ...] = ()
    #: ``url-credentials``: ``"warn"`` (write a credential found, with a
    #: ``WARNING:``) or ``"refuse"`` (write no SBOM while one is not accepted).
    url_credentials: str = MODE_WARN

    def __post_init__(self) -> None:
        """Refuse a bad ``accept_url_credentials`` entry, ``url_credentials``
        or ``sbom_basename`` when the config is built, as ``loom.Run``
        refuses one, not at its first use. A ``sbom_basename`` with white
        space or a trailing ``.spdx3.json`` keeps its base, with one
        ``WARNING:`` naming ``PitloomConfig.sbom_basename``; an empty one is
        no name (the default).

        Raises:
            ValueError: an entry is not a fingerprint, the mode is neither
                warn nor refuse, or ``sbom_basename`` is not a plain file
                name (``option-invalid``).
        """
        _ = self.credential_policy
        base = self.sbom_basename
        if base is None or base == "":
            return
        where = Parameter("PitloomConfig.sbom_basename")
        if not isinstance(base, str) or not is_plain_file_name(base):
            raise invalid_value(where, "file-name", got=base)
        if bare_sbom_base(base) != base:
            # sbom_base_name warns: said here, before any entry point. Only
            # then, so a library caller's own logger set-up is kept.
            configure_logging()
        self.sbom_basename = sbom_base_name(base, where)

    @property
    def credential_policy(self) -> CredentialPolicy:
        """Return the CredentialPolicy of these settings.

        Raises:
            ValueError: an ``accept_url_credentials`` entry is not a
                fingerprint, or ``url_credentials`` is not ``"warn"`` or
                ``"refuse"`` (a config built in code is never parsed).
        """
        mode = require_mode(self.url_credentials, table=None)
        return CredentialPolicy(
            accepted=frozenset(self.accept_url_credentials),
            refuse=mode == MODE_REFUSE,
        )

    @property
    def provenance(self) -> ProvenanceConfig:
        """Return ProvenanceConfig constructed from current config settings.

        Raises:
            ValueError: ``provenance_format``, ``provenance_schema``,
                ``provenance_detail`` or
                ``provenance_preserve_source_metadata`` is not one the
                setting takes, or
                ``provenance_max_source_metadata_bytes`` is not ``0`` or a
                valid budget (``option-invalid``: a config built in code is
                never parsed).
        """
        require_provenance_choices(
            self.provenance_format,
            self.provenance_schema,
            self.provenance_detail,
            self.provenance_preserve_source_metadata,
            owner="PitloomConfig.provenance_",
        )
        require_max_source_metadata_bytes(
            self.provenance_max_source_metadata_bytes,
            Parameter("PitloomConfig.provenance_max_source_metadata_bytes"),
        )
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
