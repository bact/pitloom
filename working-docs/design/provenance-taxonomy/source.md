---
Created: 2026-11-14
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Source: where Pitloom read a value

See also: [README.md](README.md) (the claim model),
[asserter.md](asserter.md),
[renames-and-migration.md](renames-and-migration.md) (old label to new kind),
[resweep-rulings.md](resweep-rulings.md) (rulings C7 and C8 of
2026-11-28, written into rule 5 and rule C here).
Replaces the source taxonomy of [license-rules.md](../license-rules.md)
section 1 and the label set `TRANSPARENT_SOURCES` (`THIRD_PARTY_SOURCES`,
the second set, is gone on `main` since bdf35a29, pull request 569).

**Status:** draft; re-based on `main` dfa11c14 (release 0.25.1) on
2026-11-28. Nothing here is built: where the page says what the code does,
it says so with its evidence.

## Definition

The **source** of a claim is the thing Pitloom itself read to get the value.
It is never the thing that source copied from: a licence read from the PyPI
JSON API has the source `PyPI JSON API`, although PyPI copied it from the
project's upload. Whose statement it is belongs to
[Asserter](asserter.md).

A source has four parts:

| Part | Key | Holds | Example |
| --- | --- | --- | --- |
| label | `Source` | a name a person recognises: a file name or a service name | `pyproject.toml`, `PyPI JSON API` |
| kind | `Kind` | one value of the closed list below | `manifest` |
| location | `Location` | where inside the source: a key, a field, a tag | `project.license`, `License-Expression`, `general.name` |
| container | `Container` | the archive, repository or directory that holds the source, when the label alone does not find it | `pkg-1.0-py3-none-any.whl`, `pkg.egg-info` |

Today the label does the kind's work: the code lower-cases it and looks it
up in one set, `TRANSPARENT_SOURCES` (`_provenance_encoders.py:22-32`,
read at dfa11c14); the second set, `THIRD_PARTY_SOURCES`, was removed by
bdf35a29, and `is_license_concluded` now asks only whether a source is
named (`:70-79`, read). A file name cannot be looked up, so every dynamic
label has no kind. The kind is now carried with the value from the reader that
produced it.

## Kinds

| Kind | Definition | Labels today |
| --- | --- | --- |
| `manifest` | A project file a person writes to describe the package. | `pyproject.toml`, `setup.cfg`, `setup.py` |
| `build-backend` | Core metadata as a build backend resolved it, in memory. | `Hatchling build backend` |
| `core-metadata` | A Core Metadata file of the artefact itself or of the project tree. | `wheel METADATA`, `sdist PKG-INFO`, an in-tree `.egg-info`/`.dist-info` |
| `lock-file` | A resolver's output. | `pylock.toml`, `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock` |
| `pin-file` | A hand-kept list of exact pins. | `requirements.txt` |
| `package-file` | A file inside the package or project the claim is about, other than the kinds above. | `LICENSE`, `CITATION.cff`, `codemeta.json`, a version file, a source file's header tags |
| `artifact-content` | The bytes of the one file the element *is*: its header, its embedded metadata, its content. | a model file name, `downloaded file`, a dataset file |
| `artifact-name` | The described file's name. | `wheel filename`, a model's file name stem |
| `pointer` | A small file that stands in for content stored elsewhere. | a Git LFS pointer |
| `card` | A model or dataset card, or a dataset description file. | `README.md` front matter, a Croissant file |
| `repository` | The hosting repository: a file of it that is not part of the described artefact, or its refs (a branch or tag that names a commit; widened 2026-11-23, rule C). | Hub repository config files, `AUTHORS` |
| `linked-document` | A document outside the element and its hosting repository, reached by a link a source gives (added 2026-11-23). The label is the URL, or the file's name with `Container:` naming the other repository. | (none today in Pitloom; the enrichment skill's agent reads a card's `license_link` page) |
| `registry` | The API or index of a package or model registry. | `PyPI JSON API`, `PyPI`, `Hugging Face Hub` (API fields) |
| `environment` | The Python environment Pitloom runs in or inspects, also when the element described is a package installed there. | `installed metadata`, `deployed package metadata`, `pipdeptree`; on `main` since 075195ea also a licence file of an installed `.dist-info`, written `Source: installed metadata \| Package: <name> \| File: <RECORD entry>` (`_deps_license_files.py:136-141`, read at dfa11c14); its kind is open (below, "Open points") |
| `config` | Pitloom's own configuration: `[tool.pitloom]`, a CLI flag, an Action input. | (none today; the file is named) |
| `caller` | Code that calls Pitloom's library or SDK. | a caller script path |
| `session` | The SBOM author's answer in an interactive session. | `SBOM author` |
| `fragment` | An SBOM fragment merged into the document. | (fragment file name) |

