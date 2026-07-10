"""
Vibe Diff generator — plain-English HITL prompts.

Phase 6.3 (§7 CLAUDE.md, Day 4 Pillar 5).

Public API : `generate(reason, tool, payload, user_message, layer) -> str`.

Sequence :
1. Sélectionne un template par `reason` (fallback générique si inconnu).
2. Remplit les placeholders (résumé du payload, troncature du user_message).
3. Masque tout PII qui aurait fuité dans le rendu.
4. Enforce la longueur (≤ 350 chars) et le nombre de lignes (≤ 5).

Fail-tolerant : `generate()` ne raise JAMAIS et ne retourne JAMAIS None.
L'invariant `hitl_has_vibe_diff` du contrat `check()` doit tenir — si
la génération primaire échoue, on dégrade proprement (fallback + trunc).

Source de vérité pour la spec des templates :
    `meta/vibe_diff_checklist.md`

Les templates y sont dupliqués en Python constants pour perf + testabilité.
Un test de dérive (`test_vibe_diff_drift_markdown`) vérifie que chaque
clé Python a bien une section correspondante dans le markdown — protège
d'un ajout/suppression d'un côté sans l'autre.
"""

from __future__ import annotations
import re
from typing import Any


MAX_LENGTH = 350
MAX_LINES = 5
TRUNCATION_SUFFIX = "..."


# ─── Templates (source de vérité: meta/vibe_diff_checklist.md) ──────────
# Les placeholders utilisent la syntaxe str.format : {tool}, {payload_summary},
# {user_message_short}, {reason}. Un template peut ignorer des placeholders
# — Python .format() les ignore silencieusement s'ils ne sont pas présents.

TEMPLATES: dict[str, str] = {
    # HITL structural — tool "act" (side-effect, irréversible)
    "act_tool_default_hitl": (
        "Action : invoquer {tool}.\n"
        "Détails : {payload_summary}.\n"
        "⚠ Cette action est irréversible.\n"
        "[Approuver] [Rejeter]"
    ),
    # HITL semantic — PII en clair dans le payload
    "pii_leak_risk": (
        "Payload contient des PII en clair (email/téléphone/ID).\n"
        "Convention : ces valeurs devraient être des placeholders [[VAR]].\n"
        "Approuver si test/dev local, sinon corriger.\n"
        "[Approuver] [Rejeter et corriger]"
    ),
    # HITL semantic — draft en désaccord avec les sources citées
    "policy_conflict": (
        "Draft {tool} en désaccord avec les sources citées.\n"
        "Un humain doit trancher (force majeure ? cas spécial ?).\n"
        "[Approuver le draft] [Rejeter et refaire]"
    ),
    # HITL semantic — exclusion sélective avec raison opérationnelle
    "exclusion_with_business_context": (
        "Filtre d'exclusion demandé avec raison opérationnelle.\n"
        'Message : "{user_message_short}".\n'
        "Humain valide la légitimité de l'exclusion.\n"
        "[Approuver l'exclusion] [Rapport complet]"
    ),
}

# Fallback pour toute `reason` non listée dans TEMPLATES.
# Le LLM du Semantic Gate PEUT inventer une catégorie non anticipée ;
# on ne veut pas crash, on veut un vibe_diff dégradé mais actionable.
FALLBACK_TEMPLATE = (
    "HITL requis : {reason}.\n"
    "Tool : {tool}.\n"
    "[Approuver] [Rejeter]"
)


# ─── Regex de validation post-hoc ────────────────────────────────────────
# PII patterns : détectés dans le rendu final pour masquage.
# Volontairement permissifs — un faux positif "email" masque un
# mot@domaine bénin ; c'est acceptable dans un vibe_diff (qui doit être
# concis, pas fidèle au caractère près).

PII_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# téléphone : 8+ chiffres avec ou sans séparateurs, pas dans une plus longue séquence
PII_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s.\-]{7,}\d)(?!\d)")
# IDs client Marina Rentals conventionnels : CUST-XXXX ou CLI-XXXX
PII_CLIENT_ID = re.compile(r"\b(?:CUST|CLI)-\d{4,}\b", re.IGNORECASE)

PII_PATTERNS: list[re.Pattern[str]] = [PII_EMAIL, PII_PHONE, PII_CLIENT_ID]

# Anti-patterns du contrat vibe_diff_checklist.md §Anti-patterns.
# Utilisés par `_validate()` pour signaler un vibe_diff invalide en test —
# generate() les prévient déjà en amont, la validation est belt-and-suspenders.
JSON_DUMP_PATTERN = re.compile(r'"\w+"\s*:\s*["\d\[{]')
NON_ACTIONABLE_OPTIONS = re.compile(
    r"\[(Voir plus|Consulter|Plus tard|Revenir plus tard)\]",
    re.IGNORECASE,
)


# ─── Helpers de rendu ────────────────────────────────────────────────────


def _truncate(value: Any, max_chars: int = 30) -> str:  # noqa: ANN401 — accepte tout type
    """Convertit en string bornée par `max_chars` avec suffixe `...`."""
    s = str(value)
    return s if len(s) <= max_chars else s[: max_chars - 3] + "..."


