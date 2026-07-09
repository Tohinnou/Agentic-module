"""
Agrégation déterministe d'une liste de tickets Marina Rentals.

Déterministe : évite les erreurs de comptage LLM (biais sur les nombres,
confusion additions).

Utilisé par la skill `generating-weekly-report` à l'étape 3 de sa procédure.
Ce fichier n'est PAS un tool — c'est un helper interne à la skill.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def aggregate_by_category(
    tickets: list[dict[str, Any]],
    top_n: int = 5,
) -> dict[str, Any]:
    """
    Agrège une liste de tickets par catégorie et priorité.

    Entrée :
        tickets = [
            {
                "category": "cancellation",
                "priority": "urgent",
                "created_at": "2026-07-01T14:32:00",
                ...
            },
            ...
        ]
        top_n = nombre de catégories les plus fréquentes à retourner

    Sortie :
        {
            "total": 42,
            "top_categories": [
                {"category": "cancellation", "count": 15, "share": 0.357},
                ...
            ],
            "priority_distribution": {"urgent": 5, "normal": 30, "low": 7},
            "urgent_ratio": 0.119,
        }

    Invariants garantis :
    - top_categories est triée par count décroissant
    - share ∈ [0.0, 1.0] avec 3 décimales
    - urgent_ratio ∈ [0.0, 1.0] avec 3 décimales
    - sum(top_categories.count) ≤ total (peut être < si top_n < nb cats distincts)
    """
    total = len(tickets)

    if total == 0:
        return {
            "total": 0,
            "top_categories": [],
            "priority_distribution": {},
            "urgent_ratio": 0.0,
        }

    categories = Counter(t.get("category", "unknown") for t in tickets)
    priorities = Counter(t.get("priority", "normal") for t in tickets)

    top_categories = [
        {
            "category": cat,
            "count": count,
            "share": round(count / total, 3),
        }
        for cat, count in categories.most_common(top_n)
    ]

    urgent_count = priorities.get("urgent", 0)

    return {
        "total": total,
        "top_categories": top_categories,
        "priority_distribution": dict(priorities),
        "urgent_ratio": round(urgent_count / total, 3),
    }
