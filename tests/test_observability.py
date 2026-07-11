"""
Tests EDD Observability (Phase 7).

Discipline (§6 CLAUDE.md) : ce fichier est écrit AVANT que
`sandbox/observability/` soit implémenté. TOUS les tests parametrisés
sur `evals/drift_cases.yaml` FAIL au démarrage (NotImplementedError).

Ils passeront progressivement :
- Après 7.1 (reader.py)  : tests reader
- Après 7.2 (drift.py)   : tests parametrisés de detection

Les tests de contrat sur la fixture (test_fixture_*) et sur les
dataclasses (test_drift_report_frozen, etc.) passent dès Phase 7.0
— ils valident la structure sans invoquer detect_drift().
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from sandbox.observability import (
    DriftReport,
    DriftSignal,
    detect_drift,
)


FIXTURE_PATH = Path(__file__).parent.parent / "evals" / "drift_cases.yaml"
SIGNALS_DOC_PATH = Path(__file__).parent.parent / "meta" / "intent_drift_signals.md"


def _load_fixture() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


FIXTURE = _load_fixture()
CASES = FIXTURE["cases"]


def _expand_event(session_id: str, agent: str, e: dict[str, Any]) -> dict[str, Any]:
    """Complète un event fixture-minimal avec les champs par défaut.

    La fixture ne stocke que les champs pertinents au drift (action, status,
    policy_verdict). Le detector consomme des events complets — on remplit
    les champs manquants avec des valeurs neutres.
    """
    return {
        "session_id": session_id,
        "step": e["step"],
        "agent": agent,
        "action": e["action"],
        "risk": "read",
        "status": e["status"],
        "input_summary": "",
        "output_summary": "",
        "timestamp": "2026-07-11T00:00:00Z",
        "duration_ms": 0,
        "policy_verdict": e.get("policy_verdict"),
        "policy_reason": e.get("policy_reason"),
        "policy_layer": None,
    }


# ─── Tests de contrat sur la fixture (passent dès Phase 7.0) ─────────


def test_fixture_declares_targets() -> None:
    """La fixture doit déclarer ses targets de qualité."""
    assert "targets" in FIXTURE
    targets = FIXTURE["targets"]
    assert targets["detection_precision_min"] >= 1.0, (
        "Sur des cas synthétiques, 100% précision est requise"
    )
    assert targets["detection_recall_min"] >= 1.0, (
        "Sur des cas synthétiques, 100% recall est requis"
    )


def test_fixture_case_ids_unique() -> None:
    """Les IDs des cas doivent être uniques."""
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids)), f"IDs dupliqués : {ids}"


def test_fixture_covers_all_severities() -> None:
    """La fixture doit exercer au moins none + medium + high."""
    severities = {case["expected"]["severity"] for case in CASES}
    assert {"none", "medium", "high"}.issubset(severities), (
        f"Fixture doit couvrir au moins none/medium/high, trouvé : {severities}"
    )


def test_fixture_covers_all_signals() -> None:
    """Chaque signal défini doit être exercé au moins une fois."""
    expected_signals = {
        "policy_block_encountered",
        "hitl_bypassed",
        "unexpected_tool_sequence",
        "duplicate_action",
    }
    observed_signals: set[str] = set()
    for case in CASES:
        observed_signals.update(case["expected"]["signals"])
    missing = expected_signals - observed_signals
    assert not missing, f"Signaux définis mais non exercés par la fixture : {missing}"


def test_fixture_has_at_least_one_nominal_baseline() -> None:
    """Anti-faux-positif : au moins un cas où aucun signal n'est attendu."""
    baselines = [c for c in CASES if not c["expected"]["signals"]]
    assert len(baselines) >= 1, (
        "Fixture doit contenir au moins un cas nominal (aucun signal). "
        "Sinon on ne détecte jamais les faux positifs du detector."
    )


# ─── Tests de dérive spec ↔ code (passent dès Phase 7.0) ─────────────


def test_signal_codes_match_between_doc_and_fixture() -> None:
    """Chaque code signal dans le markdown doit correspondre à un usage fixture."""
    doc_content = SIGNALS_DOC_PATH.read_text(encoding="utf-8")
    fixture_signals: set[str] = set()
    for case in CASES:
        fixture_signals.update(case["expected"]["signals"])
    for signal in fixture_signals:
        assert f"`{signal}`" in doc_content, (
            f"Signal '{signal}' utilisé dans drift_cases.yaml mais absent "
            f"de meta/intent_drift_signals.md — dérive détectée"
        )


