---
Created: 2026-10-02
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: determinism and parsing

See also: [README.md](README.md) (index of these notes),
[sort-order-canonicalization.md](../sort-order-canonicalization.md),
[iri-name-encoding.md](../iri-name-encoding.md),
[lock-file-cascade.md](../lock-file-cascade.md),
[lock-hash-preservation.md](../lock-hash-preservation.md),
[deployed-env-pipdeptree.md](../deployed-env-pipdeptree.md),
[ai-model-scan-security-lessons.md](../ai-model-scan-security-lessons.md)
section 3.6 (determinism of model metadata).

## 1. Same input, same bytes

- **A document UUID can be content-derived.** Pitloom's is UUIDv5 over a
  NUL-joined seed: name, version, the sorted normalised dependencies, then
  the locked dependencies and the string naming their source
  (`Source: pylock.toml | Method: resolved_lockfile`), then the files'
  Merkle root. The source string matters: a `poetry.lock`-only run and a
  `pylock.toml`-only run resolving to the same pins otherwise share one
  UUID. A real lock resolving to zero dependencies still folds its source
  in, or it collides with "no lock at all"
  ([lock-file-cascade.md](../lock-file-cascade.md)).
  Do: seed on everything that changes the content, including provenance.
- **`SOURCE_DATE_EPOCH` is the middle of a cascade, not the top.**
  Pitloom resolves `created` as explicit `--creation-datetime` (or its
  config key) > `SOURCE_DATE_EPOCH` > current UTC. An unparseable value is
  ignored with `WARNING: Ignoring invalid SOURCE_DATE_EPOCH: ...`. The
  enrichment fragment's `created` used the wall clock until #231 (#148, #231).
  Do: route every timestamp through one resolver; give the explicit value
  the last word.
