---
Created: 2026-10-03
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: SPDX 3 modelling

See also: [README.md](README.md) (index of these notes),
[identity-and-archives.md](identity-and-archives.md),
[determinism-and-parsing.md](determinism-and-parsing.md),
[remote-metadata.md](remote-metadata.md),
[license-pipeline.md](../license-pipeline.md).

How facts map onto SPDX 3.0.1 elements, and where the model has no slot
for them. Items marked "decided, not built" or "design only" describe
plans; the lesson holds without the code.

## 1. Identity and integrity

- **A package id keyed by name alone gives every release one id.**
  Registry v2 keys `software_Package` by PEP 503 name only, so `foo 1.0`
  and `foo 2.0` share an `spdxId` and merging two releases' SBOMs unifies
  them. Registry v3 Q-D (decided 2026-10-02, not built): key is PEP 503
  name plus PEP 440-normalised version, purl-shaped (`pkg:pypi/foo@1.0`),
  with an empty version part for an unpinned or range dependency;
  releases are linked by relationships, not by a shared id
  ([id-registry-v3.md](../id-registry-v3.md)).
  Do: include the version in any package identity key.
- **A Merkle root over content digests alone does not bind file names.**
  The wheel `verifiedUsing` hash is a Merkle root over sorted per-file
  SHA-256 leaves with no path in the leaf, so a rename that keeps sort
  position, or a swap of two identical-content files, leaves the root
  unchanged. Its `Hash.comment` says "not a hash of a single artifact".
  Decided for registry v3 datasets, not built: leaf is path, NUL, digest,
  and the comment says "path and content". Size-plus-mtime hashing was
  rejected: it differs across clones.
  Do: put the relative POSIX path in every Merkle leaf, and say in
  `Hash.comment` that the value is not a single-artefact hash.
- **One dependency declared several times is one node.** numpy declared
  under 2 extras and 2 `python_version` markers gave 4 `software_Package`
  nodes with the same purl and hash. The grouping key is now (PEP 503
  name, PEP 440 version). SPDX 3 has no field for a declared range, so
  the raw constraints go into provenance as `declared_constraint`, joined
  with `" | "` (PR not identified).
  Do: never put constraint text in the identity key; keep it as
  provenance.
