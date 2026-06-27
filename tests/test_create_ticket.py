"""Tests : create_ticket (Act level, side-effect INSERT)."""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sandbox.models import Base, Ticket
from sandbox.tools.create_ticket import (
    TOOL_METADATA,
    CreateTicketInput,
    create_ticket,
)


@pytest.fixture
def db_session():
    """DB SQLite in-memory, isolée par test."""
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


def _valid_input(**overrides) -> CreateTicketInput:
    """Factory : payload minimum valide, surchargeable par test."""
    base = dict(
        subject="Demande annulation",
        category="cancellation",
        priority="normal",
        cited_policy_id="MR-CANCEL-2024-01",
    )
    base.update(overrides)
    return CreateTicketInput(**base)


def test_create_returns_output_shape(db_session):
    out = create_ticket(_valid_input(), db_session)
    assert len(out.ticket_id) == 36  # UUID
    assert out.status == "new"
    assert out.idempotency_replay is False
    assert out.created_at is not None


def test_ticket_persisted_in_db(db_session):
      out = create_ticket(
          _valid_input(subject="Sujet test", cited_policy_id="MR-X-2024"),
          db_session,
      )
      row = db_session.execute(
          select(Ticket).where(Ticket.id == out.ticket_id)
      ).scalar_one()
      assert row.subject == "Sujet test"
      assert row.category == "cancellation"
      assert row.priority == "normal"
      assert row.cited_policy_id == "MR-X-2024"
      assert row.status == "new"


def test_idempotency_replay_returns_same_ticket(db_session):
      payload = _valid_input(idempotency_key="key-abc-123")
      first = create_ticket(payload, db_session)
      second = create_ticket(payload, db_session)
      assert first.ticket_id == second.ticket_id
      assert first.idempotency_replay is False
      assert second.idempotency_replay is True
      count = len(db_session.execute(select(Ticket)).scalars().all())
      assert count == 1


def test_no_idempotency_key_creates_new_each_time(db_session):
      first = create_ticket(_valid_input(), db_session)
      second = create_ticket(_valid_input(), db_session)
      assert first.ticket_id != second.ticket_id
      count = len(db_session.execute(select(Ticket)).scalars().all())
      assert count == 2


def test_pydantic_rejects_empty_subject():
      with pytest.raises(ValidationError):
          _valid_input(subject="")

def test_pydantic_rejects_invalid_category():
      with pytest.raises(ValidationError):
          CreateTicketInput(
              subject="ok",
              category="not-a-category",
              priority="normal",
              cited_policy_id="MR-X",
          )


def test_draft_text_with_placeholders_persisted_intact(db_session):
      draft = "Bonjour [[CUSTOMER_NAME]], votre réservation [[BOOKING_ID]]..."
      out = create_ticket(_valid_input(draft_text=draft), db_session)
      row = db_session.execute(
          select(Ticket).where(Ticket.id == out.ticket_id)
      ).scalar_one()
      assert row.draft_text == draft
      assert "[[CUSTOMER_NAME]]" in row.draft_text


def test_no_pii_columns_in_ticket_schema():
      """Régression Q1 : aucun champ PII ne doit apparaître dans Ticket."""
      cols = {c.name for c in Ticket.__table__.columns}
      forbidden = {"customer_email", "customer_name", "message", "body", "email", "phone"}
      leaked = cols & forbidden
      assert leaked == set(), f"PII leakage in Ticket schema: {leaked}"


def test_tool_metadata_shape():
      assert TOOL_METADATA["name"] == "create_ticket"
      assert TOOL_METADATA["risk_level"] == "act"
      in_props = set(TOOL_METADATA["input_schema"]["properties"].keys())
      assert {"subject", "category", "priority", "cited_policy_id"} <= in_props
      assert "body" not in in_props  # régression Q1
      out_props = set(TOOL_METADATA["output_schema"]["properties"].keys())
      assert {"ticket_id", "status", "created_at", "idempotency_replay"} <= out_props