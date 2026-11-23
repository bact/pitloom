---
Created: 2026-11-14
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Asserter: whose determination a value is

See also: [README.md](README.md) (the claim model),
[asserter-licence.md](asserter-licence.md) (the licence field: split off
2026-11-23), [source.md](source.md), [conflict.md](conflict.md),
[alignment.md](alignment.md),
[renames-and-migration.md](renames-and-migration.md). Replaces the `role`
vocabulary of
[role-vocabulary.md](../../implementation/provenance/role-vocabulary.md).

**Status:** draft. The name `Asserter` and the five values are ruled
(2026-11-23; "for now" since 2026-11-16): `originator` (was `subject`, which
is also an SPDX `Annotation` property), `sbom-tool` (was `generator`),
`other-party` (was `third-party`, which in common use means a dependency).

## Definition

The **asserter** of a claim is the party whose determination the value is.
It is not where Pitloom read the value (that is the source) and not what
Pitloom did to get it (that is the method).

The released `role` was defined the same way, by whose determination a
value is, but three of its words say how the value came to exist
(`declared`, `detected`, `inferred`). This facet keeps the definition and
names each party with a noun; those three words go to
[Basis](basis.md).

## Values

| Value | Definition | Decision question | Example | Was |
| --- | --- | --- | --- | --- |
| `originator` | The party that made or published the element the claim is about. For a claim about a dependency, that is the dependency's own maker, not the project that depends on it. | Did the element's own author, vendor or build say this, in the artefact or in metadata it published? | `project.license` in `pyproject.toml`; `License-Expression` in a wheel's `METADATA`; `license:` in `CITATION.cff` | `declared` |
| `sbom-tool` | Pitloom. | Did Pitloom work this out, by matching, deriving or composing? | a content type matched from a file's bytes; a hash; a parameter count summed from tensors | `detected` |
| `other-party` | A party that is neither the originator, Pitloom, an AI agent nor the SBOM author. | Is this another party's own determination, relayed as that party gave it? | a hosting service's own licence detector; a registry's computed file size; a paper's reading of a model's licence | `externalReported` |
| `ai-agent` | An AI agent using judgement. | Did an agent reason its way to the value from prose or context? | a training dataset named from a README sentence | `inferred` |
| `sbom-author` | The person or organisation operating Pitloom. | Did the operator state the fact itself, by a flag, a config key or an answer in a session? | a content type set in `[tool.pitloom]`; `license_concluded=` passed by a library caller | `sbomAuthorSupplied` |

## Rules

1. **Ask whose determination, never where the data was.** Local or remote,
   file or API, makes no difference.
