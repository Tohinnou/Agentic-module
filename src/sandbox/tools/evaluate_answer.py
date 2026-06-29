"""Tool : evaluate_answer (Read level, LLM-as-judge via OpenRouter).

  Read-only : aucun side-effect DB. Cache fichier amortit les appels API.
"""

from pydantic import BaseModel, Field

from sandbox.classification.rules import Category
from sandbox.evaluation.judge import (
  DIMENSIONS,
  MODEL,
  PROMPT_VERSION,
  judge_answer,
)

class EvaluateAnswerInput(BaseModel):
      customer_request: str = Field(..., min_length=1, description="Demande textuelle du client.")
      category: Category = Field(..., description="Catégorie du ticket (sortie de classify_ticket).")
      cited_policy_id: str = Field(..., min_length=1, description="ID du doc de policy cité (audit trail).")
      cited_policy_excerpt: str = Field(..., min_length=1, description="Extrait textuel de la policy cité par l'agent.")
      draft_reply: str = Field(..., min_length=1, description="Brouillon de réponse rédigé par l'agent.")
      
class EvaluateAnswerOutput(BaseModel):
      clarte: int = Field(..., ge=0, le=5)
      exactitude: int = Field(..., ge=0, le=5)
      ton: int = Field(..., ge=0, le=5)
      securite: int = Field(..., ge=0, le=5)
      completude: int = Field(..., ge=0, le=5)
      concision: int = Field(..., ge=0, le=5)
      pertinence: int = Field(..., ge=0, le=5)
      reasoning: str = Field(..., description="Justification courte des notes basses ou limites.")
      judge_model: str = Field(..., description="Modèle pinné utilisé (AgBOM trail).")
      prompt_version: str = Field(..., description="Version du prompt utilisé (calibration trail).")
      
def evaluate_answer(payload: EvaluateAnswerInput) -> EvaluateAnswerOutput:
      """Évalue un draft de réponse par rapport à la demande client et la policy citée.
  
      Appelle le juge LLM via OpenRouter, avec cache fichier pour amortir les appels API.
      """
      raw = judge_answer(
          customer_request=payload.customer_request,
          category=payload.category,
          cited_policy_excerpt=payload.cited_policy_excerpt,
          draft_reply=payload.draft_reply,
      )
      return EvaluateAnswerOutput(
          **{dim: raw[dim] for dim in DIMENSIONS},
          reasoning=raw.get("reasoning", ""),
          judge_model=MODEL,
          prompt_version=PROMPT_VERSION,
      )
      
      
TOOL_METADATA = {
    "name": "evaluate_answer",
    "description": (
        "Note un brouillon de réponse client sur 7 dimensions (0-5) via LLM-as-judge : "
        "clarté, exactitude, ton, sécurité, complétude, concision, pertinence. "
        "Read-only : aucun side-effect DB. Utilise un cache fichier (data/judge_cache.json) "
        "keyé sur (model, prompt_version, payload) → 1er run = appel API (~5s), "
        "runs suivants instantanés. À utiliser APRÈS draft_reply pour décider si le "
        "brouillon est envoyable ou nécessite une réécriture humaine. "
        "Trail d'audit complet via judge_model + prompt_version en sortie."
    ),
    "risk_level": "read",
    "input_schema": EvaluateAnswerInput.model_json_schema(),
    "output_schema": EvaluateAnswerOutput.model_json_schema(),
}