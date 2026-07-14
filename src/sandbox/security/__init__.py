"""Red / Blue / Green teaming — sécurité agentique (Phase 10, capstone).

Trois rôles SÉPARÉS : Red attaque (catalogue), Blue détecte (monitor), Green décide la
réponse (suggest). `triage` les compose en une décision de QUARANTAINE : une action
signalée n'est pas exécutée — elle est isolée, avec une réponse recommandée. C'est le
modèle mental qui range tout ce qu'on a construit en sécurité. Déterministe, offline.
"""

from sandbox.security.blue_team import monitor
from sandbox.security.green_team import suggest
from sandbox.security.models import Action, AttackCase, Disposition
from sandbox.security.red_team import RED_CASES


def triage(action: Action) -> Disposition:
    """Red → Blue → Green : signal + réponse + mise en quarantaine (si réponse ≠ proceed)."""
    signal = monitor(action)
    response = suggest(signal, action)
    return Disposition(signal=signal, response=response, quarantined=response != "proceed")


__all__ = [
    "Action",
    "AttackCase",
    "Disposition",
    "RED_CASES",
    "monitor",
    "suggest",
    "triage",
]
