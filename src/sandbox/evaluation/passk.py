"""Harness pass^k — mesure la STABILITÉ d'une éval sur k runs identiques (Phase 8.3).

pass^k (CLAUDE.md §7) : un cas passe^k ssi il réussit les k exécutions
INDÉPENDANTES. Il démasque la flakiness probabiliste qu'un seul run (pass^1)
cache — un juge LLM qui réussit 2 fois sur 3 n'est PAS fiable. Cible métier :
pass^3 >= 0.85 sur le dataset.

Générique par conception : le harness ne connaît ni le juge ni le réseau. On lui
passe `run_once(case) -> bool` (UNE évaluation → réussite/échec). C'est ce qui le
rend testable offline avec des stand-ins (déterministe = 1.0, flaky < seuil), le
vrai pass^k sur le juge LLM restant un opt-in tier-2.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

RunOnce = Callable[[Any], bool]


def passes_k(run_once: RunOnce, case: Any, k: int) -> bool:
    """Vrai ssi les k exécutions indépendantes de `case` réussissent TOUTES.

    Court-circuit volontaire : dès qu'un run échoue, on arrête (le cas échoue^k
    quoi qu'il arrive) — ça économise les appels LLM des runs restants.
    """
    if k < 1:
        raise ValueError("k doit être >= 1")
    return all(run_once(case) for _ in range(k))


def passk_rate(cases: Sequence[Any], run_once: RunOnce, k: int) -> float:
    """Fraction des cas qui passent^k — la métrique dataset (cible pass^3 >= 0.85)."""
    if not cases:
        raise ValueError("cases ne peut pas être vide")
    return sum(passes_k(run_once, c, k) for c in cases) / len(cases)