def _payload_summary(payload: dict, max_chars: int = 100) -> str:
    """
    Résumé humain-lisible du payload : `k=v, k=v, k=v` sur ≤ 3 clés.

    Jamais de JSON dump — le contrat §Anti-patterns interdit
    `"key":"value"` dans un vibe_diff. Format `k=v` est reconnaissable
    comme argument nommé, pas comme JSON parsable.
    """
    if not payload:
        return "aucun paramètre"
    pairs = list(payload.items())[:3]
    parts = [f"{k}={_truncate(v)}" for k, v in pairs]
    summary = ", ".join(parts)
    return summary if len(summary) <= max_chars else summary[: max_chars - 3] + "..."


def _mask_pii(text: str) -> str:
    """Remplace tout match PII par `[PII masqué]`. Idempotent."""
    for pattern in PII_PATTERNS:
        text = pattern.sub("[PII masqué]", text)
    return text


def _enforce_length(text: str) -> str:
    """
    Garantit ≤ MAX_LINES lignes, puis ≤ MAX_LENGTH caractères.

    Ordre important : lignes AVANT chars — sinon on peut trunquer au milieu
    d'une ligne et se retrouver avec 5 lignes techniquement OK mais 6 lignes
    "morales" mal coupées.
    """
    lines = text.split("\n")
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
    text = "\n".join(lines)
    if len(text) > MAX_LENGTH:
        text = text[: MAX_LENGTH - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX
    return text


# ─── Validation post-hoc (testable indépendamment) ──────────────────────


def _validate(vibe_diff: str) -> tuple[bool, str]:
    """
    Contrôle post-hoc contre le contrat de vibe_diff_checklist.md.

    Utilisé principalement par les tests — `generate()` construit déjà
    un output valide-par-construction, mais `_validate()` sert d'audit
    indépendant : si un futur template introduit un bug, ces tests
    l'attraperont AVANT que le vibe_diff soit servi à un humain.

    Returns:
        (True, "ok") si toutes les conditions sont satisfaites.
        (False, "<reason_code>") sinon — le reason_code identifie
        laquelle des 5 conditions échoue, pour un debug ciblé.
    """
    if len(vibe_diff) > MAX_LENGTH:
        return False, f"length_exceeded:{len(vibe_diff)}"
    if len(vibe_diff.split("\n")) > MAX_LINES:
        return False, f"too_many_lines:{len(vibe_diff.split(chr(10)))}"
    options = re.findall(r"\[[^\]]+\]", vibe_diff)
    if len(options) < 2:
        return False, f"missing_options:{len(options)}"
    if JSON_DUMP_PATTERN.search(vibe_diff):
        return False, "json_dump_detected"
    if NON_ACTIONABLE_OPTIONS.search(vibe_diff):
        return False, "non_actionable_option"
    for pattern in PII_PATTERNS:
        if pattern.search(vibe_diff):
            return False, "pii_in_clear"
    return True, "ok"


# ─── Public API ─────────────────────────────────────────────────────────


def generate(
    reason: str,
    tool: str,
    payload: dict,
    user_message: str,
    layer: str,
) -> str:
    """
    Génère un Vibe Diff plain-English pour un tool call HITL.

    Contrat garanti :
    - retourne TOUJOURS une string valide (jamais None, jamais raise)
    - ≤ MAX_LENGTH caractères
    - ≤ MAX_LINES lignes
    - aucun PII (email, téléphone, ID client) en clair
    - contient au moins 2 options entre `[...]`

    Fail-tolerant par design : un `reason` inconnu tombe sur FALLBACK_TEMPLATE
    (dégradé mais actionable). Un payload contenant un email est masqué avant
    rendu. Un template trop long est tronqué. `generate()` ne DOIT jamais casser
    la chaîne `check()` — c'est un contrat d'invariant.

    Args:
        reason: code kebab-case décidé par un gate (ex. `policy_conflict`,
            `act_tool_default_hitl`, `pii_leak_risk`). Détermine le template.
        tool: nom du tool ciblé, injecté dans certains templates.
        payload: dict d'arguments du tool — résumé via `_payload_summary()`
            (jamais dump JSON brut).
        user_message: message initial de l'utilisateur — tronqué à 80 chars
            pour les templates qui le citent.
        layer: "structural" ou "semantic". Actuellement non utilisé dans
            le rendu ; présent pour futures extensions (ex. wording par layer).

    Returns:
        Vibe Diff string conforme au contrat de vibe_diff_checklist.md.
    """
    del layer  # placeholder pour extensions futures, ignore pour l'instant

    template = TEMPLATES.get(reason, FALLBACK_TEMPLATE)

    rendered = template.format(
        reason=reason,
        tool=tool,
        payload_summary=_payload_summary(payload),
        user_message_short=_truncate(user_message, 80),
    )

    # Défense 1 : masquage PII dans le rendu final (belt).
    # Un template peut fuiter un email via {payload_summary} — on nettoie ici.
    rendered = _mask_pii(rendered)

    # Défense 2 : longueur (suspenders).
    # Enforce même si le template est correct — protège contre un
    # payload_summary ou user_message qui gonflerait la sortie.
    rendered = _enforce_length(rendered)

    return rendered


__all__ = ["generate", "TEMPLATES", "FALLBACK_TEMPLATE", "MAX_LENGTH", "MAX_LINES"]
