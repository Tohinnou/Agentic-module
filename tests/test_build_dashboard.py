"""Golden sur la spec A2UI de build_dashboard (Phase 9, EDD).

Le hook de la phase : une spec UI déclarative est de la DATA → testable comme tout
tool. On asserte la STRUCTURE de l'arbre (version, surface, racine, intégrité
référentielle), pas un rendu. Déterministe, offline, aucun LLM.
"""

import pytest

from sandbox.tools.build_dashboard import (
    A2UISpec,
    BuildDashboardInput,
    Component,
    QualityMetric,
    Surface,
    TicketBucket,
    _validate,
    build_dashboard,
    gather_dashboard_data,
)

_SAMPLE = BuildDashboardInput(
    tickets=[
        TicketBucket(category="cancellation", priority="normal", count=3),
        TicketBucket(category="weather", priority="urgent", count=1),
    ],
    quality=[QualityMetric(label="pass", value="2"), QualityMetric(label="fail", value="2")],
)


def _dump():
    return build_dashboard(_SAMPLE).model_dump(by_alias=True, exclude_none=True)


# ─── Golden sur la spec (structure déclarative) ───────────────────
def test_spec_envelope_is_v09_a2ui() -> None:
    spec = _dump()
    assert spec["version"] == "v0.9"
    assert spec["updateComponents"]["surfaceId"] == "support_dashboard"


def test_root_is_column_with_three_sections() -> None:
    comps = {c["id"]: c for c in _dump()["updateComponents"]["components"]}
    assert comps["root"]["component"] == "Column"
    assert comps["root"]["children"] == ["title", "tickets", "quality"]
    assert comps["title"]["text"] == "Support Dashboard"


def test_tickets_become_metrics() -> None:
    comps = {c["id"]: c for c in _dump()["updateComponents"]["components"]}
    metric = comps["ticket-cancellation-normal"]
    assert metric["component"] == "Metric"
    assert metric["value"] == "3"


def test_referential_integrity_all_children_exist() -> None:
    comps = {c["id"]: c for c in _dump()["updateComponents"]["components"]}
    for c in comps.values():
        for child in c.get("children") or []:
            assert child in comps, f"child pendouillant : {child}"


def test_text_nodes_have_no_children_key() -> None:
    """exclude_none : un Text ne trimballe pas de children/label/value nuls."""
    comps = {c["id"]: c for c in _dump()["updateComponents"]["components"]}
    assert "children" not in comps["title"]
    assert "value" not in comps["title"]


# ─── Validation défensive ─────────────────────────────────────────
def test_validate_rejects_dangling_child() -> None:
    bad = [Component(id="root", component="Column", children=["ghost"])]
    with pytest.raises(ValueError):
        _validate(bad)


def test_validate_rejects_unknown_component() -> None:
    with pytest.raises(ValueError):
        _validate([Component(id="x", component="Hologram")])


def test_validate_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError):
        _validate([Component(id="dup", component="Text"), Component(id="dup", component="Text")])


# ─── Séparation data/UI : gather (offline, données réelles) ───────
def test_gather_from_eval_artifacts_builds_valid_spec() -> None:
    data = gather_dashboard_data()
    assert data.tickets and data.quality  # dérivé de golden.yaml + judge_golden.yaml
    spec = build_dashboard(data)  # ne lève pas → spec valide
    assert isinstance(spec, A2UISpec)
    assert isinstance(spec.update_components, Surface)
    assert spec.update_components.surface_id == "support_dashboard"
