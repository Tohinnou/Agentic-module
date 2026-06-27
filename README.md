# Agentic Support & Operations Sandbox

Mini-laboratoire d'apprentissage du cours *Kaggle x Google 5-Day AI Agents: Intensive Vibe Coding Course With Google*.
Plateforme de support client agentique pour l'entreprise fictive **Marina Rentals** (location nautique).

> **Statut :** sandbox pédagogique, pas de production. Voir `CLAUDE.md` pour les regles d'ingenierie et le vocabulaire.

## Quick Start

```bash
# 1. Environnement virtuel
python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell : .venv\Scripts\Activate.ps1)

# 2. Installation
pip install -e ".[dev,ui,llm]"

# 3. Tests
pytest

# 4. Variables d'env
cp .env.example .env            # puis remplir si besoin (mock LLM par defaut)

# 5. Lancer l'API
uvicorn sandbox.api:app --reload

# 6. (Optionnel) UI Streamlit
streamlit run src/sandbox/ui.py
```

## Ou regarder

| Tu cherches... | Va voir |
|---|---|
| La DNA du projet (regles, vocabulaire) | `CLAUDE.md` |
| La roadmap (10 phases) | `PROJECT.MD` |
| La theorie du cours | `day{1..5}.txt` |
| Le corpus RAG | `docs/` (10 policies Marina Rentals) |
| La doc projet (architecture, policies) | `meta/` |
| Les skills | `.agent/skills/` |
| Les specs SDD | `specs/` |
| Les evals (5 patterns) | `evals/` |
| Les traces post-hoc | `trajectories/` |

## Stack

Python 3.11+ - FastAPI - SQLite - pytest - ruff - Streamlit - Mock LLM (TF-IDF/BM25 par defaut)

**Non utilise volontairement :** LangChain, LlamaIndex (cf. CLAUDE.md §2).
Le cours enseigne les primitives, on les code a la main pour comprendre.

## Licence

MIT - projet pedagogique personnel.
