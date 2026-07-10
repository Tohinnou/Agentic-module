"""Tool : classification rules-based d'un ticket support Marina Rentals (read-only)."""                                 
from pydantic import BaseModel, Field

from sandbox.classification.rules import Category, Priority, classify_text

class ClassifyTicketInput(BaseModel):
      text: str = Field(
          ...,
          min_length=1,
          description="Texte du ticket (sujet + corps mergés par le caller).",
      )


class ClassifyTicketOutput(BaseModel):
      category: Category
      priority: Priority
      confidence: float = Field(..., ge=0.0, le=1.0)
      matched_keywords: list[str]


def classify_ticket(payload: ClassifyTicketInput) -> ClassifyTicketOutput:
    category, priority, confidence, matched = classify_text(payload.text)
    return ClassifyTicketOutput(
        category=category,
        priority=priority,
        confidence=confidence,
        matched_keywords=matched,
    )
    
TOOL_METADATA = {
    "name": "classify_ticket",
    "description": (
        "Classe un ticket support Marina Rentals en (catégorie, priorité, confidence). "
        "À utiliser au premier contact pour router le ticket vers le bon flow et déterminer "
        "l'urgence avant de répondre. "
        "Catégories : cancellation, payment, booking, safety, weather, equipment, damage, other. "
        "Priorités : urgent, high, normal, low."
    ),
    "risk_level": "read",
    "input_schema": ClassifyTicketInput.model_json_schema(),
    "output_schema": ClassifyTicketOutput.model_json_schema(),
}