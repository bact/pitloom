---
Created: 2026-11-26
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Configuration reference, sub-tables

See also: [Configuration reference](configuration.md) for where settings
come from and the main `[tool.pitloom]` table, and [Command line
flags](cli-flags.md#configuration) for the matching flags.

The `[tool.pitloom.*]` sub-tables: content type, fragments, creation
metadata, creators and provenance.

## `[tool.pitloom.content-type]`

Content-type detection (`magika`/filename-extension) is independent of
`extract-file-header` in [`[tool.pitloom]`](configuration.md#toolpitloom) -- that one is on by default, this one off,
because they have different cost profiles and apply to different kinds
of files (a header only exists in text source; a content type applies
to every file, text or binary).

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `enabled` | bool | `false` | `--content-type` / `--no-content-type` | `content-type` | `content_type` | Detect each file's real IANA media type. Off by default -- `magika` inference is a real per-file cost (~5ms/file). |
| `method` | `"auto"` \| `"magika"` \| `"extension"` | `"auto"` | `--content-type-method` | `content-type-method` | `content_type_method` | Which detector resolves a value: `"auto"` tries `magika`, falling back to a filename-extension guess when `magika` isn't installed or its result is inconclusive; `"magika"` behaves identically per-file but raises immediately if the package isn't installed at all; `"extension"` skips `magika` entirely. |

**Invalid values / fallback behaviour:** a non-boolean `enabled`, or a
`method` outside the three listed, is `config-invalid`. `method = "magika"`
with the `magika` package not installed raises `ImportError` (coded
`library-missing`, naming `pitloom[content-type]`; `library-unusable` when it
is installed but fails to import) at
generation time, before any file is scanned -- you asked for `magika`
specifically, so this fails loudly rather than silently degrading every
file's `contentType` the way `"auto"` would. `"auto"`/`"extension"`
never raise for a missing/inconclusive detector; they just resolve to
`None` for that file. With `"auto"`, a `magika` that is installed but fails
to import gives every file its extension's type and one `WARNING:` per process
(`library-unusable`). Overrides below only ever apply while `enabled`
is `true` -- with it `false`, no file gets a `contentType` at all,
configured overrides or not.

### `[[tool.pitloom.content-type.override]]`

A deterministic, config-asserted `contentType` for files matching a
glob pattern -- pre-empts detection for that file entirely (no
`magika`/extension guess runs). Config-only: no CLI flag, Action input,
or API parameter, since a glob-to-MIME-type mapping doesn't fit a
scalar flag; a caller who wants this programmatically constructs their
own `PitloomConfig`.

| Key | Type | Meaning |
| :-- | :--- | :------ |
| `pattern` | string | A shell-glob (`fnmatch.fnmatchcase`, case-sensitive on every platform) matched against the file's `distribution_path`. `*` matches `/` too, so `vendor/*` matches everything under `vendor/`. |
| `content-type` | string | The MIME/IANA media type to assign on a match, e.g. `"font/woff2"`. |

```toml
[tool.pitloom.content-type]
enabled = true
method = "auto"

[[tool.pitloom.content-type.override]]
pattern = "*.woff2"
content-type = "font/woff2"

[[tool.pitloom.content-type.override]]
pattern = "vendor/*"
content-type = "application/octet-stream"
```

**Invalid values / fallback behaviour:** `override` present but not an
array of tables, an entry not a table, a missing/empty `pattern`, or a
`content-type` not shaped like `type/subtype` -- each raises
`ValueError` at config-read time with a message naming the exact
problem. First-match-wins in declaration order; a file matching no
pattern falls through to normal detection.

## `[tool.pitloom.fragment]`

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `files` | array of strings and/or tables | `[]` | -- | -- | -- | Pre-generated SPDX 3 JSON-LD fragment files merged into a project directory's SBOM (not a wheel, sdist, environment or model file SBOM). Each entry is either a plain path string (shorthand -- every other field below defaults) or an inline table with `path` plus any of the fields below. See [Merge fragments](fragments.md#merge-fragments), [`loom fragment list`](fragments.md#list-configured-fragments). |

Kept as its own table (rather than folded into a flat `[tool.pitloom]`
key) since it's expected to grow more fragment-related settings.

**`files` table-entry fields** (all optional besides `path`):

| Key | Type | Default | Meaning |
| :-- | :--- | :------ | :------ |
| `path` | string | *(required)* | Path to the fragment file, relative to the directory of the file that sets it (the project directory for its own `pyproject.toml`). |
| `role` | string | `null` | Free-form, unvalidated label for what *part* this fragment plays in a pipeline (e.g. `input_dataset`, `output_dataset`, `ai_model`, `software_package`, `source`, `training_script`, `data_cleaning_script`, `post_processing_script`, `guardrail_safety_function`) -- not enforced, and not read by the merge itself yet; informational only, shown by `loom fragment list`. |
| `description` | string | `null` | Human-readable description of what the fragment covers. |
| `required` | boolean | `false` | If `true`, a missing, unreadable or unmergeable fragment fails the build (`FragmentMergeError`, code `fragment-missing`) instead of the default warn-and-skip. |
| `sha256` | string | `null` | Expected SHA-256 hex digest of the fragment file: 64 hex digits, in either case. Anything else is a `config-invalid` error. Currently checked for display only by `loom fragment list` -- not yet enforced before merge (planned: `loom fragment sign`). |
| `link-to-main` | string | `null` | Reserved for a future SPDX relationship type between the fragment's root element and the project's main package. Stored but not yet acted on. |

```toml
[tool.pitloom.fragment]
files = [
    "fragments/legacy.spdx3.json",
    { path = "fragments/model.spdx3.json", role = "ai_model", required = true, sha256 = "a3f1..." },
]
```

## `[tool.pitloom.creation]`

| Key | Type | Default | CLI flag | Meaning |
| :-- | :--- | :------ | :------- | :------ |
| `creation-datetime` | string (ISO 8601) | *(current time)* | `--creation-datetime` | Overrides the SBOM's recorded creation timestamp. |
| `creation-comment` | string | `null` | `--creation-comment` | Free-text comment on `CreationInfo`. |
| `no-creation-tool` | bool | `false` | `--no-creation-tool` | Omit the default `"Pitloom"` creation-tool entry. |

**`creation-datetime` resolution order:** an explicit pin here (or
`--creation-datetime`) always wins when set -- it is a deliberate,
per-SBOM value and so takes priority over the ambient,
workspace-wide [`SOURCE_DATE_EPOCH`][source-date-epoch] environment
variable (reproducible-builds.org). When neither is set, the current UTC
time is used. The same priority order applies to the Hatchling build
hook's `builtTime` field. `SOURCE_DATE_EPOCH` is a useful default for CI
environments that already export it for reproducibility without needing
a per-project `creation-datetime` pin, but an explicit pin always
overrides it. A `SOURCE_DATE_EPOCH` that is not an integer number of seconds
(or is out of range for a date) is an `ERROR:` on every surface (the CLI exits
1, the library raises `ValueError`, the hook fails the build; code
[`source-date-epoch-invalid`](message-codes-config.md#source-date-epoch-invalid)), as the
specification asks, and whether or not a `creation-datetime` pins the date:
Hatchling fails on it either way.

**Embedding into a wheel (`loom embed-wheel`, `loom wheel --embed`):** a
`.whl` is a ZIP archive, and the ZIP format's own per-entry timestamp
field can only represent dates from 1980-01-01 onward -- a binary format
limitation, unrelated to Unix time (what `SOURCE_DATE_EPOCH` counts from,
starting 1970-01-01) or to the SBOM's own `created` field (plain JSON,
no such limit). A `SOURCE_DATE_EPOCH` set below 1980 (e.g. `0`, a
value some build systems use deliberately as a fixed placeholder) is
floored to `1980-01-01` for the wheel's embedded ZIP entry only -- the
SBOM's own `created` field keeps the true value, so the two can
legitimately diverge. When this happens, Pitloom prints an `INFO:` line
rather than silently rewriting the SBOM's stated creation date to match
the ZIP format's limitation. To avoid the divergence entirely, set
`SOURCE_DATE_EPOCH` to `315532800` (1980-01-01) or later.

[source-date-epoch]: https://reproducible-builds.org/specs/source-date-epoch/

## `[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]`

Array-of-tables, one entry per creator/tool. See
[Creator and creation metadata](cli-flags.md#creator-and-creation-metadata)
for worked examples and [Creation metadata](creation-metadata.md) for
what these fields record in the generated SBOM.

| Table | Key | Type | Meaning |
| :---- | :-- | :--- | :------ |
| `[[tool.pitloom.creator]]` | `name` | string (required) | Creator's name. |
| | `email` | string | Creator's email. |
| | `type` | `"person"` \| `"organization"` \| `"software-agent"` \| `"agent"` | Defaults to `"person"`. |
| `[[tool.pitloom.creation-tool]]` | `name` | string (required) | Tool name recorded as having produced the SBOM. |

**Invalid values / fallback behaviour:** a missing/empty `name` on
either table, or a non-string `type`/`email`, is `config-invalid`. `--creator-name`/`--creation-tool` on the CLI replace
the whole configured list for that run rather than merging with it.

## `[tool.pitloom.provenance]`

Config-only, except `max-source-metadata-bytes` (see below) -- see
[Metadata provenance](metadata-provenance.md) for what each setting
changes in the generated SBOM's Annotations.

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `format` | `"annotation"` \| `"comment"` \| `"both"` | `"both"` | -- | -- | -- | How metadata provenance is recorded: SPDX Core `Annotation` elements, legacy `Element.comment` strings, or both. |
| `schema` | string | `"pitloom/1"` | -- | -- | -- | Which statement schema encodes provenance Annotations. |
| `detail` | `"minimal"` \| `"full"` | `"minimal"` | -- | -- | -- | `"minimal"` emits a field-source Annotation only when the source adds signal the native value can't convey; `"full"` emits the per-field source map for every field. |
| `preserve-source-metadata` | `"auto"` \| `"always"` \| `"never"` | `"auto"` | -- | -- | -- | Whether to embed an artefact's verbatim original metadata blob. `"auto"` does so only when the artefact isn't shipped with the distribution (and so can't be re-extracted later). |
| `max-source-metadata-bytes` | `0` or an integer >= 8 | `0` | `--max-source-metadata-bytes` | `max-source-metadata-bytes` | `max_source_metadata_bytes` | Byte budget for the serialised artifact-metadata `Annotation.statement`. `0` means unlimited. When exceeded, the largest metadata entries are dropped first and the result is marked `truncated`/`truncatedKeys`/`truncatedKeyCount`/`maxMetadataBytes` -- see [Metadata provenance](metadata-provenance-artifact-metadata.md#size-bounded-preservation). Unlike its siblings above, this one has a CLI flag, an Action input and an API parameter (`generate()`, `generate_*_sbom()`; `ConfigOverrides` for `embed_wheel_sbom()`): a byte cap is an operational knob someone may want to override per-run without editing `pyproject.toml`. |

**Invalid values / fallback behaviour:** a non-string value, or a
`format`/`detail`/`preserve-source-metadata` outside its listed set,
is `config-invalid`, and so is an unknown `schema` id (`must be one of
pitloom/1`), when the config is read. `max-source-metadata-bytes`: only `0` (unlimited) or
at least 8 bytes -- the smallest JSON object it could ever hold -- is
valid. A non-integer, a `bool`, a negative value or 1 to 7 is an error,
never "unlimited": at config-read time, on `--max-source-metadata-bytes`
(exit 2) and on the library's `max_source_metadata_bytes=`.
