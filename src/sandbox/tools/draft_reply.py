"""Tool : génération d'un brouillon de réponse client Marina Rentals (draft-level)."""

from typing import Literal
from pydantic import BaseModel, Field

from sandbox.classification.rules import Category, Priority
from sandbox.drafting.templates import (                                                                                  
    Tone,                                                                                                                 
    extract_placeholders,                                                                                                 
    load_template,                                                                                                        
    select_tone,
)

class DraftReplyInput(BaseModel):
    category: Category           
    priority: Priority           
    policy_doc_id: str = Field(
      ...,
      min_length=1,
      description="ID du doc de policy cité (sortie de retrieve_docs). Conservé en audit trail, non inséré dans le draft.",
    )       

class DraftReplyOutput(BaseModel):
    draft_text: str              # contient des [[VAR]] non résolus
    placeholders: list[str]      # ex: ["[[CUSTOMER_NAME]]", "[[BOOKING_ID]]"]
    tone: Tone
    cited_policy_id: str   
    

def draft_reply(payload: DraftReplyInput) -> DraftReplyOutput:
    template = load_template(payload.category)
    placeholders = extract_placeholders(template)
    tone = select_tone(payload.category, payload.priority)
    return DraftReplyOutput(
        draft_text=template,
        placeholders=placeholders,
        tone=tone,
        cited_policy_id=payload.policy_doc_id,
    )
    

TOOL_METADATA = {
    "name": "draft_reply",
    "description": (
        "Génère un brouillon de réponse client Marina Rentals à partir de la catégorie et de la "
        "priorité (sortie de classify_ticket) et de l'ID du doc policy (sortie de retrieve_docs). "
        "Le draft contient des placeholders [[VAR]] non résolus (CUSTOMER_NAME, BOOKING_ID, "
        "AGENT_NAME, etc.) à substituer par un tool downstream avant tout envoi. "
        "À utiliser APRÈS classify_ticket et retrieve_docs, AVANT tout tool d'envoi. "
        "Le draft DOIT être relu et approuvé par un humain (HITL: Human in the Loop) avant envoi effectif au client. "
        "Tone retourné : formal, empathetic, urgent, neutral."
    ),
    "risk_level": "draft",
    "input_schema": DraftReplyInput.model_json_schema(),
    "output_schema": DraftReplyOutput.model_json_schema(),
}