No kind for "Pitloom made it up": such a claim has no source. It has
`Asserter: sbom-tool` and `Method: synthesized`, and `Source` is omitted.
`Pitloom generator` and `unknown` are retired as labels.

## Rules

1. **The label is for people, the kind for code.** No code compares labels.
2. **No label stands for several kinds at once.** A file name can have
   different kinds in different places (`METADATA` in a wheel is
   `core-metadata`, in an environment `environment`; `pyproject.toml` is
   `manifest` for `[project]` and `config` for `[tool.pitloom]`); the
   kind written with it says which. What is not allowed is one label
   used for everything a service holds: `Hugging Face Hub` covers four
   kinds today (API
   fields, the card, repository files, a licence file). Each gets its own
   label and kind: `Hugging Face Hub API` (`registry`), the card's file name
   (`card`), the file's name (`repository`), with `Container:` naming the
   repository.
3. **No qualifier in parentheses.** `pipdeptree (deployed environment)`
   becomes label `pipdeptree`, kind `environment`.
4. **One source per claim.** A value built from two files
   (`setup.py, setup.cfg`) is two claims and a [conflict](conflict.md) or a
   merge rule, or one claim whose `Location` lists the keys of one file.
5. **No default label.** A value with no recorded source gets none; the
   fallbacks `AI model metadata`, `model file / Hugging Face Hub`,
   `Dataset metadata`, `LICENSE`, `lock file`, `Unknown source` stay
   faults to fix at the reader (ruled again 2026-11-28, C7 of
   [resweep-rulings.md](resweep-rulings.md)). A stand-in that Pitloom
   writes because a format requires a value (a package named `unknown`,
   a creation time of 1970) is another thing: it is no claim, and sits in
   one small closed list ([method.md](method.md), "Stand-ins"). A default
   label is a missing source; a stand-in is a missing value.
6. **`Location` is a locator, not prose.** A method written inside it
   (`raw pickle (fickling)`, `keras_version attribute (major version)`) moves
   to `Technique` or `Tool`.
7. **`Container` has one meaning.** The marker file inside a labelled
   directory (`x.egg-info | File: PKG-INFO`) turns round: label `PKG-INFO`,
   container `x.egg-info`. The downloaded file itself is the label, not a
   container.
8. **`Kind` is always written** (ruled 2026-11-23), on every claim that
   has a source; a claim with no source (`Method: synthesized`, above)
   has none. A consumer filters on the key and needs no table of
   Pitloom's labels, and one label with two kinds (`pyproject.toml`,
   rule 2) is told apart. Not taken: the kind looked up from the label
   for fixed labels and written only for file names.
