---
Created: 2026-09-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom known limitations: detail

See also: `../SKILL.md` ("Known limitations", which holds the rule for
each case: say so plainly, do not paper over it).

Pitloom's dependency/supplier/licence extraction is Python-packaging-native:
it reads `pyproject.toml`/`setup.cfg`/`setup.py`, installed
`importlib.metadata`, and the PyPI JSON API. Outside that world, coverage
drops.

## No Python packaging markers

Typical files: `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`/
`build.gradle`, `Gemfile`, `composer.json`, a `.csproj`/`.sln`. The
refusing `ERROR:` names `pyproject.toml`, `setup.cfg` and `setup.py`.

## Mixed-ecosystem repos

The SBOM inventories `[project.dependencies]`, the project's extras and what
is importable; every non-Python dependency leaves no element, no error and no
placeholder. Look for non-Python ecosystem files beside `pyproject.toml`.

## Non-PyPI dependencies

`git+https://...`, a local path requirement or a private-index-only
package: unless it is installed locally (its installed metadata is read),
supplier/licence/hash enrichment has nothing to look up, so the copyright
lands on `NOASSERTION`, supplier and hash stay empty, and the package gets
no licence relationship -- Pitloom never asserts a licence it was not told
(a source that itself says `UNKNOWN`/`NOASSERTION` gives the
`NoAssertionLicense` individual).

## Extras, edge kinds and authors

- **Extras** (`[project.optional-dependencies]`, Poetry extras, setuptools
  `extras_require`, `[tool.setuptools.dynamic]` or `setup.cfg` `file:`
  requirements files) are
  listed on every route except `loom env`. PEP 735 dependency-groups,
  Poetry `group.*` and PDM `dev-dependencies` are not (a wheel has no
  equivalent).
- A required or locked dependency is `dependsOn` with lifecycle scope
  `runtime`; one only under extras is `hasOptionalDependency`, **no** scope,
  comment `extras: a, b`, even when a lock resolved it. Never read a
  lifecycle from an extra's name (`dev`, `test`): say it is optional,
  nothing more. `loom env` edges are plain `dependsOn`.
