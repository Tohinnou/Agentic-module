"""
Observability — analyse post-hoc des Vibe Trajectory JSONL.

Phase 7 architecture (§7 CLAUDE.md, Day 4 — Vibe Trajectory) :

    trajectories/*.jsonl → reader.load_*()  → list[dict] (raw events)
                        → drift.detect_drift() → DriftReport
                        → (Phase 7.3 CLI report)

Public API :
- `detect_drift(events)` : LE point d'entrée du detector. Toute la logique
  de détection vit ici — les callers (CLI, tests) n'utilisent que ça.
- `DriftReport` / `DriftSignal` : frozen dataclasses, immuables — impossible
  pour un caller de modifier un rapport après analyse.

Ce fichier est écrit AVANT l'implémentation (discipline EDD).
`detect_drift()` lève `NotImplementedError` tant que Phase 7.2 n'est pas
complétée. Les tests parametrisés sur `evals/drift_cases.yaml` FAIL au
démarrage — devient vert progressivement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Severity = Literal["none", "low", "medium", "high"]
SignalSeverity = Literal["low", "medium", "high"]  # pas de "none" sur un signal


@dataclass(frozen=True)
class DriftSignal:
    """Un signal de drift détecté sur une session.

    - `code` : slug kebab-case, une des 4 catégories de
      `meta/intent_drift_signals.md` (Phase 7.0).
    - `severity` : niveau du signal isolé (pas du report global).
    - `detail` : message humain-lisible, pour la CLI et l'audit.
    - `events` : liste des `step` numbers concernés (traçabilité).

    Immuable par design — un signal est un fait post-hoc, pas un état
    mutable. Un futur consommateur peut compter dessus pour dédupliquer
    ou hasher un rapport.
    """

    code: str
    severity: SignalSeverity
    detail: str
    events: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DriftReport:
    """Rapport de drift pour une session.

    - `session_id` : identifiant de la session analysée.
    - `signals` : tuple des signaux détectés (peut être vide).
    - `severity` : max des sévérités des signaux, ou "none" si vide.

    Invariants :
    - `signals == ()` ⇔ `severity == "none"`
    - `severity` est le max sur `signals` — jamais < max, jamais > max.

    Immuable par design — pas de mutation post-analyse.
    """

    session_id: str
    signals: tuple[DriftSignal, ...] = field(default_factory=tuple)
    severity: Severity = "none"


# Ordre de sévérité pour le calcul du max (typé pour éviter la comparaison
# de strings arbitraire — "high" < "low" lexicographiquement, on ne veut pas).
_SEVERITY_ORDER: dict[Severity, int] = {"none": 0, "low": 1, "medium": 2, "high": 3}


def detect_drift(
    events: list[dict[str, Any]],
    *,
    expected_agent: str = "support_agent",
) -> DriftReport:
    """
    Analyse une session (liste d'events) et retourne un `DriftReport`.

    Séquence :
    1. Valider que la liste n'est pas vide (ValueError sinon).
    2. Identifier `session_id` (tous les events doivent partager le même).
    3. Détecter les 4 signaux via les helpers privés de `drift.py`.
    4. Calculer la sévérité globale = max des signal severities, ou "none"
       si aucun signal.
    5. Retourner un DriftReport immuable, signaux triés par code (alpha).

    Contrat comportemental :
    - Ne mute jamais `events` (analyse read-only).
    - Deterministe : mêmes events → même report.
    - Idempotent : rejouer sur le même report renvoie le même report.
    - Ordre des signaux dans le report : alphabétique par `code`.

    Args:
        events: liste d'events JSONL-décodés (dicts). Chaque event doit
            porter au moins : session_id, step, action, status,
            policy_verdict (optionnel).
        expected_agent: agent attendu, détermine la séquence de tools
            attendue (utilisé par le check `unexpected_tool_sequence`).
            Défaut : "support_agent".

    Returns:
        DriftReport immuable.

    Raises:
        ValueError: si events est vide ou session_ids incohérents.
    """
    if not events:
        raise ValueError("detect_drift : liste d'events vide, rien à analyser")

    session_ids = {e.get("session_id") for e in events}
    if len(session_ids) > 1:
        raise ValueError(
            f"detect_drift : session_ids incohérents dans la liste : {session_ids}"
        )
    session_id = events[0].get("session_id")
    if not session_id:
        raise ValueError("detect_drift : session_id absent ou vide sur les events")

    # Import déféré : évite le circular (drift.py importe DriftSignal depuis
    # ici). Même pattern que policy_server/__init__.py -> structural_gate.
    from .drift import (
        _detect_duplicate_action,
        _detect_hitl_bypassed,
        _detect_policy_block,
        _detect_unexpected_sequence,
    )

    raw_signals = [
        _detect_policy_block(events),
        _detect_hitl_bypassed(events),
        _detect_unexpected_sequence(events, expected_agent),
        _detect_duplicate_action(events),
    ]
    # Filter None, trier par code (contrat : ordre alphabétique).
    signals = tuple(sorted((s for s in raw_signals if s is not None), key=lambda s: s.code))

    # Sévérité globale = max via _SEVERITY_ORDER (pas de comparaison de strings).
    if not signals:
        severity: Severity = "none"
    else:
        max_rank = max(_SEVERITY_ORDER[s.severity] for s in signals)
        # Inverse lookup rank → label.
        severity = next(k for k, v in _SEVERITY_ORDER.items() if v == max_rank)

    return DriftReport(session_id=session_id, signals=signals, severity=severity)


__all__ = [
    "DriftSignal",
    "DriftReport",
    "Severity",
    "SignalSeverity",
    "detect_drift",
]