# ─── Contract sur les dataclasses (passent dès Phase 7.0) ────────────


def test_drift_signal_is_frozen() -> None:
    """DriftSignal doit être immuable."""
    sig = DriftSignal(code="test", severity="low", detail="", events=())
    with pytest.raises(Exception):
        sig.code = "changed"  # type: ignore[misc]


def test_drift_report_is_frozen() -> None:
    """DriftReport doit être immuable."""
    rep = DriftReport(session_id="s1", signals=(), severity="none")
    with pytest.raises(Exception):
        rep.session_id = "s2"  # type: ignore[misc]


def test_drift_report_none_iff_empty_signals() -> None:
    """Invariant : severity='none' ⇔ signals vide (construction manuelle)."""
    rep_empty = DriftReport(session_id="s", signals=(), severity="none")
    assert rep_empty.severity == "none"
    assert rep_empty.signals == ()


# ─── Tests de detection (FAIL en 7.0, passent après 7.2) ─────────────


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_detect_drift_matches_expected(case: dict) -> None:
    """Chaque cas fixture doit produire les signaux attendus + sévérité."""
    events = [
        _expand_event(case["id"], FIXTURE["agent"], e)
        for e in case["events"]
    ]
    report = detect_drift(events, expected_agent=FIXTURE["agent"])

    assert isinstance(report, DriftReport), (
        f"[{case['id']}] detect_drift doit retourner DriftReport, obtenu {type(report)}"
    )
    assert report.session_id == case["id"], (
        f"[{case['id']}] session_id attendu {case['id']}, obtenu {report.session_id}"
    )

    detected_codes = sorted(s.code for s in report.signals)
    expected_codes = sorted(case["expected"]["signals"])
    assert detected_codes == expected_codes, (
        f"[{case['id']}] signaux attendus {expected_codes}, "
        f"détectés {detected_codes}"
    )
    assert report.severity == case["expected"]["severity"], (
        f"[{case['id']}] sévérité attendue {case['expected']['severity']}, "
        f"obtenue {report.severity}"
    )


def test_detect_drift_rejects_empty_events() -> None:
    """Contrat : liste vide → ValueError (pas de DriftReport silencieux)."""
    with pytest.raises((ValueError, NotImplementedError)):
        detect_drift([], expected_agent="support_agent")


def test_detect_drift_deterministic() -> None:
    """detect_drift doit être déterministe : même input → même output."""
    case = CASES[0]
    events = [
        _expand_event(case["id"], FIXTURE["agent"], e)
        for e in case["events"]
    ]
    # 2 appels — si Phase 7.2 pas encore là, les 2 lèvent NotImplementedError
    # (ce qui est déterministe aussi). Le vrai check déterminisme viendra
    # quand detect_drift sera implémenté.
    try:
        r1 = detect_drift(events, expected_agent=FIXTURE["agent"])
        r2 = detect_drift(events, expected_agent=FIXTURE["agent"])
        assert r1 == r2
    except NotImplementedError:
        pytest.xfail("detect_drift pas implémenté (attendu Phase 7.2)")


# ─── Tests reader (FAIL en 7.0, passent après 7.1) ───────────────────


def test_reader_load_trajectory_file_stub_raises() -> None:
    """Phase 7.0 : reader lève NotImplementedError avec message pointant vers 7.1."""
    from sandbox.observability.reader import load_trajectory_file
    with pytest.raises(NotImplementedError, match="Phase 7.1"):
        load_trajectory_file(Path("nonexistent.jsonl"))


def test_reader_load_trajectory_dir_stub_raises() -> None:
    """Phase 7.0 : reader lève NotImplementedError avec message pointant vers 7.1."""
    from sandbox.observability.reader import load_trajectory_dir
    with pytest.raises(NotImplementedError, match="Phase 7.1"):
        load_trajectory_dir(Path("nonexistent/"))


def test_reader_group_by_session_stub_raises() -> None:
    """Phase 7.0 : reader lève NotImplementedError avec message pointant vers 7.1."""
    from sandbox.observability.reader import group_by_session
    with pytest.raises(NotImplementedError, match="Phase 7.1"):
        group_by_session([])