- Every `[project].authors` entry is `originatedBy` of the main package;
  maintainers are not. The authors never make the copyright text: it is the
  notice lines found in the project's own `LICENSE`/`COPYING` files, else
  `NOASSERTION`. A name field (`Author`, `setup.cfg`/`setup.py` `author`)
  is one author: `Jane, Bob` or `Ann and Bob` there is one author
  (backends write a name-only author so; a free-text list of names is one
  author too: for the project's own, holding `,`, `;` or `and`, one `INFO:
  AUTHOR=...: read as one author; it may list several`). It is cut only
  next to an address (after a closed `<address>` or a bare address, before
  a bare address, between two `<address>` entries), with a `WARNING:`:
  `Ann <a@x.org>; Bob <b@x.org>` and `Ann <a@x.org> and Bob <b@x.org>` are
  two authors, `Doe, Jane <j@x.org>` one. An address field (`Author-email`, `author_email`)
  is split on `,` and `;`, never `and` (`Ann and Bob <t@x.org>` is one
  author), with a `WARNING:`; a name and addresses are never paired by position
  (`Jane, Bob` plus two addresses is three authors). A bare wheel's
  `METADATA` loses the declared order and poetry-core writes only the
  first author; `embed-wheel --project-dir` and an sdist with
  `pyproject.toml` keep it.
- Detail: <https://bact.github.io/pitloom/dependency-sources/#extras-and-the-optional-edge>
  <https://bact.github.io/pitloom/metadata-provenance-authors/#how-authors-are-read>
  and <https://bact.github.io/pitloom/metadata-provenance-licences/#how-the-copyright-text-is-found>.

## AI model formats

Formats, suffixes and header checks:
<https://bact.github.io/pitloom/ai-model-formats/>; what counts as a model:
<https://bact.github.io/pitloom/ai-model-scan-limits/#what-is-a-model>. A
`.bin` or `.model` file without a format's magic, and a Python
path-configuration `.pth`, are silently not models (other tools use those
suffixes).

A **stub** is an `ai_AIPackage` with no `ai_*` property and no `comment`
entry `Source: <model file> | Field: ...`; its `name` is the file's stem
(`Method: file_name_stem`). A `comment` citing the README (`--enrich`,
`Method: yaml_frontmatter`) does not make it read. The stderr line says why:

- `INFO: AI models in a wheel in these formats are listed without metadata
  ...: onnx. Pass --trust-wheel-model ...` -- the wheel gate (fastText, GGUF,
  HDF5, ONNX, PyTorch `.pt`/`.pth`); tell the user, never add the flag.
- `WARNING: FORMAT=<fmt> FILE=<path>: required library not installed; ...` --
  install `pitloom[ai]` and regenerate.
- `... failed to extract metadata; ...` -- the file has a model's header but
  could not be parsed (truncated or corrupt): check the file.
- `... max-model-extract-bytes cap; metadata not read` -- the ceiling (512
  MiB, wheel scans; `--max-model-extract-bytes BYTES` or the config key);
  `WARNING: ... model-scan budget cap; ...`
  -- the per-wheel budget (4x the ceiling, one line); any other `...; metadata
  not read` is a fixed bound. Lists past 1000 entries are cut with one
  `WARNING:`. Never raise a ceiling on your own.
- `... header is not <fmt>; not listed as an AI model` -- the file is no model
  and gets no `ai_AIPackage`.
- Catalogued messages end in a stable `[code]`; look the code up in the table
  below. Trust a code only when the line's text is one the row prints. A
  Git LFS pointer is a small placeholder file that stands in for the real
  content in a repository: Pitloom lists it by the SHA-256 the placeholder
  states (no SHA-512, no content type), never reads or downloads the content,
  and adds no `ai_AIPackage`. An `ERROR:` line may start with the command that
  failed (`model command failed:`). You explain and relay the advice; you
  do not run the fix.

<!-- BEGIN GENERATED: pitloom.messages -->
<!-- Generated by scripts/generate_message_reference.py; do not edit. -->
A line reads `LEVEL: text [code]`; `<name>` in a text stands for a value.

| Code | Level | Printed as | Meaning | What Pitloom did | What to tell the user |
| --- | --- | --- | --- | --- | --- |
| `lfs-pointer` | ERROR, WARNING | `FILE=<file>: Git LFS pointer, content not read<count>; run 'git lfs pull' for the content` or `FILE=<file>: Git LFS pointer, content not read<count>; clone with git lfs, then run on the directory` or `'<path>': header is a Git LFS pointer, content not pulled (oid sha256:<oid>, size <size>); run 'git lfs pull'` | A file is a Git LFS pointer: a small text file standing in for content the checkout does not have (made or cloned without Git LFS). | Listed each pointer file by the SHA-256 the pointer states for its content, with the stated size in the hash comment (no SHA-512, no content type); did not read the content or list it as an AI model. One warning names the first file in sorted order and, for more than one, how many. | Tell the user the SBOM still identifies each file by its content's SHA-256 but lacks what reading it gives (AI model details, SHA-512). If they want them, they run 'git lfs pull' in the checkout (for a Git URL: clone it with Git LFS and run Pitloom on that directory) and generate again. Do not pull, clone or regenerate for them; ask first, and with nobody to ask, report it only. |
| `lfs-pointer-malformed` | ERROR, WARNING | `FORMAT=<format> FILE=<file>: header looks like a Git LFS pointer but is not a valid one; not listed as an AI model` or `FILE=<file>: header looks like a Git LFS pointer but is not a valid one; not listed as an AI model` or `'<path>': header looks like a Git LFS pointer but is not a valid one` | A file starts with the Git LFS pointer line but is not a valid pointer: damaged, cut short, or 1 KiB or larger. | Listed it as an ordinary file, hashed as it is, not as an AI model. | Tell the user the file is neither its content nor a valid pointer: they check it out again or replace it with the real content, then generate again. Do not change the file for them. |
| `lfs-pointer/shipped` | WARNING | `FILE=<file>: Git LFS pointer shipped<count>; the build did not pull LFS content` | A built wheel or sdist holds Git LFS pointer files where the content belongs: it was built from a checkout without the LFS content. | Listed each file as the artefact holds it, with the hashes of the pointer text. | Tell the user the artefact is probably broken: whoever installs it gets pointer text, not the files. If the content belongs in it, they run 'git lfs pull' before building and build again, before publishing. Do not rebuild for them. |
<!-- END GENERATED -->

A model whose read fails is a stub, never dropped, with the same `WARNING:`
from a scan and from `loom model FILE` (exit 0). Beyond that:

- A file-named entry with other properties was read: NumPy, fastText,
  CRFsuite and classic PyTorch carry no model name, nor does an ONNX file
  whose `graph.name` is an exporter default.
- Producer and parameter count (`ai_AIPackage`): `originatedBy` holds one
  generic `Agent` (name only) per name a structured field states (ONNX
  `model_author`, split on commas, so `Doe, Jane` becomes two; PT2
  `extra/author`; GGUF `general.author`, `general.organization`; Safetensors
  `modelspec.author`; the Hub repository owner, `Method: repository_owner`).
  `suppliedBy` is set only on the Hub route, to the same repository owner
  (the distribution source); no model file format sets it, and a model never
  inherits the main package's. A GGUF `general.organization` is
  often guessed by the llama.cpp converter from the base model's
  `_name_or_path` (a fine-tune can name the base model's organisation):
  Pitloom reads it as stated, and the Hub route names the repository owner
  instead, so one model can show two producers by route. The count is the
  `ai_hyperparameter` entry `parameters`, a decimal integer, with a `comment`
  line saying it is not a hyperparameter (SPDX 3.0.1 has no model-size
  property): the sum of the elements of the tensors
  (`Method: tensor_element_sum`) for GGUF, Safetensors and ONNX, or the Hub's
  own sum (`safetensors.total`, else `gguf.total`, same method). It counts
  all stored tensors, so buffers (attention masks, shape constants) and tied
  weights stored twice are in it, and packed or quantised weights (GPTQ, AWQ,
  bitsandbytes, ONNX `MatMulNBits`) under-count: not the "trainable
  parameters" of a model-size figure, and a Hub total may cover only part of
  a multi-component repository. No count is normal for PT2, a GGUF split
  over files (`split.count` above 1) and an empty model (a split GGUF keeps
  its producer); neither value is read from PyTorch classic, Keras, HDF5,
  NumPy, fastText and CRFsuite; a Safetensors file
  with no `modelspec.author` has no producer; a Safetensors shard counts its
  own file only. In a wheel, a GGUF or ONNX model gets neither without
  `--trust-wheel-model` (the gate leaves it a stub); PT2 and Safetensors are
  read. Stderr, one `WARNING: FORMAT=<fmt> FILE=<path>:` line each: a
  hostile or malformed shape, or a count over 10^15, gives no count
  (`... parameter count not recorded`); an ONNX `model_author` is cut at
  1000 distinct names (`larger than the 1000-entry per-field cap; the first
  1000 kept in originators`) and read to at most 16016 non-empty parts,
  repeats included (`larger than the 16016-part model-author cap; rest of
  model_author not read`); a model's own
  `parameters` hyperparameter gives way to the count (`hyperparameter
  parameters replaced by the parameter count`). Detail:
  <https://bact.github.io/pitloom/ai-model-formats/#producer-and-parameter-count>
  and
  <https://bact.github.io/pitloom/ai-model-formats/#what-the-count-counts>.
- A name ending `...~` and 8 hex digits was cut at 1024 characters (code
  points), the digest of the whole name keeping two long names apart: the
  model's own name, or its file name stem, whichever is shown, and its
  base model, dataset and dataset creator names, and the model originator
  names. A base model's or dataset's registry key and `spdxId` use the same cut
  name (a model with a file is keyed by its path instead); a generic `Agent`
  (originator, supplier, dataset creator) has an id carrying its name,
  `Agent-<name>-1` (`--update-id-registry` records it by name, but nothing
  looks it up).
  `WARNING: FORMAT=<fmt> FILE=<path>: larger than the 1024-character name
  cap; model name cut` (or `base model name`, `dataset name`, `dataset
  creator name`, `model originator name`, the last one warning once per
  model however many names are cut).
- A `\udXXX` in a name or value was a lone surrogate in the file (a JSON
  or YAML `"\ud800"`), which UTF-8 cannot hold: `WARNING: FORMAT=<fmt>
  FILE=<path>: lone surrogates written as \uXXXX`.
- A CRFsuite or fastText model with no `labels` but a `num_labels` (or an
  `outputs` shape) had a label over 4 KiB: then none is recorded, and a
  CRFsuite model gets no generated description. `WARNING: FORMAT=<fmt>
  FILE=<path>: larger than the 4096-byte label cap; no label recorded`. A CRFsuite
  description shows at most 20 labels of 64 characters each, by design.
- `\u202e`, `\ufeff` and the like in a name, description, type,
  hyperparameter, `ai_informationAboutApplication`, a reference, a
  licence, or a Hugging Face base model or dataset are escaped invisible,
  bidi or control characters, a URL percent-encoded (U+202E can make
  `txt.exe` read `exe.txt`):
  `WARNING: FORMAT=<fmt> FILE=<path>: invisible or bidi control characters
  written as \uXXXX in <properties>`. The escape is not reversible on its own:
  a `\u202e` the file held as text looks the same, so check the
  `artifact-metadata` annotation's `metadata` (kept as read; not every
  field, e.g. an ONNX graph name) or the model file. Which fields are escaped:
  <https://bact.github.io/pitloom/metadata-reading-back/>.
- `INFO: FORMAT=<fmt> FILE=<path>: no SPDX 3.0.1 property: model-architecture
  (written in ai_typeOfModel)`, once per model: the architecture has no
  property of its own, so it is recorded beside the model type. Expected, not
  a problem; mention it when the user asks where the architecture is.
- No `ai_typeOfModel` on an ONNX model: a node uses an `ai.onnx.ml`
  operator (trees, linear models, SVMs), and the file does not say which
  kind of model that is, so it is left unset, silently. Otherwise it is
  `neural network` (the ONNX-ML opset import alone does not count).
- Reading values back from the `artifact-metadata` annotation (`/2`):
  collections (`labels`, shapes) are JSON arrays, scalars are text, and
  `valueTypes` names the type of each (`integer`, `float`, `boolean`).
  fastText `labels` is a JSON array too, so parse it, do not split on
  commas. A `truncated` or `maxEntries` key means entries were cut at the
  cap. How to decode: <https://bact.github.io/pitloom/metadata-reading-back/>.
- After the per-wheel budget is spent, later models are stubbed without a
  further line, except one over the ceiling or missing its library, which
  adds its own.
- The same input gives the same SBOM for the same settings;
  `--trust-wheel-model`, `--max-model-extract-bytes`, `--scan-model-usage`,
  `--allow-build` and (for `loom.Run` and `loom id generate` with `-e`)
  `max-dataset-hash-bytes` each change
  what is recorded, so do not compare SBOMs made with different ones. The
  last drops a dataset's hash, with a `WARNING:`, when its bytes pass the
  cap; the hash's provenance says `not_measured | Reason: over-cap` and a
  single-file dataset keeps its size, from `stat()`.

Every cap, its value and message (the single source of truth):
<https://bact.github.io/pitloom/ai-model-scan-limits/#size-and-count-caps>.

## Unsupported build backend

Hatchling, setuptools, Poetry, PDM-backend and Flit-core get accurate
file-level discovery (files, hashes, Merkle root) by default; no
`build-backend` declared means setuptools (PEP 517). Any other
backend (`uv_build`, or one still without its own toolchain, e.g.
`maturin`/`scikit-build-core`/`meson-python`) falls back to a
Hatchling-based heuristic. Project-level metadata (name, version,
dependencies, licence, authors) is read independently and unaffected
either way. Full detail: [docs/cli.md's Generate an SBOM
section](https://bact.github.io/pitloom/cli/#generate-an-sbom).

## Wheel SBOM contents and signing

A wheel SBOM (`loom wheel`, `generate <whl>`, `embed-wheel`, `wheel --embed`)
lists the payload only: nothing under the wheel's own `.dist-info`, `licenses/`
included. `embed-wheel` and `wheel --embed` refuse a wheel with `RECORD.jws` or
`RECORD.p7s` unless `--allow-signed-wheel` (deletes the signature files, one
`INFO:` each; re-sign afterwards). Pitloom cannot see signatures or hashes over
the wheel file itself (GPG `.asc`, Sigstore, PEP 740, lock-file hash); any embed
invalidates them, so embed first, then sign, attest, upload and hash.

### Signed wheels: what to tell the user

Use when `unzip -l <wheel>` shows `RECORD.jws` or `RECORD.p7s`, or `embed-wheel`
/ `wheel --embed` refused with a signature `ERROR:`.

1. **Plain explanation.** The wheel carries a signature over its file list
   (`RECORD`). Embedding adds the SBOM and rewrites that list, so the old
   signature would no longer verify. Pitloom stops rather than leave a broken
   signature or delete one silently.
2. **The choice.** `--allow-signed-wheel` deletes the signature file(s) (one
   `INFO:` each) and embeds. Afterwards the wheel is unsigned until the user
   re-signs it. Or skip embedding, or embed before the wheel is first signed.
3. **Order of operations.** Build, embed, then sign, attest (Sigstore, PEP 740),
   upload and record hashes (lock file, `pip --hash`): anything made over the
   whole `.whl` stops matching after an embed, and Pitloom cannot detect it.
4. **Context.** For wording matching the wheel's situation (publishing, an
   internal index, verifying someone else's wheel), fetch
   <https://bact.github.io/pitloom/wheel-sbom/#signed-wheels>
   with WebFetch or `curl` and relay the relevant part; fall back to 1-3.
5. **Never** add the flag on your own. Non-interactive: report the refusal, the
   explanation and the exact re-run command with the flag.

### Refused wheels and unknown identity

A wheel's name and version come from its own top-level `.dist-info` only.
`wheel`, `generate`, `wheel --embed` and `embed-wheel` refuse a file that is
not a ZIP and a wheel with a member they cannot read (damaged, encrypted, a
name that is not UTF-8), two members of one name or a NUL in a name: one
`ERROR:`, exit 1, nothing written (in a batch the other wheels run). It reads
`ERROR: wheel command failed: ARCHIVE=... ENTRY=...: <cause> -- wheel refused`
from `wheel` and `wheel --embed`, `ERROR: SBOM generation failed: ARCHIVE=...`
from `generate`, `ERROR: ARCHIVE=...` from `embed-wheel`. The two embeds also
refuse a wheel with no single own `.dist-info`, or an own `.dist-info` member
stored under a non-conforming name (`./`, `\`); for no single own `.dist-info`
a `WARNING: ... -- identity unknown` line comes before the `ERROR:`.
With no single own `.dist-info`, or a `METADATA` that is missing or over a cap,
`wheel` and `generate` only warn (`WARNING: ... identity unknown`) and write an
SBOM that names the wheel `unknown`; an ID registry neither looks up nor
records that placeholder (one `INFO:` when a registry is declared); its ids
derive from the wheel's file name and payload, so a renamed copy gets new ids.
The embeds do the same (one registry `INFO:` per batch) for a `METADATA`
that is missing or over a cap, but fail with the `ERROR:` above where there is
no single `.dist-info` to write into. Where the file name names no top-level
`.dist-info` but one other exists, every one of these commands uses it and logs
`WARNING: ... the file name names no top-level .dist-info; using ...`: report
that line, as the name and version then come from a directory the file name
does not name. It is not a model bound.

## Licence detection unavailable

Prepare the database before the first run of a session that reads licences:
`licenseid update --source packaged` (without an install, `uvx --from
"licenseid>=0.6.0" licenseid update --source packaged`). It uses the copy in
the `licenseid` wheel: no network. On a missing database it creates it
(`Update complete. Database updated at <path>`); on a current one it prints
`Database is already at version <v>. Skipping update.` and changes nothing, so
run it again without checking first. It may print `WARNING: popularity.csv:
missing` (no ranking data offline): harmless, not a Pitloom line. A packaged
copy older than the database is refused (`older than the database`): the
database is kept and the preflight counts as failed. The database is per user,
`~/.local/share/licenseid/licenses.db` (a platform directory on Windows), so
any environment's Pitloom reads it.

`WARNING: licenseid database cannot be used: <reason> -- license text detection
and license id reading skipped` (once per run; the reason ends `run 'licenseid
update'` when the file is missing or empty): the `licenseid` SPDX database is
missing or empty, so the preflight was skipped or failed. Licences are taken as
written: no `LICENSE` text is matched to an id and no respelt id (`Apache2`) is
read as the id it names, so the SBOM is thinner. Report the line and the
command. When the declared licence is already an SPDX expression and the file
is only missing, the line is `INFO: licenseid database not found: <path> --
license text detection skipped; run 'licenseid update --source packaged'`
(0.21.1 and later): the declared value is recorded as written and only the
`LICENSE` file is not matched.

If the preflight failed, generate anyway and report the line. Do not run a
network `licenseid update` or regenerate unasked: ask; non-interactive: report
only. A regenerate after fixing needs the same `-o`, `--config` and target.
With an ID registry, file, package and model ids are unchanged (keyed by path
or name), but the licence, relationship and annotation ids can change, and a
run updates the declared registry unless `--no-update-id-registry` is given (a
thin run stores a `SimpleLicensingText` entry that the later run replaces by a
`LicenseExpression` one).
Ask before regenerating over a registry the user pinned; non-interactive:
report only.

## A licence that looks like a broken expression

Text with an operator or parenthesis and a known id (`MIT OR`, `(MIT`) is
kept as `SimpleLicensingText`, not dropped, with one stderr line per value,
e.g.:

```text
WARNING: LICENSE='MIT OR': not a valid SPDX license expression (Unexpected 'OR'); recorded as license text
```

Fix the source value to get a `LicenseExpression`.

A single-line value `licenseid` (`resolve`) reads as one licence (`Apache2`,
`MIT License`, `GPLv2+`, a `License ::` classifier's name) is recorded as that
id (`Apache-2.0`, `MIT`, `GPL-2.0-or-later`), with one `INFO:` line per value
(no `FIELD=` for a classifier) and the reading in the licence element's
provenance `comment`: `Normalized-From: <value as written>`, `Method:
licenseid_resolution`, `Resolution-1: <value> -> <id> (<steps>)`,
`Expansion-1: plus_to_or_later` for a `+` or a stated "or later", and `Tool:
licenseid==<version>`. A change of case or `+` alone (`mit`, `GPL-2.0+`)
keeps only `Normalized-From`, with no `INFO:`. Report the line; the result is
the resolver's reading, not the author's words:

```text
INFO: FIELD=project.license LICENSE='Apache2': read as Apache-2.0 (separator, version_spelling)
INFO: LICENSE='MIT License': read as MIT (listed_name)
```

A field that holds an SPDX expression only (`project.license` string,
`License-Expression`, PyPI `license_expression`, `SPDX-License-Identifier`,
GGUF `general.license`) whose value is not one and `licenseid` reads as none
(`Acme-Terms`, `MIT OR Foo`, `Apache2 OR MIT`) is kept as text, with one line
per value naming the field:

```text
WARNING: FIELD=project.license LICENSE='Acme-Terms': not read as an SPDX license expression (Unknown Expression 'Acme-Terms'); recorded as license text
```

Report the line and suggest the listed id (`Apache-2.0`); do not rewrite the
value in the SBOM.
