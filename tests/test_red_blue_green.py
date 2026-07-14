"""Red/Blue/Green teaming — eval (Phase 10, capstone).

Chaque cas Red passe par Blue (détection) et Green (réponse) : on asserte le bon signal
et la bonne réponse — le RED_CASES est le golden du teaming. Meta : les 4 signaux Blue et
les 3 réponses Green sont tous exercés, et le contrôle nominal n'est PAS mis en quarantaine
(garde false-positive). Offline, déterministe, aucun LLM.
"""

import pytest

from sandbox.security import RED_CASES, monitor, suggest, triage
from sandbox.security.blue_team import SIGNALS
from sandbox.security.models import Action


# ─── Blue : détection ─────────────────────────────────────────────
@pytest.mark.parametrize("case", RED_CASES, ids=lambda c: c.id)
def test_blue_detects_expected_signal(case) -> None:
    assert monitor(case.action) == case.expected_signal


# ─── Green : réponse (à partir du signal attendu, en isolation) ───
@pytest.mark.parametrize("case", RED_CASES, ids=lambda c: c.id)
def test_green_suggests_expected_response(case) -> None:
    assert suggest(case.expected_signal, case.action) == case.expected_response


# ─── Pipeline end-to-end : triage ─────────────────────────────────
@pytest.mark.parametrize("case", RED_CASES, ids=lambda c: c.id)
def test_triage_end_to_end(case) -> None:
    d = triage(case.action)
    assert d.signal == case.expected_signal
    assert d.response == case.expected_response
    assert d.quarantined == (case.expected_response != "proceed")


# ─── Couverture du contrat ────────────────────────────────────────
def test_catalog_exercises_all_blue_signals() -> None:
    covered = {c.expected_signal for c in RED_CASES if c.expected_signal}
    assert set(SIGNALS) <= covered, f"signaux Blue non couverts : {set(SIGNALS) - covered}"


def test_catalog_exercises_all_green_responses() -> None:
    covered = {c.expected_response for c in RED_CASES}
    assert {"bloquer", "corriger_le_brouillon", "demander_validation_humaine"} <= covered


def test_nominal_control_is_not_quarantined() -> None:
    benign = [c for c in RED_CASES if c.vector == "benign"]
    assert benign, "besoin d'un contrôle nominal (garde false-positive)"
    for c in benign:
        assert not triage(c.action).quarantined


def test_clean_action_proceeds() -> None:
    assert triage(Action(kind="retrieve", target="conditions annulation")).response == "proceed"
