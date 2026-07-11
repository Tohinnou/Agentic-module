"""
Intent Drift detector — analyse rule-based post-hoc.

Phase 7.2 (§7 CLAUDE.md, Day 4 — Vibe Trajectory analysis).

Source de vérité des signaux : `meta/intent_drift_signals.md`.
La fonction publique `detect_drift()` vit dans `__init__.py` — ce
module contient les helpers de détection par signal (privés).

Chaque helper retourne `DriftSignal | None` :
- `None` si aucun drift de ce type n'est détecté.
- `DriftSignal` avec `code`, `severity`, `detail`, `events` (steps).
"""

from __future__ import annotations

from typing import Any

from . import DriftSignal


# ─── Séquences attendues par agent ────────────────────────────────────
# Rule-based volontairement (§meta/intent_drift_signals.md). Chaque agent
# a un pipeline fixe que son orchestrator garantit — toute déviation est
# un candidat drift.
#
# `support_agent` : classify_ticket → retrieve_docs → draft_reply →
#                   [evaluate_answer]? (le dernier tool est optionnel)
EXPECTED_SEQUENCES: dict[str, list[list[str]]] = {
    "support_agent": [
        ["classify_ticket", "retrieve_docs", "draft_reply"],
        ["classify_ticket", "retrieve_docs", "draft_reply", "evaluate_answer"],
    ],
}


def _detect_policy_block(events: list[dict[str, Any]]) -> DriftSignal | None:
    """Signal 1 : au moins un event a policy_verdict=block.

    Retourne un signal `high` avec la liste des steps concernés.
    """
    blocked_steps = tuple(
        e["step"] for e in events if e.get("policy_verdict") == "block"
    )
    if not blocked_steps:
        return None
    return DriftSignal(
        code="policy_block_encountered",
        severity="high",
        detail=f"Policy Server a bloqué {len(blocked_steps)} tool call(s)",
        events=blocked_steps,
    )


def _detect_hitl_bypassed(events: list[dict[str, Any]]) -> DriftSignal | None:
    """Signal 2 : event policy_verdict=hitl_required + status=success.

    Mode strict_hitl=False de la sandbox : HITL loggé mais exécution
    poursuivie. Attendu en dev, critique en prod → signal medium.
    """
    bypassed_steps = tuple(
        e["step"]
        for e in events
        if e.get("policy_verdict") == "hitl_required" and e.get("status") == "success"
    )
    if not bypassed_steps:
        return None
    return DriftSignal(
        code="hitl_bypassed",
        severity="medium",
        detail=f"HITL requis mais tool exécuté ({len(bypassed_steps)} occurrence(s))",
        events=bypassed_steps,
    )


def _detect_unexpected_sequence(
    events: list[dict[str, Any]], expected_agent: str
) -> DriftSignal | None:
    """Signal 3 : la séquence des actions ne matche AUCUN pattern attendu.

    Compare `[e["action"] for e in events]` avec `EXPECTED_SEQUENCES[expected_agent]`.
    Un agent inconnu déclenche le signal (impossible de valider).
    """
    actual = [e["action"] for e in events]
    expected_patterns = EXPECTED_SEQUENCES.get(expected_agent, [])
    if actual in expected_patterns:
        return None
    return DriftSignal(
        code="unexpected_tool_sequence",
        severity="high",
        detail=(
            f"Séquence {actual} ne matche pas les patterns attendus "
            f"pour {expected_agent}"
        ),
        events=tuple(e["step"] for e in events),
    )


def _detect_duplicate_action(events: list[dict[str, Any]]) -> DriftSignal | None:
    """Signal 4 : même action apparaît 2+ fois dans la session.

    On liste tous les steps concernés (pas juste les doublons — la 1re
    occurrence est aussi ambiguë a posteriori).
    """
    seen: dict[str, list[int]] = {}
    for e in events:
        action = e["action"]
        seen.setdefault(action, []).append(e["step"])
    duplicated_actions = {a: steps for a, steps in seen.items() if len(steps) >= 2}
    if not duplicated_actions:
        return None
    all_steps: tuple[int, ...] = tuple(
        step for steps in duplicated_actions.values() for step in steps
    )
    return DriftSignal(
        code="duplicate_action",
        severity="medium",
        detail=(
            f"Action(s) dupliquée(s) : "
            f"{', '.join(f'{a}×{len(s)}' for a, s in duplicated_actions.items())}"
        ),
        events=all_steps,
    )


__all__ = [
    "EXPECTED_SEQUENCES",
    "_detect_policy_block",
    "_detect_hitl_bypassed",
    "_detect_unexpected_sequence",
    "_detect_duplicate_action",
]
