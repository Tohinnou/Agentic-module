"""Golden Dataset runner — pattern eval_as_unit_test (CLAUDE.md §6, Phase 8.1).

Contrat : meta/golden_dataset_spec.md. Fixture : evals/golden.yaml.

Deux couches, deux fonctions de test — délibérément séparées :

  - `test_golden_behavior`  : category + priority + placeholders_nonempty.
    Couche DÉTERMINISTE (classif + draft). Attendue verte sur 100% des cas.

  - `test_golden_retrieval` : policy_doc_id (BM25 top-1) vs l'INTENTION.
    Couche EMPIRIQUE. Les cas `retrieval_status: gap` sont marqués xfail(strict) :
    le golden encode le doc VOULU, pas le doc observé (spec §5). Un gap est un bug
    tracké — le golden rouge EST le test de reproduction (Rule 1, TDD-inversé).

Quand le retrieval sera corrigé, un cas gap passera XPASS → strict xfail le signale
en échec → on flippe `gap` → `confirmed` dans golden.yaml. Scoreboard auto-nettoyant.

Runner offline : SupportAgent(enforce_policy=False, evaluate=False) — aucune gouvernance
(testée en Phase 6), aucun LLM (qualité = judge, Phase 8.3). 100% déterministe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from sandbox.agents.orchestrator import SupportAgent
from sandbox.retrieval.corpus import load_corpus

FIXTURE_PATH = Path(__file__).parent.parent / "evals" / "golden.yaml"
SPEC_PATH = Path(__file__).parent.parent / "meta" / "golden_dataset_spec.md"


def _load_fixture() -> dict[str, Any]:
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


FIXTURE = _load_fixture()
META = FIXTURE["meta"]
CASES = FIXTURE["cases"]
VALID_DOCS = {doc.doc_id for doc in load_corpus()}


def _run(case: dict[str, Any]) -> Any:
    """Exécute l'agent sur un cas golden, offline et déterministe."""
    agent = SupportAgent(
        enforce_policy=False, evaluate=False, session_id=case["id"]
    )
    return agent.run(case["when"]["question"])


def _retrieval_param(case: dict[str, Any]) -> Any:
    """Param pytest : xfail(strict) si le cas est un gap retrieval connu."""
    marks: tuple[Any, ...] = ()
    if case.get("retrieval_status") == "gap":
        reason = (
            f"retrieval gap: BM25 renvoie '{case.get('observed_doc')}' "
            f"au lieu de '{case['then']['policy_doc_id']}'"
        )
        marks = (pytest.mark.xfail(reason=reason, strict=True),)
    return pytest.param(case, id=case["id"], marks=marks)


# --------------------------------------------------------------------------- #
# Meta-tests : intégrité de la fixture (échouent AVANT de rien exécuter)       #
# --------------------------------------------------------------------------- #

def test_fixture_ids_unique_and_nonempty() -> None:
    ids = [c["id"] for c in CASES]
    assert ids, "golden.yaml ne contient aucun cas."
    assert len(ids) == len(set(ids)), f"IDs dupliqués : {ids}"


def test_fixture_enums_and_docs_valid() -> None:
    """Chaque cas ne référence que des catégories/priorités/docs connus."""
    for case in CASES:
        then = case["then"]
        assert then["category"] in META["categories"], (
            f"{case['id']}: catégorie inconnue {then['category']}"
        )
        assert then["priority"] in META["priorities"], (
            f"{case['id']}: priorité inconnue {then['priority']}"
        )
        assert then["policy_doc_id"] in VALID_DOCS, (
            f"{case['id']}: policy_doc_id '{then['policy_doc_id']}' absent du corpus"
        )


def test_fixture_gap_cases_are_well_formed() -> None:
    """retrieval_status ∈ {confirmed, gap} ; gap ⇒ observed_doc (connu) présent."""
    for case in CASES:
        status = case.get("retrieval_status")
        assert status in {"confirmed", "gap"}, (
            f"{case['id']}: retrieval_status invalide {status!r}"
        )
        if status == "gap":
            observed = case.get("observed_doc")
            assert observed in VALID_DOCS, (
                f"{case['id']}: gap sans observed_doc valide ({observed!r})"
            )
            assert observed != case["then"]["policy_doc_id"], (
                f"{case['id']}: gap mais observed_doc == doc voulu (incohérent)"
            )


# --------------------------------------------------------------------------- #
# Couche déterministe — attendue verte sur 100% des cas                        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden_behavior(case: dict[str, Any]) -> None:
    """classify + priority + HITL placeholders : le squelette déterministe."""
    resp = _run(case)
    then = case["then"]
    assert resp.category == then["category"], (
        f"{case['id']}: category {resp.category} != {then['category']}"
    )
    assert resp.priority == then["priority"], (
        f"{case['id']}: priority {resp.priority} != {then['priority']}"
    )
    assert (len(resp.placeholders) > 0) == then["placeholders_nonempty"], (
        f"{case['id']}: placeholders_nonempty attendu {then['placeholders_nonempty']}"
    )


# --------------------------------------------------------------------------- #
# Couche retrieval — 3 confirmed verts + 7 gap en xfail(strict)                #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("case", [_retrieval_param(c) for c in CASES])
def test_golden_retrieval(case: dict[str, Any]) -> None:
    """policy_doc_id = doc VOULU. Les gaps xfail : golden encode l'intention (spec §5)."""
    resp = _run(case)
    assert resp.policy_doc_id == case["then"]["policy_doc_id"], (
        f"{case['id']}: policy_doc_id {resp.policy_doc_id} "
        f"!= {case['then']['policy_doc_id']} (voulu)"
    )


# --------------------------------------------------------------------------- #
# Garde pass^k — déterminisme (spec §8)                                        #
# --------------------------------------------------------------------------- #

def test_golden_passk_determinism() -> None:
    """pass^k : même input × k runs × config identique → sortie identique.

    Sur ce pipeline déterministe, pass^k == 1.0 PAR CONSTRUCTION. Ce test est une
    GARDE : s'il flanche, un non-déterminisme a fui (itération de set, ordre de dict,
    horloge). Les vraies dents de pass^k arrivent en 8.3 (juge LLM probabiliste).
    """
    case = CASES[0]
    k = 3
    outputs = set()
    for _ in range(k):
        resp = _run(case)
        outputs.add(
            (
                resp.category,
                resp.priority,
                resp.policy_doc_id,
                tuple(sorted(resp.placeholders)),
            )
        )
    assert len(outputs) == 1, f"pass^{k} < 1.0 : sortie non déterministe {outputs}"