- **Datetimes: UTC, whole seconds, a literal `Z`.** SPDX 3 `DateTime` is
  `YYYY-MM-DDThh:mm:ssZ`. Python 3.10's `datetime.fromisoformat()` rejects
  `2026-01-01T00:00:00Z` (`Invalid isoformat string`; 3.11 accepts it), so
  a pinned `Z` value failed the Hatchling build on 3.10 only. Pitloom
  maps a trailing `Z` to `+00:00`, reads a naive value as UTC, converts
  offsets, and drops microseconds (#232).
  Do: parse with your own wrapper and test on the oldest supported
  runtime.
- **Canonical JSON orders keys, not arrays.** RFC 8785 (JCS) sorts object
  members; array order is the producer's. Every array that reaches the
  output (annotation `statement`s, file summaries, the fragment-merge
  winner key) needs its own explicit sort, commented as canonical at the
  call site. The non-default `--pretty` output uses
  `json.dumps(indent=2, sort_keys=True, ensure_ascii=False)`
  ([sort-order-canonicalization.md](../sort-order-canonicalization.md)).
  Do: grep every `sorted()` on the output path and label it canonical or
  bookkeeping.
- **Line endings are part of the bytes.** Python's text mode writes CRLF
  on Windows. SBOM, fragment and registry files are now opened with
  `newline="\n"` and UTF-8 in one helper (#232).
  Do: open every output file through one writer that fixes encoding and
  newline.
- **Order from an external tool is not a contract.** pipdeptree happens to
  sort by `key` but does not document it, and `Package-N` numbering, the
  first registry claimant and relationship order all follow input order.
  The extractor sorts packages by `(key, version, name)` and each
  dependency list by `key`; on real output it changes no bytes (#236).
  Do: sort at your boundary even when the input already looks sorted.
- **A tie-break on URLs sorts by the wrong thing.** For several hashes of
  one package Pitloom prefers a wheel, then the file name, then the
  digest. Sorting raw `uv.lock`/`pylock.toml` URLs sorts by PyPI's
  content-addressed directories instead
  (`.../packages/32/34/d4e1.../alabaster-0.7.16-py3-none-any.whl`), an
  order nobody promises. Reduce a URL to its basename first; a pathless
  URL gives `None`, not the host name. `Pipfile.lock` lists bare digests
  with no file names, so its pick is arbitrary by construction, though
  stable (#212).
  Do: tie-break on the domain key (file name), never on a container of it.
- **A temporary path must not reach the output.** A file discovered by a
  real build (`--allow-build`) has an absolute `physical_path` in a fresh
  temporary directory; joined onto the project or used as a key, it made
  every run differ. The same inline `is_absolute()` check recurred in three
  consumers before one helper, `project_relative_or_fallback()`, replaced
  them (#215).
  Do: map every temporary path to a stable name in one helper.
- **A name inside an IRI must be encoded, losslessly.** A Safetensors
  `modelspec.title` of `Stable Diffusion XL` gave `AIPackage-Stable
  Diffusion XL`, which fails SHACL (`sh:nodeKind sh:IRI`). Pitloom
  percent-encodes what is not RFC 3987 `ipchar`, plus `%` itself
  (`a%20b` becomes `a%2520b`), so two names never share an id; a slug
  (`a b` to `a-b`) would merge `a b` with `a-b`. Bidi controls U+200E,
  U+200F and U+202A-U+202E are encoded (RFC 3987 4.1); plane 14's
  `ucschar` starts at U+E1000. Valid names, every PEP 503 name included,
  are byte-identical to before. The element `name` keeps the source text
  (#253).
  Do: keep display names faithful and derive identifiers by one injective
  rule.
- **Hash-map order from a library changes per process.** The Safetensors
  metadata map came back in a different order every call; see the
  lessons doc, 3.6, for the cap that picked a different subset each run.
  Do: survey each reader's source order: file order is stable, hash-map
  order is not.

## 2. Parsing traps

- **`json.loads(bytes)` strips a UTF-8 BOM; `json.loads(str)` does not.**
  `json.loads(b'\xef\xbb\xbf{"a":1}')` returns `{'a': 1}`; the same bytes
  decoded with `"utf-8"` raise `JSONDecodeError: Unexpected UTF-8 BOM`.
  The SPDX 3 deserialiser reads a binary handle, so a BOM-prefixed
  fragment merged in a build and was rejected by `loom fragment list`.
  The bug shipped twice in one PR, in two files (#217).
  Do: parse JSON from bytes wherever another path parses a binary handle.
- **A format parser can still raise the encoding error.** `tomllib`,
  `json` and `open(..., encoding="utf-8")` raise a bare
  `UnicodeDecodeError` for invalid bytes, separate from `TOMLDecodeError`
  or `JSONDecodeError`. A "degrade on bad input" helper that catches only
  the format error crashes on a Latin-1 file
  ([recurring-bug-patterns.md](../recurring-bug-patterns.md)).
  Do: catch the encoding error next to the format error.
- **Deep JSON nesting fails differently on 3.14.** `json.loads("[" *
  100_000)` raises `RecursionError` on 3.10-3.13; 3.14's decoder checks
  the real stack instead, reads all 100 000 levels and fails with a plain
  `JSONDecodeError` ("Expecting value"). It still raises `RecursionError`
  at 1 000 000 on the default main-thread stack. `RecursionError` is not
  a `ValueError`, so a parser that catches only the decode error crashes
  on 3.10-3.13; a test pinned to "nested too deeply" (Pitloom's own
  message) fails on 3.14 only (#270).
  Do: catch `RecursionError` beside the decode error; build a deep-nesting
  fixture that raises on every supported version.
- **A one-line trim regex can be quadratic; `str.strip` is not.** To
  drop final line breaks from a licence text, Pitloom used
  `\A[ \t\r\n]+|(?:\r\n|\n|\r)+\Z`. On text with a long run of line
  breaks *in the middle*, the `\Z` branch is tried at every position of
  the run and fails at its end each time: 10 000 breaks took 0.74 s,
  20 000 took 2.96 s, 40 000 took 12.1 s (CPython 3.10, `re.sub`). A
  crafted wheel stalled SBOM generation for seconds. The same result from
  `s.lstrip(" \t\r\n").rstrip("\r\n")` took about 2 µs at every size
  (#276 final review).
  Do: trim, split and prefix-test with `str` methods; use a regex only
  when the pattern needs one, and then time it on adversarial input.
- **`dict.get(key, default)` guards absence, not type.**
  `data.get("@graph", [])` on `{"@graph": 5}` returns `5`, and `len(5)`
  crashed a whole multi-file listing instead of marking one record bad
  (#217).
  Do: `isinstance`-check every value read from a file a user can edit.
- **`setup.cfg` is interpolated: `%` is syntax.** `description = 50%
  faster` makes `configparser.ConfigParser` raise
  `InterpolationSyntaxError: '%' must be followed by '%' or '('`.
  Checked 2026-10-02: setuptools 84.0.0's own `setup.py --description`
  fails the same way, and `loom project` gives one
  `ERROR: SBOM generation failed: ...`, exit 1. The author must write
  `%%`. A bad `%` in an sdist's `[tool:pitloom]` is one `ValueError`
  naming the archive member (#232).
  Do: read an INI file with the interpolation its own tool uses, and
  document the escape.
- **`configparser`'s `[DEFAULT]` makes every section declare its keys.**
  `key in cfg[section]` and `cfg.items(section)` merge `[DEFAULT]` in, so
  a shared default looks like an explicit, possibly empty, per-section
  declaration. Pitloom reads the section's own keys from `cfg._sections`,
  the only place without the merge
  ([recurring-bug-patterns.md](../recurring-bug-patterns.md)).
  Do: separate "what is the value" from "was it declared here".
- **`None` and `[]` are different answers.** In a source cascade `None`
  means "does not apply, try the next"; `[]` means "authoritative, zero
  results, stop". A lock that resolves to no runtime dependencies wins
  over a lower-ranked file that lists some. The same rule broke provenance
  in five metadata producers in one PR: `if parsed_value:` dropped the
  provenance of an explicit `dependencies = []`
  ([lock-file-cascade.md](../lock-file-cascade.md),
  [recurring-bug-patterns.md](../recurring-bug-patterns.md)).
  Do: gate "was it declared" on the raw key's presence, never on the
  resolved value's truthiness.
- **An empty result needs proof that the file is the format.** An empty
  package list from an unrelated or truncated file under a lock-file name
  would win the cascade. Each format's own marker is checked first:
  `poetry.lock` string `metadata.lock-version`, `pdm.lock` string
  `metadata.lock_version`, `Pipfile.lock` integer `_meta.pipfile-spec`,
  `uv.lock` flat integer `version`. `uv.lock` was missed after three
  siblings had the check
  ([recurring-bug-patterns.md](../recurring-bug-patterns.md)).
  Do: add a new source with every guard its siblings already have.
- **A presence-only key set can hide one boolean.** In `Pipfile.lock`,
  `git` (and `hg`, `bzr`, `svn`), `path` and `file` mean "not from a
  registry" by presence, but
  `"editable": false` is schema-legal and means "not editable"; a
  presence check reads it as an editable source and drops the package
  ([recurring-bug-patterns.md](../recurring-bug-patterns.md)).
  Do: check each key's schema before reusing a presence-only helper.
- **One lock format, two hash layouts.** In this repository's real
  fixtures, `poetry.lock` lock-version 1.1 (`pastel-0.2.1`) keeps hashes
  in one top-level `[metadata.files]` table keyed by package name, while
  lock-versions 2.0 (`cleo-2.1.0`) and 2.1 (`pendulum-3.2.0`,
  `tomlkit-0.15.1`) put a `files` array on each `[[package]]`. `uv.lock`
  holds one `"sha256:<hex>"` string per artifact; `pylock.toml` a
  per-artifact table that may hold only `blake2b` (#212).
  Do: verify a format's layout against real files of each version, not
  against the spec alone.
- **Poetry's constraints are not PEP 440.** `^1.2.3` is `>=1.2.3,<2.0.0`
  but `^0.2.3` is `>=0.2.3,<0.3.0`; `~1.2.3` is `>=1.2.3,<1.3.0`; a bare
  `1.2.3` is `==1.2.3`; `*` is no constraint. `python = "*"` is an
  explicit "no constraint", not an absent one
  ([poetry-support.md](../poetry-support.md)).
  Do: convert to PEP 440 at the boundary, keeping "explicitly
  unconstrained" distinct from "not declared".
- **One tool, two JSON shapes.** `pipdeptree --json` is a flat list of
  `{"package": {...}, "dependencies": [...]}`; `--json-tree` nests
  `{key, package_name, installed_version, dependencies}`. The extractor ran
  one and the assembler read the other, so every package became `unknown`
  with no `dependsOn`; the tests stubbed the shape by hand and never saw it.
  The output is now validated at the boundary (one `ERROR:` on a wrong
  shape), parsed as bytes (BOM accepted), and an empty list is a valid
  empty environment (#236).
  Do: test against captured real output of the exact command line.
- **A private API returns today's shape only.** `packaging` 26.3's
  `Marker('A or B and C')._markers` is the flat list
  `[A, 'or', B, 'and', C]`: precedence is not pre-grouped, so a fold over
  it must rebuild `and`-before-`or` itself
  ([recurring-bug-patterns.md](../recurring-bug-patterns.md)).
  Do: inspect a private structure live and mirror the library's public
  algorithm.
- **A pinned `requirements.txt` is not a lock file, and says so.** Every
  lock source is tagged `Method: resolved_lockfile` except
  `requirements.txt`, tagged `pinned_requirements` and used only when
  every line is an exact `==` pin: no resolver produced it and no hashes
  are guaranteed. It ranks last of six: `pylock.toml`, `uv.lock`,
  `poetry.lock`, `pdm.lock`, `Pipfile.lock`, `requirements.txt` (#208,
  #211, #212).
  Do: record how a dependency list was obtained, not only where from.
- **`METADATA` headers need a count cap as well as a byte cap.** A 28 KB
  wheel inflated to 16 MiB of short headers parsed to 2.4 million of them;
  see the lessons doc, 3.8 (#266).
  Do: stop at the first blank line and cap both bytes and header count.
