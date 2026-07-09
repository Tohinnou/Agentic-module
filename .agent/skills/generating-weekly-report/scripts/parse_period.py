"""
Parse une expression naturelle de période en (start_date, end_date).

Déterministe : évite l'hallucination de dates par le LLM (biais systématique
sur intervalles, oublis de bornes, confusion mois/semaine).

Utilisé par la skill `generating-weekly-report` à l'étape 1 de sa procédure.
Ce fichier n'est PAS un tool — c'est un helper interne à la skill.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

ISO_RANGE = re.compile(r"de\s+(\d{4}-\d{2}-\d{2})\s+à\s+(\d{4}-\d{2}-\d{2})")


def parse_period(text: str, today: date | None = None) -> tuple[date, date]:
    """
    Reconnaît des expressions naturelles de période et retourne (start, end).

    Cas supportés :
    - "cette semaine"           → lundi courant → today
    - "la semaine dernière"     → lundi passé → dimanche passé
    - "les 7 derniers jours"    → today - 6 → today
    - "ce mois" / "mois en cours" → 1er du mois courant → today
    - "le mois dernier"         → 1er du mois passé → dernier du mois passé
    - "les 30 derniers jours"   → today - 29 → today
    - "de YYYY-MM-DD à YYYY-MM-DD" → parse explicite ISO 8601

    L'argument `today` permet d'injecter une date fixe pour les tests.
    En prod, `today = date.today()`.

    Raise ValueError si aucun pattern ne matche — la skill doit alors
    refuser avec `refusal_reason: "missing_period"`.
    """
    today = today or date.today()
    normalized = text.lower().strip()

    if match := ISO_RANGE.search(normalized):
        start = date.fromisoformat(match.group(1))
        end = date.fromisoformat(match.group(2))
        if start > end:
            raise ValueError(f"start > end : {start} > {end}")
        return start, end

    if "cette semaine" in normalized or "semaine en cours" in normalized:
        monday = today - timedelta(days=today.weekday())
        return monday, today

    if "semaine dernière" in normalized or "semaine précédente" in normalized:
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return start, end

    if "7 derniers jours" in normalized:
        return today - timedelta(days=6), today

    if "ce mois" in normalized or "mois en cours" in normalized:
        return today.replace(day=1), today

    if "mois dernier" in normalized or "mois précédent" in normalized:
        first_of_this = today.replace(day=1)
        last_of_prev = first_of_this - timedelta(days=1)
        return last_of_prev.replace(day=1), last_of_prev

    if "30 derniers jours" in normalized:
        return today - timedelta(days=29), today

    raise ValueError(f"Période non reconnue : {text!r}")
