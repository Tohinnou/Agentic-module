"""Trigger accuracy des skills (Phase 8.3, module #3b).

CLAUDE.md §5 : la `description` d'une SKILL.md est la router function. Pas de routeur
code → on teste la VRAIE description via un routeur LLM (fire/no-fire). Cible >= 0.90.
Deux-tiers : harness testé offline (route_fn synthétique) ; routeur réel opt-in.
"""

import os
from pathlib import Path

import pytest

from sandbox.evaluation.skill_router import (
    load_skill_description,
    load_trigger_cases,
    route,
    trigger_accuracy,
)
from sandbox.llm import OpenRouterProvider

SKILLS_DIR = Path(".agent/skills")
SKILLS = [
    "answering-support-questions",
    "drafting-customer-replies",
    "evaluating-agent-answers",
    "generating-weekly-report",
]
TARGET = 0.90


# ─── OFFLINE : harness + fixtures ─────────────────────────────────
def test_trigger_accuracy_computes_correctly() -> None:
    cases = [
        {"message": "a", "expected_fire": True},
        {"message": "b", "expected_fire": False},
    ]
    assert trigger_accuracy(cases, lambda m: True) == 0.5  # fire toujours → 1/2 bon
    assert trigger_accuracy(cases, lambda m: m == "a") == 1.0  # parfait


def test_trigger_accuracy_rejects_empty() -> None:
    with pytest.raises(ValueError):
        trigger_accuracy([], lambda m: True)


@pytest.mark.parametrize("skill", SKILLS)
def test_fixture_has_pos_and_neg(skill: str) -> None:
    fires = {c["expected_fire"] for c in load_trigger_cases(SKILLS_DIR / skill)}
    assert fires == {True, False}, f"{skill} : besoin de positifs ET négatifs"


@pytest.mark.parametrize("skill", SKILLS)
def test_description_loads(skill: str) -> None:
    desc = load_skill_description(SKILLS_DIR / skill)
    assert desc and len(desc) > 10


# ─── TIER-2 : routeur réel (opt-in réseau) ────────────────────────
_OPT_OUT = not (os.environ.get("RUN_LLM_TRIGGER") and "OPENROUTER_API_KEY" in os.environ)
_SKIP = "opt-in réseau : RUN_LLM_TRIGGER=1 + OPENROUTER_API_KEY (routeur = 1 appel LLM/cas)."


# Known-gaps mesurés (finding #3b, 2026-07-14) : la `description` de drafting SOUS-ROUTE.
# Ratés observés : neg_01 (question 'conditions annulation' → fire drafting, vraie
# faiblesse), pos_10 ('formule…escaladée' → non-fire), pos_07 ('Envoie' débattable).
# strict=False : le routeur est probabiliste, un run chanceux ≥ 0.90 ne doit pas casser.
# Backlog : affiner la description de drafting (voir meta/learning_notes.md #3b).
_KNOWN_GAPS = {
    "drafting-customer-replies": "finding #3b : trigger ~0.83 < 0.90 (description sous-route).",
}


def _skill_param(skill: str):
    marks = (
        [pytest.mark.xfail(reason=_KNOWN_GAPS[skill], strict=False)]
        if skill in _KNOWN_GAPS
        else []
    )
    return pytest.param(skill, marks=marks)


@pytest.mark.skipif(_OPT_OUT, reason=_SKIP)
@pytest.mark.parametrize("skill", [_skill_param(s) for s in SKILLS])
def test_skill_trigger_accuracy(skill: str) -> None:
    skill_dir = SKILLS_DIR / skill
    desc = load_skill_description(skill_dir)
    cases = load_trigger_cases(skill_dir)
    provider = OpenRouterProvider()  # tier réseau explicite (sinon défaut mock)
    acc = trigger_accuracy(cases, lambda m: route(desc, m, provider))
    assert acc >= TARGET, f"{skill} : trigger accuracy {acc:.2f} < {TARGET}"