9. **A linked document is not the element's own** (ruled
   2026-11-23). What `linked-document` holds is read as
   `other-party`: Pitloom does not know who wrote the page. The
   field that gave the link (`license_link`) is not recorded; no
   key is added for it. `web-page` was looked at as a name and is
   too narrow: a link can name a file in another repository
   ([examples/sbom-tool.md](examples/sbom-tool.md#sbom-tool-detected),
   ST-1;
   [examples/ai-agent-and-sbom-author.md](examples/ai-agent-and-sbom-author.md#ai-agent-inferred),
   AI-1). The originator's link does not make a matched text the
   originator's declared licence (ruled 2026-11-23;
   [asserter-licence.md](asserter-licence.md), the `sbom-tool`
   row). One thing this does not decide: whether Pitloom itself
   fetches a linked document (code stage; a URL taken from a card
   is chosen by whoever wrote the card).

## A source that can change (rules A to D ruled 2026-11-23)

Raised by the OWASP AIBOM Foundations Guide v1.0
([vocabularies-considered-sbom.md](vocabularies-considered-sbom.md)): a name can be
pointed at a newer snapshot with no release on the reader's side (p. 7,
24); an approval has to bind to a version or hash of a definition, not to
its name (p. 29); a change on the supplier's side is the one kind that
comes with no local release (p. 37). This page had no rule for it.

A source is in one of three cases:

| Case | Same read, same bytes | Examples | What fixes it |
| --- | --- | --- | --- |
| held | yes: Pitloom has the bytes | a project file, a wheel, a downloaded model file | a digest of the bytes |
| fixed by an id | yes, by the service's promise | a Git commit; a Hub repository at a commit; a file of a PyPI release (PyPI does not let a file name be used again, also after a project is deleted and made again; a file can only be removed: PyPI documentation, "Publishing", "Troubleshooting", read 2026-11-22) | the id |
| moving | no | an environment; a Hub read after `model_info` failed; a branch or `latest` only where no id can be had for it (else rule A makes the read one of the case above) | nothing; the claim is of the moment of the read |

What the code does. Read at this branch's base 257b7260 (0.24.0) and
checked 2026-11-22: the lines the table rests on are also on `main` at
a4aa51cd (#506; this checkout's copy of the remote branch, not fetched
again); the Git route was run with the fetch stood in for; the Hub
revision tests were run (18 pass). No route was run against the network.

| Route | Read at | Written in the SBOM |
| --- | --- | --- |
| Hub model | `model_info` with no revision, so the head of the default branch; then the card, three config files and each licence file at that answer's `sha`. The list of licence files was not at that state at the draft's base (`list_repo_files` with no revision, so the head); on `main` (dd31412b, read 2026-11-23) it is the `siblings` of the same `model_info` answer, so it is. Not at that state: every file when `model_info` fails or states no `sha` (no revision, one `WARNING:` each). On `main` dfa11c14 a model the Hub does not know (`RepositoryNotFoundError`, not its gated subclass) is refused instead, with no file fetched and no SBOM (982f3e84; `input-not-found/hub`); other failures keep the warnings (commit message read, code not re-read). A URL that names a revision (`/tree/<rev>`, `/blob/<rev>/...`, `/commit/<sha>`) is still read at the default branch, now with one `WARNING:` `hub-revision-unpinned/url` (5f48eb5f; `log_hf_url_revision` in `extract/remote/huggingface.py`, read in the diff) | the commit as the element's version and in its PURL, when it is a 40-digit hash, with a claim `Field: model_info sha`. Not written: the name asked for (the default branch). The API fields (tags, parameter total) are the answer of that moment |
| Hub dataset | `dataset_info` with no revision; then the card at that answer's `sha`; no other file | the commit as the version, with a claim `Field: dataset_info sha` |
| PyPI URL | the release the URL names, else the latest; one file | the acquisition record: version (`Method: latest-release` when none was named), file name, digest measured and digest declared, status |
| PyPI lookup for a dependency | the pinned version; with no version, the latest | the claim names the service and the package (`Source`, `Package`), no release. With no version, the licence and originator of the latest release are written on the dependency; a digest only when the version is known |
| Git URL | a branch, tag or commit; the commit checked out is resolved (`GitCheckout.commit`) | nothing of the fetch. A run of `loom project` on a URL gave an SBOM with no commit, no ref name and no host of the URL; no code reads the commit (the model route was not run) |
| project tree, environment | the files as they are | not looked at for this page |

