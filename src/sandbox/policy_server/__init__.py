"""
Policy Server — governance layer that inspects every tool call before execution.

Phase 6 architecture (§7 CLAUDE.md, Day 4 Pillar 4-5) :

    orchestrator → policy_server.check(...) → allow / block / hitl_required
                                                 ↓
                                          structural_gate.check  (Phase 6.1)
                                          semantic_gate.check    (Phase 6.2)
                                          vibe_diff.generate     (Phase 6.3)

Public API : `check()` — LE seul point d'entrée que l'orchestrator utilise.
Les trois modules internes (structural_gate, semantic_gate, vibe_diff) sont
des détails d'implémentation ; leurs signatures peuvent évoluer, `check()`
est le contrat gelé.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


Verdict = Literal["allow", "block", "hitl_required"]
Layer = Literal["structural", "semantic"]


@dataclass(frozen=True)
class PolicyDecision:
    """
    Verdict retourné par check(). Immuable par design.

    Immuabilité = anti-Confused-Deputy : impossible pour un caller de
    modifier a posteriori le verdict pour contourner la décision.

    Invariants garantis :
    - verdict == "hitl_required" ⇒ vibe_diff is not None
    - verdict == "allow"          ⇒ vibe_diff is None
    - verdict == "block"          ⇒ vibe_diff is None (BLOCK est final)
    - layer_triggered indique QUEL gate a produit la décision finale
    - reason est en kebab-case, préfixé d'un code (ex. "tool_not_allowed",
      "policy_conflict:refund_amount") pour permettre le regroupement
      dans les évals sans parser du texte libre
    """

    verdict: Verdict
    reason: str
    vibe_diff: str | None
    layer_triggered: Layer


def check(
    agent: str,
    env: str,
    tool: str,
    payload: dict,
    user_message: str,
) -> PolicyDecision:
    """
    Inspecte un tool call en attente d'exécution et retourne le verdict.

    Séquence (fast → slow) :
    1. structural_gate.check(agent, env, tool)
       - BLOCK ou HITL immédiat si structural refuse ou force HITL
       - ALLOW passe au semantic
    2. semantic_gate.check(tool, payload, user_message)
       - Peut re-classifier en HITL_REQUIRED ou BLOCK
       - Sinon confirme ALLOW
    3. Si le verdict final est HITL_REQUIRED → invoquer vibe_diff.generate
    4. Retourner PolicyDecision immuable.

    Invariants comportementaux (testés) :
    - `payload` n'est jamais modifié (Confused Deputy prevention, Day 4 Pillar 5)
    - `check()` est idempotent : même (agent, env, tool, payload, user_message)
      → même verdict (à modulo l'aléa du LLM-judge, cible pass^3 >= 0.85)
    - `HITL_REQUIRED` produit toujours un vibe_diff non-null et ≤ 350 chars
    - `BLOCK` ne produit jamais de vibe_diff (final, pas de review humaine)

    Args:
        agent: nom de l'agent invoquant (ex. "support_agent"). Doit exister
            dans meta/agent_security_policy.md.
        env: environnement d'exécution ("dev" | "staging" | "prod").
        tool: nom du tool ciblé (ex. "retrieve_docs"). Doit exister dans
            meta/tool_registry.json.
        payload: dict d'arguments passés au tool (JSON-serializable).
        user_message: message utilisateur qui a initié la trajectoire.
            Nécessaire pour Semantic Gate (contexte d'intention).

    Returns:
        PolicyDecision immuable.

    Raises:
        ValueError: si `agent`, `env`, ou `tool` non reconnus.

    Example:
        >>> decision = check(
        ...     agent="support_agent",
        ...     env="dev",
        ...     tool="retrieve_docs",
        ...     payload={"query": "conditions annulation", "top_k": 3},
        ...     user_message="Quelles sont les conditions d'annulation ?",
        ... )
        >>> decision.verdict
        'allow'
    """
    # Layer 1 : Structural Gate (Phase 6.1 — implémenté)
    from .structural_gate import check_structural

    structural = check_structural(agent, env, tool)

    if structural.verdict == "block":
        # BLOCK est final — pas d'appel Semantic.
        return structural

    if structural.verdict == "hitl_required":
        # HITL structural (act default) : vibe_diff délégué à vibe_diff.generate()
        # (Phase 6.3 — remplace le stub inline précédent).
        from .vibe_diff import generate as generate_vibe_diff

        return PolicyDecision(
            verdict="hitl_required",
            reason=structural.reason,
            vibe_diff=generate_vibe_diff(
                reason=structural.reason,
                tool=tool,
                payload=payload,
                user_message=user_message,
                layer="structural",
            ),
            layer_triggered="structural",
        )

    # Layer 2 : Semantic Gate (Phase 6.2 — implémenté)
    from .semantic_gate import check_semantic

    semantic = check_semantic(tool, payload, user_message)

    if semantic.verdict == "block":
        # BLOCK sémantique est final — pas de vibe_diff (BLOCK ≠ HITL).
        return semantic

    if semantic.verdict == "hitl_required":
        # HITL sémantique : générer vibe_diff selon la catégorie détectée
        # (Phase 6.3 — délégué au module vibe_diff avec masquage PII + validation).
        from .vibe_diff import generate as generate_vibe_diff

        return PolicyDecision(
            verdict="hitl_required",
            reason=semantic.reason,
            vibe_diff=generate_vibe_diff(
                reason=semantic.reason,
                tool=tool,
                payload=payload,
                user_message=user_message,
                layer="semantic",
            ),
            layer_triggered="semantic",
        )

    # Semantic ALLOW → verdict final
    return semantic


__all__ = ["check", "PolicyDecision", "Verdict", "Layer"]
