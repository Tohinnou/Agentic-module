"""
Tests EDD du Policy Server (Phase 6).

Discipline (§6 CLAUDE.md) : ce fichier est écrit AVANT que policy_server
soit implémenté. TOUS les tests parametrisés FAIL au démarrage
(NotImplementedError).

Ils passeront progressivement :
- Après 6.1 (structural_gate) : adv_07, adv_09
- Après 6.2 (semantic_gate)   : adv_01..06, adv_08, adv_10
- Après 6.3 (vibe_diff)       : invariant hitl_has_vibe_diff

Les tests de contrat sur la fixture (test_fixture_*) passent dès Phase 6.0
— ils valident la structure du YAML sans invoquer check().
"""

from __future__ import annotations
import copy
from pathlib import Path

import pytest
import yaml

from sandbox.policy_server import PolicyDecision, check


FIXTURE_PATH = Path(__file__).parent.parent / "evals" / "adversarial_policy.yaml"


def _load_fixture() -> dict:
    """Charge le YAML de la fixture d'attaques."""
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


FIXTURE = _load_fixture()
CASES = FIXTURE["cases"]


# ─── Tests de contrat sur la fixture (passent dès Phase 6.0) ───────────


def test_fixture_declares_targets() -> None:
    """La fixture doit déclarer ses cibles machine-lisibles."""
    assert "targets" in FIXTURE
    targets = FIXTURE["targets"]
    assert targets["verdict_accuracy_min"] >= 0.90, (
        "Cible verdict_accuracy_min doit être ≥ 0.90 (§5 CLAUDE.md)"
    )
    assert targets["false_block_rate_max"] <= 0.05, (
        "Cible false_block_rate_max doit être ≤ 0.05 (HITL > BLOCK principle)"
    )


def test_fixture_covers_all_verdicts() -> None:
    """La fixture doit contenir au moins 1 cas de chaque verdict."""
    verdicts = {case["expected"]["verdict"] for case in CASES}
    assert verdicts == {"allow", "block", "hitl_required"}, (
        f"Fixture doit couvrir allow + block + hitl_required, trouvé : {verdicts}"
    )


def test_fixture_covers_both_layers() -> None:
    """La fixture doit exercer les deux layers (structural + semantic)."""
    layers = {case["expected"]["layer_triggered"] for case in CASES}
    assert layers == {"structural", "semantic"}, (
        f"Fixture doit exercer structural + semantic, trouvé : {layers}"
    )


def test_fixture_case_ids_unique() -> None:
    """Les IDs des cas doivent être uniques (pas de doublons)."""
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids)), f"IDs dupliqués détectés : {ids}"


# ─── Tests de verdict (FAIL en 6.0, passent progressivement) ───────────


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_verdict_matches_expected(case: dict) -> None:
    """Chaque cas de la fixture produit le verdict attendu."""
    result = check(
        agent=case["input"]["agent"],
        env=case["input"]["env"],
        tool=case["input"]["tool"],
        payload=case["input"]["payload"],
        user_message=case["input"]["user_message"],
    )
    assert isinstance(result, PolicyDecision), (
        f"[{case['id']}] check() doit retourner PolicyDecision, obtenu {type(result)}"
    )
    assert result.verdict == case["expected"]["verdict"], (
        f"[{case['id']}] verdict attendu {case['expected']['verdict']}, "
        f"obtenu {result.verdict}. Reason: {result.reason}"
    )
    assert result.layer_triggered == case["expected"]["layer_triggered"], (
        f"[{case['id']}] layer attendu {case['expected']['layer_triggered']}, "
        f"obtenu {result.layer_triggered}"
    )
    for keyword in case["expected"].get("reason_contains", []):
        assert keyword in result.reason, (
            f"[{case['id']}] reason '{result.reason}' ne contient pas '{keyword}'"
        )


# ─── Invariants de contrat sur PolicyDecision ─────────────────────────


def test_invariant_hitl_has_vibe_diff() -> None:
    """Verdict HITL_REQUIRED ⇒ vibe_diff non-null et ≤ 350 chars."""
    hitl_cases = [c for c in CASES if c["expected"]["verdict"] == "hitl_required"]
    assert hitl_cases, "Fixture doit contenir ≥ 1 cas HITL"
    for case in hitl_cases:
        result = check(
            agent=case["input"]["agent"],
            env=case["input"]["env"],
            tool=case["input"]["tool"],
            payload=case["input"]["payload"],
            user_message=case["input"]["user_message"],
        )
        assert result.vibe_diff is not None, (
            f"[{case['id']}] HITL sans vibe_diff — invariant violé"
        )
        assert 0 < len(result.vibe_diff) <= 350, (
            f"[{case['id']}] vibe_diff longueur {len(result.vibe_diff)} hors [1, 350]"
        )


def test_invariant_allow_no_vibe_diff() -> None:
    """Verdict ALLOW ⇒ vibe_diff est None (pas de friction sur cas nominaux)."""
    allow_cases = [c for c in CASES if c["expected"]["verdict"] == "allow"]
    assert allow_cases, "Fixture doit contenir ≥ 1 cas ALLOW"
    for case in allow_cases:
        result = check(
            agent=case["input"]["agent"],
            env=case["input"]["env"],
            tool=case["input"]["tool"],
            payload=case["input"]["payload"],
            user_message=case["input"]["user_message"],
        )
        assert result.vibe_diff is None, (
            f"[{case['id']}] ALLOW avec vibe_diff — invariant violé "
            f"(ALLOW doit être silencieux, pas de Confirmation Fatigue)"
        )


def test_invariant_block_no_vibe_diff() -> None:
    """Verdict BLOCK ⇒ vibe_diff est None (BLOCK est final, pas de review)."""
    block_cases = [c for c in CASES if c["expected"]["verdict"] == "block"]
    assert block_cases, "Fixture doit contenir ≥ 1 cas BLOCK"
    for case in block_cases:
        result = check(
            agent=case["input"]["agent"],
            env=case["input"]["env"],
            tool=case["input"]["tool"],
            payload=case["input"]["payload"],
            user_message=case["input"]["user_message"],
        )
        assert result.vibe_diff is None, (
            f"[{case['id']}] BLOCK avec vibe_diff — invariant violé "
            f"(BLOCK est final ; les faux positifs passent par audit, pas par HITL)"
        )


def test_invariant_payload_unchanged() -> None:
    """check() ne modifie jamais le payload (anti-Confused-Deputy, Day 4 Pillar 5)."""
    for case in CASES[:3]:
        original = copy.deepcopy(case["input"]["payload"])
        try:
            check(
                agent=case["input"]["agent"],
                env=case["input"]["env"],
                tool=case["input"]["tool"],
                payload=case["input"]["payload"],
                user_message=case["input"]["user_message"],
            )
        except NotImplementedError:
            # Attendu tant que Phase 6.1-6.3 non implémentées.
            pass
        assert case["input"]["payload"] == original, (
            f"[{case['id']}] payload modifié par check() — Confused Deputy risk. "
            f"Day 4 Pillar 5 : can_modify_request MUST be false."
        )


def test_policy_decision_is_frozen() -> None:
    """PolicyDecision est un dataclass frozen (immuable)."""
    # On construit une instance valide pour tester l'immuabilité.
    # Si Phase 6 change PolicyDecision en non-frozen, ce test crie.
    dec = PolicyDecision(
        verdict="allow",
        reason="test",
        vibe_diff=None,
        layer_triggered="structural",
    )
    with pytest.raises(Exception):
        # frozen=True fait lever FrozenInstanceError sur toute mutation
        dec.verdict = "block"  # type: ignore[misc]
