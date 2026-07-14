"""Canary / Shadow harness — tests (Phase 8, pattern 5).

Offline & DÉTERMINISTE (contraste avec les tiers-2 de 8.3). On teste le harness avec des
stand-ins synthétiques (agreement, classification des divergences, verdict de promotion),
PUIS une démo RÉELLE sur le changement BM25 stemming de 8.1 : le shadow doit montrer que
le stemming a CORRIGÉ ≥ 1 cas sans RIEN régresser → verdict PROMOTE.
"""

from pathlib import Path

import yaml

from sandbox.canary import promotion_verdict, shadow_run
from sandbox.retrieval.bm25 import BM25Index
from sandbox.retrieval.corpus import load_corpus

GOLDEN = Path("evals/golden.yaml")


# ─── Harness générique (offline, synthétique) ─────────────────────
def test_shadow_agreement_no_divergence() -> None:
    report = shadow_run(lambda x: x, lambda x: x, [1, 2, 3])
    assert report.agreement_rate == 1.0
    assert report.divergences == []


def test_shadow_classifies_improvement() -> None:
    report = shadow_run(lambda x: "wrong", lambda x: "right", ["a"], lambda x: "right")
    assert len(report.improvements) == 1
    assert not report.regressions


def test_shadow_classifies_regression() -> None:
    report = shadow_run(lambda x: "right", lambda x: "wrong", ["a"], lambda x: "right")
    assert len(report.regressions) == 1


def test_shadow_classifies_neutral() -> None:
    # Les deux faux, différemment → on ne peut pas dire qui est meilleur.
    report = shadow_run(lambda x: "wrongA", lambda x: "wrongB", ["a"], lambda x: "right")
    assert report.divergences[0].verdict == "neutral"


def test_shadow_without_golden_is_all_neutral() -> None:
    report = shadow_run(lambda x: "a", lambda x: "b", ["x"])
    assert report.neutrals and not report.improvements and not report.regressions


def test_promotion_holds_on_any_regression() -> None:
    report = shadow_run(lambda x: "right", lambda x: "wrong", ["a"], lambda x: "right")
    assert promotion_verdict(report) == "HOLD"


def test_promotion_promotes_when_only_improvements() -> None:
    report = shadow_run(lambda x: "wrong", lambda x: "right", ["a"], lambda x: "right")
    assert promotion_verdict(report) == "PROMOTE"


# ─── Démo RÉELLE : BM25 pré/post-stemming sur le golden ───────────
def test_canary_bm25_stemming_is_safe_promotion() -> None:
    """Le vrai changement de 8.1 rejoué en shadow : improvement + zéro régression."""
    corpus = load_corpus()
    old_idx = BM25Index(corpus, use_stemming=False)  # AVANT 8.1
    new_idx = BM25Index(corpus, use_stemming=True)  # APRÈS 8.1

    cases = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["cases"]
    golden = {c["when"]["question"]: c["then"]["policy_doc_id"] for c in cases}

    report = shadow_run(
        old_fn=lambda q: old_idx.query(q)[0][0].doc_id,
        new_fn=lambda q: new_idx.query(q)[0][0].doc_id,
        inputs=list(golden),
        golden_fn=lambda q: golden[q],
    )

    assert not report.regressions, f"le stemming a régressé : {report.regressions}"
    assert report.improvements, "le stemming devait corriger ≥ 1 cas (cancel-refund-normal)"
    assert promotion_verdict(report) == "PROMOTE"
