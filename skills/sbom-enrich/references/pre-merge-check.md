---
Created: 2026-10-29
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pre-merge check: the one-liner and its interpreter

See also: `../SKILL.md` (step 7, which holds the rule: the check is mandatory)
and `examples.md` (section 3, the check on the worked example).

Read every drafted fragment (step 2's and step 6's) with the JSON-LD
deserialiser `merge_fragments()` itself uses. It catches malformed JSON and
many SPDX-shape errors (an unknown property on a known type, a wrongly typed
value, an element without an `spdxId`, a misspelled type that carries
properties) before registration. Otherwise a fragment that fails to read is
skipped with only a `WARNING:` (the merge fails if it is registered with
`required = true`), a wasted `loom` run. It does not catch a bare unrecognised
type with no other key, not even `spdxId` (read as an extensible object), or a
missing required property (step 10 does). Exit 0 is a pass. This is the one home
of the snippet.

It imports `spdx_python_model`, which only Pitloom's own environment has, so
run it with the interpreter Pitloom is installed in, not whichever `python3` is
on `PATH`:

```bash
python3 -c "import sys,io,pathlib; from spdx_python_model.bindings import v3_0_1 as s; [s.JSONLDDeserializer().read(io.BytesIO(pathlib.Path(p).read_bytes()), s.SHACLObjectSet()) for p in sys.argv[1:]]" model.enrich.spdx3.json fragments/agent-enrichment.spdx3.json
```

With no persistent install, replace `python3` by `uvx --from
"pitloom>=0.22.0" python` (or, with pipx, `pipx run --spec
"pitloom>=0.22.0" python`; its "already on your PATH" notice is harmless). With
`pipx install`, use the venv's interpreter (`$(pipx environment --value
PIPX_LOCAL_VENVS)/pitloom/bin/python`; `Scripts\python.exe` on Windows); on
Windows otherwise use `py` or `python`.

Do not use `uv run --with` for this: in a project directory it creates `.venv`
and `uv.lock` there and builds the project (running its build backend, against
the `--allow-build` hard rule).

Do not use `loom fragment validate` or `spdx3-validate` on a fragment: it
refers to the base SBOM's ids without an `ExternalMap`, so it fails SHACL on its
own (exit 1) in most cases, even when correct. The merged SBOM is validated at
step 10.
