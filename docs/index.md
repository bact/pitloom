---
Created: 2026-07-08
Last-Modified: 2026-08-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom

[![PyPI - Version](https://img.shields.io/pypi/v/pitloom)](https://pypi.org/project/pitloom/)
![GitHub License](https://img.shields.io/github/license/bact/pitloom)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/14001/badge)](https://www.bestpractices.dev/projects/14001)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/bact/pitloom/badge)](https://scorecard.dev/viewer/?uri=github.com/bact/pitloom)
[![DOI](https://img.shields.io/badge/doi-10.5281%2Fzenodo.19246283-blue)](https://doi.org/10.5281/zenodo.19246283)

**Pitloom** automates the generation of SPDX 3-compliant SBOMs for AI models
and Python projects, documenting the composition and provenance of software
systems. It reads metadata directly from Python packages and AI models
(GGUF, ONNX, PyTorch, Safetensors) and offers native Hatchling integration
so SBOMs can be generated automatically as part of a build.

When used with Hatchling, it embeds the generated SBOM directly into
the Python distribution package (wheel) `.dist-info/sboms` --
follows [PEP 770].

[PEP 770]: https://peps.python.org/pep-0770/

## Install

```bash
pip install pitloom
```

Install with AI model metadata extraction support:

```bash
pip install "pitloom[ai]"
```

Install with extra content type detection:

```bash
pip install "pitloom[content-type]"
```

## Pick your usage surface

Pitloom generates the same kind of SBOM regardless of how you invoke it
(so long as it's the same target) -- pick the page for how you actually
want to run it. Each page has its own quick guide, install steps, usage
details, config, and code examples.

| Surface | Reach for this when... |
| :--- | :--- |
| [Command line](cli.md) (`loom`) | You want a one-off SBOM from a terminal, a Makefile target, or any shell script. |
| [Python API](python-api.md) | You are calling Pitloom from Python code you control, or want to track provenance during training/evaluation. |
| [Hatchling build hook](hatchling-build-hook.md) | You build wheels with Hatchling and want an SBOM embedded automatically (PEP 770). |
| [GitHub Action](github-action.md) | Your project isn't Hatchling-based, or you just want CI to produce an SBOM artifact with one `uses:` line. |
| [Agent Skills](agent-skills.md) | You want an AI coding agent to generate (and optionally enrich or validate) an SBOM on request. |
| [Claude Code plugin](claude-code-plugin.md) | You use Claude Code and want the Skills installable with one command. |

## Reference docs

Background reading -- useful for auditing or debugging a generated SBOM,
not needed to just generate one:

- [Configuration](configuration.md) -- every `[tool.pitloom]` setting,
  its default, and how to reach it from each surface.
- [Creation metadata](creation-metadata.md) -- who/what/when/how every
  Pitloom-generated element records about its own creation.
- [Metadata provenance](metadata-provenance.md) -- how Pitloom tracks the
  source of each metadata field for auditability.
- [Resources](resources.md) -- SBOM, AIBOM, SPDX, and related standards
  reading list.
- [Project README](https://github.com/bact/pitloom#readme) for more information.

## Security

For supported versions and vulnerability reporting guidelines,
please read our [Security policy][security].

[security]: https://github.com/bact/pitloom/security/policy

## Citation

If you use Pitloom in your academic work, please cite it as follows:

> Suriyawongkul, A. (2026). Pitloom - SBOM generator for AI models and Python projects (Version 0.16.2) [Computer software]. https://doi.org/10.5281/zenodo.19246283

BibTeX:

```bibtex
@software{Suriyawongkul_Pitloom_-_SBOM_2026,
    author = {Suriyawongkul, Arthit},
    doi = {10.5281/zenodo.19246283},
    month = aug,
    title = {{Pitloom - SBOM generator for AI models and Python projects}},
    url = {https://github.com/bact/pitloom},
    version = {0.16.2},
    year = {2026}
}
```
