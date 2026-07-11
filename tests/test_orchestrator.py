"""Tests pour SupportAgent orchestrator (Phase 3, adapté Phase 6.4).

Deux familles :
  - Tests locaux (sans réseau) : forme du pipeline, HITL, sink JSONL, erreurs.
    Passent `evaluate=False` pour ne pas déclencher l'appel LLM du juge.
  - Tests bout-en-bout : `evaluate=True`, skipif OPENROUTER_API_KEY absent.
    Même pattern que `test_evaluate_answer.py` — le juge nécessite un appel réel.

**Phase 6.4** — tous ces tests passent `enforce_policy=False` : ils exercent
la mécanique du pipeline (ordre des events, HITL des placeholders, forme du
JSONL sink), pas le Policy Server. Le câblage 6.4 est testé indépendamment
dans `test_policy_server_integration.py`.
"""

from __future__ import annotations

import json
import os

import pytest

from sandbox.agents.orchestrator import (
    SupportAgent,
    SupportResponse,
    TrajectoryEvent,
)


def test_pipeline_shape_without_llm_judge() -> None:
    """3 events attendus, dans l'ordre, avec le vocabulaire risk du cours."""
    agent = SupportAgent(enforce_policy=False, evaluate=False, session_id="shape")
    response = agent.run("Comment annuler ma réservation dans 48h ?")

    assert isinstance(response, SupportResponse)
    assert response.evaluation is None

    assert len(response.trajectory) == 3
    assert [e.action for e in response.trajectory] == [
        "classify_ticket",
        "retrieve_docs",
        "draft_reply",
    ]
    # Vocabulaire du cours (§7 CLAUDE.md), pas low/medium/high.
    assert [e.risk for e in response.trajectory] == ["read", "read", "draft"]
    assert [e.step for e in response.trajectory] == [1, 2, 3]
    assert all(e.status == "success" for e in response.trajectory)
    assert all(e.session_id == "shape" for e in response.trajectory)
    assert all(e.agent == "support_agent" for e in response.trajectory)
    assert all(isinstance(e, TrajectoryEvent) for e in response.trajectory)


def test_hitl_placeholders_preserved() -> None:
    """Le draft revient BRUT avec [[VAR]] non résolus — HITL fail-safe."""
    agent = SupportAgent(enforce_policy=False, evaluate=False)
    response = agent.run("J'ai un problème avec ma réservation.")

    # Au moins un placeholder [[VAR]] intact dans la réponse.
    assert "[[" in response.answer and "]]" in response.answer
    # Liste explicite des placeholders exposée pour que l'humain les substitue.
    assert isinstance(response.placeholders, list)
    assert len(response.placeholders) > 0
    # Chaque placeholder listé est bien présent dans le texte.
    for placeholder in response.placeholders:
        assert placeholder in response.answer


def test_response_carries_context_for_downstream() -> None:
    """category/priority/policy_doc_id sont exposés pour un tool downstream."""
    agent = SupportAgent(enforce_policy=False, evaluate=False)
    response = agent.run("Est-ce que je peux annuler pour cause de météo ?")

    assert response.category is not None
    assert response.priority is not None
    assert response.policy_doc_id
    assert response.cited_policy_excerpt


def test_default_session_id_is_generated() -> None:
    agent = SupportAgent(enforce_policy=False, evaluate=False)
    response = agent.run("Question de test")
    assert response.trajectory[0].session_id.startswith("s-")
    assert len(response.trajectory[0].session_id) > len("s-")


def test_run_resets_trajectory_between_calls() -> None:
    """Deux runs successifs → trajectoires indépendantes, step recompte à 1."""
    agent = SupportAgent(enforce_policy=False, evaluate=False, session_id="reuse")
    r1 = agent.run("Première question")
    r2 = agent.run("Deuxième question")

    assert r1.trajectory[0].step == 1
    assert r2.trajectory[0].step == 1
    assert len(r1.trajectory) == 3
    assert len(r2.trajectory) == 3
    # session_id reste stable (une instance = une session).
    assert r1.trajectory[0].session_id == r2.trajectory[0].session_id == "reuse"


