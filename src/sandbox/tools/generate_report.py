from datetime import date
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from sandbox.reporting.builder import (
  RULES_VERSION, 
  TEMPLATE_VERSION, 
  aggregate_categories, 
  build_recommendations,
  build_summary, 
  compute_days, 
  fetch_tickets, 
  render_markdown,
)


class GenerateReportInput(BaseModel):
    period_start: date = Field(..., description="Start date of the report period")
    period_end: date = Field(..., description="End date of the report period")
    ticket_ids: list[str] | None = Field(None, description="Optional list of ticket IDs to filter")
    
    
class CategoryCount(BaseModel):
    category: str = Field(..., description="Category name")
    count: int = Field(..., description="Count of tickets in the category")
    

class GenerateReportOutput(BaseModel):
    template_version: str = Field(..., description="Version of the report template")
    rules_version: str = Field(..., description="Version of the rules used for aggregation")
    summary: str = Field(..., description="Summary of the report")
    recommendations: list[str] = Field(..., description="Recommendations based on the report data")
    report_markdown: str = Field(..., description="Rendered Markdown report")
    top_categories: list[CategoryCount] = Field(..., description="List of top categories with counts")
    
def generate_report(payload: GenerateReportInput, db_session: Session) -> GenerateReportOutput:
    """Generate a report based on the provided input and database session."""
    # Fetch tickets based on the input parameters
    tickets = fetch_tickets(
        db_session=db_session,
        period_start=payload.period_start,
        period_end=payload.period_end,
        ticket_ids=payload.ticket_ids,
    )
    
    n_tickets = len(tickets)
    
    # Aggregate categories from the fetched tickets
    top_categories = aggregate_categories(tickets)
    
    # Compute the number of days in the report period
    days_count = compute_days(payload.period_start, payload.period_end)
    
    # Build summary and recommendations based on the tickets and top categories
    summary = build_summary(n_tickets)
    recommendations = build_recommendations(n_tickets, top_categories, days_count)
    
    # Render the final report in Markdown format
    report_markdown = render_markdown( 
        period_start=payload.period_start,
        period_end=payload.period_end,
        n_tickets=n_tickets,
        top_categories=top_categories,
        recommendations=recommendations
    )
    
    return GenerateReportOutput(
        template_version=TEMPLATE_VERSION,
        rules_version=RULES_VERSION,
        summary=summary,
        recommendations=recommendations,
        report_markdown=report_markdown,
        top_categories=[CategoryCount(category=c.category, count=c.count) for c in top_categories],
    )
    
TOOL_METADATA = {
    "name": "generate_report",
    "description": (
       "Génère un rapport déterministe des tickets sur une période donnée. "
       "Agrège par catégorie + applique 4 règles heuristiques versionnées. "
       "Read-only : aucun side-effect DB. "
       "Optionnel filtre ticket_ids (AND avec période). "
       "Contraste pédagogique avec evaluate_answer : agrégation pure, zéro LLM, reproductible. "
       "Trail : template_version + rules_version en sortie." 
    ),
   "risk_level": "read",
   "input_schema": GenerateReportInput.model_json_schema(),
   "output_schema": GenerateReportOutput.model_json_schema()
  
}