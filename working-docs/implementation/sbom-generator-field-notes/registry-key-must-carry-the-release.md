---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: a registry key must carry every field that tells releases apart

See also: [README.md](README.md) (index of these notes),
[spdx-modelling.md](spdx-modelling.md) (section 1: the 2026-10-02 design,
a purl-shaped key; #407 reverses it, see section 2 below),
[identity-and-archives.md](identity-and-archives.md) (section 3, registry
ids and file keys), [id-registry-v3-lessons.md](id-registry-v3-lessons.md),
[path-keys-lessons.md](path-keys-lessons.md) (the same question for models:
name or path),
[id-registry-v3.md](../id-registry-v3.md) (the design; #407 adds its
section 6.1),
[known-bugs.md](../../design/known-bugs.md),
[open-research-questions.md](open-research-questions.md).

**Status: #407 is in review, not merged** (branch
`registry-package-version-key`, head eb3fed66, 2026-10-30). Everything
below about its code is read from that branch; the remote-entry plan
(section 6) is a recommendation, not built.

## 1. The finding: a registry made two releases less distinct than none

- **What the ID registry is for.** It pins `spdxId`s so a re-run, or a
  run on another surface, writes the same ids. It had keyed a
  `software_Package` by its PEP 503 name alone since v2, and v3 (#305)
  kept that.
- **The symptom.** With a registry, `Demo_Pkg` 1.0 and then 2.0, and
  `requests` 2.31.0 and then 2.32.3, kept one id each (`#Package-1`,
  `#Package-2`); with no registry the two releases got different ids.
  A feature added so ids would be stable made two different things share
  one id, and nothing looked wrong: the lookup hit (report of the design
  agent, session scratch, on tree dfd0047a; reproduced there, not
  re-run for these notes). Merging the SBOMs of two releases then unifies
  them ([spdx-modelling.md](spdx-modelling.md)).
- **A second symptom of the same rule.** `loom id generate -e
  Requests@2.31.0:software_Package` was stored as `requests@2-31-0`:
  the key normaliser applied the PEP 503 *name* rule (runs of `-`, `_`,
  `.` become `-`) to the whole key, version included.
  Do: a normaliser written for one part of a key must not run over the
  whole key.
- **Known and put off.** The fix was decided on 2026-10-02 as Q-D and left
  "not built" (known-bugs, P1). The 2026-10-30 0.22.0 cut listed it among
  the serious bugs (a wrong identity), which is why it was built now.

## 2. A reversal of the first design

- The 2026-10-02 decision keyed a package by a purl-shaped string
  (`pkg:pypi/foo@1.0`), with an empty version part for an unpinned or
  range dependency. #407 does not. Its rulings of 2026-10-30:
  - **D1**: a range dependency is keyed by the version the SBOM states,
    resolved from the lock file or the environment, not by its range. An
    empty version part for every range would have been the original bug
    for the range case: two releases, one id.
  - **D6**: the key is `<PEP 503 name>[@<canonical PEP 440 version>]`, not
    a purl: a purl would be a second spelling of the same two facts.
  Rejected, with the reason recorded: B, key exact pins only (ranges would
  share ids); C, the purl as the key; D, strip local and dev labels
  (`1.0+cu121` and `1.0.dev1` are different builds).
- **Why a reversal is worth a note.** The first decision named the
  problem correctly and chose a key shape that kept part of it: an empty
  version part, meant for "no version known", also stood for every range.
  The purl spelling reuses the output's own PURL form (*inference*: no
  record says why it was chosen).
  Do: when a key reuses an output format's spelling, check that the format
  was designed to identify what the key must identify.

## 3. The key

- `package_key(name, version)` in `id_registry/_types.py` (branch head):
  the PEP 503 name; a `%` or `@` in it percent-encoded (`%25`, `%40`) so
  the first `@` is always the separator; then `@` and the version part
  when a version is stated; NFC.
- **The version part** is the canonical PEP 440 form from Pitloom's
  bounded parser (`canonicalize_version` of `pitloom.core.pep440.parse_version`),
  so `1.0` and `1.0.0` are one key; text that does not parse is kept as
  given; local and dev versions stay distinct (D4); old releases are never
  pruned (D5). The last commit on the branch (eb3fed66) records that the
  version part agrees with `is_same_version` on stated versions, the
  comparison every other layer uses.
- **The placeholder rule.** A bare key (no `@`) is for a package that
  states no version: `unknown`, `NOASSERTION` or blank. A placeholder is
  not a claim, so it must not be turned into a version that then equals
  another package's. And a bare key never matches a versioned one: no
  fallback and no table scan (the project rule that an alias must be a
  lookup of a few built candidates, never a scan). `requests` and
  `requests@2.31` are two entries.
- **One function builds every key.** `_element_key` rebuilds a package key
  from what it states (`split_package_key`), so a stored `PyYAML@6.0`, a
  typed `-e` key and a looked-up `pyyaml@6` reach one entry, and
  normalising twice changes nothing (a fixed point). The lookup records
  the key it used; harvest, `id import` and a merged fragment derive the
  key from the element's name and `software_packageVersion`
  (`_ambiguous._element_key_of`); a drift test holds the two equal.
  Do: one builder, and a test that compares the key a lookup wrote with
  the key an element implies.

## 4. A second defect found while fixing: resolving twice