def test_timing_recorded_on_each_event() -> None:
    agent = SupportAgent(enforce_policy=False, evaluate=False)
    response = agent.run("Petite question")
    for event in response.trajectory:
        assert event.duration_ms >= 0


def test_jsonl_sink_writes_valid_events(tmp_path) -> None:
    sink = tmp_path / "traj.jsonl"
    agent = SupportAgent(enforce_policy=False, evaluate=False, session_id="jsonl", trajectory_sink=sink)
    agent.run("Question pour tester le sink.")

    assert sink.exists()
    lines = sink.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert [p["step"] for p in parsed] == [1, 2, 3]
    assert [p["action"] for p in parsed] == [
        "classify_ticket",
        "retrieve_docs",
        "draft_reply",
    ]
    assert all(p["session_id"] == "jsonl" for p in parsed)


def test_jsonl_sink_appends_across_runs(tmp_path) -> None:
    """Sink en append → 2 runs successifs cumulent 6 events dans un même fichier."""
    sink = tmp_path / "traj.jsonl"
    agent = SupportAgent(enforce_policy=False, evaluate=False, trajectory_sink=sink)
    agent.run("Question 1")
    agent.run("Question 2")

    lines = sink.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6


def test_error_records_failure_event_and_propagates(monkeypatch) -> None:
    """Si un tool raise, on enregistre un event error puis on propage."""
    from sandbox.agents import orchestrator as orch

    def broken(payload):
        raise ValueError("simulated tool failure")

    # Remplace la référence du tool dans le module orchestrator (import direct).
    monkeypatch.setattr(orch, "classify_ticket", broken)

    agent = SupportAgent(enforce_policy=False, evaluate=False)
    with pytest.raises(ValueError, match="simulated tool failure"):
        agent.run("Question qui va casser à l'étape 1.")

    # 1 event error, aucun événement supplémentaire (pipeline stoppé).
    assert len(agent.trajectory) == 1
    event = agent.trajectory[0]
    assert event.action == "classify_ticket"
    assert event.status == "error"
    assert "ValueError" in event.output_summary


def test_error_dumps_trajectory_even_on_failure(tmp_path, monkeypatch) -> None:
    """La trace JSONL doit exister même quand un tour échoue (audit post-hoc)."""
    from sandbox.agents import orchestrator as orch

    def broken(payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(orch, "retrieve_docs", broken)

    sink = tmp_path / "err.jsonl"
    agent = SupportAgent(enforce_policy=False, evaluate=False, trajectory_sink=sink)
    with pytest.raises(RuntimeError, match="boom"):
        agent.run("Question qui va casser à l'étape 2.")

    lines = sink.read_text(encoding="utf-8").strip().splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [p["action"] for p in parsed] == ["classify_ticket", "retrieve_docs"]
    assert parsed[0]["status"] == "success"
    assert parsed[1]["status"] == "error"
    assert "RuntimeError" in parsed[1]["output_summary"]


@pytest.mark.skipif(
    "OPENROUTER_API_KEY" not in os.environ,
    reason="OPENROUTER_API_KEY non défini (evaluate_answer nécessite un appel LLM réel).",
)
def test_full_pipeline_with_llm_judge() -> None:
    """Pipeline complet 4 étapes avec vraie éval LLM."""
    agent = SupportAgent(enforce_policy=False, evaluate=True, session_id="llm-e2e")
    response = agent.run(
        "Je veux annuler ma réservation dans 3 jours, quels sont mes droits ?"
    )

    assert response.evaluation is not None
    assert len(response.trajectory) == 4
    assert [e.action for e in response.trajectory] == [
        "classify_ticket",
        "retrieve_docs",
        "draft_reply",
        "evaluate_answer",
    ]
    assert response.trajectory[3].risk == "read"
    assert response.trajectory[3].status == "success"
