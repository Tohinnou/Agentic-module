import uuid
from datetime import date, datetime, time
from pathlib import Path
import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sandbox.models import Base, Ticket
from sandbox.tools.generate_report import (
    GenerateReportInput,
    TOOL_METADATA,
    generate_report,
)

# --- Fixture : DB SQLite in-memory, isolée par test ---

@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
    
    
# --- Helper : seed des tickets avec created_at explicite ---
    
def _seed_tickets(db_session, tickets_spec):
    """Insère les tickets du golden dans la DB.
    
    `created_at` est mis à midi (12:00) pour s'écarter des bornes
    [time.min, time.max] utilisées par le filtre période dans le builder.
    Sinon les cases boundary deviennent ambigus.
    """
    for spec in tickets_spec:
      ticket = Ticket(
        id=spec.get("ticket_id") or str(uuid.uuid4()),
        subject="Seed ticket",
        category=spec["category"],
        priority="normal",
        created_at=datetime.combine(
            date.fromisoformat(spec["created_at"]),
            time(12, 0),
        ),
      )
      db_session.add(ticket)
    db_session.commit()
    
# --- Chargement du golden (1 source de vérité, partagée avec le YAML) ---
    
GOLDEN_PATH = Path(__file__).parent.parent / "evals" / "report_golden.yaml"
GOLDEN = yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))
CASES = GOLDEN["cases"]
    
    
# --- Assertion helper : branche conditionnelle par clé du golden ---
    
def _assert_expected(out, expected):
    """Inspecte chaque clé du golden `expected` et exécute l'assertion correspondante.
        
    Les clés sont optionnelles (un case n'a pas forcément tous les checks) — on
    skip silencieusement quand la clé est absente.
    """
    if "top_categories" in expected:
        actual = [(c.category, c.count) for c in out.top_categories]
        spec = [(s["category"], s["count"]) for s in expected["top_categories"]]
        assert actual == spec, (
            f"top_categories mismatch:\n  got      {actual}\n  expected {spec}"
        )
    
        if "top_categories_length" in expected:
            assert len(out.top_categories) == expected["top_categories_length"], (
                f"top_categories length {len(out.top_categories)} "
                f"!= {expected['top_categories_length']}"
            )
    
        if "top_categories_all_count" in expected:
            target = expected["top_categories_all_count"]
            for cc in out.top_categories:
                assert cc.count == target, (
                    f"category '{cc.category}' has count={cc.count}, "
                    f"expected all == {target}"
                )
    
        if "summary_contains" in expected:
            for needle in expected["summary_contains"]:
                assert needle in out.summary, (
                    f"summary missing '{needle}': {out.summary!r}"
                )
    
        if "recommendations_contains" in expected:
            for needle in expected["recommendations_contains"]:
                assert any(needle in r for r in out.recommendations), (
                    f"'{needle}' missing in any recommendation:\n  {out.recommendations}"
                )
    
        if "recommendations_not_contains" in expected:
            for needle in expected["recommendations_not_contains"]:
                for rec in out.recommendations:
                    assert needle not in rec, (
                        f"'{needle}' should NOT appear in recommendation: {rec!r}"
                    )
    
        if "report_markdown_contains" in expected:
            for needle in expected["report_markdown_contains"]:
                assert needle in out.report_markdown, (
                    f"report_markdown missing '{needle}'"
                )
    
    
# --- Main parametrize test : 1 case golden = 1 test pytest ---
    
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_generate_report_golden(case, db_session):
    _seed_tickets(db_session, case["given"]["tickets"])
    payload = GenerateReportInput(**case["input"])
    out = generate_report(payload, db_session)
    _assert_expected(out, case["expected"])
    
    
# --- Test additionnel : stamping AgBOM toujours présent ---
    
def test_output_includes_versioning(db_session):
    out = generate_report(
        GenerateReportInput(
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 7),
        ),
        db_session,
    )
    assert out.template_version, "template_version manquant en sortie"
    assert out.rules_version, "rules_version manquant en sortie"