2. **A relay does not change the asserter.** The PyPI JSON API and a
   dependency's installed copy carry the project's own Core Metadata: the
   asserter is `originator`, the source is the registry or the environment. A
   relay can be stale; the source kind says a relay was read.

   The rule covers a relay a system makes, which copies a field
   unchanged. A person who quotes another party is not one (ruled
   2026-11-23): a card that gives a leaderboard's score and names
   the leaderboard is the card writer's statement, `originator`,
   `declared`. A person can misquote, and Pitloom read the card,
   not the leaderboard. The named source is not carried in the
   claim. A result the Hub verified is another case: the Hub's
   own, `other-party`, `detected`
   ([examples/originator.md](examples/originator.md#originator-detected-and-inferred),
   OX-3).
3. **A tool's output belongs to whoever ran it.** A match by LicenseID inside
   Pitloom is `sbom-tool`. A badge from a hosting service's detector is
   `other-party`. "Was an algorithm involved" is not the test.
4. **A pointer is not a statement.** When the SBOM author says "look in X",
   the asserter is whoever the value in X belongs to, never `sbom-author`.
   Reading a source outside the project needs the author's consent; consent
   is a gate, not an asserter.
5. **Naming what the originator stated keeps the asserter.** A stated licence
   name, classifier or URL read as the one SPDX id it lists for is still
   the originator's claim, with a [change](change.md). So is a licence file:
   by convention a licence file placed in a project says the project uses
   that licence, so placing it is the originator's statement, and matching
   its text to an id only names what was stated (ruled 2026-11-16). The
   match is recorded as the method and tool. `sbom-tool` is the asserter
   when Pitloom goes beyond what the originator stated: it picks one of
   several stated values, or combines them.
6. **Derived inside Pitloom, stored in the output.** One function computes
   the asserter from the source kind and the method class (and, where the
   tables below say so, the field or the argument), so they cannot
   disagree; a fragment's own `Asserter` is kept as written. The
   value is always written (README rule 7).
7. **No "unknown".** A fragment entry with no `Asserter` has none; it is not
   assumed. A library caller is covered by the table below.
8. **An agent's value the SBOM author confirms is the author's, and keeps
   the agent** (ruled 2026-11-23). The asserter becomes `sbom-author`: the
   author took the value as their own. `Basis: inferred` is written, since
   how the value was come to does not change; `Tool` keeps the agent and
   its version; `Source` and `Location` keep what the agent read. So a
   reader tells an author's own statement (`declared`, no `Tool`) from a
   reading by an agent that the author confirmed. Not taken: a key for the
   review on the claim (`Asserter: ai-agent` with `Reviewed`), which puts
   two parties on one claim; who reviewed a document, when and in what
   scope is metadata of the document in the OWASP AIBOM Foundations Guide
   (p. 8, 36). Not taken: `sbom-author` and nothing else, where the agent
   is lost. Confirming is an explicit yes of the author to one value,
   shown with what the agent read (ruled 2026-11-23). Merging a fragment
   that an agent wrote is not confirming: it is using the tool, and
   every claim in it stays `ai-agent`; so does every claim of a run with
   no person present. The enrichment skill has no such act today: an
   author who states a fact is `sbom-author` with `declared`, and
   consent to read a source is a gate (rule 4).

## Default asserter by source kind and method class

| Source kind | `read`, `parsed` | `matched`, `derived`, `synthesized` |
| --- | --- | --- |
| `manifest`, `build-backend`, `core-metadata`, `lock-file`, `pin-file`, `package-file`, `artifact-content`, `artifact-name`, `pointer`, `card`, `repository` | `originator` | `sbom-tool` |
| `registry`, `environment` | by field: `originator` or `other-party` (table below) | `sbom-tool` |
| `linked-document` | `other-party` (ruled 2026-11-23; [source.md](source.md), rule 9) | `sbom-tool`; the licence exception below does not reach it |
| `config`, `session` | `sbom-author` | `sbom-tool` |
| `caller` | by the argument the caller fills (below) | `sbom-tool` |
| `fragment` | as the fragment states | as the fragment states |

`ai-agent` is never a default: an agent's claim arrives in a fragment or an
enrichment record that states it.

A lock or pin file is the depending project's file. What it says about the
project's dependency (which version the project uses) is the project's own
statement: `originator`, the claim being about the dependency relationship.
What it records about the dependency's artefact (a hash, a size, a URL) is
not the statement of the dependency's maker: `other-party`.

Exception to the `matched` column: a licence text matched to an id, when
the text is the manifest's own licence text or a licence file of the
element, of its project tree or of its hosting repository, keeps
`originator` (rule 5), and `declared` with it. Ruled 2026-11-21: it is
written as this exception, `Method: matched`, not as a `Change` step
on the originator's claim ([asserter-licence.md](asserter-licence.md),
"The form of a text match").

Registry and environment fields. One row per field a reader uses; a field
not listed is not read. `detected` in the Basis column says the party
got the value by its own procedure, exact or not
([basis.md](basis.md), rule 2).

| Source | Field | Asserter | Basis | Fixed by the element's state | Why |
| --- | --- | --- | --- | --- | --- |
| PyPI JSON API | `info.*` (licence, author, summary, classifiers, `requires_dist`, URLs) | `originator` | `declared` | yes: of the release | the uploader's Core Metadata, relayed |
| PyPI JSON API | file `digests`, `size` | `other-party` | `detected` | yes: of the file | PyPI computed it from the upload |
| PyPI JSON API | `upload_time`, `yanked`, the release list | `other-party` | `declared` | `upload_time` yes; `yanked` and the release list no | PyPI's own record |
| Hugging Face Hub API | `cardData.*`, `tags` taken from the card | `originator` | `declared` | yes: of the commit | the card's front matter, relayed |
| Hugging Face Hub API | `sha` | `originator` | `declared` | it is the commit | the repository's ref, relayed: whoever pushed the branch says which commit it names (ruled 2026-11-23) |
| Hugging Face Hub API | `tags` the Hub adds | `other-party` | `detected` | no | the Hub computed them |
| Hugging Face Hub API | `safetensors.total`, `gguf.total` | `other-party` | `detected` | not stated by the Hub's library | the Hub computed it from the files |
| Hugging Face Hub API | the repository owner | `other-party` | `declared` | no: of the repository | the Hub assigned it |
| Hugging Face Hub API | `last_modified`, `created_at` | `other-party` | `declared` | no: of the repository (`created_at` does not change) | the Hub's own record |
| installed metadata, pipdeptree | Core Metadata fields | `originator` | `declared` | no: an environment has no state | the distribution's own metadata, as installed |
| installed metadata, pipdeptree | which versions are installed, the dependency tree | `sbom-tool` | `measured` | no | Pitloom's own look at the environment, through a tool it starts (rule 3; ruled 2026-11-23, was `other-party`, `detected`) |

