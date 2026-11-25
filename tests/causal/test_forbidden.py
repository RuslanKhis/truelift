"""C4: the ground-truth deny-list, and the encoded prefix agrees with the guard's (D13).

No test spells the hackathon prefix: it is taken from the guard and varied from there.
"""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

import yaml

from truelift.causal import forbidden
from truelift.causal.forbidden import DenyList, is_forbidden

REPO = Path(__file__).resolve().parents[2]


def _guard():
    spec = importlib.util.spec_from_file_location("guard_public", REPO / "scripts" / "guard_public.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_encoded_prefix_equals_the_guards() -> None:
    guard = _guard()
    assert base64.b64encode(guard.TRUTH_PREFIX.encode("ascii")).decode("ascii") == forbidden._TRUTH_PREFIX_B64


def test_private_prefix_is_denied_in_any_case() -> None:
    prefix = _guard().TRUTH_PREFIX
    for variant in (prefix, prefix.upper(), prefix.lower(), prefix.swapcase()):
        assert is_forbidden(variant + "_effect")
    assert not is_forbidden("x" + prefix)  # a prefix, not a substring


def test_synthetic_prefix_and_controls() -> None:
    assert is_forbidden("truth_roi")
    assert is_forbidden("TRUTH_baseline_revenue")
    for ok in ("revenue", "discount_rate", "untruth", "truthful_index"):
        assert not is_forbidden(ok)


def test_sidecar_columns_are_denied() -> None:
    truth = yaml.safe_load((REPO / "data" / "sample" / "truth.yaml").read_text())
    deny = DenyList.from_sidecar(truth | {"truth_columns": truth["truth_columns"] + ["Hidden_Effect"]})
    assert deny.is_forbidden("hidden_effect")
    assert deny.filter(["week", "truth_roi", "hidden_effect", "revenue"]) == ["week", "revenue"]
    assert not DenyList().is_forbidden("hidden_effect")
