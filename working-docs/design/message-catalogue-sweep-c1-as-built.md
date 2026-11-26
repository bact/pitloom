---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-26
Last-Modified: 2026-11-26
---

# Message catalogue sweep C1: as built

See also: [message-catalogue-sweep-c1-plan.md](message-catalogue-sweep-c1-plan.md)
(the plan, its rulings Q1-Q9 and the per-item design this records the
differences from).

## C1a as built (PR #545, 2026-11-26)

Built as planned, with these differences (plan claims found wrong are
marked):

- **A1**: the empty-input rule lives in the input probe
  (`messages/_input_not_found_say._input_stat`: an empty spelling is
  nothing there), so every surface reaching `input_exists`/`is_input_file`
  shares it; `refuse_empty_input` covers the entries that never probe
  (`require_wheel_path`, `generate`, the model and project entries, `loom
  id`, the loom `pitloom_config=`). An empty `-o`, `--project-dir`,
  `--id-registry` (CLI) and `loom.run("")`/`id_registry=""` (SDK) are
  `option-invalid` `non-empty`. `loom id generate ""` is checked where any
  missing PATH is, so both say `option-missing` without a registry.
- **A2**: `namespace_invalid` is in `messages/_options_say.py`, not
  `core/iri.py` (plan wrong).
- **A10**: ENAMETOOLONG is "missing" only when a component is longer than
  255 bytes (`path_probe.names_too_long_component`): a whole path past
  PATH_MAX whose parts exist is still a read failure (a scan warns
  `dir-unlistable`), as the ruling's "a name the file system cannot hold"
  means. An empty library `output_path` or `id_registry` (and
  `[tool.pitloom] id-registry = ""`, `config-invalid`) is refused first,
  as on the CLI.
- **A3**: the inventory took the best kind of any call in a helper's body,
  not "the first coded return" (plan wrong); now every return branch
  (`IfExp`, `BoolOp`, each assignment of a returned name) is judged, and a
  recursive call is neutral. `_render.py` no longer recurses forever on a
  parameter passed through a recursive call (pre-existing crash).
- **A7**: `file_unreadable_error(dir=".")` cannot carry a gone cwd (ENOENT
  is refused as absent, plan wrong): `current_dir_error` and an `ERROR` `DIR=`
  line say it. `resolve_registry` takes `None` for "the current directory,
  read only when a relative registry needs it", so an absolute-path run never
  reads the cwd. `id_registry/_registry.root_dir()` keeps `os.getcwd()`: its
  callers degrade on `OSError` by contract.
- **A8**: `READ_USES` is the one `use` vocabulary for reads and writes;
  `FRAGMENT_USE` joins it.
- **A9**: a NUL in a local `croissant=` is `input-not-found`, read by
  `_extract_utils._read_local`; other refusals keep `for the Croissant
  document`.
- **A11**: the `argument --namespace:` frame cannot carry
  `credentials-unsafe/registry`, so `loom id generate` checks the namespace
  with the library's `require_registry_namespace` after parsing (exit 1).
- **A12**: `PitloomConfig` configures logging only when its basename will
  warn (`file_names.bare_sbom_base`), so a library caller's logger is kept.
- **A15**: the report-only full run found 0 uncoded records in wider-scoped
  fixtures; the check is on, installed when `tests/conftest.py` is imported.
- **R1** (C2 ruling 10): each missing `input_datasets` name once per output.

### Follow-ups (not in C1a)

- A RELATIVE path with the current directory removed still fails uncoded
  where it is resolved before any probe: `cli/id.py`
  (`_normalized_absolute`, a relative `--project-dir`, `id import`'s
  `.resolve()`), `_embed_generate.py`, `_embed_wheel_batch.py`
  (`Path(project_dir).resolve()`), `id_registry/resolve.py`,
  `_loom_caller.py` (`os.getcwd()`); a relative project path then says
  `input-not-found`, not `DIR=.`.
- `generate("   ")` (blank, not empty) strips to `""` and reads the cwd; the
  CLI names `'   '` as not found.
- `tests/extract/project/test_setuptools_hostile.py::test_a_long_unread_value_is_cut_in_the_warning`
  fails under a long `--basetemp` (the path is part of the cut text).
- The inventory still takes the best kind of the calls inside one value
  (`ValueError(str(CodedValueError(...)))` reads coded).
- `tests/messages/test_drift_strict.py` is 519 lines: split the child-pytest
  tests out.
- `discovery_chdir`'s gone-cwd line says "for resolving relative paths".
- `IdRegistry.load("")` names `.`, and `IdRegistry.save("")` raises an
  uncoded `ValueError`; `Path("")` cannot be told from `.` anywhere.
- `NAME_MAX_BYTES` counts bytes: an APFS name of 128-255 non-ASCII
  characters inside a path past PATH_MAX would read as missing.

## Plan section 9: overlap, as planned

- **Masking PR**: owns `logging_config.py` (split plus `one_line`, Q8),
  `core/url_masking/`, `log_masking.py`. C1a touches
  `messages/_field_writers.py` (A2, raise types only): the masking PR may
  reorder mask/cut/escape there; land masking first, C1a rebases (small).
  B1 does not edit `log_masking.py` (its handlers are allowlisted).
- **C2**: owns docs/skills quotes, per-line `since`, `ELEMENT=`, wording of
  the conflict, over-cap and author lines. Shared: `messages/_types.py`
  (C2 adds `Line.since`; C1a A2 changes `line_for`'s raise) and the
  generated pages. **Order: masking, C1a, C2, C1b.** C2 after C1a so its
  quote sweep sees C1a's new lines and sets their `since`; if C2 lands
  first, C1a's new lines carry `since="0.25.0"` explicitly. C1b last: it
  is a re-runnable mechanical conversion, so rebasing it is cheap.

## Appendix: plan probes at 4c194136 (abridged)

```text
loom wheel ""          ERROR: loom wheel: file='' is not a file
loom enrich ""         ERROR: loom enrich: '.': not an AI model file ... [model-wrong-format]
loom merge ""          WARNING: FILE=.markdownlint.json: SBOM fragment is not ... (merges the cwd)
loom project -o ""     ERROR: loom project: FILE=.: could not write for the SBOM; Is a directory [file-unwritable]
input_datasets="a.txt" 5 x WARNING: ... names input_datasets='a' / '.' / 't' / 'x' / 't' ...
[["a.txt"]]            TypeError code=None: unhashable type: 'list' (at exit, no fragment)
set_model(None)        TypeError code=None: Value must be of type str. Got NoneType
set_model_hyperparameters(["a"])  AttributeError code=None
dataset_type="bogus"   fragment dtypes ['text']
croissant="a\x00b"     ValueError code=None: embedded null byte
loom.run(), cwd gone   FileNotFoundError code=None at __enter__
any loom command, cwd gone   Traceback ... project.py default=Path.cwd()
loom.run("ro/f.json")  PermissionError code=None
loom enrich/model <300a>.gguf  ERROR: ... [Errno 63] File name too long (3.10/3.11/3.13 macOS)
--namespace https://user:ghp_...@   CLI [option-invalid]; IdRegistry(namespace=) [credentials-unsafe/registry]
symlink link.py -> real/s.py  software_File real/s.py; provenance Source: link.py
AST: 214 broad handlers; 16 guarded, 11 re-raise, 145 swallow, 42 convert (106 files)
```
