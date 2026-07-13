"""Harness pass^k — tests (Phase 8.3, module #2).

pass^k = un cas passe ssi il réussit les k runs indépendants ; il démasque la
flakiness qu'un seul run (pass^1) cache. Ces tests OFFLINE prouvent que le harness
DISCRIMINE (stand-in déterministe → 1.0 ; flaky → < 0.85). Le pass^k RÉEL sur le
juge LLM est tier-2 (skipif clé) : test_judge_passk_real.
"""

import os
from pathlib import Path

import pytest
import yaml

from sandbox.evaluation.judge import DIMENSIONS, judge_answer
from sandbox.evaluation.passk import passes_k, passk_rate
from sandbox.llm import OpenRouterProvider


# ─── Stand-ins déterministes (offline) ────────────────────────────
def _always_pass(_case) -> bool:
    return True


def _flaky_on_case(bad_case, fail_run: int):
    """run_once flaky reproductible (sans aléa) : échoue au run `fail_run` de `bad_case`."""
    counters: dict = {}

    def run_once(case) -> bool:
        counters[case] = counters.get(case, 0) + 1
        return not (case == bad_case and counters[case] == fail_run)

    return run_once


# ─── passes_k : un cas ────────────────────────────────────────────
def test_passes_k_all_green_is_stable() -> None:
    assert passes_k(_always_pass, "case", k=3) is True


def test_passes_k_catches_flaky_that_pass1_hides() -> None:
    """LE point : un cas flaky (run 2 échoue) passe^1 mais échoue^3."""
    assert passes_k(_flaky_on_case("case", fail_run=2), "case", k=1) is True
    assert passes_k(_flaky_on_case("case", fail_run=2), "case", k=3) is False


def test_passes_k_rejects_bad_k() -> None:
    with pytest.raises(ValueError):
        passes_k(_always_pass, "case", k=0)


# ─── passk_rate : dataset ─────────────────────────────────────────
def test_passk_rate_all_stable_is_one() -> None:
    assert passk_rate(["a", "b", "c"], _always_pass, k=3) == 1.0


def test_passk_rate_discriminates_flaky_below_threshold() -> None:
    """3 cas stables + 1 flaky → 3/4 = 0.75 < 0.85 : le seuil attrape la flakiness."""
    run_once = _flaky_on_case("c1", fail_run=2)
    rate = passk_rate(["c0", "c1", "c2", "c3"], run_once, k=3)
    assert rate == 0.75
    assert rate < 0.85


def test_passk_rate_rejects_empty() -> None:
    with pytest.raises(ValueError):
        passk_rate([], _always_pass, k=3)


# ─── pass^k RÉEL du juge (tier-2, opt-in réseau) ──────────────────
_JUDGE_GOLDEN = Path("evals/judge_golden.yaml")


def _load_judge_golden():
    data = yaml.safe_load(_JUDGE_GOLDEN.read_text(encoding="utf-8"))
    return data["cases"], data["meta"]["tolerance_default"]


def _within_tolerance(actual: dict, expected: dict, tol: int) -> bool:
    return all(abs(actual[d] - expected[d]) <= tol for d in DIMENSIONS)


@pytest.mark.skipif(
    not (os.environ.get("RUN_LLM_PASSK") and "OPENROUTER_API_KEY" in os.environ),
    reason="opt-in réseau : RUN_LLM_PASSK=1 + OPENROUTER_API_KEY (k appels LLM/cas, ~1min + coût).",
)
def test_judge_passk_real() -> None:
    """pass^3 réel du juge sur judge_golden : cible >= 0.85.

    use_cache=False est CRITIQUE : sinon les runs 2..k tapent le cache → sortie
    trivialement identique → pass^k = 1.0 factice qui masquerait la flakiness.
    """
    cases, tol = _load_judge_golden()

    def run_once(case) -> bool:
        actual = judge_answer(
            customer_request=case["input"]["customer_request"],
            category=case["input"]["category"],
            cited_policy_excerpt=case["input"]["cited_policy_excerpt"],
            draft_reply=case["input"]["draft_reply"],
            use_cache=False,
            provider=OpenRouterProvider(),
        )
        return _within_tolerance(actual, case["expected"]["scores"], tol)

    rate = passk_rate(cases, run_once, k=3)
    assert rate >= 0.85, f"pass^3 = {rate:.2f} < 0.85 — juge flaky sur judge_golden"
