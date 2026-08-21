---
Created: 2026-08-12
Last-Modified: 2026-08-20
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Configuration reference

Every `[tool.pitloom]` setting, its default, and how to reach it from
each surface (CLI flag, GitHub Action input, Python API parameter).
This is the exhaustive reference; [Command line](cli.md) and
[GitHub Action](github-action.md) have narrative walkthroughs with
worked examples for the settings people reach for most (creator/creation
metadata, provenance).

A CLI flag or API parameter of `None` (its default, when omitted) always
defers to `pyproject.toml`; passing an explicit value overrides it for
that run only. A GitHub Action input of `""` (empty, its default) defers
the same way.

## `[tool.pitloom]`

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `pretty` | bool | `false` | `--pretty` / `--no-pretty` | `pretty` | `pretty` | Indent the JSON output with 2 spaces. |
| `describe-relationship` | bool | `false` | `--describe-relationship` / `--no-describe-relationship` | -- | `describe_relationship` | Include human-readable text on SPDX relationships. |
| `sbom-basename` | string | *(derived from project name/version)* | -- | -- | `sbom_basename` | Base filename (no extension) for the generated SBOM. |
| `offline` | bool | `false` | `--offline` | -- | `offline` | Skip the PyPI JSON API fallback used to fill dependency metadata gaps. Network attempted, best-effort, by default -- any failure (including no network) silently falls back to local-only data. |
| `extract-file-header` | bool | `true` | `--extract-file-header` / `--no-extract-file-header` | `extract-file-header` | `extract_file_header` | Scan each source file's leading comment header for SPDX-File\* tags. Independent of content-type detection below -- a binary file with no text header still gets a `contentType` when that's on. |
| `enrich` | bool | `false` | `--enrich` / `--no-enrich` | `enrich` | `enrich` | Run local README/model-card enrichment for discovered AI models. |
| `ids-file` | string | `null` (auto-discovers `loom-ids.json` by walking up from the project directory) | -- | -- | -- (see `registry` param) | Path to the Loom ID registry file. |
| `update-registry` | bool | `true` (`project` command only -- `wheel`/`env` aren't pyproject-cascaded, same as `ids-file`) | `--update-registry` / `--no-update-registry` | -- | `update_registry` | After generating, harvest newly-minted ids back into the resolved registry and save it. Only consulted by `project`/`wheel`/`env`/`generate`; accepted but has no effect on `model`/`enrich`/`embed-wheel`. No effect when no registry is resolved -- see [Loom IDs across fragments](../README.md#loom-ids-across-fragments-pitloom-ids). |

**Invalid values / fallback behavior:** every boolean above raises
`ValueError` at config-read time if set to a non-boolean (e.g. the TOML
string `"true"` instead of the bare value `true`) -- no silent
coercion. `sbom-basename`/`ids-file` raise `ValueError` if set to a
non-string. `extract-file-header` off never errors and never blocks
content-type detection -- see below.

## `[tool.pitloom.content-type]`

Content-type detection (`magika`/filename-extension) is independent of
`extract-file-header` above -- both are opt-in, gated separately,
because they have different cost profiles and apply to different kinds
of files (a header only exists in text source; a content type applies
to every file, text or binary).

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `enabled` | bool | `false` | `--content-type` / `--no-content-type` | `content-type` | `content_type` | Detect each file's real IANA media type. Off by default -- `magika` inference is a real per-file cost (~5ms/file). |
| `method` | `"auto"` \| `"magika"` \| `"extension"` | `"auto"` | `--content-type-method` | `content-type-method` | `content_type_method` | Which detector resolves a value: `"auto"` tries `magika`, falling back to a filename-extension guess when `magika` isn't installed or its result is inconclusive; `"magika"` behaves identically per-file but raises immediately if the package isn't installed at all; `"extension"` skips `magika` entirely. |

**Invalid values / fallback behavior:** `enabled` non-boolean raises
`ValueError` at config-read time. `method` not one of the three listed
values raises `ValueError` at config-read time. `method = "magika"`
with the `magika` package not installed raises `RuntimeError` at
generation time, before any file is scanned -- you asked for `magika`
specifically, so this fails loudly rather than silently degrading every
file's `contentType` the way `"auto"` would. `"auto"`/`"extension"`
never raise for a missing/inconclusive detector; they just resolve to
`None` for that file. Overrides below only ever apply while `enabled`
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

**Invalid values / fallback behavior:** `override` present but not an
array of tables, an entry not a table, a missing/empty `pattern`, or a
`content-type` not shaped like `type/subtype` -- each raises
`ValueError` at config-read time with a message naming the exact
problem. First-match-wins in declaration order; a file matching no
pattern falls through to normal detection.

## `[tool.pitloom.fragment]`

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `files` | array of strings | `[]` | -- | -- | -- | Paths to pre-generated SPDX 3 JSON-LD fragment files (relative to the project directory) merged into the final SBOM. See [Merge fragments](cli.md#merge-fragments). |

Kept as its own table (rather than folded into a flat `[tool.pitloom]`
key) since it's expected to grow more fragment-related settings.

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
overrides it.

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
[Creator and creation metadata](cli.md#creator-and-creation-metadata)
for worked examples and [Creation metadata](creation-metadata.md) for
what these fields record in the generated SBOM.

| Table | Key | Type | Meaning |
| :---- | :-- | :--- | :------ |
| `[[tool.pitloom.creator]]` | `name` | string (required) | Creator's name. |
| | `email` | string | Creator's email. |
| | `type` | `"person"` \| `"organization"` \| `"software-agent"` \| `"agent"` | Defaults to `"person"`. |
| `[[tool.pitloom.creation-tool]]` | `name` | string (required) | Tool name recorded as having produced the SBOM. |

**Invalid values / fallback behavior:** a missing/empty `name` on
either table, or a non-string `type`/`email`, raises `ValueError` at
config-read time. `--creator-name`/`--creation-tool` on the CLI replace
the whole configured list for that run rather than merging with it.

## `[tool.pitloom.provenance]`

Config-only (no CLI flags) -- see [Metadata provenance](metadata-provenance.md)
for what each setting changes in the generated SBOM's Annotations.

| Key | Type | Default | Meaning |
| :-- | :--- | :------ | :------ |
| `format` | `"annotation"` \| `"comment"` \| `"both"` | `"both"` | How metadata provenance is recorded: SPDX Core `Annotation` elements, legacy `Element.comment` strings, or both. |
| `schema` | string | `"pitloom/1"` | Which statement schema encodes provenance Annotations. |
| `detail` | `"minimal"` \| `"full"` | `"minimal"` | `"minimal"` emits a field-source Annotation only when the source adds signal the native value can't convey; `"full"` emits the per-field source map for every field. |
| `preserve-source-metadata` | `"auto"` \| `"always"` \| `"never"` | `"auto"` | Whether to embed an artifact's verbatim original metadata blob. `"auto"` does so only when the artifact isn't shipped with the distribution (and so can't be re-extracted later). |

**Invalid values / fallback behavior:** a non-string value, or a
`format`/`detail`/`preserve-source-metadata` outside its listed set,
raises `ValueError` at config-read time. An unknown `schema` id is not
caught here (`core` doesn't import the assembly layer's encoder
registry) -- it's caught with a clear error the first time an SBOM is
actually generated.

## See also

- [Command line](cli.md) -- flag-by-flag usage with worked examples.
- [GitHub Action](github-action.md) -- input reference for CI.
- [Python API](python-api.md) -- calling Pitloom from Python code.
- [Hatchling build hook](hatchling-build-hook.md) -- inherits the
  project's `[tool.pitloom]` automatically, no separate hook-level
  config surface (only `[tool.hatch.build.hooks.pitloom] enabled`
  controls whether the hook itself runs).
