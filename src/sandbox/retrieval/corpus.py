from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Doc:
  doc_id: str
  content: str
  
CORPUS_DIR = Path("docs")

def load_corpus() -> list[Doc]:
  """Lit tous les .md de docs/ et retourne une liste de Doc triée par doc_id."""
  return [
    Doc(doc_id=path.stem, content=path.read_text(encoding="utf-8"))
    for path in sorted(CORPUS_DIR.glob("*.md"))
  ]