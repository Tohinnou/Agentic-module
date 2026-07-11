"""Tests d'intégration Phase 6.4 — Policy Server câblé dans SupportAgent.

Ces tests couvrent le CÂBLAGE `check() → orchestrator._call_tool` :
  - trajectoire enrichie des champs policy_* quand `enforce_policy=True`
  - trajectoire silencieuse côté policy quand `enforce_policy=False`
  - BLOCK verdict → PolicyBlockError + event trajectoire
  - HITL verdict + strict_hitl=True → PolicyHITLRequired + event trajectoire
  - HITL verdict + strict_hitl=False → log seulement, pipeline continue

Les cas 1-2 hittent OpenRouter (Semantic Gate) au premier run — puis cache.
Les cas 3-5 utilisent `monkeypatch` pour forcer le verdict sans appel réel.
"""

from __future__ import annotations

import pytest

from sandbox.agents.orchestrator import SupportAgent
from sandbox.policy_server import PolicyDecision
from sandbox.policy_server.exceptions import PolicyBlockError, PolicyHITLRequired


# ─── 1-2 : câblage sur cas nominal (hittent le vrai Policy Server) ────────


def test_orchestrator_records_policy_verdict_when_enforcing() -> None:
    """Chaque TrajectoryEvent porte les 3 champs policy_* quand enforce_policy=True."""
    agent = SupportAgent(
        enforce_policy=True,
        evaluate=False,
        session_id="int-enforce",
    )
    response = agent.run("Comment annuler ma réservation dans 48h ?")

    # 3 events : classify → retrieve → draft. Tous devraient passer allow.
    assert len(response.trajectory) == 3
    for event in response.trajectory:
        assert event.policy_verdict is not None, (
            f"[{event.action}] policy_verdict absent — câblage rompu"
        )
        assert event.policy_reason is not None
        assert event.policy_layer in {"structural", "semantic"}


def test_orchestrator_omits_policy_fields_when_bypassed() -> None:
    """Quand enforce_policy=False, tous les champs policy_* restent None."""
    agent = SupportAgent(
        enforce_policy=False,
        evaluate=False,
        session_id="int-bypass",
    )
    response = agent.run("Comment annuler ?")

    assert len(response.trajectory) == 3
    for event in response.trajectory:
        assert event.policy_verdict is None
        assert event.policy_reason is None
        assert event.policy_layer is None


# ─── 3-5 : verdicts forcés via monkeypatch (pas d'appel réseau) ───────────


def _fake_decision(verdict: str, reason: str, layer: str = "structural") -> PolicyDecision:
    """Construit une PolicyDecision synthétique pour forcer le verdict."""
    vibe = (
        "Action test HITL.\nDétails synthétiques.\n[Approuver] [Rejeter]"
        if verdict == "hitl_required"
        else None
    )
    return PolicyDecision(
        verdict=verdict,  # type: ignore[arg-type]
        reason=reason,
        vibe_diff=vibe,
        layer_triggered=layer,  # type: ignore[arg-type]
    )


def test_orchestrator_blocks_on_policy_block_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """BLOCK verdict lève PolicyBlockError et laisse un event trajectoire."""

    def fake_check(**kwargs: object) -> PolicyDecision:
        return _fake_decision("block", "tool_not_allowed:test", "structural")

    monkeypatch.setattr("sandbox.agents.orchestrator.policy_check", fake_check)

    agent = SupportAgent(
        enforce_policy=True,
        evaluate=False,
        session_id="int-block",
    )
    with pytest.raises(PolicyBlockError) as exc_info:
        agent.run("Question quelconque")

    # L'exception porte la PolicyDecision complète (pour un handler HTTP downstream)
    assert exc_info.value.decision.verdict == "block"
    assert exc_info.value.decision.reason == "tool_not_allowed:test"

    # Trajectoire : 1 seul event, sur le PREMIER tool (classify_ticket), status=error
    assert len(agent.trajectory) == 1
    event = agent.trajectory[0]
    assert event.action == "classify_ticket"
    assert event.status == "error"
    assert event.policy_verdict == "block"
    assert event.policy_reason == "tool_not_allowed:test"


def test_orchestrator_strict_hitl_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """HITL + strict_hitl=True lève PolicyHITLRequired avec vibe_diff attaché."""

    def fake_check(**kwargs: object) -> PolicyDecision:
        return _fake_decision("hitl_required", "policy_conflict", "semantic")

    monkeypatch.setattr("sandbox.agents.orchestrator.policy_check", fake_check)

    agent = SupportAgent(
        enforce_policy=True,
        strict_hitl=True,
        evaluate=False,
        session_id="int-strict-hitl",
    )
    with pytest.raises(PolicyHITLRequired) as exc_info:
        agent.run("Question qui déclenche HITL")

    # Le vibe_diff doit être présent (invariant PolicyDecision pour HITL)
    assert exc_info.value.decision.vibe_diff is not None
    assert exc_info.value.decision.reason == "policy_conflict"

    # Trajectoire : 1 event, sur classify_ticket, status=error avec hitl_required
    assert len(agent.trajectory) == 1
    assert agent.trajectory[0].policy_verdict == "hitl_required"


def test_orchestrator_permissive_hitl_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """HITL + strict_hitl=False (défaut sandbox) : log seulement, pipeline continue.

    C'est le mode par défaut de la sandbox — aucun humain n'est branché sur
    l'API, on ne peut pas vraiment attendre son approbation. Le vibe_diff est
    perdu en console/log mais la trajectoire capture le verdict pour audit.
    """

    def fake_check(**kwargs: object) -> PolicyDecision:
        return _fake_decision("hitl_required", "pii_leak_risk", "semantic")

    monkeypatch.setattr("sandbox.agents.orchestrator.policy_check", fake_check)

    agent = SupportAgent(
        enforce_policy=True,
        strict_hitl=False,  # explicite pour clarté même si c'est le défaut
        evaluate=False,
        session_id="int-permissive-hitl",
    )
    response = agent.run("Comment annuler ma réservation ?")

    # Pipeline complet exécuté : 3 events, tous status=success
    assert len(response.trajectory) == 3
    assert all(e.status == "success" for e in response.trajectory)
    # Mais chaque event porte le verdict HITL — l'audit pourra détecter qu'on
    # a proceed malgré HITL
    for event in response.trajectory:
        assert event.policy_verdict == "hitl_required"
        assert event.policy_reason == "pii_leak_risk"