- **`CreationInfo` is not an `Element`.** It is a blank node (`NODE_KIND
  BlankNodeOrIRI`), the one graph node without an `spdxId`, which is
  correct per the spec; Pitloom emits `_:CreationInfo0`. After a fragment
  merge, identical `CreationInfo` blank nodes are deduplicated by
  fingerprint and references redirected (#102).
  Do: do not flag a missing `spdxId` on `CreationInfo`; deduplicate
  identical ones after a merge.

## 2. Claims, profiles and completeness

- **`profileConformance` comes from the content present.**
  `simpleLicensing` is declared only when licence elements exist, and
  `dataset` only when datasets exist. Earlier code always added
  `simpleLicensing`, even for NOASSERTION-only documents (PR not
  identified).
  Do: claim a profile only when the document uses it.
- **Leave `completeness` unset on lock-derived `dependsOn` edges.** Lock
  extractors legitimately skip VCS and path sources, non-default groups
  and marker-ambiguous variants, so `complete` would overstate the graph
  ([lock-file-cascade.md](../lock-file-cascade.md)).
  Do: assert `complete` only when you can prove the closure.
- **The provenance role records whose claim it is, not where it came
  from.** Roles: `declared`, `detected`, `externalReported`, `inferred`,
  `sbomAuthorSupplied`. `inferred` is reserved for an agent's judgement;
  an author who states a fact gives `sbomAuthorSupplied`, and one who
  points at a source gives the role that reading earns. A lookup outside
  the project is a consent gate, not a role (#102).
  Do: tag the epistemic source; keep consent separate from provenance.
- **SPDX 3.0.1 has only `trainedOn` and `testedOn` for datasets.**
  `finetunedOn`, `validatedOn` and `pretrainedOn` do not exist (the
  bindings list `trainedOn`, `testedOn`, `hasTest`, `hasTestCase`,
  `hasAssociatedVulnerability`). Pitloom falls back to
  `RelationshipType.other` with a comment
  ([ai-dataset-linking.md](../ai-dataset-linking.md)).
  Do: map finer roles to `other` plus a comment; never invent a type.
- **SPDX 3.0.1 `Tool` has no version property.** Pitloom puts
  `"Pitloom <ver>"` in `Tool.summary` and attaches `pkg:pypi/pitloom@<ver>`
  as an `externalIdentifier`, the machine-readable stand-in for CISA's
  "tool version". In the local 3.1 bindings (spdx-python-model commit
  3d24398) `Tool` still has no own properties; `Core/version` sits on
  `software_Package`, `hardware_*` and `DefinedProcess`. A code comment
  saying `Tool.version` arrives in 3.1-dev is unconfirmed (PR not
  identified).
  Do: carry the tool version as a purl `externalIdentifier`.
- **Vulnerability findings: plain relationship, not VEX** (design only,
  not built). Use `security_Vulnerability` plus
  `hasAssociatedVulnerability`, not `security_Vex*` subclasses, which
  encode a judgement; CVE aliases go in `ExternalIdentifierType.cve`,
  others in `securityOther`. Query OSV only for a pinned version
  ([osv-vulnerability-lookup.md](../../design/osv-vulnerability-lookup.md)).
  Do: record an observation as an observation; add a judgement only when
  someone makes it.

## 3. Licences

- **Normalise a licence expression with a parser, never a word-boundary
  regex.** `re.sub(r"\bor\b", "OR", "GPL-2.0-or-later", flags=re.I)` gives
  `GPL-2.0-OR-later`, since `\b` matches at hyphens. Pitloom's
  py-spdx-license 0.0.1 normaliser turns `mit and gpl-3.0-only` into
  `GPL-3.0-only AND MIT`, drops redundant parentheses, upper-cases
  `with`, sorts `MIT OR Apache-2.0` to `Apache-2.0 OR MIT` and keeps
  `LicenseRef-my-or-license` intact. Each rewrite is tagged
  `Normalized-From: <raw> | Normalizer: py-spdx-license==<v>` (#121).
  Do: compare licences only after canonical parsing, and record the raw
  value and the normaliser version.
- **A licence text matcher's top hit is not the licence.** `licenseid`
  0.3.7 scored `Pixar` 0.9963 over `Apache-2.0` 0.9921 on requests'
  verbatim Apache `LICENSE`, `JSON` 0.935 over `MIT` 0.929 on wcwidth's,
  and gave `Xnet` 0.902 for PyYAML's MIT (MIT scores 1.013 with the two
  copyright lines removed; SPDX matching omits the notice). On 90
  installed licence files: 66 right, 10 wrong, 14 none; reading both with
  and without the notice, preferring the stated licence within 0.01 and
  concluding none on an unstated near-tie: 76/4/10 (#286).
  A verbatim GPL text scores `-only` and `-or-later` alike (pylint 1.069
  vs 1.060): a tie rule that drops it loses every unstated GPL.
  Do: treat a near-tie between licence families as no answer unless the
  package states one of them; keep a corpus of real files that fooled the
  matcher.

## 4. Dependency scope: SPDX lifecycle vs Python extras

- **Python has no lifecycle scope.** SPDX 3.0.1 gives a relationship one
  scope (`design`, `build`, `development`, `test`, `runtime`, `other`); a
  Python project states only required, optional under a free-form extra name
  (`dev`, `test`, `full`, `async` look alike to a build tool), PEP 735 groups
  (never in a wheel) and build requirements. PyThaiNLP 5.4.0: 152 of 154
  `Requires-Dist` lines carry `extra ==` (2026-10-09).
- **A first design claimed `runtime` for every extra.** Review caught it:
  `runtime` on a `dev` or `lint` extra asserts what the project never stated.
  Built: `hasOptionalDependency` with no scope; required stays `dependsOn` +
  `runtime` (#300).
  Do: emit the weaker claim by default; let the project state the scope.
- **Proposed practice (to present with a provenance taxonomy).** Name an
  extra after its lifecycle stage, keep feature names for runtime options,
  and map extra to scope in configuration: a name becomes data only when the
  project says so; inferring it is a guess with its own provenance (Method,
  not Role). Design only:
  [extra-lifecycle-scope.md](../../design/extra-lifecycle-scope.md).
- **Build tools disagree on the same pyproject.** Hatchling 1.32 expands a
  self-referencing extra and sorts; setuptools 84 keeps `demo[dev]`;
  poetry-core 2.5 keeps it and writes the first author only.
  Do: resolve the self-reference yourself on every route.
- **A lock list is not who needs whom.** A lock reaches the generator as a
  flat `name==version` list. pendulum 3.2.0's `poetry.lock` puts
  `time-machine` in `main` (`optional = false`) though only its `test` extra
  and `test` group need it, so "locked" does not prove "required at runtime"
  (#300).
  Do: keep an extra-only dependency optional unless a lock records a path to
  it from the required set.

## 5. Author strings: splitting and typing

- **Two problems in one field.** `Holger Krekel, Bruno Oliveira and others`
  needs *span detection* (a comma separates authors, orders a name as in
  `Doe, Jane`, or sits in `Acme, Inc.`) and *typing* (Person, Organization
  or unknown). PEP 621 forbids a comma in a pyproject author name; core
  metadata `Author:`, `setup.cfg` and `setup.py` are free text.
- **Rule by field kind, not by surface.** The first version split `Author:`
  on the wheel route only, so one author list gave different SBOMs from a
  wheel, a `setup.cfg` and a dependency's record. The second split every
  free-text field on `,` / `and`; then measured builds (Hatchling, setuptools,
  flit_core, pdm-backend) showed backends write a structured name-only author
  (`{name = "Doe, Jane"}`) into `Author` verbatim, so one declared author
  was one on the directory route and two from the wheel: the field cannot
  tell a backend's one name from `setup.py` free text. Built (#300): the
  address field, a list by RFC 5322 syntax, splits on `,` / `;` (never
  `and`), with one `WARNING:` per document. The name field was at first
  never split, so `Author: Ann <a@x.org>; Bob <b@x.org>` (free text, two
  complete mailboxes) recorded nobody: one mailbox cannot hold two
  addresses. The rule kept: one reader for both fields, differing only in
  where a cut may happen; the name field is cut only where the text proves
  a list, after a closed `<address>` or a bare address, never after a name,
  so `Doe, Jane <j@x.org>` and `Jane, Bob` stay one author (a free-text
  list of names in one `Author` is one author, the stated limit), and the
  same two-mailbox text reads alike in `Author` and `Author-email`. A
  heuristic (multi-word names, legal suffixes) was rejected: right often
  enough to hide where it is wrong.
  Do: decide by what the writers put in the field, not what it may hold;
  cut only where the text itself proves a boundary; check a reading
  against real backend output on every route.
- **Do not type a name you cannot type (design only).** SPDX 3.0.1 `Agent`
  is concrete and the range of `originatedBy`/`suppliedBy`; a lone handle
  (`TheBloke`, `Qwen`) is honest only as `Agent`. A wrong `Person` costs:
  personal data in an SBOM, liability pinned on an employee, sanctions
  screening that misses an organisation. Candidate NLP / NER pipeline
  (footprint and accuracy unmeasured):
  [author-entity-recognition.md](../../design/author-entity-recognition.md).
- **A "found" field is never composed.** SPDX 3.0.1 defines `copyrightText` as
  the notices *found* for the element (`NONE`: none whatsoever; `NOASSERTION`:
  no determination). A line built from the authors and the SBOM creation year
  asserts what no source stated, and a creation year is not a notice year.
  Read the notice lines verbatim from the licence files, else `NOASSERTION`;
  never `NONE`, because absence in the files read is not absence in the
  package. A licence *document* also holds notices (the GPL preamble's FSF
  line): found is not the same as the project's.
- **Installed is not used.** An environment listing (`loom env`) supplies
  versions and the installed requirement graph, not the lifecycle stage in
  which a package is used: a package may be a development tool or the result
  of an extra. Scope `runtime` is claimed where the source states a
  requirement (declared, locked) or ships the code (bundled); a plain
  `dependsOn` states only what is known.

## 6. A model's producer and size (#306)

Where the AI profile has no slot, and what a file says against what a hub
says. Measured on the fixtures and on `openai-community/gpt2`; the decisions
are in
[g7-model-producer-parameter-count.md](../g7-model-producer-parameter-count.md).

- **SPDX 3.0.1 and 3.1-dev have no model-size or parameter-count
  property.** `ai_metric` is performance, `software_artifactSize` (3.1 only)
  is storage bytes, and a published AI-SBOM mapping calls the G7 "number of
  parameters" a gap with only a broad match to `ai_hyperparameter`. Pitloom
  writes a `DictionaryEntry` key `parameters` (decimal text) there and adds
  one constant line to the package `comment` that says it is a stand-in, so a
  reader does not take it for a hyperparameter.
  Do: when a field has to ride on a near-miss slot, say so in the element
  itself, once, in fixed wording, not only in the documentation.
- **"Parameters" is a sum of stored tensor elements, not of weights.** A
  derived count sums the elements of every stored tensor, so buffers and tied
  copies are in it: `gpt2-tiny-decoder.onnx` gives 404256, of which a
  262144-element `uint8` mask is 65 %; the Hub's `safetensors.total` for
  `openai-community/gpt2` is 137022720, against about 124 million weights.
  Packed formats (GPTQ, AWQ, bitsandbytes, ONNX `MatMulNBits`) under-count
  because several weights share a stored element. The same number computed
  from different formats of one model differs.
  Do: name the quantity (`Method: tensor_element_sum`) in the provenance, and
  state the exclusions where the number is shown.
- **A file's author and the repository owner are different claims.** The
  same model gives a producer from the file (ONNX `model_author`, GGUF
  `general.author`) and one from the hub (the repository owner, which for
  `openai-community/gpt2` is not OpenAI). Pitloom records both as
  `originatedBy`, and only the hub owner also as `suppliedBy`, because a
  file says who made the model and nothing about who ships it. GGUF
  `general.organization` is often a converter's guess (llama.cpp fills it
  from the base model's `_name_or_path`), so a fine-tune can name the base's
  organisation.
  Do: map "who made it" and "who distributes it" to separate properties and
  set the second only from a source that has a distribution fact.
- **Do not decide Person or Organization from a name.** A generic `Agent`
  with the name only is valid SPDX 3.0.1 and passes the schema and SHACL
  checks; a later step that reads the model card may add a typed agent
  beside it, and nothing can retype or remove the generic one. An ONNX
  `model_author` is a comma-separated list by the format's own text, so
  `Doe, Jane` becomes two agents, a documented cost of not guessing.
