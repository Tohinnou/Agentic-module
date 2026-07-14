"""Green Team — propose une réponse à un signal Blue (Phase 10).

3 réponses (PROJECT.MD §10) : bloquer · corriger_le_brouillon · demander_validation_humaine
(+ `proceed` quand rien n'est signalé). Politique conservatrice, HITL sur l'ambigu
(principe « HITL > BLOCK » de Phase 6).
"""

from __future__ import annotations

from sandbox.security.models import Action

RESPONSES = ("bloquer", "corriger_le_brouillon", "demander_validation_humaine", "proceed")


def suggest(signal: str | None, action: Action) -> str:
    """Mappe (signal, action) → réponse recommandée."""
    if signal is None:
        return "proceed"
    if signal in ("acces_interdit", "trop_d_appels"):
        return "bloquer"  # violation nette / runaway : on stoppe
    if signal == "outil_suspect":
        # Slopsquatting possible, MAIS un install peut être légitime → l'humain tranche.
        return "demander_validation_humaine"
    if signal == "action_hors_scope":
        # problème de CONTENU dans un brouillon → on corrige ; ACTION irréversible → on bloque.
        return "corriger_le_brouillon" if action.kind == "draft" else "bloquer"
    return "demander_validation_humaine"  # défaut prudent (signal inconnu)
