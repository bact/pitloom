# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How a ``loom.run`` relates its model to the datasets it added: a run
that creates the model (``set_model()``, ``generated`` true or not given)
trained it on each :func:`~pitloom.loom.add_dataset` dataset
(``trainedOn``); a run that only uses it (``use_model()``,
``set_model(generated=False)``) tested it on them (``testedOn``), once
each, with its validation datasets. The ends are read back through the
SPDX 3 bindings: from the ``ai_AIPackage`` to ``dataset_DatasetPackage``
elements.

See also: :mod:`tests.core.test_loom` (``loom.run`` basics),
:mod:`tests.core.test_loom_dataset_dedup` (one package per dataset).
"""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom

#: Files written and read back through ``chdir``: run on every OS.
pytestmark = pytest.mark.platform

_TRAINED = spdx3.RelationshipType.trainedOn
_TESTED = spdx3.RelationshipType.testedOn


def _ends(fragment: Path) -> dict[str, list[tuple[str, list[str]]]]:
    """Each model-dataset relationship of *fragment* by type: the model's
    and the datasets' names, in order. The ends must be an
    ``ai_AIPackage`` and ``dataset_DatasetPackage`` elements."""
    objects = spdx3.SHACLObjectSet()
    with fragment.open("rb") as handle:
        spdx3.JSONLDDeserializer().read(io.BytesIO(handle.read()), objects)
    found: dict[str, list[tuple[str, list[str]]]] = {}
    for rel in objects.foreach_type(spdx3.Relationship):
        if rel.relationshipType not in (_TRAINED, _TESTED):
            continue
        model = rel.from_
        assert isinstance(model, spdx3.ai_AIPackage)
        names: list[str] = []
        for dataset in rel.to:
            assert isinstance(dataset, spdx3.dataset_DatasetPackage)
            names.append(str(dataset.name))
        found.setdefault(str(rel.relationshipType), []).append((str(model.name), names))
    return {kind: sorted(pairs) for kind, pairs in found.items()}


def _run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: Callable[[], None]
) -> Path:
    """*body* in a ``loom.run`` from *tmp_path*; the fragment written."""
    monkeypatch.chdir(tmp_path)
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_bytes(name.encode())
    out = tmp_path / "f.json"
    with loom.run(out):
        body()
    return out


def _declare(how: str) -> None:
    """Declare the model ``m`` as *how* says."""
    if how == "use":
        loom.use_model("m")
    elif how == "not-generated":
        loom.set_model("m", generated=False)
    elif how == "generated":
        loom.set_model("m", generated=True)
    else:
        loom.set_model("m")


@pytest.mark.parametrize(
    ("how", "kind"),
    [
        ("set", _TRAINED),
        ("generated", _TRAINED),
        ("use", _TESTED),
        ("not-generated", _TESTED),
    ],
    ids=["set-model", "generated", "use-model", "generated-false"],
)
def test_an_added_dataset_is_trained_or_tested_on(
    how: str, kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def body() -> None:
        _declare(how)
        loom.add_dataset("a.txt")

    assert _ends(_run(tmp_path, monkeypatch, body)) == {kind: [("m", ["a.txt"])]}


@pytest.mark.parametrize("how", ["use", "set"], ids=["use-model", "set-model"])
def test_validation_datasets_stay_tested_on(
    how: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dataset added both ways is one ``testedOn`` in a use-only run;
    a training run keeps both relationships."""

    def body() -> None:
        _declare(how)
        loom.add_dataset("a.txt")
        loom.add_validation_dataset("a.txt")
        loom.add_validation_dataset("b.txt")

    tested = [("m", ["a.txt"]), ("m", ["b.txt"])]
    wanted = (
        {_TESTED: tested}
        if how == "use"
        else {_TRAINED: [("m", ["a.txt"])], _TESTED: tested}
    )
    assert _ends(_run(tmp_path, monkeypatch, body)) == wanted


def test_the_last_declaration_decides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run's model is its last declaration, and so is its role: a used
    model declared after a trained one makes every dataset ``testedOn``."""

    def body() -> None:
        loom.set_model("n")
        loom.add_dataset("a.txt")
        loom.use_model("m")

    assert _ends(_run(tmp_path, monkeypatch, body)) == {_TESTED: [("m", ["a.txt"])]}
