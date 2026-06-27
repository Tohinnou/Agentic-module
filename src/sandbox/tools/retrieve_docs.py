"""Tool : recherche BM25 dans le corpus de policies Marina Rentals (read-only)."""                                                                       
                                                                                                                                                           
from pydantic import BaseModel, Field                                                                                                                    
                                                                                                                                                         
from sandbox.retrieval.bm25 import BM25Index
from sandbox.retrieval.corpus import load_corpus

class RetrieveDocsInput(BaseModel):
    """Input model for retrieving documents based on a query."""
    query: str = Field(
      ..., 
      min_length=1,
      description="The search query string."
    )
    top_k: int = Field(
      3, 
      ge=1,
      le=10,
      description="Number of top documents to retrieve."
    )
    
class RetrieveDoc(BaseModel):
    """Model representing a retrieved document."""
    doc_id: str
    content: str
    score: float
    

class RetrieveDocsOutput(BaseModel):
    """Output model for retrieved documents."""
    results: list[RetrieveDoc]
    

_INDEX: BM25Index | None = None

def _get_index() -> BM25Index:
    """Load the BM25 index from the corpus if not already loaded."""
    global _INDEX
    if _INDEX is None:
        docs = load_corpus()
        _INDEX = BM25Index(docs)
    return _INDEX
  
def retrieve_docs(payload: RetrieveDocsInput) -> RetrieveDocsOutput:
  hits = _get_index().query(payload.query, payload.top_k)
  results = [
      RetrieveDoc(doc_id=doc.doc_id, content=doc.content[:200], score=score)
      for doc, score in hits
  ]
  return RetrieveDocsOutput(results=results)


TOOL_METADATA = {
  "name": "retrieve_docs",
  "description": (
      "Cherche dans les policies Marina Rentals (annulation, paiement, sécurité, "
      "météo, équipements, etc.). À utiliser quand le client pose une question "
      "factuelle dont la réponse est dans la documentation interne."
  ),
  "risk_level": "read",
  "input_schema": RetrieveDocsInput.model_json_schema(),
  "output_schema": RetrieveDocsOutput.model_json_schema(),
}