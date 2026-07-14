"""build_dashboard — tool A2UI : données → spec UI DÉCLARATIVE (Phase 9).

A2UI (Agent-to-UI) : l'agent ne peint pas de pixels, il émet une DESCRIPTION
déclarative de l'interface — un arbre de composants typés. Un renderer (web / mobile /
CLI) la transforme en UI. Séparation data/UI : une même spec → N surfaces.

Ce tool est READ (zéro side-effect) et BOUNDED (schéma in/out explicite). Il construit
un SOUS-ENSEMBLE minimal du vocabulaire v0.9 (Column / Text / Metric) — pas les 18
composants, juste ceux d'un dashboard support « tickets + qualité ».

Boucle avec la Phase 8 : la sortie est de la DATA → golden-testable comme n'importe
quel tool. `gather_dashboard_data()` dérive l'input des artefacts d'éval réels
(golden.yaml, judge_golden.yaml). Déterministe, offline, aucun LLM.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

SURFACE_ID = "support_dashboard"
A2UI_VERSION = "v0.9"
_COMPONENT_TYPES = frozenset({"Column", "Row", "Text", "Metric"})


# ─── Input : données métier ───────────────────────────────────────
class TicketBucket(BaseModel):
    category: str
    priority: str
    count: int = Field(..., ge=0)


class QualityMetric(BaseModel):
    label: str
    value: str


class BuildDashboardInput(BaseModel):
    tickets: list[TicketBucket]
    quality: list[QualityMetric]


# ─── Output : spec A2UI déclarative ───────────────────────────────
class Component(BaseModel):
    id: str
    component: str
    text: str | None = None
    label: str | None = None
    value: str | None = None
    children: list[str] | None = None


class Surface(BaseModel):
    surface_id: str = Field(serialization_alias="surfaceId")
    components: list[Component]


class A2UISpec(BaseModel):
    version: str = A2UI_VERSION
    update_components: Surface = Field(serialization_alias="updateComponents")


def _validate(components: list[Component]) -> None:
    """Invariants A2UI : ids uniques, composants connus, children résolus."""
    ids = [c.id for c in components]
    if len(ids) != len(set(ids)):
        raise ValueError("ids de composants dupliqués")
    idset = set(ids)
    for c in components:
        if c.component not in _COMPONENT_TYPES:
            raise ValueError(f"composant inconnu : {c.component!r}")
        for child in c.children or []:
            if child not in idset:
                raise ValueError(f"child {child!r} référencé par {c.id!r} n'existe pas")


def build_dashboard(payload: BuildDashboardInput) -> A2UISpec:
    """Assemble une spec A2UI : Column racine → titre + section tickets + section qualité."""
    components: list[Component] = [
        Component(id="title", component="Text", text="Support Dashboard"),
    ]

    # Section tickets : un Metric par (catégorie, priorité).
    components.append(Component(id="tickets-header", component="Text", text="Tickets"))
    ticket_ids = ["tickets-header"]
    for t in payload.tickets:
        cid = f"ticket-{t.category}-{t.priority}"
        components.append(
            Component(
                id=cid,
                component="Metric",
                label=f"{t.category}/{t.priority}",
                value=str(t.count),
            )
        )
        ticket_ids.append(cid)
    components.append(Component(id="tickets", component="Column", children=ticket_ids))

    # Section qualité : un Metric par bucket de qualité.
    components.append(Component(id="quality-header", component="Text", text="Qualité (juge)"))
    quality_ids = ["quality-header"]
    for i, q in enumerate(payload.quality):
        cid = f"quality-{i}"
        components.append(Component(id=cid, component="Metric", label=q.label, value=q.value))
        quality_ids.append(cid)
    components.append(Component(id="quality", component="Column", children=quality_ids))

    # Racine.
    components.append(
        Component(id="root", component="Column", children=["title", "tickets", "quality"])
    )

    _validate(components)
    return A2UISpec(update_components=Surface(surface_id=SURFACE_ID, components=components))


def gather_dashboard_data(
    golden_path: Path = Path("evals/golden.yaml"),
    judge_path: Path = Path("evals/judge_golden.yaml"),
) -> BuildDashboardInput:
    """Dérive les données du dashboard des artefacts d'éval (déterministe, offline).

    Séparation data/UI : cette fonction fournit la DATA ; `build_dashboard` fournit l'UI.
    """
    golden = yaml.safe_load(golden_path.read_text(encoding="utf-8"))
    ticket_counts: Counter = Counter(
        (c["then"]["category"], c["then"]["priority"]) for c in golden["cases"]
    )
    tickets = [
        TicketBucket(category=cat, priority=pri, count=n)
        for (cat, pri), n in sorted(ticket_counts.items())
    ]

    judge = yaml.safe_load(judge_path.read_text(encoding="utf-8"))
    buckets: Counter = Counter(c["bucket"] for c in judge["cases"])
    quality = [QualityMetric(label=b, value=str(n)) for b, n in sorted(buckets.items())]

    return BuildDashboardInput(tickets=tickets, quality=quality)


TOOL_METADATA = {
    "name": "build_dashboard",
    "description": (
        "Construit une spec UI DÉCLARATIVE A2UI (v0.9) d'un dashboard support à partir "
        "de données tickets + qualité. Read-only, aucun side-effect. Sortie = arbre de "
        "composants (Column/Text/Metric) qu'un renderer transforme en UI — séparation data/UI."
    ),
    "risk_level": "read",
    "input_schema": BuildDashboardInput.model_json_schema(),
    "output_schema": A2UISpec.model_json_schema(),
}