- The dependency versions were resolved in two places, once to look ids up
  and once to build the packages. With a registry in use that doubled the
  conflict `WARNING:` lines (a pin the lock file contradicts; a locked
  version outside its range) and let the two identity rules drift.
  `document.build` now resolves and groups once
  (`assemble/spdx3/_dep_groups.group_dependencies`); the lookups and the
  packages share the result (commits 21ff2d0b, 04135973). Two versions of
  one dependency in one document are two keys now, no longer an
  "ambiguous name".
- A test of two spellings of one unparsable version (NFC and NFD) pins the
  shared-key path: they are two packages with one NFC key; the pin goes to
  the first, the second gets the claim `WARNING:` (9210cc42).

## 5. No migration

- **D2: a version 3 registry is an `ERROR:`, never rewritten.** The file
  format is 4; a v3 file fails with the same message a v2 one does
  (`ID registry file <path>: version 3, expected 4 (no migration support
  -- delete it and re-run ...)`), and the file is left as it is.
- **Rejected:** load a v3 file and drop its package entries with one
  `INFO:`. It is a silent loss of pins and keeps a second load path
  (`id-registry-v3.md`, D10). The project is a one-developer
  alpha with "no backward compatibility needed yet".
- **Consequences handled in the same PR:** the wording of the version error
  tells the user to run `loom id generate` or `loom id import`; tests that
  hard-coded the version changed (the plan's chore list); the demo registry
  (`examples/sentimentdemo-aibom/loom-id-registry.json`) was regenerated
  by the pipeline script, twice (the steady state), with ids unchanged,
  and the example's Pitloom floor moved to 0.22.0 (7c17b000). The planning
  report estimated the no-migration chores at about 1.5 to 2 days and the
  whole change at 2 to 3 agent days (*estimates*, not measured).
- **Accepted cost (D3).** A `project` run of a project whose version is
  dynamic states `unknown` and keys its own package bare; a wheel or hook
  run states the real version, so one project has two package ids across
  those routes. The alternative (reading the version at `project` time)
  was not tried. Documented in `docs/id-registry-keys.md`.

## 6. Remote entries: a second finding, a second PR

While designing the key, the same question was asked of things that live
elsewhere (a Hugging Face model, a URL dataset, a Git source). The
findings are in the planning report (session scratch; the plan is also in
the branch's known-bugs entries):

- A model given to `loom model` as a Hub id never reaches the registry (the
  registry option is inert and warns).
- `id import` keys a Hub model by the last segment of its repository id.
  A `loom.Run` looks it up as `org-a/llama`, so import and run disagree.
- `loom.use_model` and the `add_*_dataset` calls key remote things by bare
  name and never pin a revision: one id for every revision.
- **Two repositories, `org-a/llama` and `org-b/llama`, at one commit get
  identical `spdxId`s, with no registry at all.** This is the name-collision
  bug of section 2 of
  [name-keyed-lookups-and-direct-references.md](name-keyed-lookups-and-direct-references.md),
  not a registry one: the id is derived from the last segment.
- A Git source's commit and repository URL are not used.

The recommendations (D7a to D7h of the report; the maintainer's rulings of
2026-10-30 chose "a second PR"):

- a remote-shaped key with the revision (`huggingface.co/<id>@<sha40>`, or
  the sanitised https URL), entry fields `remote` (true only) and `iri`
  (https, no user information, query or fragment, at most 2048 characters,
  no control characters), and no `sha256` with a remote entry, because no
  bytes were read;
- an unpinned remote thing keeps the bare key and one `INFO:`, and never
  aliases a pinned key (the same rule as a bare package key);
- `loom model <hub id>` stays registry-free; `revision=` is added to
  `loom.use_model` and the `add_*_dataset` calls;
- Git sources wait until a `pkg:git` identifier exists;
- **Why a second PR:** it is its own decision set and about a day's work
  (size M in known-bugs), and it must ship in the same release as #407 or
  the registry format would need a v5 later. A flag alone cannot tell a
  Hub id from a local directory of the same name, which is why the key
  has a shape of its own.
- **Not offline-pinnable.** A remote revision is learned from the network;
  how to pin it for an offline or reproducible run is open (below).

## 7. What generalises

- List what makes two instances different things (version, revision,
  platform, repository) and put each in the key, or record why not. The
  same sentence is the new item in `recurring-bug-patterns.md` on the
  #407 branch.
- A stable-id feature needs a test that a changed input changes the id,
  not only that an unchanged one keeps it: the first test of #407's
  matrix is a package at versions 1.0, 2.0 and 1.0 again (the planning
  report's 18-row test matrix).
- A generator that offers stable ids across releases owes its users an
  answer to "do two releases ever share an element?". #407 answers for
  packages: no. Whether it should be possible to ask for the other
  answer (one element, several versions) is open.

## 8. Open

- Does keying by release make a *union* of SBOM graphs across releases
  sound: two releases of a library now have two ids, so a consumer that
  merges graphs by id never conflates them, but also never learns they
  are releases of one thing. What relationship says it (SPDX has none
  Pitloom writes) is not decided.
- How is a remote revision pinned offline? A Hub revision (`sha`) is
  fetched from the network; a registry that must work offline can hold
  the pin only after one online run.
- The `unknown` bare key of the `project` route (D3): can the project route
  recover the version a build would state?
