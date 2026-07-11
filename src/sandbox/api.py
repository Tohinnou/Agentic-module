import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from sandbox import __version__
from sandbox.agents.orchestrator import SupportAgent, SupportResponse
from sandbox.db import init_db

load_dotenv()

# Spike (Phase 6 durcira) : premier branchement live du contrat Vibe Trajectory
# (CLAUDE.md regle 7). Lu ici et pas seulement dans judge.py, pour ne plus dependre
# d'un side-effect d'import pour charger .env au niveau de l'app.
TRAJECTORY_DIR = Path(os.getenv("TRAJECTORY_DIR", "./trajectories"))
TRAJECTORY_ENABLED = os.getenv("TRAJECTORY_ENABLED", "true").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    init_db()  # Initialize the database and create tables if they don't exist
    yield  # Control is returned to the application, and it will run until shutdown


app = FastAPI(
    title="Marina Rentals Support Sandbox",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.exception_handler(ValidationError)
async def validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """ClassifyTicketInput/etc. sont construits à la main dans l'orchestrateur
    (pas par FastAPI), donc leur ValidationError échappe au handler intégré de
    FastAPI (celui-là ne couvre que le parsing du body de la requête) et
    remontait en 500 brut avant ce handler.
    """
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


class AskRequest(BaseModel):
    question: str
    evaluate: bool = False  # True = appelle le judge LLM reel (OpenRouter, cout reel)


@app.post("/support/ask", response_model=SupportResponse)
def ask(payload: AskRequest) -> SupportResponse:
    """Spike end-to-end : premiere route qui fait vraiment tourner SupportAgent.

    Volontairement minimal (pas d'auth, pas de gating Policy Server — Phase 6
    ne l'a pas encore construit, cf. PROJECT.MD). `evaluate` par defaut a False
    pour ne jamais declencher un appel OpenRouter reel sans consentement explicite
    de l'appelant.
    """
    sink = TRAJECTORY_DIR / "api.jsonl" if TRAJECTORY_ENABLED else None
    agent = SupportAgent(trajectory_sink=sink, evaluate=payload.evaluate)
    return agent.run(payload.question)
