---
Created: 2026-10-03
Last-Modified: 2026-10-05
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
  ([id-registry-v3.md](../../design/id-registry-v3.md)).
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
  `Hash.comment` that the value is not a single-artifact hash.
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
  Do: treat a near-tie as no answer unless the package states one of the
  tied licences; keep a corpus of real files that fooled the matcher.
