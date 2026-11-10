---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Python API: remote targets

See also: [Python API](python-api.md) (the generator functions and the rest
of the library), [API reference](api.md) (exact signatures),
[SBOM from a Git URL](git-urls.md) and [SBOM from a PyPI URL](pypi-urls.md).

Reading a project, a model or a release from a URL with the library. The
examples assume these imports:

```python
from pathlib import Path
```

A project in a Git repository is read through its URL, with `generate()`,
`generate_git_sbom()` or `generate_git_project_sbom()` (the last reads a project
only; `generate_git_sbom(url, sbom_kind="project")` is the same):

```python
from pitloom.assemble import generate_git_project_sbom

generate_git_project_sbom(
    "https://gitlab.com/group/project/-/tree/main/services/api",
    output_path=Path("sbom.spdx3.json"),
    check_url=my_address_check,  # called with each redirect target before it is asked
)
```

The repository is fetched shallowly into a temporary directory that is removed
on return. It is untrusted: its own `[tool.pitloom]` is ignored unless you pass
`pitloom_config=`, and its own build-time code (Hatchling metadata hooks,
setuptools `cmdclass`, PDM hooks) is not run while its files are listed. A failure is a
`pitloom.extract.remote.RemoteSourceError` whose `code` names it
(`git.clone-failed`, `git.timeout`, `git.ref-not-found`, `git.path-not-found`,
`git.no-project`, `git.url-invalid`, `git.offline`, `git.too-many-redirects`,
`git.not-found`, `git.output-too-large`, `git.too-large`); the two size codes
also carry the catalogued code `over-cap` as `pitloom_code`
(`pitloom.messages.code_of(exc)`; see
[Message codes](message-codes.md#over-cap)). *check_url* may raise any
exception to refuse an address, and it reaches you unchanged. To read the
fetched project yourself, use `pitloom.extract.remote.fetch_git_project(url)`,
a context manager yielding a `GitCheckout` (`folder` is the directory to read,
`commit` the commit checked out). Reads inside the block are confined to the
checkout and the repository's build-time code is not run, as for
`generate_git_sbom()`, with no further call (`with checkout.reading():` is
optional and may be nested); blocks that overlap in time each keep their own
confinement. Its *max_bytes* (no limit by default) stops the fetch, with
`git.too-large`, once the checkout takes more disk than that; the generators
take `max_download_bytes=` instead (else `pitloom_config=`'s
`max-download-bytes`, else 512 MiB, as for a PyPI URL; `over-cap` as
`pitloom_code`). See [SBOM from a Git URL](git-urls.md).

The wheel or the sdist of a release on PyPI is read through the URL of its
project or release page, with `generate()`, `generate_wheel_sbom()`,
`generate_project_sbom()` (each given the URL as a `str`) or
`generate_pypi_sbom()`:

```python
from pitloom.assemble import generate, generate_pypi_sbom

generate_pypi_sbom(
    "https://pypi.org/project/demo/1.0/",
    kind="wheel",  # "wheel" (an Analyzed SBOM) or "sdist" (a Source SBOM)
    max_download_bytes=256 * 1024 * 1024,
    check_url=my_address_check,  # every URL of the lookup and download
    output_path=Path("sbom.spdx3.json"),
)

# generate() reads a PyPI URL as `loom generate` does: the wheel, with an
# INFO: naming `loom project <url>` for the sdist.
generate("https://pypi.org/project/demo/", output_path=Path("sbom.spdx3.json"))
```

The file is downloaded into a temporary directory removed on return, its SHA-256
checked against the one PyPI declares, and read as a local file; the SBOM
carries one provenance record of how it was obtained. A PyPI URL is never
sent to Git. `max_download_bytes=` (else `pitloom_config=`'s
`max-download-bytes`, else 512 MiB) caps the file; a value that is not an
integer of at least 1 raises `ValueError` on every target, and on a target
that downloads nothing it warns that it has no effect. A malformed URL raises
a `pitloom.messages.CodedValueError` (`pypi-url-invalid`); any other failure is
a `pitloom.extract.remote.RemoteSourceError` whose `code` (`pypi.*`) names it
and whose `pitloom_code` is the catalogued code (see [Message
codes](message-codes.md)). *check_url* is called with every URL of the release
lookup and the download before it is requested (the JSON API's, the file's and
each redirect target); the PyPI lookup of a dependency's licence and
originator (made unless `offline` is true) does not pass through it. It may raise any exception to refuse an address, and it reaches you
unchanged. `generate_pypi_sbom_with_download()` returns
`PypiSbom(sbom, download, metadata)`. `generate_git_sbom()` and
`generate_git_project_sbom()` refuse PyPI-family URLs (`git.url-invalid`, with
`pypi-url-unusable` as `pitloom_code`); `generate()` names the library route in
its hint. `offline=True` raises
`pypi.offline` before any request. AI models in a downloaded wheel are gated
as a Git URL's are (`reader-unsafe/remote`), and `trust_model_files=True`
lifts the gate for a release you trust; an sdist's models are not scanned, so
for `kind="sdist"` it warns that it has no effect. See [SBOM from a PyPI URL](pypi-urls.md).

A URL can name an AI model instead: a `blob` or `raw` page of a model file, or
a folder (or the repository) holding one. `generate()` and
`generate_git_sbom()` choose between the project and the model by what the URL
names; `sbom_kind` fixes the choice:

```python
from pitloom.assemble import generate_git_sbom

generate_git_sbom(
    "https://github.com/owner/repo/blob/main/models/m.keras",
    sbom_kind="model",  # "auto" (the default), "project" or "model"
    output_path=Path("model.spdx3.json"),
)
```

`"auto"` reads a model file the URL names (even beside a project), else the
folder's project, else the folder's one model file; `"model"` reads the named
file, else the folder's one model file. The folder is read non-recursively.
Several model files, or neither a project nor a model, raise a
`pitloom.messages.CodedValueError` (a `ValueError`; codes `model-ambiguous`,
`project-or-model-not-found`, see [Message codes](message-codes.md)); with
`git.no-project` a `RemoteSourceError`, which keeps the code
`project-or-model-not-found` as `pitloom_code`, names subprojects when the
repository has some. A Git LFS pointer raises `ValueError` coded `lfs-pointer`.
The readers of fastText, HDF5 and ONNX files (C/C++ libraries), PyTorch
`.pt`/`.pth` files (a pickle parser) and GGUF files (a parsing loop a crafted
file can make very slow or very large) are not run on a file from a Git URL,
whether a model SBOM describes it or a project's build file list holds it
(`"project"`, or `"auto"` with a project config): it is listed with its name,
format and hash only, and one `INFO:` per SBOM says so, unless you pass
`trust_model_files=True` for a repository you trust. Keras, Safetensors,
NumPy, CRFsuite and PT2 files are read in full. `generate_project_sbom()` on
a local directory reads every format. `check_url=`, `offline=` and `max_download_bytes=` apply as for a project;
options a model SBOM cannot use warn once.
