"""
Policy Server exceptions — raised by orchestrator when a tool call
is refused (BLOCK) or requires human review (HITL_REQUIRED).

Phase 6.4 (§7 CLAUDE.md, Day 4 Pillar 4-5).

Design :
- Chaque exception porte la `PolicyDecision` complète — reason, layer,
  vibe_diff (pour HITL). Un handler HTTP peut donc formater le corps
  de réponse sans re-appeler `check()`.
- Les deux exceptions héritent d'une base `PolicyRefusal` pour permettre
  un `except PolicyRefusal` unique côté caller (patterns "n'importe quel
  refus policy").
- Volontairement PAS de `raise from` chain interne — la décision n'est
  pas une conséquence d'une autre exception, elle EST l'événement primaire.
"""

from __future__ import annotations

from . import PolicyDecision


class PolicyRefusal(Exception):
    """
    Base commune : le Policy Server a refusé (BLOCK) ou différé (HITL) l'appel.

    Un caller qui veut traiter les deux cas identiquement (ex. audit log
    unique) peut faire `except PolicyRefusal`. Un caller qui veut distinguer
    BLOCK vs HITL fait `except PolicyBlockError` puis `except PolicyHITLRequired`.
    """

    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision
        super().__init__(
            f"{decision.verdict}:{decision.reason} (layer={decision.layer_triggered})"
        )


class PolicyBlockError(PolicyRefusal):
    """
    Verdict = BLOCK. L'exécution du tool est refusée, sans recours possible.

    HTTP mapping (via `api.py` handler) : 403 Forbidden.
    Le corps de réponse doit contenir `reason` et `layer_triggered`, PAS
    de vibe_diff (BLOCK n'en produit jamais — cf. invariants PolicyDecision).
    """


class PolicyHITLRequired(PolicyRefusal):
    """
    Verdict = HITL_REQUIRED. L'exécution est différée en attente d'un humain.

    HTTP mapping (via `api.py` handler) : 428 Precondition Required.
    Le corps de réponse contient `reason` ET `vibe_diff` — l'humain doit
    voir le vibe_diff pour prendre sa décision.

    En sandbox (`strict_hitl=False`) l'orchestrateur PEUT choisir de logger
    l'événement sans lever cette exception, pour ne pas bloquer les tests
    end-to-end quand aucun humain n'est branché.
    """


__all__ = ["PolicyRefusal", "PolicyBlockError", "PolicyHITLRequired"]
