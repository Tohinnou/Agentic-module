from sandbox.tools.draft_reply import (                                                                                                                  
      DraftReplyInput,                                                                                                                                     
      DraftReplyOutput,                                                                                                                                  
      TOOL_METADATA,                                                                                                                                       
      draft_reply,                                                                                                                                         
  )                                                                                                                 
def test_returns_output_shape():                                                                                                                         
      out = draft_reply(                                                                                                                                   
          DraftReplyInput(                                                                                                                                 
              category="cancellation",                                                                                                                   
              priority="normal",
              policy_doc_id="policy_cancellation_v2",
          )
      )
      assert isinstance(out, DraftReplyOutput)
      assert out.tone in {"formal", "empathetic", "urgent", "neutral"}
      assert out.cited_policy_id == "policy_cancellation_v2"
      assert "Marina Rentals" in out.draft_text


def test_tone_routing():
      # safety override : peu importe la priority, ton = empathetic
      safety = draft_reply(
          DraftReplyInput(category="safety", priority="urgent", policy_doc_id="p1")
      )
      assert safety.tone == "empathetic"

      # urgent priority sur catégorie non-safety → ton = urgent
      damage_urgent = draft_reply(
          DraftReplyInput(category="damage", priority="urgent", policy_doc_id="p2")
      )
      assert damage_urgent.tone == "urgent"

      # cancellation normal → branche "formal"
      cancel = draft_reply(
          DraftReplyInput(category="cancellation", priority="normal", policy_doc_id="p3")
      )
      assert cancel.tone == "formal"

      # equipment normal → branche par défaut "neutral"
      equip = draft_reply(
          DraftReplyInput(category="equipment", priority="normal", policy_doc_id="p4")
      )
      assert equip.tone == "neutral"


def test_placeholders_extracted_sorted_and_unique():
      out = draft_reply(
          DraftReplyInput(
              category="cancellation", priority="normal", policy_doc_id="p1"
          )
      )
      # cancellation.txt contient ces 5 placeholders (CUSTOMER_NAME apparaît 1x, AGENT_NAME 1x, etc.)
      expected = [
          "[[AGENT_NAME]]",
          "[[BOOKING_DATE]]",
          "[[BOOKING_ID]]",
          "[[CUSTOMER_NAME]]",
          "[[SUPPORT_EMAIL]]",
      ]
      assert out.placeholders == expected
      # tri alphabétique + dedup garantis
      assert out.placeholders == sorted(set(out.placeholders))


def test_other_fallback():
      out = draft_reply(
          DraftReplyInput(category="other", priority="low", policy_doc_id="p_other")
      )
      assert out.tone == "neutral"
      assert "[[CUSTOMER_NAME]]" in out.placeholders
      assert out.cited_policy_id == "p_other"


def test_tool_metadata_shape():
      assert TOOL_METADATA["name"] == "draft_reply"
      assert TOOL_METADATA["risk_level"] == "draft"
      # schemas Pydantic auto-générés → présence des champs attendus
      in_props = TOOL_METADATA["input_schema"]["properties"]
      out_props = TOOL_METADATA["output_schema"]["properties"]
      assert {"category", "priority", "policy_doc_id"} <= set(in_props.keys())
      assert {"draft_text", "placeholders", "tone", "cited_policy_id"} <= set(out_props.keys())