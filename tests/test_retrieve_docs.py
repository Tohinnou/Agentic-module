"""Eval-as-unit-test : régression déterministe pour retrieve_docs."""                                                                                                                         

from sandbox.tools.retrieve_docs import (                                                                                                                
      RetrieveDocsInput,                                                                                                                                 
      RetrieveDocsOutput,
      retrieve_docs,
)


def test_retrieve_docs_returns_expected_shape():
  out = retrieve_docs(RetrieveDocsInput(query="annulation", top_k=3))
  assert isinstance(out, RetrieveDocsOutput)
  assert len(out.results) == 3
  for r in out.results:
    assert r.doc_id
    assert r.score >= 0
    assert len(r.content) <= 200
    
    
def test_retrieve_docs_top_hit_for_cancellation_query():
  out = retrieve_docs(RetrieveDocsInput(query="annulation gratuite 48h", top_k=1))
  assert out.results[0].doc_id == "cancellation_policy"
  
    
def test_retrieve_docs_respects_top_k():
      out = retrieve_docs(RetrieveDocsInput(query="paiement", top_k=2))
      assert len(out.results) == 2