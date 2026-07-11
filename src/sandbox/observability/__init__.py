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


def detect_drift(
    events: list[dict[str, Any]],
    *,
    expected_agent: str = "support_agent",
) -> DriftReport:
    """
    Analyse une session (liste d'events) et retourne un `DriftReport`.

    Séquence :
    1. Identifier `session_id` depuis les events (tous doivent partager le même).
    2. Détecter les 4 signaux (§meta/intent_drift_signals.md) :
       - policy_block_encountered
       - hitl_bypassed
       - unexpected_tool_sequence
       - duplicate_action
    3. Calculer la sévérité globale = max des signal severities (ou "none").
    4. Retourner un DriftReport immuable.

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
        NotImplementedError: tant que Phase 7.2 non complétée.
        ValueError: si events est vide ou session_ids incohérents.
    """
    raise NotImplementedError(
        "Phase 7.2 implémentera detect_drift(). "
        "Phase 7.0 pose les contrats (DriftReport, DriftSignal). "
        "Phase 7.1 fournit le reader qui produit les events."
    )


__all__ = [
    "DriftSignal",
    "DriftReport",
    "Severity",
    "SignalSeverity",
    "detect_drift",
]
