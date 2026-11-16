# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``--accept-url-credential`` and ``--refuse-url-credentials``: on every
command that writes an SBOM (``loom id`` takes the second alone), checked
as fingerprints without echoing the value, and united with
``[tool.pitloom] accept-url-credentials`` and ``url-credentials``.

See also: :mod:`tests.core.test_credential_policy` (the policy itself).
"""

from __future__ import annotations

import argparse

import pytest

from pitloom.cli._parser_credentials import credential_policy_from_args
from pitloom.cli.options_config import overrides_from_options, run_options
from pitloom.cli.parser import _build_parser
from pitloom.core.config import parse_pitloom_config
from pitloom.core.config_cascade import apply_overrides
from pitloom.core.credential_policy import CredentialPolicy

_A = "sha256:" + "a" * 16
_B = "sha256:" + "b" * 20
_ACCEPT = "--accept-url-credential"
_REFUSE = "--refuse-url-credentials"
_FLAGS = (_ACCEPT, _REFUSE)

#: Leaf commands that write no SBOM, and the flags each takes all the same.
_NO_SBOM: dict[str, tuple[str, ...]] = {
    "verify-wheel": (),  # reads a wheel's SBOM, writes none
    "validate-wheel": (),  # reads a wheel's SBOM, writes none
    "fragment validate": (),  # reads an SBOM, writes none
    "fragment list": (),  # lists fragments, writes no SBOM
    # An ID registry key or file entry follows the mode; no fingerprint.
    "id generate": (_REFUSE,),
    "id import": (_REFUSE,),
}


def _leaves() -> dict[str, argparse.ArgumentParser]:
    """Every leaf subcommand of the real parser, by its command path."""
    found: dict[str, argparse.ArgumentParser] = {}

    def walk(parser: argparse.ArgumentParser, prefix: str) -> None:
        # pylint: disable-next=protected-access
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            found[prefix] = parser
        for action in subs:
            for name, child in action.choices.items():
                walk(child, f"{prefix} {name}".strip())

    walk(_build_parser(), "")
    return found


def _options(parser: argparse.ArgumentParser) -> set[str]:
    # pylint: disable-next=protected-access
    return {s for action in parser._actions for s in action.option_strings}


def test_every_sbom_command_takes_both_flags() -> None:
    """A new subcommand must take the flags or be listed in ``_NO_SBOM``."""
    leaves = _leaves()
    assert set(_NO_SBOM) <= set(leaves), sorted(set(_NO_SBOM) - set(leaves))
    for path, parser in sorted(leaves.items()):
        has = set(_FLAGS) & _options(parser)
        expected = set(_NO_SBOM.get(path, _FLAGS))
        assert has == expected, path


@pytest.mark.parametrize("command", ["generate", "import"])
def test_id_takes_the_refuse_flag(command: str) -> None:
    target = "s.json" if command == "import" else "."
    assert _parse("id", command, target).refuse_url_credentials is None
    args = _parse("id", command, target, _REFUSE)
    assert args.refuse_url_credentials is True


def _parse(*argv: str) -> argparse.Namespace:
    return _build_parser().parse_args(list(argv))


@pytest.mark.parametrize(
    "command", [("wheel", "x.whl"), ("merge", "frags"), ("env",)], ids=str
)
def test_flags_give_a_policy(command: tuple[str, ...]) -> None:
    assert credential_policy_from_args(_parse(*command)) is None
    args = _parse(
        *command,
        "--accept-url-credential",
        _A,
        "--accept-url-credential",
        _B,
        _REFUSE,
    )
    assert credential_policy_from_args(args) == CredentialPolicy(
        accepted=frozenset({_A, _B}), refuse=True
    )
    refuse_only = credential_policy_from_args(_parse(*command, _REFUSE))
    assert refuse_only == CredentialPolicy(refuse=True)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("ghp_" + "x" * 36, id="pasted-token"),
        pytest.param("sha256:" + "A" * 16, id="uppercase"),
        pytest.param("sha256:" + "a" * 15, id="15-hex"),
    ],
)
def test_a_bad_fingerprint_is_refused_without_echo(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as info:
        _parse("wheel", "x.whl", "--accept-url-credential", value)
    assert info.value.code == 2
    err = capsys.readouterr().err
    assert "argument --accept-url-credential: not a fingerprint" in err
    assert value not in err


def test_cli_and_pyproject_fingerprints_unite() -> None:
    cfg = parse_pitloom_config({"tool": {"pitloom": {"accept-url-credentials": [_A]}}})
    args = _parse("wheel", "x.whl", "--accept-url-credential", _B)
    merged = apply_overrides(cfg, overrides_from_options(run_options(args, cfg)))
    assert merged.accept_url_credentials == (_A, _B)
    assert merged.url_credentials == "warn"
    flagged = apply_overrides(
        cfg,
        overrides_from_options(run_options(_parse("wheel", "x.whl", _REFUSE), cfg)),
    )
    assert flagged.accept_url_credentials == (_A,)
    assert flagged.url_credentials == "refuse"


def test_a_flag_without_refuse_keeps_the_pyproject_refuse_mode() -> None:
    """CLI > pyproject > default, as far as a store-true flag goes: there is
    no flag to turn the project's refusal off."""
    cfg = parse_pitloom_config({"tool": {"pitloom": {"url-credentials": "refuse"}}})
    args = _parse("wheel", "x.whl", _ACCEPT, _B)
    merged = apply_overrides(cfg, overrides_from_options(run_options(args, cfg)))
    assert merged.url_credentials == "refuse"
    assert merged.credential_policy == CredentialPolicy(
        accepted=frozenset({_B}), refuse=True
    )


def test_omitted_flags_leave_the_config_unchanged() -> None:
    cfg = parse_pitloom_config({"tool": {"pitloom": {"accept-url-credentials": [_A]}}})
    options = run_options(_parse("wheel", "x.whl"), cfg)
    assert options.get("credentials") is None
    assert apply_overrides(cfg, overrides_from_options(options)) == cfg
