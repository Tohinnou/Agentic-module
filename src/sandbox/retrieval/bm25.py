import math                                                                                                                                              
import re
from collections import Counter

from sandbox.retrieval.corpus import Doc

K1 = 1.5
B = 0.75


def tokenize(text: str) -> list[str]:
      """Découpe un texte en tokens lowercase (alphanumériques uniquement)."""
      return re.findall(r"\b\w+\b", text.lower())


# --- Stemming FR léger (Phase 8.1) -------------------------------------------
# Problème : BM25 compare des tokens EXACTS → "annuler" (requête) ≠ "annulation"
# (doc), donc le doc qui parle littéralement d'annulation ne gagne aucun point.
# Fix : raciniser verbe et nom vers une racine commune ("annul"), appliqué
# SYMÉTRIQUEMENT côté index ET côté query. Volontairement conservateur (pas de
# dépendance type snowball) : min 3 caractères de racine conservés.
#
# Isolé à BM25 : `tokenize()` reste NON stemmé car `classification/rules.py`
# l'importe pour du keyword-matching sur des mots-clés non racinisés — stemmer
# là casserait le classifier.

# Suffixes dérivationnels/flexionnels, testés du plus long au plus court.
# Le pluriel (s/x) est retiré AVANT (pass 1) pour faire converger orage/orages.
_STEM_SUFFIXES = ("ation", "ement", "ment", "er", "ir", "ée", "ee", "é", "e")


def stem(token: str) -> str:
      """Racinisation FR légère : pluriel puis un suffixe dérivationnel."""
      if len(token) > 3 and token[-1] in "sx":
          token = token[:-1]
      for suffix in _STEM_SUFFIXES:
          if token.endswith(suffix) and len(token) - len(suffix) >= 3:
              return token[: -len(suffix)]
      return token


def _stem_tokens(tokens: list[str]) -> list[str]:
      return [stem(t) for t in tokens]


class BM25Index:
  def __init__(self, docs: list[Doc]) -> None:
    self.docs = docs
    self.n = len(docs)
    self.doc_tokens = [_stem_tokens(tokenize(d.content)) for d in docs]
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
    q_tokens = _stem_tokens(tokenize(q))
    scored = [(self.docs[i], self._score(q_tokens, i)) for i in range(self.n)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]