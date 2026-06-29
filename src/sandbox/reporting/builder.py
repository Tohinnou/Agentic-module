"""Aggregation déterministe + règles heuristiques + template Markdown pour les tickets Marina Rentals.

Logique pure (zéro LLM). Contraste pédagogique avec sandbox.evaluation.judge (Tool 5)
qui est probabiliste. Ici, mêmes inputs → mêmes outputs, toujours.
"""

from collections import Counter
from datetime import date, datetime, time
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from sandbox.models import Ticket

# --- Versioning (invalidation golden) ---

TEMPLATE_VERSION = "v1"   # bump si rendu Markdown change → re-valider report_golden.yaml
RULES_VERSION = "v1"      # bump si seuil R2 ou wording R1-R4 change → re-valider golden

# --- Heuristic constants (rules v1) ---

DOMINANT_THRESHOLD_PCT = 40   # R2 : seuil "catégorie dominante" (2x la part égalitaire pour 5 cats)


# --- Data classes (internes au module) ---

class CategoryCount(NamedTuple):
    category: str
    count: int


# --- Fetch (Zero Ambient Authority : db_session injecté, pas de globale) ---

def fetch_tickets(
    db_session: Session,
    period_start: date,
    period_end: date,
    ticket_ids: list[str] | None = None,
) -> list[Ticket]:
    """Récupère les tickets dans [period_start, period_end] (inclusif des deux côtés).

    Si `ticket_ids` est fourni, filtre additionnel en AND (pas OR) — un ticket hors
    période est exclu même s'il est listé.
    """
    start_dt = datetime.combine(period_start, time.min)
    end_dt = datetime.combine(period_end, time.max)
    stmt = select(Ticket).where(
        Ticket.created_at >= start_dt,
        Ticket.created_at <= end_dt,
    )
    if ticket_ids is not None:
        stmt = stmt.where(Ticket.id.in_(ticket_ids))
    return list(db_session.scalars(stmt))


# --- Aggregation (pure, zéro side-effect) ---

def aggregate_categories(tickets: list[Ticket]) -> list[CategoryCount]:
    """Compte par catégorie, trié décroissant. Counter.most_common() est stable."""
    counter = Counter(t.category for t in tickets)
    return [CategoryCount(c, n) for c, n in counter.most_common()]


def compute_days(period_start: date, period_end: date) -> int:
    """Nombre de jours dans la période, inclusif des deux côtés (cohérent avec fetch_tickets)."""
    return (period_end - period_start).days + 1


# --- Rules R1-R4 (pure) ---

def build_recommendations(
    n_tickets: int,
    top_categories: list[CategoryCount],
    days: int,
) -> list[str]:
    """Applique R1-R4. Ordre : R1 seul, OU (R3 + R2/R4 exclusifs).

    Bumpe RULES_VERSION en tête de module si tu modifies un seuil, un wording
    ou la logique de sélection ; sinon les goldens passeront alors qu'ils
    ne devraient plus.
    """
    if n_tickets == 0:
        # R1 — edge case : aucune autre règle ne s'applique (pas de division par n_tickets)
        return ["Aucun ticket sur la période ; vérifier l'ingestion."]

    recs: list[str] = []

    # R3 — toujours présent quand il y a des tickets
    avg = n_tickets / days
    recs.append(
        f"Volume total : {n_tickets} tickets sur {days} jours (moyenne {avg:.1f}/jour)."
    )

    # R2 vs R4 — mutuellement exclusifs
    top = top_categories[0]
    top_pct = round(top.count / n_tickets * 100)
    if top_pct > DOMINANT_THRESHOLD_PCT:
        recs.append(
            f"La catégorie {top.category} représente {top_pct}% des tickets ; investiguer."
        )   # R2
    else:
        recs.append(
            f"Distribution équilibrée entre {len(top_categories)} catégories."
        )   # R4

    return recs


# --- Template Markdown (pure) ---

def _ticket_word(n: int) -> str:
    """Convention française : 0 et 1 → singulier ; 2+ → pluriel."""
    return "ticket" if n <= 1 else "tickets"


def build_summary(n_tickets: int) -> str:
    return f"Rapport sur {n_tickets} {_ticket_word(n_tickets)}."


def render_markdown(
    period_start: date,
    period_end: date,
    n_tickets: int,
    top_categories: list[CategoryCount],
    recommendations: list[str],
) -> str:
    """Rend le rapport en Markdown. Bump TEMPLATE_VERSION si tu changes ce template."""
    lines = [
        "# Rapport hebdomadaire Marina Rentals",
        "",
        f"**Période** : {period_start.isoformat()} → {period_end.isoformat()}",
        "",
        "## Volume",
        f"- Total : {n_tickets} {_ticket_word(n_tickets)}",
        "",
        "## Top catégories",
    ]
    if not top_categories:
        lines.append("- Aucune")
    else:
        for cc in top_categories:
            pct = round(cc.count / n_tickets * 100)
            lines.append(f"- {cc.category} : {cc.count} ({pct}%)")
    lines.extend(["", "## Recommandations"])
    for r in recommendations:
        lines.append(f"- {r}")
    return "\n".join(lines)
