"""Drafting templates — logique pure pour Tool 3 draft_reply (chargement, extraction de placeholders, sélection du 
  ton)."""                                                                                                                  
                                                                                                                            
import re             
from pathlib import Path                                                                                                  
from typing import Literal

from sandbox.classification.rules import Category, Priority

Tone = Literal["formal", "empathetic", "urgent", "neutral"]

TEMPLATES_DIR = Path(__file__).parent / "templates"

PLACEHOLDER_PATTERN = re.compile(r"\[\[[A-Z_]+\]\]")

def load_template(category: Category) -> str:
    path = TEMPLATES_DIR / f"{category}.txt"
    return path.read_text(encoding="utf-8")


def extract_placeholders(text: str) -> list[str]:
    """Extrait les placeholders [[VAR_NAME]] uniques, triés alphabétiquement."""
    return sorted(set(PLACEHOLDER_PATTERN.findall(text)))
  

def select_tone(category: Category, priority: Priority) -> Tone:
    """Sélectionne le ton du draft en fonction de la catégorie et de la priorité."""
    if category == "safety":
        return "empathetic"
    if priority == "urgent":
        return "urgent"
    if category in {"cancellation", "payment", "booking"}:
        return "formal"
    return "neutral"