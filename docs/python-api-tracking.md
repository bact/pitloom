---
Created: 2026-11-27
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Python API: tracking decorator

See also: [Python API](python-api.md) (the generator functions and
standalone enrichment), [API reference](api.md#tracking-decorator) (exact
signatures), [SBOM fragments](fragments.md) (merging what a run writes) and
[Loom ID registry](id-registry.md) (stable ids across runs).

Annotate scripts or Jupyter notebooks to generate external SBOM fragments
that Pitloom merges during the build process, as a function decorator or
a context manager. Use `set_model` when generating a new model, and
`use_model` when consuming one for inference or evaluation.

## Quick guide

```python
from pitloom import loom


@loom.run(output_file="fragments/train.json")
def train_model():
    loom.set_model("model-name")
    loom.add_dataset("dataset-name", dataset_type="text")
    # ... training logic ...
```

## Usage details

```python
from pitloom import loom


@loom.run(output_file="fragments/train.json")
def train_model():
    loom.set_model("model-name")  # <-- (A)
    loom.add_dataset("dataset-name", dataset_type="text")  # <-- (B)
    # ... training logic ...


@loom.run(output_file="fragments/eval.json")
def evaluate_model():
    loom.use_model("model-name")  # <-- (C)
    loom.add_validation_dataset("eval-set", dataset_type="text")  # <-- (D)
    # ... evaluation logic ...
```

- (A) and (C) set the relationship between the code and the model: (A) a
  model the run creates, (C) one it only uses.
- (B) relates the model to a dataset: `trainedOn` in a run that creates the
  model (`set_model()`), `testedOn` in a run that only uses it
  (`use_model()`).
- (D) relates the model to a dataset as `testedOn` in either kind of run.

Each call checks its arguments first. A model or dataset name that is empty
or blank raises `ValueError` (`option-invalid`). An argument of the wrong type (`None`
for a model name, a number for a path, a string for `input_datasets=`, a
`bool` for a string) raises `TypeError`, and a `dataset_type` that is not an
SPDX dataset type term spelt exactly (`text`, `image`, `noAssertion`, ...)
raises `ValueError`; both carry the code `option-invalid` and name the
argument and what it must be. An empty `loom.run("")` output path
raises `ValueError` (`option-invalid`) at the call. `loom.run()`'s
`pitloom_config=` and `max_dataset_hash_bytes=` are checked as the run
begins: a value of the wrong type raises `TypeError`, an integer below 1
`ValueError`, both `option-invalid`. `data_preprocessing=` and
`input_datasets=` take a list or a tuple of strings; a path takes a `str` or
an `os.PathLike`, never `bytes`. A fragment the run cannot write raises
`OSError` (`file-unwritable`), and a run started where the current directory
no longer exists raises `ValueError` (`file-unreadable`).

