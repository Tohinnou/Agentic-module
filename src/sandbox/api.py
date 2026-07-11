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
from sandbox.policy_server.exceptions import PolicyBlockError, PolicyHITLRequired

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


@app.exception_handler(PolicyBlockError)
async def policy_block_handler(
    request: Request, exc: PolicyBlockError
) -> JSONResponse:
    """403 Forbidden : verdict BLOCK du Policy Server (Phase 6.4).

    Pas de vibe_diff dans le body — BLOCK est final, aucune review humaine
    n'est envisagée. `layer_triggered` (structural vs semantic) permet à
    l'appelant de savoir si c'est un refus policy dur (allowlist) ou une
    détection sémantique (payload suspect).
    """
    d = exc.decision
    return JSONResponse(
        status_code=403,
        content={
            "verdict": d.verdict,
            "reason": d.reason,
            "layer_triggered": d.layer_triggered,
        },
    )


@app.exception_handler(PolicyHITLRequired)
async def policy_hitl_handler(
    request: Request, exc: PolicyHITLRequired
) -> JSONResponse:
    """428 Precondition Required : verdict HITL du Policy Server (Phase 6.4).

    Le vibe_diff est LA charge utile — c'est ce que l'humain doit lire pour
    approuver ou rejeter. `strict_hitl=True` côté SupportAgent est requis pour
    que cette exception soit levée (sinon HITL est loggé et l'exécution continue).
    """
    d = exc.decision
    return JSONResponse(
        status_code=428,
        content={
            "verdict": d.verdict,
            "reason": d.reason,
            "layer_triggered": d.layer_triggered,
            "vibe_diff": d.vibe_diff,
        },
    )


class AskRequest(BaseModel):
    question: str
    evaluate: bool = False  # True = appelle le judge LLM reel (OpenRouter, cout reel)
    strict_hitl: bool = False  # True = HITL leve 428 au lieu de logger et proceder


@app.post("/support/ask", response_model=SupportResponse)
def ask(payload: AskRequest) -> SupportResponse:
    """Spike end-to-end : premiere route qui fait vraiment tourner SupportAgent.

    Phase 6.4 : Policy Server enforce_policy=True par defaut. Un BLOCK rend 403,
    un HITL rend 428 (si strict_hitl=True dans le body — sinon HITL est loggé
    dans la trajectoire et le pipeline continue).

    `evaluate=False` par defaut : pas d'appel OpenRouter judge sans consentement.
    """
    sink = TRAJECTORY_DIR / "api.jsonl" if TRAJECTORY_ENABLED else None
    agent = SupportAgent(
        trajectory_sink=sink,
        evaluate=payload.evaluate,
        strict_hitl=payload.strict_hitl,
    )
    return agent.run(payload.question)