Four rules, all ruled 2026-11-23.

- **A. One read, one state** (ruled 2026-11-23). All claims of one
  element that come from one container are read at one state of it.
  Pitloom resolves a name (a branch, `latest`, a default) to an id
  first, then reads by the id. The Hub routes do this today, but for
  the two reads the table names: the code does not meet the rule there
  yet (code stage, list below).
- **B. The state is written once, on the element** (ruled 2026-11-23).
  As its version (a Hub commit), its acquisition record (a PyPI file),
  its digest (a held file) or, for a Git commit beside a version that is
  taken, one of the places of the subsection below; a claim's
  `Container` leads there. A claim names a state of its own only when it
  was read at another one: a licence taken from the latest release for a
  dependency whose version is not known. Today that claim names no
  release (table). Not taken: the state on each claim. It would repeat
  one id on every claim of an element, and two claims of one element
  could then name two states with nothing to say which is the
  element's. Open under B: the name of the key for the exception; and
  an element fed by more than one container (a dependency read from a
  lock file and from a registry), where only one state can be the
  element's. Both are taken up below ("Rule B: the two open points").
- **C. A name asked for is written beside the id it resolved to**
  (ruled 2026-11-23): `latest` and the release, a branch and the commit.
  Then the next SBOM shows that the name moved. Not taken: the id
  alone, where a reader of two SBOMs cannot tell a name that moved from
  a user who asked for another thing. Done for a PyPI release today, by
  `Method`; here the pick of a release is the conflict rule `latest`
  ([conflict.md](conflict.md)). Not done for the default branch of a
  Hub repository or for a Git branch (code stage, list below). Ruled
  2026-11-28 (C8 of [resweep-rulings.md](resweep-rulings.md)): when a
  revision was asked for and another was read, both are recorded
  (table under "Rule C", below); `Rule: default-branch` is written also
  when no commit is known. Today a Hub URL's revision is read at the
  default branch with a `WARNING:` and no record in the SBOM. Open
  under C: the form for a branch, and where on the element it sits
  (rule B); taken up below ("Rule C: the form for a branch or a tag"). PAV has this
  pair: `pav:hasCurrentVersion` relates a resource with no version to
  the one snapshot that holds its content now (a sub-property of
  `pav:hasVersion`); in PROV-O the snapshot is a `prov:specializationOf`
  the resource.
