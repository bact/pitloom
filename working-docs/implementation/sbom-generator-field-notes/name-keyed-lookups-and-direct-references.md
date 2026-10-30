---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: a name-keyed lookup returned data for another package

See also: [README.md](README.md) (index of these notes),
[identity-and-archives.md](identity-and-archives.md) ("A URL requirement
never yields a version"; "An explicit pin beats the generator's own
environment"),
[evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md)
(why a skipped read may need a record),
[remote-metadata.md](remote-metadata.md) (what PyPI-style sources contain),
[known-bugs.md](../../design/known-bugs.md) (the entries cited below),
[open-research-questions.md](open-research-questions.md).

A dependency written `foo @ git+https://...` took its licence, supplier and
hash from whatever PyPI project is called `foo`. Work of 2026-10-30: #405
(merged), on the 0.22.0 list of serious bugs ("Serious known bugs for
0.22.0" in [message-catalogue-migration-plan.md](../../design/message-catalogue-migration-plan.md),
decided in #398). Commits 287930f5, 97441278, 3c7259f8, 980a16dc.

## 1. What happened

- **PyPI knows a package by name alone.** The dependency lookup
  (licence, supplier, release hash) asked the index for the name in the
  requirement. A PEP 508 direct reference (`name @ URL`) names the package
  by where it lives; the name is a label, and the index's project of the
  same name may be another project. Whatever PyPI returned for that name
  was written into the dependency's package, and the lookup also cost a
  network request nobody asked for (commit 97441278; known-bugs,
  "A direct-URL dependency is looked up on PyPI by name").
- **It was a wrong claim, not a missing one.** A wrong licence on a
  package is worse than none: a consumer checking licences trusts it. The
  regression test serves a fake PyPI record whose every fact carries the
  looked-up name (`LicenseRef-pypi-<name>`, `pypi-author-<name>`, a hash
  of the name), so a leak into the output cannot be mistaken for a real
  value (`tests/test_direct_reference_surfaces.py`, 228 lines).
- **It reached every route.** The test covers `loom generate`, the
  library's `generate_project_sbom()`, the Hatchling hook, a requirements
  file a setuptools directive lists, and a project whose `pylock.toml`
  locks the dependency to a VCS source. A registry dependency beside it is
  still looked up (the same test).

## 2. The class: identity by name where the ecosystem has other sources

- A name is an identity only inside one namespace. In Python packaging
  the namespaces that are not "the public index" are: a direct reference
  (an archive, a Git repository, a `file:` path), a VCS or path source in
  a lock file, a private or extra index (`[tool.uv.sources]`,
  `--index-url`), and an environment listing that does not say where a
  package came from. Each one makes "ask the index for this name" return
  data for a different thing, silently.
- Other notes in this set are the same bug at other layers: the ID
  registry keyed a package by name alone
  ([registry-key-must-carry-the-release.md](registry-key-must-carry-the-release.md))
  and a Hub model by the last segment of its repository id.
  Do: for every key or lookup that uses a name, list the sources of
  packages that have a name but not that namespace, and decide each.

## 3. The fix, and what it chose not to do

- **One predicate, no logging.** `pitloom.core.pep508.is_direct_reference()`
  reads the requirement with `packaging` and answers whether it has a URL.
  When `packaging` cannot parse the text, it falls back to a prefix rule
  (`name [extras] @ URL`), so unparsable text that starts as a direct
  reference is still kept off the index. The caller's own parse warns of a
  refusal; the predicate says nothing, so one bad requirement is not
  reported twice. Ten parametrised cases: a pin, an `@` inside a marker
  (`A_b.C>=1 ; os_name == 'x @ y'`, not direct), a Git URL, extras plus a
  `;` in the URL, a Windows `file:` URL and a Windows path, an unparsable
  `a @ https://h/x @ y`, and a 900-deep marker after a URL (all direct).
  Do: a safety predicate answers for text its parser refuses, on the safe
  side, and tests the marker-contains-`@` case in both directions.
- **Three places, one predicate.** The prefetch in
  `_document_locked_deps.py`, the prefetch in `deps.add_dependencies` and
  the enrichment step (`_finish_dependency_enrichment(pypi=...)`). A
  package is kept off the index if *any* declared string of it (the
  strings grouped under one canonical name) names a URL
  (`pypi=not any(map(is_direct_reference, declared_constraints))`): a
  name that is a URL in one string and a pin in another is still the
  URL's package.
- **The package stays in the SBOM.** It is listed with its declared
  constraint; licence, supplier and hash come from its installed copy if
  there is one, else stay unset (`docs/dependency-sources.md`). Rejected
  implicitly: dropping the dependency, which would hide a real component.
- **What was left, on purpose, as open entries** (known-bugs, 2026-10-30):
  1. a `loom env` package installed from a URL is still looked up, because
     pipdeptree's JSON has no `direct_url.json`, so the install source is
     not visible; a private-index dependency is read as a PyPI name;
  2. a direct reference can still take its version and installed metadata
     from Pitloom's *own* environment by name, and keeps a `pkg:pypi`
     PURL. This is the mirror of the "explicit pin beats the local
     environment" rule: the declared source says "a URL", and the
     generator's environment answers by name anyway.
  Each is the same class of bug on a route #405 did not reach; recording
  them as separate entries kept the fix to the lookup the user could see
  (the wrong licence), and kept the open ones searchable.

## 4. Why the skip is silent

- The project rule is that absent source data is quiet: a field the source
  lacks stays unset with no `WARNING:`. The skipped lookup contradicts no
  instruction of the user; it removes a request that should not have been
  made. #405 therefore logs nothing.
- The known-bugs entry says the skip "is also silent" and that a coded
  `INFO:` ("direct reference, not looked up on PyPI") waits for a
  catalogue family PR. The ratchet that keeps new uncoded messages out
  while the catalogue is migrated is the likely reason a new free-text
  line was not added now (*inference*; the entry gives only "waits for a
  catalogue family").
- The cost of silence: from the SBOM alone, "no licence because the
  lookup was skipped" and "the index had no licence" look the same. That
  is the question the evidence notes ask for a fact not read
  ([evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md)):
  a skipped source is `refused` there, and a `refused` source is written.
  Whether a direct reference's absence deserves a `Reason:` is open.

## 5. What generalises

- Any generator that fills a component from a registry by name has the
  same exposure wherever its ecosystem allows a dependency from a Git
  URL, a local path or a second registry. *Unverified here:* that npm
  (`git+` and `file:` specifiers), Cargo (`git`, `path`, alternative
  registries) and Go (`replace`) have the same shape; Pitloom measured
  only Python.
- Test the predicate with a fake index that returns facts naming the
  query. A leak is then unmistakable, with no real project's data.
- A fix to one route needs the others listed. #405 found the five above
  by the surfaces test, not by reading the code.

## 6. Open

- Does a skipped lookup need a recorded reason, and in which property?
  (See section 4.)
- How should a generator learn the source of an installed package?
  `direct_url.json` (PEP 610) exists in an installed distribution's
  `.dist-info`; pipdeptree does not pass it on. Whether reading it
  directly is better than adding a pipdeptree option was not measured.
- Mutation testing: seven mutants of the fix were prepared in session
  scratch (the predicate's two returns, each of the three call sites);
  their results were not preserved in the repository, so the kill rate is
  *unverified*.
