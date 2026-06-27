import math                                                                                                                                              
import re
from collections import Counter

from sandbox.retrieval.corpus import Doc

K1 = 1.5
B = 0.75


def tokenize(text: str) -> list[str]:
      """Découpe un texte en tokens lowercase (alphanumériques uniquement)."""
      return re.findall(r"\b\w+\b", text.lower())


class BM25Index:
  def __init__(self, docs: list[Doc]) -> None:
    self.docs = docs
    self.n = len(docs)
    self.doc_tokens = [tokenize(d.content) for d in docs]
    self.doc_lengths = [len(t) for t in self.doc_tokens]
    
    if not docs:
      raise ValueError("BM25Index requires at least one document.")
    
    self.avgdl = sum(self.doc_lengths) / self.n
    self.doc_freqs = [Counter(t) for t in self.doc_tokens]
    self.idf = self._compute_idf()

  def _compute_idf(self) -> dict[str, float]:
    df: Counter[str] = Counter()
    for tokens in self.doc_tokens:
        for term in set(tokens):
            df[term] += 1
    return {
        term: math.log(1 + (self.n - freq + 0.5) / (freq + 0.5))
        for term, freq in df.items()
    }

  def _score(self, q_tokens: list[str], doc_idx: int) -> float:
    score = 0.0
    freqs = self.doc_freqs[doc_idx]
    dl = self.doc_lengths[doc_idx]
    for term in q_tokens:
        if term not in self.idf:
            continue
        tf = freqs[term]
        num = tf * (K1 + 1)
        denom = tf + K1 * (1 - B + B * dl / self.avgdl)
        score += self.idf[term] * num / denom
    return score

  def query(self, q: str, top_k: int = 3) -> list[tuple[Doc, float]]:
    q_tokens = tokenize(q)
    scored = [(self.docs[i], self._score(q_tokens, i)) for i in range(self.n)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]