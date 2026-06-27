"""Tool : création d'un ticket Marina Rentals (act-level, side-effect: INSERT en DB)."""                   

from datetime import datetime                                                                                                                            

from pydantic import BaseModel, Field                                                                                                                    
from sqlalchemy import select                                                                                                                          
from sqlalchemy.exc import IntegrityError                                                                                                                
from sqlalchemy.orm import Session

from sandbox.classification.rules import Category, Priority                                                                                            
from sandbox.models import Ticket


class CreateTicketInput(BaseModel):
    subject: str = Field(..., min_length=1, description="Sujet du ticket (ex: 'Problème de paiement').")
    category: Category = Field(..., description="Catégorie du ticket (sortie de classify_ticket).")
    priority: Priority = Field(..., description="Priorité du ticket (sortie de classify_ticket).")
    cited_policy_id: str = Field(..., min_length=1, description="ID du doc de policy cité (sortie de retrieve_docs).")
    draft_text: str | None = Field(default=None, max_length=10000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=64)
    

class CreateTicketOutput(BaseModel):
    ticket_id: str = Field(..., description="ID du ticket créé (UUID).")
    status: str = Field(..., description="Statut initial du ticket (ex: 'new').")
    idempotency_replay: bool = Field(..., description="True si le ticket a déjà été créé avec le même idempotency_key.")
    created_at: datetime = Field(..., description="Timestamp de création du ticket.")
    
def create_ticket(payload: CreateTicketInput, db_session: Session) -> CreateTicketOutput:
    """Crée un ticket support Marina Rentals en DB (INSERT)."""
    ticket = Ticket(
        subject=payload.subject,
        category=payload.category,
        priority=payload.priority,
        cited_policy_id=payload.cited_policy_id,
        draft_text=payload.draft_text,
        idempotency_key=payload.idempotency_key,
    )
    db_session.add(ticket)
    try:
        db_session.commit()
        db_session.refresh(ticket)
    except IntegrityError as e:
        db_session.rollback()
        if payload.idempotency_key is None:
          raise
        existing_ticket = db_session.execute(
            select(Ticket).where(Ticket.idempotency_key == payload.idempotency_key)
        ).scalar_one()
        return CreateTicketOutput(
            ticket_id=existing_ticket.id,
            status=existing_ticket.status,
            idempotency_replay=True,
            created_at=existing_ticket.created_at,
        )
    
    return CreateTicketOutput(
        ticket_id=ticket.id,
        status=ticket.status,
        idempotency_replay=False,
        created_at=ticket.created_at,
    )
    
    
TOOL_METADATA = {
      "name": "create_ticket",
      "description": (
        "Crée un ticket Marina Rentals en base (INSERT). Side-effect non-idempotent par défaut, "
        "rendu idempotent par fourniture d'un idempotency_key (unique en DB). "
        "À utiliser APRÈS retrieve_docs + classify_ticket + draft_reply, comme dernière étape du "
        "workflow agent → ticket. Audit trail : cited_policy_id stocké pour traçabilité de la "
        "décision agent (quel doc policy a guidé la réponse). Le draft_text est stocké avec "
        "placeholders [[VAR]] non résolus (Context Hygiene — résolution downstream uniquement). "
        "ATTENTION (risk_level=act) : nécessite Vibe Diff (résumé humain pré-action) avant exécution "
        "en production. Le ticket créé est immédiatement visible dans la file de l'agent humain."
      ),
      "risk_level": "act",
      "input_schema": CreateTicketInput.model_json_schema(),
      "output_schema": CreateTicketOutput.model_json_schema(),
}