---
Created: 2026-07-08
Last-Modified: 2026-10-07
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

**Pitloom** automates the generation of [SPDX 3]-compliant
software bills of materials (SBOMs) for Python applications and AI models.

It extracts metadata directly from Python projects, whether declared in
the standard `[project]` table (Flit, Hatchling, PDM, uv_build and others),
Poetry's `[tool.poetry]`, or setuptools' `setup.cfg` and `setup.py`,
and from leading AI model formats,
including PyTorch, ONNX, Safetensors, GGUF, and fastText.

With native Hatchling integration and an official GitHub Action,
Pitloom embeds SBOMs directly into your wheel distribution under
`.dist-info/sboms`, following the
PyPA [Package Installation Metadata][dist-info] specification ([PEP 770]) --
offering software supply chain transparency without disrupting
the build pipeline.

[SPDX 3]: https://spdx.github.io/spdx-spec/
[dist-info]: https://packaging.python.org/en/latest/specifications/recording-installed-packages/#the-dist-info-directory
[PEP 770]: https://peps.python.org/pep-0770/

## Install

```bash
pip install pitloom
pip install "pitloom[ai]"            # AI model metadata extraction
pip install "pitloom[content-type]"  # content type detection (magika)
pip install "pitloom[validate]"      # SPDX 3 schema/SHACL validation
```

## Pick your usage surface

Pitloom generates the same kind of SBOM for the same target on every surface.
Each page has a quick guide, install steps, usage details, config and code
examples.

| Surface | Reach for this when... |
| :--- | :--- |
| [Command line](cli.md) (`loom`) | You want a one-off SBOM from a terminal, a Makefile target or a shell script. |
| [Python API](python-api.md) | You call Pitloom from Python code, or want to track provenance during training/evaluation. |
| [Hatchling build hook](hatchling-build-hook.md) | You build wheels with Hatchling and want an SBOM embedded automatically (PEP 770). |
| [GitHub Action](github-action.md) | Your project is not Hatchling-based, or you want CI to produce an SBOM artifact. |
| [Agent Skills](agent-skills.md) | You want an AI coding agent to generate (and optionally enrich or validate) an SBOM on request. |
| [Claude Code plugin](claude-code-plugin.md) | You use Claude Code and want the Skills installed with one command. |

## Guides

- [Wheel SBOMs and PEP 770 embedding](wheel-sbom.md) -- `embed-wheel`,
  `verify-wheel`, `validate-wheel`, the package hash.
- [SBOM fragments](fragments.md) -- merge, validate and list fragments.
- [Loom ID registry](id-registry.md) -- keep `spdxId`s stable across fragments
  and runs.
- [Building a project (`--allow-build`)](allow-build.md) -- discover a
  project's real file list with its own build backend.
- [AI model formats](ai-model-formats.md) and [AI model scan
  limits](ai-model-scan-limits.md).

## Reference

Background for auditing or debugging a generated SBOM, not needed to just
generate one:

- [Configuration](configuration.md) -- every `[tool.pitloom]` setting, its
  default, and how to reach it from each surface.
- [Dependency sources and precedence](dependency-sources.md) -- what a Source
  SBOM's dependency list holds, which lock file wins, and which commands use
  lock files.
- [Creation metadata](creation-metadata.md) -- who/what/when/how each element
  records about its own creation.
- [Metadata provenance](metadata-provenance.md) -- how Pitloom tracks the
  source of each metadata field.
- [Resources](resources.md) -- SBOM, AIBOM, SPDX and related standards reading
  list.
- [Project README](https://github.com/bact/pitloom#readme).

## Security

For supported versions and vulnerability reporting guidelines,
please read our [Security policy][security].

[security]: https://github.com/bact/pitloom/security/policy

## Citation

If you use Pitloom in your academic work, please cite it as follows:

> Suriyawongkul, A. (2026). Pitloom - SBOM generator for AI models and Python projects (Version 0.20.0) [Computer software]. <https://doi.org/10.5281/zenodo.19246283>

BibTeX:

```bibtex
@software{Suriyawongkul_Pitloom_SBOM_2026,
    author = {Suriyawongkul, Arthit},
    doi = {10.5281/zenodo.19246283},
    month = aug,
    title = {{Pitloom - SBOM generator for AI models and Python projects}},
    url = {https://github.com/bact/pitloom},
    version = {0.20.0},
    year = {2026}
}
```
