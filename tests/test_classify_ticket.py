from sandbox.tools.classify_ticket import (
      ClassifyTicketInput,
      ClassifyTicketOutput,
      classify_ticket,
  )

def test_returns_output_shape():
  out = classify_ticket(ClassifyTicketInput(text="Bonjour"))
  assert isinstance(out, ClassifyTicketOutput)
  assert 0.0 <= out.confidence <= 1.0
  
  
def test_cancellation_routing():
      out = classify_ticket(
          ClassifyTicketInput(text="Je veux annuler ma réservation aujourd'hui")
      )
      assert out.category == "cancellation"
      assert out.priority == "high"
      assert "annuler" in out.matched_keywords


def test_safety_escalates_to_urgent():
      out = classify_ticket(
          ClassifyTicketInput(text="Personne tombée à l'eau, urgence secours")
      )
      assert out.category == "safety"
      assert out.priority == "urgent"


def test_unknown_text_falls_back_to_other_low():
      out = classify_ticket(ClassifyTicketInput(text="Bonjour"))
      assert out.category == "other"
      assert out.priority == "low"
      assert out.matched_keywords == []
      assert out.confidence == 0.0