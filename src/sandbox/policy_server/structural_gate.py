"""
Structural Gate — allow-list check déterministe.

Phase 6.1 (§7 CLAUDE.md, Day 4 Pillar 4).

Lit `meta/agent_security_policy.md` comme source de vérité. Applique deux
mécanismes indépendants en séquence :

1. **Allow-list** : allowlist[agent][env] → allowed_tools
2. **Act rules**  : act_rules[tool] → force_hitl

Aucun LLM. Rapide (~ms). Fail-closed (default_policy: deny) — un tool
inconnu ou un couple (agent, env) inconnu = refus immédiat.

Le Structural Gate ne connaît PAS le `payload` — il ne peut donc pas
générer de vibe_diff pour les cas HITL. La génération du vibe_diff pour
les HITL structurels est déléguée au niveau `check()` dans `__init__.py`.
Phase 6.3 remplacera le stub par le vrai générateur.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import PolicyDecision


# Chemin vers la source de vérité — 4 niveaux au-dessus de ce fichier
# (src/sandbox/policy_server/structural_gate.py → repo_root/meta/...)
POLICY_PATH = Path(__file__).resolve().parents[3] / "meta" / "agent_security_policy.md"


@dataclass(frozen=True)
class StructuralPolicy:
    """
    Représentation parsée de `meta/agent_security_policy.md`.

    Chargée UNE fois par process via `_load_policy()` + `lru_cache`.
    Immuable après chargement — aucun composant downstream ne peut
    muter la policy en cours d'exécution.
    """

    version: str
    default_policy: str  # "deny" ou "allow" — fail-closed par défaut
    allowlist: dict[str, dict[str, list[str]]]  # {agent: {env: [tool, ...]}}
    act_rules: dict[str, dict[str, Any]]  # {tool: {force_hitl: bool, reason_code: str, ...}}


def _extract_yaml_blocks(markdown: str) -> list[dict]:
    """
    Extrait TOUS les blocs YAML d'un fichier Markdown.

    On ne peut pas se contenter du premier bloc : `agent_security_policy.md`
    contient plusieurs blocs (allowlist, act_rules, rate_limits, ...). On les
    parse tous et le caller filtrera par contenu.
    """
    blocks: list[dict] = []
    for raw in re.findall(r"```yaml\n(.*?)\n```", markdown, re.DOTALL):
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError:
            # Bloc YAML mal formé — on le skip silencieusement.
            # Le fichier de policy est sous notre contrôle ; un bloc mal
            # formé serait un bug détecté à la 1re invocation.
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
    return blocks


@lru_cache(maxsize=1)
def _load_policy() -> StructuralPolicy:
    """
    Parse `meta/agent_security_policy.md` UNE SEULE FOIS par process.

    `lru_cache(maxsize=1)` mémoïse le résultat — appels subséquents sont
    instantanés. Convention (§Chargement dans la policy elle-même) :
    aucun hot-reload. Modification du fichier = redémarrer le process.
    """
    if not POLICY_PATH.exists():
        raise FileNotFoundError(
            f"Policy file introuvable : {POLICY_PATH}. "
            "Structural Gate ne peut pas fonctionner sans meta/agent_security_policy.md."
        )

    text = POLICY_PATH.read_text(encoding="utf-8")
    blocks = _extract_yaml_blocks(text)

    allowlist_block = next((b for b in blocks if "allowlist" in b), None)
    act_rules_block = next((b for b in blocks if "act_rules" in b), None)

    if allowlist_block is None:
        raise ValueError(
            f"Bloc 'allowlist' introuvable dans {POLICY_PATH}. "
            "Structural Gate ne peut pas fonctionner sans allow-list explicite (fail-closed)."
        )

    return StructuralPolicy(
        version=allowlist_block.get("version", "unknown"),
        default_policy=allowlist_block.get("default_policy", "deny"),
        allowlist=allowlist_block["allowlist"],
        act_rules=(act_rules_block or {}).get("act_rules", {}),
    )


def check_structural(agent: str, env: str, tool: str) -> PolicyDecision:
    """
    Applique la policy structurelle.

    Séquence (fast → slow, chaque étape peut terminer la chaîne) :

    1. **Allow-list** : le tool est-il dans `allowlist[agent][env]` ?
       Non → **BLOCK** (`reason: tool_not_allowed:{agent}:{env}:{tool}`)
    2. **Act rules** : le tool a-t-il `force_hitl: true` dans `act_rules` ?
       Oui → **HITL_REQUIRED** (`reason: act_tool_default_hitl`)
    3. Sinon → **ALLOW** (`reason: allowlist_match`) — provisoire, le
       Semantic Gate peut re-classifier en 6.2.

    Args:
        agent: nom de l'agent invoquant (ex. "support_agent")
        env: environnement d'exécution ("dev" | "staging" | "prod")
        tool: nom du tool ciblé (ex. "retrieve_docs")

    Returns:
        PolicyDecision avec `layer_triggered="structural"` et `vibe_diff=None`
        (le vibe_diff éventuel est ajouté par `check()` qui a accès au payload).

    Fail-closed : agent inconnu, env inconnu, tool inconnu → BLOCK.
    """
    policy = _load_policy()

    # Étape 1 : allow-list
    # Structure YAML : allowlist[agent][env]["allowed_tools"] → list
    # `.get(..., {})` implémente le fail-closed : agent absent → dict vide
    # → allowed_tools vide → tool ne peut pas y être → BLOCK.
    env_config = policy.allowlist.get(agent, {}).get(env, {})
    allowed_tools = env_config.get("allowed_tools", []) if isinstance(env_config, dict) else []
    if tool not in allowed_tools:
        return PolicyDecision(
            verdict="block",
            reason=f"tool_not_allowed:{agent}:{env}:{tool}",
            vibe_diff=None,
            layer_triggered="structural",
        )

    # Étape 2 : act rules
    rule = policy.act_rules.get(tool)
    if rule and rule.get("force_hitl"):
        return PolicyDecision(
            verdict="hitl_required",
            reason=rule.get("reason_code", "act_tool_default_hitl"),
            vibe_diff=None,  # rempli par check() dans __init__.py
            layer_triggered="structural",
        )

    # Étape 3 : allow provisoire
    return PolicyDecision(
        verdict="allow",
        reason="allowlist_match",
        vibe_diff=None,
        layer_triggered="structural",
    )
