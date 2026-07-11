"""
Intent Drift detector — analyse rule-based post-hoc.

Phase 7.2 (§7 CLAUDE.md, Day 4 — Vibe Trajectory analysis).

Source de vérité des signaux : `meta/intent_drift_signals.md`.
La fonction publique `detect_drift()` vit dans `__init__.py` — ce
module contient les helpers de détection par signal (privés).

Phase 7.0 : stub. Phase 7.2 implémente.
"""

from __future__ import annotations

from typing import Any


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


def _detect_policy_block(events: list[dict[str, Any]]) -> Any | None:
    """Signal 1 : au moins un event a policy_verdict=block. Phase 7.2."""
    raise NotImplementedError("Phase 7.2")


def _detect_hitl_bypassed(events: list[dict[str, Any]]) -> Any | None:
    """Signal 2 : event policy_verdict=hitl_required + status=success. Phase 7.2."""
    raise NotImplementedError("Phase 7.2")


def _detect_unexpected_sequence(
    events: list[dict[str, Any]], expected_agent: str
) -> Any | None:
    """Signal 3 : la séquence des actions ne matche pas EXPECTED_SEQUENCES. Phase 7.2."""
    raise NotImplementedError("Phase 7.2")


def _detect_duplicate_action(events: list[dict[str, Any]]) -> Any | None:
    """Signal 4 : même action apparaît 2+ fois dans la session. Phase 7.2."""
    raise NotImplementedError("Phase 7.2")


__all__ = ["EXPECTED_SEQUENCES"]
