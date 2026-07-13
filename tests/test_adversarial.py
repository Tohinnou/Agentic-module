"""Adversarial end-to-end au niveau agent (Phase 8.3, module #3a).

Complément agent-level de test_policy_server.py (unit : payload→verdict). Ici on
vérifie que le SupportAgent CÂBLÉ refuse/escalade vraiment sur une question hostile
— la propagation gate→agent que Phase 6 ne couvre pas end-to-end.

Deux tiers :
- OFFLINE : meta-tests de FORME sur la fixture (ids, outcomes, contrôle nominal).
- TIER-2 (opt-in RUN_LLM_ADVERSARIAL + clé) : refus RÉEL via le Semantic Gate LLM.
  100% de refus sur les cas hostiles ; zéro false-block sur le nominal.
"""

import os
from pathlib import Path

import pytest
import yaml

from sandbox.agents.orchestrator import SupportAgent
from sandbox.policy_server.exceptions import PolicyBlockError, PolicyHITLRequired

FIXTURE = Path("evals/adversarial.yaml")
DATA = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
CASES = DATA["cases"]
_VALID_OUTCOMES = {"block", "hitl_required", "allow"}


# ─── OFFLINE : contrat de fixture ─────────────────────────────────
def test_fixture_ids_unique_and_nonempty() -> None:
    ids = [c["id"] for c in CASES]
    assert ids and len(ids) == len(set(ids))


def test_fixture_outcomes_valid() -> None:
    for c in CASES:
        assert c["expected"]["outcome"] in _VALID_OUTCOMES
        if c["expected"]["outcome"] != "allow":
            assert c["expected"]["reason_contains"], f"{c['id']} : reason_contains requis"


def test_fixture_has_hostile_and_nominal() -> None:
    outcomes = {c["expected"]["outcome"] for c in CASES}
    assert {"block", "hitl_required"} <= outcomes, "besoin de cas hostiles block ET hitl"
    assert "allow" in outcomes, "besoin d'un contrôle nominal (garde false-block)"


# ─── TIER-2 : refus réel end-to-end (opt-in réseau) ───────────────
_OPT_OUT = not (os.environ.get("RUN_LLM_ADVERSARIAL") and "OPENROUTER_API_KEY" in os.environ)
_SKIP = "opt-in réseau : RUN_LLM_ADVERSARIAL=1 + OPENROUTER_API_KEY (refus = Semantic Gate LLM)."


def _run_agent(case: dict):
    """SupportAgent câblé (strict_hitl pour faire lever HITL), evaluate=False (hors sujet ici)."""
    agent = SupportAgent(
        enforce_policy=True, evaluate=False, strict_hitl=True, session_id=case["id"]
    )
    return agent.run(case["question"])


def _cases_for(outcome: str) -> list:
    return [c for c in CASES if c["expected"]["outcome"] == outcome]


@pytest.mark.skipif(_OPT_OUT, reason=_SKIP)
@pytest.mark.parametrize("case", _cases_for("block"), ids=lambda c: c["id"])
def test_agent_blocks_injection(case: dict) -> None:
    with pytest.raises(PolicyBlockError) as exc:
        _run_agent(case)
    assert exc.value.decision.layer_triggered == case["expected"]["layer"]


@pytest.mark.skipif(_OPT_OUT, reason=_SKIP)
@pytest.mark.parametrize("case", _cases_for("hitl_required"), ids=lambda c: c["id"])
def test_agent_escalates_pii(case: dict) -> None:
    with pytest.raises(PolicyHITLRequired):
        _run_agent(case)


@pytest.mark.skipif(_OPT_OUT, reason=_SKIP)
@pytest.mark.parametrize("case", _cases_for("allow"), ids=lambda c: c["id"])
def test_agent_allows_nominal(case: dict) -> None:
    """Garde false-block : une question légitime ne doit PAS être refusée."""
    resp = _run_agent(case)  # ne lève pas
    assert resp.answer  # a bien produit un draft
