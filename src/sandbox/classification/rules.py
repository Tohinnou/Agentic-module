"""Classification rules-based pour les tickets Marina Rentals.                                                                                         

  Mock-friendly (zéro LLM) : keyword matching + règles de priorité 2-axes
  (catégorie × modificateurs de sévérité).
"""

from typing import Literal

from sandbox.retrieval.bm25 import tokenize

Category = Literal[
      "cancellation", "payment", "booking", "safety",
      "weather", "equipment", "damage", "other",
]

Priority = Literal["urgent", "high", "normal", "low"]


CATEGORY_KEYWORDS: dict[Category, set[str]] = {
      "cancellation": {
          "annuler", "annulation", "annulé", "annulée", "annule",
          "rembourser", "remboursement", "remboursé",
      },
      "payment": {
          "paiement", "payer", "payé", "facture",
          "carte", "prélèvement", "prélevé",
      },
      "booking": {
          "réservation", "reservation", "réserver", "reserver",
          "réservé", "disponibilité", "disponibilites",
          "calendrier", "date", "dates",
      },
      "safety": {
          "sécurité", "securite", "gilet", "secours", "noyade",
          "noyé", "urgence", "sos", "blessé", "blessure",
      },
      "weather": {
          "météo", "meteo", "vent", "vague", "vagues",
          "orage", "tempête", "tempete", "alerte", "houle", "pluie",
      },
      "equipment": {
          "équipement", "equipement", "moteur", "panne", "défaut",
          "cassé", "casse", "voile", "ancre",
          "bateau", "kayak", "paddle",
      },
      "damage": {
          "dommage", "dommages", "endommagé", "abîmé",
          "accident", "collision", "choc", "rayure",
          "fissure", "coulé", "couler",
      },
}

URGENCY_KEYWORDS: set[str] = {
      "accident", "blessé", "blessure", "danger",
      "urgent", "urgence", "alerte", "tempête", "tempete",
      "coulé", "couler", "sos", "secours", "noyade",
}

TIME_PRESSURE_KEYWORDS: set[str] = {
      "aujourd", "aujourdhui",
      "maintenant", "demain",
      "24h", "immédiatement", "immediatement",
}

def compute_priority(
  category: Category,
  matched_keywords: list[str],
  text_tokens: set[str],
) -> Priority:
  if category == "safety":
    return "urgent"
  if category == "damage":
    return "urgent" if text_tokens & URGENCY_KEYWORDS else "high"
  if category == "weather":
    return "urgent" if text_tokens & URGENCY_KEYWORDS else "normal"
  if category == "cancellation":
    return "high" if text_tokens & TIME_PRESSURE_KEYWORDS else "normal"
  if category == "other" and len(matched_keywords) == 0:
    return "low"
  return "normal"


def classify_text(text: str) -> tuple[Category, Priority, float, list[str]]:
  """Classifie un texte en catégorie et priorité, avec mots-clés associés."""
  tokens = tokenize(text)
  token_set = set(tokens)
  
  scores: dict[Category, int] = {}
  matches_per_cat: dict[Category, list[str]] = {}
  for cat, kws in CATEGORY_KEYWORDS.items():
    hits = sorted(token_set & kws)
    scores[cat] = len(hits)
    matches_per_cat[cat] = hits
    
  top_cat: Category = max(scores, key=lambda c: scores[c])
  if scores[top_cat] == 0:
    top_cat = "other"
    matched: list[str] = []
    confidence = 0.0
  else: 
    matched = matches_per_cat[top_cat]

    total = sum(scores.values())
    confidence = scores[top_cat] / (total + 1)

  priority = compute_priority(top_cat, matched, token_set)
  return top_cat, priority, confidence, matched
  