# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read the base document an ``enrich_model(project_target=...)`` fragment
names, from the fragment itself.

The fragment's enrichment ``Annotation`` has the project's ``ai_AIPackage``
as its ``subject``, an IRI in the base document's namespace -- the one its
``SpdxDocument`` has as ``spdxId``. Comparing the two is what a merge relies
on.

See also: :mod:`tests.assemble.test_model_generator_doc_identity`,
:mod:`tests.assemble.test_explicit_config_edges` and
:mod:`tests.test_unreadable_file_surfaces`, which use it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pitloom.assemble import enrich_model
from pitloom.core.creation import CreationMetadata
from tests.cli.shared import SAFETENSORS_FIXTURE

_PINNED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")


def enrich_base_namespace(project: Path, model_dir: Path, **kwargs: Any) -> str:
    """The document namespace an enrichment fragment for *project* names.

    Writes a model with a README (so enrichment has a result to annotate)
    into *model_dir*, outside *project*, then runs :func:`enrich_model` with
    ``project_target=project`` and *kwargs*.
    """
    model_dir.mkdir(parents=True, exist_ok=True)
    model = model_dir / "model.safetensors"
    shutil.copyfile(SAFETENSORS_FIXTURE, model)
    (model_dir / "README.md").write_text(
        "---\ndatasets:\n  - tiny-imagenet\n---\n", encoding="utf-8"
    )
    fragment = json.loads(
        enrich_model(model, project_target=project, creation_metadata=_PINNED, **kwargs)
    )
    subject: str = next(
        e["subject"]
        for e in fragment["@graph"]
        if e.get("type") == "Annotation"
        and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
    )
    return subject.partition("#")[0]


def sbom_namespace(sbom_json: str) -> str:
    """The ``SpdxDocument`` ``spdxId`` of a generated SBOM."""
    graph = json.loads(sbom_json)["@graph"]
    doc_id: str = next(o["spdxId"] for o in graph if o["type"] == "SpdxDocument")
    return doc_id
