from contextlib import asynccontextmanager

from fastapi import FastAPI

from sandbox import __version__
from sandbox.db import init_db


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