The fifth column (ruled 2026-11-23; [source.md](source.md), "Rule D:
registry fields beside a commit") says whether the field follows from
the element's release or commit. "No" is a claim of the moment of the
read (rule D there): the service computes it, or keeps it for the whole
repository. No key on the claim says so. Two rows were added with the
column, for fields that were read and not listed: the tags the Hub
adds, and `last_modified` with `created_at`. Not checked: whether a
later file of one PyPI release can change its `info`.

A commit that a ref names is the originator's declared statement, on
both routes (ruled 2026-11-23): read from a Git host's ref it is kind
`repository` with method `read`, so the table above gives `originator`
with no exception; read from the Hub's `sha` it is the row here. Which
branch is read when none was asked for is a selection rule
(`default-branch`, [conflict.md](conflict.md)), recorded apart from the
asserter.

Library and SDK arguments. A caller names a field by the argument it fills,
so the argument fixes the asserter when the caller gives no provenance.

| Argument | Asserter | Why |
| --- | --- | --- |
| `license_concluded=` | `sbom-author` | the caller states a conclusion (agreed 2026-11-14) |
| `license_name=`, the SDK's `declared_license=`, any other metadata field | `originator` | the caller hands on what the element's maker states; the source kind `caller` says it was not read by Pitloom |
| a value with the caller's own provenance | as that provenance says | - |

The second row is ruled (2026-11-23): `originator`. The argument's name
says what the caller hands on, a caller who concluded has
`license_concluded=`, and one who has another source passes its own
provenance (third row). Not taken: `sbom-author` for everything a
caller passes, which would turn a caller's `license_name` into
`hasConcludedLicense`, where today it is declared. Pitloom cannot check
that the caller relays the maker's statement; the kind `caller` is what
tells a reader so.

## The licence field

What the asserter decides for a licence is on its own page,
[asserter-licence.md](asserter-licence.md): the table from asserter to
`hasDeclaredLicense` and `hasConcludedLicense`, the licence file as the
originator's declaration, the gate and the form of a text match, and the
licence points that were parked, each with its ruling.

## Mappings (loose)

| Asserter | SSSOM | PAV | ECO | BSI v2.1.0 |
| --- | --- | --- | --- | --- |
| `originator` | `author_id` | `pav:authoredBy` | `ECO:0000204` author statement | original |
| `sbom-tool` | `mapping_tool` | `pav:createdBy` (autonomous software) | `ECO:0000203` automatic assertion | - |
| `other-party` | `mapping_provider` | `pav:providedBy` | `ECO:0000311` imported information | - |
| `ai-agent` | `mapping_tool` with `semapv:AgentBasedMatching` | `pav:createdBy` | `ECO:0000203` automatic assertion | - |
| `sbom-author` | `creator_id`, `reviewer_id` | `pav:curatedBy` | `ECO:0000218` manual assertion | distribution, effective |

SPDX 3 names three of the parties by property: `originatedBy`
(`originator`), `createdUsing` (`sbom-tool`) and `createdBy`
(`sbom-author`). The 2026 Minimum Elements for an SBOM (CISA and
co-authors, version 2.1; primary text read 2026-11-16) name the same three
by data field: Component Producer (the entity that created the component;
it replaces Supplier Name, and the change log says the term refers to the
entity that originated the software), SBOM Tool Name with SBOM Tool Version,
and SBOM Author (the entity operating the tool, not the tool itself). That
document uses "third party" for a component from a source external to the
SBOM author, another sense than `other-party` here. The external terms
are properties or evidence types, not parties, so every row is a related
match and no more. Rows with predicates:
[mappings/](mappings/pitloom-provenance.sssom.tsv).

In PROV-O the facet reads as `prov:wasAttributedTo`, from the statement
behind a recorded value to a `prov:Agent`; `sbom-tool` and `ai-agent` are
`prov:SoftwareAgent`. PROV-O says the relation "is useful when the
activity is not known, or irrelevant": an attribution can stand alone,
and that is the `declared` case. `prov:actedOnBehalfOf` (the tool is the
subordinate agent, the party that ran it the responsible one) is the
relation behind rule 3. It names the question for four field-table
rows and does not decide them; they are ruled since (2026-11-23):
[alignment.md](alignment.md).

For the licence field ODRL 2.2 draws one line of the "Licence
relationships" table: the originator's statement against every other
claim. An `odrl:Offer` is a policy proposed "from an assigner", the issuer
of the rule: the declared licence. An `odrl:Assertion` "only asserts the
parties claims": a conclusion by `sbom-tool` or `sbom-author`, and
loosely a claim by `other-party` or `ai-agent`. ODRL does not tell a
conclusion from a claim that yields no relationship. `odrl:Assertion` is
in ODRL's common vocabulary, which is not normative, and an Offer grants
nothing either: the line is proposing against claiming. Related matches:
ODRL types a policy, this facet names a party.