- **D. A source is moving only where no id could be had; it has no pin,
  no key says so (one exception, below), and no time is written on a
  claim** (ruled
  2026-11-23; "no time on a claim" stands, ruled again 2026-11-28, C8
  of [resweep-rulings.md](resweep-rulings.md)). An id comes first (rule A): with a commit or a release
  named, a time adds nothing about the state. What is left is a read
  with no id: an environment, and a read where the service gives no id
  or the call that gives it fails. A reader tells it by the kind
  (`environment`) and by no state on the element. The exception is
  ruling C8 ([resweep-rulings.md](resweep-rulings.md), ruled
  2026-11-28): where the default branch was read, `Rule:
  default-branch` is written also when no commit is known, so that
  case is said by a key. No time, because the
  output is deterministic (the same input gives the same bytes), and a
  clock value differs on each run also when the source did not move.
  When the clock gives the document's `created`, that is the moment of
  the run; under `SOURCE_DATE_EPOCH` or `--creation-datetime` it is
  not, and then no time of the read is in the SBOM (a known loss). This goes against PAV, which has a time for this case:
  `pav:sourceAccessedOn`, for a source that was consulted (its text says
  the time can be crucial for a source such as a weather forecast), and
  `pav:retrievedOn`. Open under D: whether each API field of the Hub
  answer follows from the commit alone, or is an answer of the moment
  (checked 2026-11-23, below: "Rule D: registry fields beside a
  commit"); and, until the code meets rules A and B, no state on an
  element also means the code did not write one (the Git route).

With B, no key is on every claim (`Revision`, `Snapshot`, `Retrieved`).
A revision in PROV-O (`prov:wasRevisionOf`: an entity that is a revised
version of an original) is what [Change](change.md) records.

### Rule B: the two open points (ruled 2026-11-23)

**B1. How a claim names a state of its own** (ruled 2026-11-23). One
case was found in the code (the table above; not an audit of every
reader): the lookup of a dependency whose version is not known, which
reads the latest release of the registry. No new key. `Package` already names the
record read in a registry or a lock file; for this claim it names the
release too, in the ecosystem's own spelling, and rule C's name goes in
`Rule`:

```text
Source: PyPI JSON API | Kind: registry | Package: requests==2.32.3 | Rule: latest | Asserter: originator | Basis: declared
```

Not taken: a key of its own (`Revision`, `State`, `At`), which one
case does not pay for; or the release inside `Container`, against
rule 7 (a registry is no container of the record). When a second case
comes that `Package` cannot hold (a repository at a commit that is not
the element's), the key is looked at again.

**B2. An element fed by more than one container** (ruled 2026-11-23).
A state belongs to the thing that was read, and is written on the
element that is that thing. An element has one state of its own, that of the thing
it is: a release (its version), a file (its digest), a repository (its
commit). The containers of its claims do not compete for it:

| The claim's container | Its state is | Example |
| --- | --- | --- |
| the element itself | the element's | a wheel's `METADATA`; a Hub repository's card |
| another element of the SBOM | on that element | a lock file of the project says which version of a dependency is used: the state is the project's, not the dependency's |
| a registry record of the element | the element's version, when the record read is of that version; else B1 | the PyPI record of release 2.32.3 for a dependency pinned at 2.32.3 |
| no element, and no id (rule D) | none | the environment |

So a dependency read from a lock file, a registry and an environment
has one state, its version; nothing of the lock file's or the
environment's state is written on it. Not settled by B2: a thing that
two elements could both be (a model described from a weight file and
from its hosting repository). Read here as two elements, a repository
with its commit and a file with its digest; whether a route puts both
on one element was not checked.

### Rule C: the form for a branch or a tag (ruled 2026-11-23)

What the Git route knows of the name asked for (`GitTarget`, read
2026-11-23): a branch, a tag, a commit, or nothing. With nothing the
default branch is read, and Pitloom does not learn its name; the Hub
route asks with no revision, the same case. A PyPI release has two of
the four cases only: a version named (the id itself) or nothing
(`Rule: latest`).

| Asked for | Written beside the commit | Why |
| --- | --- | --- |
| a commit | nothing | the id was asked for |
| nothing | `Rule: default-branch` | **C1** (ruled 2026-11-23). Pitloom picked no name; the repository's default was read. The name of that branch is not written: Pitloom does not learn it today. Rule 8 in the closed list of [conflict.md](conflict.md), beside `latest`: of several branches, the one the repository names as its default, when none was asked for |
| a branch | `Location: refs/heads/` and the name | **C2** (ruled 2026-11-23). The ref is where in the repository the commit was read, which is what `Location` holds. Git's full spelling tells a branch from a tag, and the route knows which |
| a tag | `Location: refs/tags/` and the name | as a branch |
| a revision, and another was read | the revision asked for and the one read, both | ruled 2026-11-28 (C8 of [resweep-rulings.md](resweep-rulings.md)): the case of a Hub URL that names a revision while the default branch is read. A reader then sees that the SBOM does not describe what was asked for |

`Rule: default-branch` is written also when no commit is known (ruled
2026-11-28, C8): the claim then says that a default was read, though
not which state of it. The row labels C1 and C2 above are those of
2026-11-23, not the rulings of 2026-11-28.

Where: on the claim of the field that holds the commit (rule B; which
SPDX place that is, is a code-stage choice, below). Not taken for
C2: a key of its own (`Ref`), or `Written` with a new `Change` step
(the name is the user's input, not what a source wrote).

Open with C2: on the Hub route the commit's claim has
`Location: sha`, the API field. Should that route take a named
revision one day (whether it can today was not checked), the two uses
of `Location` meet, and the claim's source becomes the repository's
ref, not the API field. The kind of a Git host's refs is
`repository` (ruled 2026-11-23; the kind's definition was widened
from "a file of the hosting repository" for it).

### Rule D: registry fields beside a commit (checked 2026-11-23)

What the Hub's library says of the fields of `model_info`
(`huggingface_hub` 2.2.0, the docstring of `ModelInfo`, read from the
installed package), and what Pitloom does with each (code at the
branch base):

| Field | The library says | Follows from the commit alone | Pitloom |
| --- | --- | --- | --- |
| `sha` | the repository's SHA "at this particular revision" | it is the commit | the element's version |
| `tags` | the model's tags; beside the card's, "extra tags computed by the Hub" | no | read for dataset ids and the like |
| `last_modified` | the date of the last commit "to the repo" | no: of the repository, not of a revision | written as the release time of the revision |
| `created_at` | the date the repository was made | no, but it does not change | kept as `hf.created_at` |
| `author` | the author of the model | no: of the repository | originator and supplier |
| `downloads` | downloads over the last 30 days | no | read; no use of it was found |
| `safetensors`, `gguf` | the model's Safetensors or GGUF information; nothing on a revision | not stated | the parameter total |

So an element with a commit still has claims of the moment: a field
the service computes or keeps for the whole repository. Rule D holds
for them (no key, no time); what was missing is where a reader learns
which they are.

Ruled 2026-11-23 (**D2**): the field table of
[asserter.md](asserter.md) has one more column, "fixed by the element's
state": yes for a field that follows from the release or the commit
(the uploader's Core Metadata, a file digest, the card's front
matter), no for one the service computes or keeps apart (the tags it
adds, a repository's owner, `yanked`, the release list). No key on the
claim. For the code stage: `last_modified` is written as the
revision's time, and the library gives it for the repository.

Not checked: the same for `dataset_info` (the `DatasetInfo` page words
`sha`, `last_modified` and `downloads` alike); whether the Hub
computes the Safetensors total from the files of the revision asked
for.

### Where SPDX 3 can hold a Git commit (read 2026-11-22)

For rule B, when the element's version is taken (a Python project
fetched from Git has the version of its `pyproject.toml`). SPDX 3.0.1 and
3.1 have no property for a commit and no external identifier type made
for one (every term of both Python bindings was searched; the 3.0.1
pages of `downloadLocation`, `contentIdentifier` and the PURL annex were
read through a summary). What can hold it:

| Place | What its specification says | Form | Fit |
| --- | --- | --- | --- |
| `externalIdentifier`, type `swhid` | SPDX: an identifier for files, directories, commits and other objects of version control. SWHID 1.2: `rev` is a recorded copy of a project's root directory, its hash computed as Git computes a commit's ("compatible" with today's Git, not promised to stay so); the qualifier `origin` is the URI where the object was found | `swh:1:rev:` and the 40 digits, then `;origin=` and the repository URL | the one typed form; one string holds the commit and the repository; not the folder read |
| `software_contentIdentifier`, type `swhid` | an identifier of the artefact's content, for identity or integrity | `swh:1:dir:` and the Git tree id of the folder read | fits "content" better than a commit, which also holds history; Pitloom does not resolve the tree id today |
| `software_packageUrl`, qualifier `vcs_url` | SPDX annex: an extra URL of the package's version control system, no format. PURL specification, Annex B (informative): tool and transport, host, path, then `@` and a commit, tag or branch, then `#` and a sub-path; a commit is recommended | `pkg:pypi/demo@1.0?vcs_url=` and the encoded `git+https` URL with `@commit` | holds repository, commit and folder; but a fact of one fetch goes into the string that identifies the package |
| `software_downloadLocation` | SPDX 3.0.1: the URI to download the package at the time the document was made; no format for a version control location | a `git+https` URL with `@commit`, by the PURL or pip syntax | the natural place; SPDX 3 fixes no syntax, so a reader cannot rely on it (a format gap) |
| `externalRef`, type `vcs` | a reference to a version control system related to the artefact | the repository URL | names the system, not a state |
| `software_packageVersion` | the version of a package | the commit | done for a Hub model; taken for a Python project |

Not fit: `verifiedUsing` with a `sha1` hash (a commit id is the hash of
the commit object, not of the artefact's bytes); `gitoid` (an identifier
of a file's bytes, by the OmniBOR specification, not of a commit). Not
read: the SPDX 2.3 clause on a download location in a version control
system; whether SWHID covers a Git repository that uses SHA-256.

So rule B needs no key of Pitloom's own for a Git commit: an external
identifier of type `swhid` holds it. Which of the places is
used is a choice of the code stage, with an entry in
[sbom-format-gaps.md](../sbom-format-gaps.md) for the download location
syntax.

For the code stage, not this page: the Git commit that is resolved and
not written; the default branch not named on the Hub route; the list of
licence files and the files after a failed `model_info`, read at no
state; the release a dependency lookup read.

Terms read for this (2026-11-22). PAV 2.3.1, its RDF file: the terms
above, and `pav:version` (a free-text version number). PROV-O, through a
summary of the page, its last quarter not read: times of an entity
(`prov:generatedAtTime`) and of an activity (`prov:startedAtTime`,
`prov:endedAtTime`), `prov:atTime` on an instantaneous event (its
definition not read), and no term for a version number, a snapshot or
the time of a retrieval; the time of a read is there the time of the act
that `prov:used` the source. Wikidata's P813 "retrieved" (below) is the
time of a read; other Wikidata, SOSA and CycloneDX terms were not looked
up.

## What the kind decides

- The default [asserter](asserter.md) (table there).
- Detail level `minimal`: no longer by source (the rule is in
  [README.md](README.md), "Use cases").
- The cascade order per surface: an order table lists kinds and locations,
  one table tested against every reader (license-rules question 6).

## Open points (2026-11-28)

1. The kind of a licence file read from an installed `.dist-info`
   (075195ea): `environment` (it was read from the environment, as
   `installed metadata` is), or `package-file` with `Container:` the
   `.dist-info` (it is a file of the package the claim is about). Its
   label too: `installed metadata` with the file in `File`, as today, or
   the file's own name.
2. Ruling C8: the keys of the row "a revision, and another was read"
   (two `Location` values, or a `Rule` with the revision asked for), and
   where on the element it sits (rule B).
3. Ruling C7: which stand-ins are in the closed list
   ([method.md](method.md), "Stand-ins").

## Mappings (loose)

| Part | PROV-O | PAV | Wikidata | CycloneDX |
| --- | --- | --- | --- | --- |
| source | `prov:wasDerivedFrom` (the entity read; not `prov:hadPrimarySource`, since a source may be a relay) | `pav:retrievedFrom` | P248 stated in | `evidence.occurrences[].location` |
| `registry`, `environment` relaying the originator | `prov:wasQuotedFrom` | `pav:importedFrom` | P248 with P813 retrieved | - |
| location | - | - | P958 section, verse, paragraph, or clause | `occurrences[].symbol` |

PROV-O has a term for the location too: `prov:atLocation`, whose
`prov:Location` may be "a non-geographic place such as a directory, row,
or column". The table's first row is the short form; in full, the source
is what Pitloom's act `prov:used`, and the recorded value is derived from
a statement inside it ([alignment.md](alignment.md)).

A quotation in PROV-O is "the repeat of (some or all of) an entity, such
as text or image, by someone who may or may not be its original author".
It holds twice: between the value Pitloom copied unchanged and the
statement in the source, and, for a relay, between the registry's record
and the originator's own metadata. The second hop is what the kinds
`registry` and `environment` stand for; it is not recorded. SIO's `has
source` ("another entity from which it stems") is a loose match for the
facet, and its `quote` for a relayed value.
