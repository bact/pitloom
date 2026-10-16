---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata provenance: authors

See also: [Metadata provenance](metadata-provenance.md) for the
provenance annotations and the `method` values, and the other parts:
[Preserved artefact metadata](metadata-provenance-artifact-metadata.md),
[Licences and copyright](metadata-provenance-licences.md).

## How authors are read

Every `[project].authors` entry, in declared order, is an `originatedBy`
Agent of the main package, on every route but `loom env`; maintainers are
not. An author, or a dependency's originator, is a `Person`, or an
`Organization` when its name holds the whole word `others` or `et al`
(`and others (see AUTHORS)`; `Jan Brothers` is a person). There is one
Agent per type, name and email, shared with an SBOM creator or another
package: a `Person` and an `Organization` of the same name are different
agents. A dependency's originator is its `Author` and `Author-email`, or,
only when neither is stated (absent, blank or `UNKNOWN`), its `Maintainer`
and `Maintainer-email`: an author that is stated but not read is no reason
to credit the maintainer. The authors never make the copyright text (see
[How the copyright text
is found](metadata-provenance-licences.md#how-the-copyright-text-is-found)).

A structured entry is one author, never split: a `[project].authors` table,
a Poetry `authors` string, a quoted display name (one mailbox, RFC 5322:
`"Ann, Bob" <team@example.com>` is one author named `Ann, Bob`;
typographic quotes, `“Ann, Bob”`, hold a name together too). A name field
is one author too, on every route, unless it holds several complete
mailboxes: core-metadata `Author` (a wheel's `METADATA`, an sdist's
`PKG-INFO`, a dependency's `Author` or `Maintainer`), `setup.cfg` `author`
and `setup.py` `author=`. Backends write a name-only author there as
declared (`{name = "Doe, Jane"}` is `Author: Doe, Jane`), so `Doe, Jane`,
`Jane, Bob` and `Ann and Bob` are one author each. The limit: a free-text
list of names in one `Author` is one author as well (`setup.py`
`author="Jane, Bob"`, or Hatchling's two name-only authors joined, `Doe,
Jane, Ann and others`, which is one `Organization`). So a project's own
name field read as one author (a wheel's `Author`, an sdist's `PKG-INFO`
whose `pyproject.toml` declares no authors, `setup.cfg`/`setup.py`
`author`) gets one `INFO:` per SBOM when it holds `,`, `;` or the word
`and` outside quotes and `<...>` (`AUTHOR='Ann, Bob': read as one author;
it may list several ...`), unless its address is not recorded; a
dependency's, a structured entry and `Author-email` get none. A name field
is cut only where the text proves a list, next to an address: on `,` or
`;` (outside quotes and `<...>`) after a closed `<address>` or a bare
address, or before a bare address (which carries no name); and between
two closed `<address>` entries, a joining `and` or `&` left out. Never
between two names. So `Ann <a@x.org>; Bob <b@x.org>` and `Ann <a@x.org>
and Bob <b@x.org>` are Ann and Bob with their addresses, `a@x.org,
b@x.org` two authors, and `Doe, a@x.org` `Doe` and the address, as in
`Author-email`; `Doe, Jane <j@x.org>` is one mailbox, its name all the
text before the `<` (`<` or `>` inside a quoted name is part of the name);
`Doe, Jane <j@x.org>, Bob Lee <b@x.org>` is two; `Ann <a@x.org>, Bob` is
Ann with the address and `Bob`. A cut gets one `WARNING:`
(`AUTHOR='Ann <a@x.org>; Bob <b@x.org>': split into 2 entries next to an
address; a name field is never cut between names`). An entry with text after its address, other than a trailing
`(comment)` or a contributor group, records its name alone (`Ann <a@x.org>
Lee` is `Ann`), and one whose address is not closed before the next
records no one (`Ann <a@x.org, Bob <b@x.org>`); either gets a `WARNING:`
(see below).
A name, in any field or table, has each run of white space read as one
space: a folded `Author` (`Ann` and `Lee` on two lines) is `Ann Lee`, as
`setup.cfg` and `[project].authors` give it.

An address field is a list: core-metadata `Author-email`, `setup.cfg`
`author_email`, `setup.py` `author_email=` and a dependency's
`Author-email` or `Maintainer-email`. It is split on `,` and `;` outside
quotes and `<...>`, never on `and`: `Ann and Bob <t@x.org>`, as backends
write `{name = "Ann and Bob", email = "t@x.org"}`, is one author on every
route. An entry with no `<`, `>` or `@` is a name (`john at example dot
com` is a `Person` of that name, with no warning), so `Author-email: Doe,
Jane <j@x.org>` is `Doe`, and `Jane` with the address: the field cannot
tell a list from one unquoted name containing a comma, and a split after
a name gets one `WARNING:` per SBOM (`AUTHOR_EMAIL='Doe, Jane <j@x.org>':
split into 2 entries on ',' / ';'`; one line for all dependencies, naming
the first and the count). A split right after an address is not warned
about, and a contributor group after an address is an entry of its own,
in either field (`Jane <j@x.org> et al.` is `Jane` with the address, and
`et al.`). A
name and addresses are never paired by position, as a reordered or
partial field would pair them wrongly: `Author: Jane, Bob` with
`Author-email: a@x.org, b@x.org` is three authors; only one name beside
one bare address is one author. A free-text field is read up to 65,536
characters and 1,000 entries; past either, the rest is not read, nor the
entry the character cap cuts (an `Author` holding no address, one entry,
not at all), with one
`WARNING:` when the authors read are used (not for `PKG-INFO` authors an
sdist's `pyproject.toml` replaces). The core metadata specification's
`Author` example, `C. Schultz, Universal Features Syndicate, Los Angeles,
CA <cschultz@peanuts.example.com>`, reads as one author with the address,
the affiliation in the name. An address is checked as written
(`a@b c` is not `a@bc`), a comma inside `<...>` included: an address of
the project's own (an entry holding `<`, `>` or `@`) that is no address
is not recorded, with one `WARNING:`
per field naming the first three and how many (`AUTHOR_EMAIL=['a', 'b',
'c', ...]: not an email address; 5 entries not recorded`), and a name
stated before its one `<` is kept (`Ann <a@b c>` is `Ann`). The `UNKNOWN`
older setuptools writes is no author: in `setup.py` it gives way to
`setup.cfg`'s author. An sdist's `pyproject.toml` gives the declared authors as a
directory's does (`[project].authors`, else `[tool.poetry].authors`); one
that cannot be read leaves the `PKG-INFO` authors, with a `WARNING:`, as `embed-wheel
--project-dir` does. How a wheel's `METADATA` reorders authors:
[What an SBOM lists](wheel-sbom.md#what-an-sbom-lists).