Pass `path=` (the model file, relative to the current directory at the call)
to `set_model()` or `use_model()` to give the model a SHA-256 and a SHA-512
(`verifiedUsing`). The file is hashed when the run ends without an
exception, so write it before the block exits. With a [Loom ID
registry](id-registry.md), the SHA-256 gates the lookup: a training and an
evaluation script declaring the same model name and file share one id, and a
retrained file gets a new one. The model is keyed by that file's path from the
registry's project root, the same key `loom model` and `id generate` use.
When a project build merges the run's fragment, the model file's `ai_AIPackage`
takes the name given to `set_model()`/`use_model()`, with one `INFO: Merge:
ELEMENT=<id>: name replaced by the one the fragments agree on; ...`; its id
and registry key do not change. Runs naming one file two
ways keep the project's name, with a `WARNING:` (see
[SBOM fragments](fragments.md#merge-fragments)).
Without `path=`, or when it is not a file when the run ends, the model gets no
hash. With a registry loaded, one `WARNING: ID registry: loom SDK model ... looked
up ungated: not hashed [registry-hash-missing]` says the model is looked up by its
name alone; the match hits an id held with no hash (a model with no file) and
never one recorded with a SHA-256, which no content vouches for: a retrained
model's id is not reused by a bare name. With no registry, a `path=` that is no
file is one `WARNING: loom SDK: model ...: path= ... is not a file at exit; not
hashed [model-file-missing]`, and no `path=` says nothing. In the context-manager form,
`run.model` is `None` until the block exits.
A `path=` that cannot be read (a NUL in it included) gets the usual
unreadable-model `WARNING:`. Leaving a block, by an exception too, restores
the enclosing run, so a recursive `@loom.run` call is safe.

The run also records *which script produced what*: the calling script becomes a
`software_File` (with SHA-256 and SHA-512 hashes; named as invoked, so a script
run through a symbolic link keeps the link's name, unless the path it was run
by holds a `..`, which is resolved through the links) with `generates` relationships
to the model it trained and/or the output datasets it wrote. A dataset that is a
file gets SHA-256 and SHA-512 hashes and a `software_File` it `contains`; a
directory gets a SHA-256 Merkle root over its files' paths and content, its
`comment` saying so, and no file elements. Below a dataset directory, the
[directories `id generate` skips](id-registry.md#directories-that-are-skipped)
and symbolic links to directories are left out of the root, as is the declared
registry file. A missing or remote dataset name gets no hash. Hashing one
dataset reads at most `max_dataset_hash_bytes=` (else the config's
`max-dataset-hash-bytes`, else 4 GiB); over it, the dataset gets no hash and one
`WARNING:`. A dataset that is a file also gets its size in bytes
(`dataset_datasetSize`): the bytes read, or, over the cap, its `stat()` size,
with the hash's absence and the reason in the
[provenance](metadata-provenance.md). A directory, a Git LFS pointer and a file
under 1,024 bytes that is over the cap get no size. The keyword is an integer of
at least 1: as the run begins, `0` raises `ValueError` and a `bool` or a string
`TypeError`. A dataset is
hashed when it is declared, an output dataset too: call `add_output_dataset()`
after the step has written the file, or it carries the hash of the file it
replaces. One name holding one content is one package per run: declaring it
again (as input and output, or twice) adds its roles to the same package, with
no collision warning. A name that is no path is compared as a model card's
`datasets:` entry is: whitespace runs count as one space and a Hugging Face
repository id is case-insensitive (`Org/Data` is `org/data`), the package
keeping the first spelling, which alone is looked up in the ID registry; an id
pinned under a later spelling is not used, with one `WARNING:`.

A dataset can carry what its own metadata states. Pass `croissant=` (a local
[Croissant](https://docs.mlcommons.org/croissant/) JSON-LD file) to any of the
four dataset calls: its licence becomes the dataset's `hasDeclaredLicense`, and
its version, description, download URL, creator (`publishedBy`) and
dataset-profile fields (collection process, preprocessing, known bias, sensitive
personal information) are written onto the package. A dataset that is a
directory has its card read too: the YAML frontmatter of its `README.md` gives
`license`, `version` and `tags` (the tags are read but have no SPDX 3.0.1
dataset property to go in). Pass `declared_license=` to state the licence
yourself:

```python
with loom.run("fragments/train.json"):
    loom.add_dataset("data/corpus", croissant="data/corpus.croissant.json")
    loom.add_dataset("data/extra.txt", declared_license="CC-BY-4.0")
```

Each field comes from the first source that states it: `declared_license=`, then
the Croissant file, then the card. A source's `unknown`, `N/A` or `NOASSERTION`
states nothing (a version, creator or licence of that text is left out), and its
download URL must be a URL. A `declared_license=` on any call for the dataset
wins over every Croissant file and card, whichever call came first; of two
declared licences, the first call's wins. The call's own name, `dataset_type`
and `data_preprocessing=` (even `[]`) always win. A licence that is an SPDX
expression is written as a `LicenseExpression`, any other text as a
`SimpleLicensingText` reached through a `LicenseExpression` of one
`LicenseRef-loom-text-<hash>`, which the relationship targets. Your own `declared_license="NOASSERTION"` (any case) is
your statement: written as the `NoAssertionLicense` individual, and no source
replaces it. Any other placeholder, yours or a source's (`unknown`, blank, a
bare `other`), and a source's `NOASSERTION`, is no licence, written as nothing
and logged as nothing, so the next source may state one. A `declared_license=`
that is not a string raises `TypeError` (`option-invalid`). `other` with a `license_name` and/or
`license_link` (a Hugging Face card's fields) is written as that name followed
by the link, unless the name reads as an SPDX licence and the link does not
read as a different one: then the name alone is written. This is the rule for
dataset cards; a model card keeps `license_name` only as extra data. Each
field the licence was read from is named in the package's provenance
(`license: Source: data/corpus/README.md | Field: license`). A list of several
licences gives each its own `hasDeclaredLicense`, in order and once each (letter
case ignored), by the rules above (a bare `other` among them gives none), and
the package comment says the source does not state whether they combine as AND
or OR. A licence that holds no text (a number, a mapping), a `version` written
as a decimal number (YAML and JSON read `1.10` as `1.1`), a card `version` that
is not quoted text (YAML 1.1 reads `1:1:1` as `3661` and `010` as `8`: quote it,
`version: "1.0"`), and any other value of the wrong shape (a description that is
a list of several texts; a creator, URL or tag that is a number) is left out,
with one `WARNING:`. A card that cannot be read at all (frontmatter YAML cannot
parse: an impossible date such as `2024-02-30`, a number of thousands of digits,
nesting thousands of levels deep) is skipped with one `WARNING:`, and the
declaration goes on with its other sources: the card is read because the dataset
is a directory, not because you named it. A `croissant=` file you name is
different: a URL, a missing file (`input-not-found`), one that is not a regular
file (a FIFO), one that is not Croissant or has no name (`dataset-name-missing`),
or one nesting more than 64 levels of arrays and objects raises `ValueError`
naming it, at the call (a URL: `loom SDK: croissant: must be a local file, not a
URL` `[option-invalid]`): loom reads no network source. Any other
failure is an `InternalError`, also a `ValueError`. For the
library's `read_croissant`, a URL that cannot be reached is
`download-network-failed` or `download-timeout`. A source file is opened as given
and named in provenance by its path from the current directory, or its bare name
when outside it. Hashing and the registry do not change: the sources add
fields, not identity.

These `generates` edges are scoped `build` -- they describe a build-time
step, not something that runs in the shipped artefact. Contrast with the
`hasDataFile` relationship Pitloom emits when it detects a script *using*
a model file at runtime -- that one is scoped `runtime`. Static detection of
such scripts needs `scan_model_usage` (off by default); a `loom.run` that
declares `use_model` emits it regardless.

`loom.run` can also be used as a context manager instead of a decorator,
which lets a single run cover more than one independent output batch
without their lineage bleeding into each other. Pass `input_datasets=` on
`add_output_dataset()` to name exactly which `add_input_dataset()` calls a
given output derives from:

```python
labels = ("positive", "negative")
with loom.run("fragments/preprocess.json") as run:
    for split in ("train", "valid", "test"):
        sources = [f"rawdata/{split}/{label}.txt" for label in labels]
        for source in sources:
            run.add_input_dataset(source, dataset_type="text")
        run.add_output_dataset(
            f"data/{split}.txt", dataset_type="text", input_datasets=sources
        )
```

Omit `input_datasets` (the default) when a run has exactly one output
batch -- it then derives from every input the run declared.
`input_datasets=` matches the string an input was declared with, not its
resolved path: an input declared as `../data/t.txt` is not found by
`data/t.txt` (one `WARNING: loom SDK: add_output_dataset(...) names
input_datasets=..., which no add_input_dataset of this run declared; not
linked [reference-not-found/dataset]`), even though a registry keys
both to one package.

## Config

Register the fragment file(s) so a later `generate()`/`loom
project`/`loom generate` call merges them into the main SBOM:

```toml
[tool.pitloom.fragment]
files = ["fragments/train.json", "fragments/eval.json"]
```

`loom.run`/`loom.Run` calls `configure_logging()` as it begins, so its
`WARNING:` and `INFO:` lines carry their tag as on the CLI. Each run resets
the `pitloom` logger's level (`INFO`, or `DEBUG` with `PITLOOM_DEBUG`) and
replaces its handlers with one stderr handler; propagation to the root
logger is left alone, so an application's own root handler also prints them.

`loom.run` accepts the same creator/tool/timestamp overrides as the CLI
and build hook, via `creation_metadata=CreationMetadata(...)`. With none
given, the fragment records the unattended-run default (Pitloom itself as
both creator and tool). See [Creation metadata](creation-metadata.md).

Pass `id_registry=` (a path, or an already-loaded `IdRegistry`) to
consult a Loom ID registry when minting ids for datasets, the model, and
the generating script -- see [Loom ID registry](id-registry.md). A dataset
package whose path exists below the registry's project root is looked up by
that path, as the same package from any directory or spelling
(`../data/t.txt` from a subdirectory is `data/t.txt`), and by its content
digest when the entry records one; a remote, missing or outside-the-root
dataset by its name. A file (a dataset's, or the script) is looked up by its
path from the registry's project root and its hash, so it keeps its id from
any directory (a path outside the root gets a new id and a `WARNING:`). A file
reached through a symlinked directory is keyed by the path as written, which
`id generate` does not index, so it finds no entry. See [keys and content
gates](id-registry-keys.md). The one entry loom
writes is a model declared with `path=` (hashed when the run ends) whose file
the registry does not know, saved after the fragment;
`update-id-registry = false` in `pitloom_config` stops it.
As on every other surface, `loom.run`/`loom.Run` uses a registry only when
one is declared (`id_registry=`, or `id-registry` in `pitloom_config=`
below): with none, no registry is used -- nothing is searched for or
auto-discovered. A declared registry that is missing (or not a file) raises
`FileNotFoundError` (`input-not-found`), and one that is invalid (a format
version 3 or 2 file included) `ValueError`, when the `with loom.run(...)`
block (or the decorated call) begins, before any fragment work happens.

`loom.run` reads no `[tool.pitloom]` of its own. Pass `pitloom_config=` (a
`PitloomConfig`, or the path of a TOML file holding `[tool.pitloom]`, relative
to the current directory) to set `id-registry`, `update-id-registry`, `max-dataset-hash-bytes`,
`accept-url-credentials` or `url-credentials`; no other key has an effect
there. `id_registry=` wins
over the config's `id-registry`, and `max_dataset_hash_bytes=` over its
`max-dataset-hash-bytes`. A config file that is missing, unreadable or invalid raises `ValueError`
as the run begins.

The merge itself (`pitloom.assemble.merge_fragments`, run by
`generate()`/`generate_project_sbom()` whenever `[tool.pitloom.fragment]`
lists files) raises `pitloom.assemble.FragmentMergeError` if an element
of the merged graph references an id that resolves to nothing -- most
commonly a fragment recorded against a base SBOM whose ids have since
changed: regenerate the base SBOM and re-run the fragment-producing
script. It raises the same error, carrying the code `fragment-missing`, when a
fragment marked `required = true` could not be merged.
`generate_merged_sbom(fragments_dir)` merges a directory of fragments into one
document, as `loom merge` does; it raises the error too, and writes nothing,
when none of the fragments could be merged. See [SBOM
fragments](fragments.md) and [API reference](api.md#fragment-merging).
