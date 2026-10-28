---
Created: 2026-07-08
Last-Modified: 2026-10-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata provenance

> **Note:** This is reference documentation for auditing or debugging a
> generated SBOM -- not needed to just generate one. The schema described
> below is still in beta and can change without notice between releases.

Pitloom tracks the source of each metadata field in the SBOM, so questions
like "why does the SBOM say the concluded licence is MIT?" or "where did
the version number come from?" have a traceable answer.

Provenance is recorded as SPDX 3 Core `Annotation` elements -- structured,
machine-readable JSON keyed by field name -- with the original human-readable
`comment` form kept alongside for back-compat. The `format`, `detail`,
`preserve-source-metadata` and `max-source-metadata-bytes` keys of
`[tool.pitloom.provenance]` control it; their values, defaults and flags are
in [Configuration](configuration.md#toolpitloomprovenance).

By default (`detail = "minimal"`), a field only gets a provenance
Annotation when it adds something the native SPDX value can't already
convey -- e.g. the value was inferred or detected rather than read
verbatim. A value with a real native SPDX home (the licence itself, the
package version, a dependency edge) is never restated in the Annotation;
only *how it was determined* is. Set `detail = "full"` for an exhaustive
per-field source map instead. A field built from more than one file names
them all, comma-separated, with each `Field` in the same order (`Source:
setup.py, setup.cfg | Field: setup(url=...), metadata.url/project_urls`);
when every one is a manifest, `minimal` leaves it out like a single
manifest read.

The provenance reference is split by topic:

- [Preserved artefact metadata](metadata-provenance-artifact-metadata.md)
  -- an artefact's own metadata kept in one annotation, and its size
  bound.
- [Licences and copyright](metadata-provenance-licences.md) -- how a
  licence source is chosen, how a licence value is recorded, and how the
  copyright text is found.
- [Authors](metadata-provenance-authors.md) -- how authors and a
  dependency's originators are read.

## Provenance examples

An `Annotation` on a package whose licence was detected (not
author-declared):

```json
{
  "type": "Annotation",
  "annotationType": "other",
  "contentType": "application/json",
  "subject": "https://spdx.org/spdxdocs/mypackage-.../#Package-1",
  "statement": "{\"fields\":{\"license\":{\"method\":\"licenseid_detection\",\"source\":\"LICENSE\",\"tool\":\"licenseid==0.6.0\"}},\"kind\":\"fields\",\"schema\":\"https://pitloom.dev/provenance/fields/1\"}"
}
```

The legacy `comment` form of the same information (present when `format`
includes `"comment"`, the default `"both"` does):

```json
{
  "type": "software_Package",
  "name": "mypackage",
  "software_packageVersion": "1.2.3",
  "comment": "Metadata provenance: version: Source: src/mypackage/__about__.py | Method: dynamic_extraction"
}
```

The provenance information shows:

- **Version**: Dynamically extracted from `src/mypackage/__about__.py`
- **Licence**: Detected from a `LICENSE` file, not author-declared

This transparency is crucial for:

- **Auditability**: Understanding where SBOM data comes from
- **Trust**: Verifying the accuracy of metadata, and distinguishing
  extracted facts from inferred/detected ones
- **Machine consumption**: Automated tools can parse provenance
- **Human review**: Manual inspection of data sources

## What the `method` values mean

The `method` field in a provenance entry says *how* Pitloom arrived at a
value, not just where it read it from. Values in use today:

| `method` | Meaning |
| --- | --- |
| `dynamic_extraction` | Read from a Python file at build time (e.g. a `__version__` or `__about__.py` variable), not from `pyproject.toml` directly. |
| `licenseid_detection` | Licence text matched against a known SPDX licence using the [`licenseid`](https://pypi.org/project/licenseid/) library -- detected, not author-declared. |
| `licenseid_resolution` | A declared licence value read as one SPDX id by `licenseid` (`Apache2` as `Apache-2.0`) -- the resolver's reading of what the author wrote, not the author's own words; the value as written stays in `Normalized-From`. |
| `copyright_notice_lines` | The main package's copyright text: the copyright notice lines of the named licence files, as written (see [How the copyright text is found](metadata-provenance-licences.md#how-the-copyright-text-is-found)). |
| `parsed_author_list` | A dependency's originators, when its author fields name more than one (several address-field entries, several mailboxes in a name field, or a name beside them). |
| `file_directive` | A `pyproject.toml` dynamic field pointed at a file (`{file = "..."}`); the value was read from that file. |
| `attr_directive` | A dynamic field pointed at a Python attribute (`pyproject.toml` `{attr = "..."}`, `setup.cfg` `attr:`); the string assigned to it was read from the module's source, which is never imported. |
| `inspect_caller` | Recorded automatically by the `pitloom.loom` tracking SDK via Python stack inspection -- identifies which script/function called the SDK. |
| `synthetic` | The element is Pitloom's own synthesised placeholder root package for an installed environment (`loom env`), not extracted from any source file. |
| `magika_content_detection` | Per-file content type resolved by the [`magika`](https://pypi.org/project/magika/) content-detection library. |
| `extension_guess` | Per-file content type resolved by a filename-extension fallback (no `magika`, or no confident result). |
| `file_name_stem` | An AI model's name is its file name without the last extension: the file names no model (or only an exporter default). |
| `semver_bit_packed` | An ONNX integer `model_version` decoded as bit-packed SemVer (`MAJOR.MINOR.PATCH`). |
| `array_length` | A GGUF array field: only its element count is recorded (property `<key>.length`); the elements are not recorded. |
| `crfsuite_model_type` | A CRFsuite model's type of model, `conditional random field`, derived from the header's model type (`FOMC`, a first-order Markov CRF, the only type CRFsuite writes). |
| `generated_from_labels` | A CRFsuite model's description, written by Pitloom from the model's labels (the file has no description): the label count and the first 20 labels, each cut to 64 characters. |
| `derived_from_format` | A value the file does not state but its format fixes: a fastText model's domain (from `args.model`) and output (`label_probabilities`, supervised models), and a CRFsuite model's output (`label_sequence`, one label per input item). |
| `resolved_lockfile` | A dependency version pinned by a lock file (`pylock.toml`, `uv.lock`, `poetry.lock` and similar), not by the project's own requirement specifier. |
| `pinned_requirements` | A dependency version pinned with `==` or `===` in a `requirements.txt`; weaker evidence than a real lock file, so tagged separately. |
| `pdm_dynamic_version` | A PDM dynamic `version`, resolved from `[tool.pdm.version]` with PDM's own resolver; the tag ends with the declared source in parentheses, e.g. `pdm_dynamic_version(file)`. |
| `flit_dynamic_metadata` | A Flit dynamic `version` or `description`, read from the module's `__version__` and docstring with flit-core's own AST scan. |
| `member_count` | A ZIP-based model archive's member count (property `archive_member_count`), read from the archive's central directory. |
| `yaml_frontmatter` | Read from a local README/model card's YAML frontmatter block during enrichment. |
| `tensor_element_sum` | An AI model's parameter count: the sum of the element counts of its tensors, derived by Pitloom (GGUF `tensor_infos`, Safetensors header shapes, ONNX `graph.initializer` and `graph.sparse_initializer`) or computed by the Hugging Face Hub (`safetensors.total`, `gguf.total`). All stored tensors count: [what that means](ai-model-formats.md#what-the-count-counts). |
| `comma_list` | An ONNX model's originators, split on commas because the `model_author` property is a comma-separated list; set only when the text has a comma. A name that holds a comma (`Doe, Jane`) is split too. |
| `repository_owner` | A Hugging Face model's originator and supplier (`originators`, `supplier`): the owner of the Hub repository (`model_info` `author`), which the Hub does not say is the model's author. |

A field with **no** `method` -- just a `source` -- was read verbatim from
the named file with no interpretation involved (e.g. `project.name` from
`pyproject.toml`). In `detail = "minimal"` (the default), these
no-`method` entries are dropped entirely when the source is a
well-known, re-readable manifest (`pyproject.toml`, `setup.cfg`/`setup.py`,
wheel metadata, an sdist's `PKG-INFO`, the Hugging Face Hub API) -- they
add no signal beyond what's already implied by the native field. Set
`detail = "full"` to see every field's source regardless.

## How a dependency-version source is chosen

The same disagreement-detection mechanism also applies to a dependency's
resolved version, once a project lock file is in play (see [Dependency
sources and precedence](dependency-sources.md)). Unlike licence, there's
no independent-detection procedure here -- both candidates are the
project's own stated claims, just from two different files, so **both are
`role: "declared"`**, not a `declared`/`detected` pair:

- A direct dependency pinned exactly (e.g. `requests==2.31.0`) whose
  pinned version doesn't match what the lock file separately resolved to.
- A direct dependency declared as a range or left unpinned (e.g.
  `requests>=2.0`) whose declared constraint the lock file's resolved
  version doesn't satisfy.

Either way, the resolved `software_packageVersion` still follows the
same "explicit pin beats local environment" precedence described in
[Dependency sources and precedence](dependency-sources.md#version-comparison-pep-440-not-semver)
(a declared exact pin always wins; otherwise the lock file's version
wins), and Pitloom adds a `conflict` Annotation (`field:
"dependency_version"`) on the dependency package recording both values:

```json
{
  "candidates": [
    {"role": "declared", "source": "Source: pyproject.toml | Field: dependencies", "value": ">=2.0"},
    {"role": "declared", "source": "Source: requirements.txt | Method: resolved_lockfile", "value": "1.5.0"}
  ],
  "field": "dependency_version",
  "kind": "conflict",
  "schema": "https://pitloom.dev/provenance/conflict/1"
}
```

Note the declared candidate's `value` is a PEP 440 specifier expression
(e.g. `">=2.0"`), not a version, when the dependency was declared as a
range rather than pinned exactly -- the exact-pin case instead has a
concrete version on both sides.

A dependency's `declared_constraint` annotation holds every string declared
for that package, extras included (see [Extras and the optional
edge](dependency-sources.md#extras-and-the-optional-edge)), sorted and
joined by ` | `. Every route spells a dependency alike: the package name
is the PEP 503 name its `pkg:pypi` PURL uses (`Foo_Bar` is `foo-bar`), and
each declared string is spelt as `packaging` writes it, whether the source
kept the spelling (a setuptools wheel) or not. `loom env` names each
installed distribution the same way (`PyYAML` is `pyyaml`), whatever its
`.dist-info` spells. The SBOM's own root package keeps the name the
project declares (`Foo_Bar`), on every route; only its PURL is PEP 503.

## See also

`[tool.pitloom.provenance]` is read the same way regardless of entry
point -- see [Command line](cli.md#configuration), [Hatchling build
hook](hatchling-build-hook.md), and [Python API](python-api.md) for where
to set it.

- [Dependency sources and precedence](dependency-sources.md) -- how
  resolved lock files feed into Source SBOM dependencies and provenance.
- [Reading values back](metadata-reading-back.md) -- the layers a value
  passes through (caps, scalar text, display escape, RFC 8785) and the
  order to undo them.
